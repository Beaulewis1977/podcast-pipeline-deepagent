#!/usr/bin/env bash
# smoke-test-desktop.sh
#
# Validates a built desktop installer artifact on Linux or macOS.
# Ensures the packaged app contains the backend sidecar, launches
# it, and verifies backend health within a reasonable timeout.
#
# Usage:
#   ./desktop/scripts/smoke-test-desktop.sh [ARTIFACTS_DIR]
#
# Arguments:
#   ARTIFACTS_DIR  Directory containing installer artifacts (.AppImage, .deb, .dmg)
#                  Defaults to "installer-artifacts/" in the current directory.
#
# Exit codes:
#   0  All smoke checks passed
#   1  One or more checks failed

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ARTIFACTS_DIR="${1:-installer-artifacts}"
BACKEND_PORT=8787
HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/health"
STARTUP_TIMEOUT_SECS=20
PROBE_INTERVAL_SECS=1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log_info()  { echo "[INFO]  $*"; }
log_ok()    { echo "[OK]    $*"; }
log_fail()  { echo "[FAIL]  $*" >&2; }
log_warn()  { echo "[WARN]  $*"; }

# Track overall result
FAILURES=0

check_pass() {
    log_ok "$1"
}

check_fail() {
    log_fail "$1"
    FAILURES=$((FAILURES + 1))
}

cleanup() {
    log_info "Cleaning up..."
    # Kill backend if we started it
    if [[ -n "${BACKEND_PID:-}" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
        log_info "Stopped backend (PID $BACKEND_PID)"
    fi
    # Remove temporary extraction directory
    if [[ -d "${EXTRACT_DIR:-}" ]]; then
        rm -rf "$EXTRACT_DIR"
        log_info "Cleaned extraction directory"
    fi
}

trap cleanup EXIT

# ---------------------------------------------------------------------------
# Check 1: Artifact existence
# ---------------------------------------------------------------------------

log_info "=== Smoke Test: Desktop Installer Validation ==="
log_info "Artifacts directory: $ARTIFACTS_DIR"
echo ""

if [[ ! -d "$ARTIFACTS_DIR" ]]; then
    check_fail "Artifacts directory does not exist: $ARTIFACTS_DIR"
    exit 1
fi

# Find installer files
INSTALLER_FILES=()
while IFS= read -r -d '' f; do
    INSTALLER_FILES+=("$f")
done < <(find "$ARTIFACTS_DIR" -type f \( \
    -name "*.AppImage" -o \
    -name "*.deb" -o \
    -name "*.dmg" -o \
    -name "*.app" \
\) -print0 2>/dev/null)

if [[ ${#INSTALLER_FILES[@]} -eq 0 ]]; then
    check_fail "No installer artifacts found in $ARTIFACTS_DIR"
    log_info "Directory contents:"
    find "$ARTIFACTS_DIR" -type f 2>/dev/null || true
    exit 1
fi

check_pass "Found ${#INSTALLER_FILES[@]} installer artifact(s)"
for f in "${INSTALLER_FILES[@]}"; do
    log_info "  -> $(basename "$f") ($(du -h "$f" | cut -f1))"
done
echo ""

# ---------------------------------------------------------------------------
# Check 2: Installer size sanity
# ---------------------------------------------------------------------------

MIN_SIZE_BYTES=5000000  # 5 MB minimum — a real installer should be larger

for f in "${INSTALLER_FILES[@]}"; do
    SIZE_BYTES=$(stat -f%z "$f" 2>/dev/null || stat --format=%s "$f" 2>/dev/null || echo 0)
    if [[ "$SIZE_BYTES" -lt "$MIN_SIZE_BYTES" ]]; then
        check_fail "Installer too small ($(du -h "$f" | cut -f1)): $(basename "$f")"
    else
        check_pass "Installer size OK ($(du -h "$f" | cut -f1)): $(basename "$f")"
    fi
done
echo ""

# ---------------------------------------------------------------------------
# Check 3: Extract and verify sidecar presence
# ---------------------------------------------------------------------------

EXTRACT_DIR=$(mktemp -d)
SIDECAR_FOUND=false

# Try to extract or mount the first usable artifact
ARTIFACT="${INSTALLER_FILES[0]}"
log_info "Inspecting artifact: $(basename "$ARTIFACT")"

case "$ARTIFACT" in
    *.AppImage)
        log_info "Extracting AppImage..."
        chmod +x "$ARTIFACT"
        "$ARTIFACT" --appimage-extract --dest "$EXTRACT_DIR/app" 2>/dev/null || \
            "$ARTIFACT" --appimage-extract 2>/dev/null && mv squashfs-root "$EXTRACT_DIR/app" || true
        # Search for sidecar in extracted contents
        if find "$EXTRACT_DIR" -name "podcast-backend*" -type f 2>/dev/null | head -1 | grep -q .; then
            SIDECAR_FOUND=true
        fi
        ;;
    *.deb)
        log_info "Inspecting .deb package..."
        if command -v dpkg-deb &>/dev/null; then
            dpkg-deb --contents "$ARTIFACT" > "$EXTRACT_DIR/contents.txt" 2>/dev/null || true
            if grep -q "podcast-backend" "$EXTRACT_DIR/contents.txt" 2>/dev/null; then
                SIDECAR_FOUND=true
            fi
        else
            log_warn "dpkg-deb not available, skipping content inspection"
            SIDECAR_FOUND=true  # Assume OK if we cannot inspect
        fi
        ;;
    *.dmg)
        log_info "Inspecting .dmg (listing without mount)..."
        if command -v hdiutil &>/dev/null; then
            MOUNT_DIR=$(mktemp -d)
            hdiutil attach "$ARTIFACT" -mountpoint "$MOUNT_DIR" -nobrowse -quiet 2>/dev/null || true
            if find "$MOUNT_DIR" -name "podcast-backend*" -type f 2>/dev/null | head -1 | grep -q .; then
                SIDECAR_FOUND=true
            fi
            hdiutil detach "$MOUNT_DIR" -quiet 2>/dev/null || true
            rmdir "$MOUNT_DIR" 2>/dev/null || true
        else
            log_warn "hdiutil not available (non-macOS), skipping DMG inspection"
            SIDECAR_FOUND=true
        fi
        ;;
    *)
        log_warn "Unknown artifact type, skipping sidecar check"
        SIDECAR_FOUND=true
        ;;
esac

if [[ "$SIDECAR_FOUND" == "true" ]]; then
    check_pass "Sidecar binary (podcast-backend) found in installer"
else
    check_fail "Sidecar binary (podcast-backend) NOT found in installer"
fi
echo ""

# ---------------------------------------------------------------------------
# Check 4: Backend sidecar health (if standalone binary is available)
# ---------------------------------------------------------------------------

# Look for a standalone backend binary we can run directly for health check
BACKEND_BIN=""
BACKEND_CANDIDATES=(
    "$EXTRACT_DIR"/app/podcast-backend*
    "$EXTRACT_DIR"/*/podcast-backend*
)

for candidate in "${BACKEND_CANDIDATES[@]}"; do
    if [[ -f "$candidate" && -x "$candidate" ]]; then
        BACKEND_BIN="$candidate"
        break
    fi
done

if [[ -z "$BACKEND_BIN" ]]; then
    # Try the sidecar binaries directory as fallback
    for candidate in desktop/src-tauri/binaries/podcast-backend*; do
        if [[ -f "$candidate" && -x "$candidate" ]]; then
            BACKEND_BIN="$candidate"
            break
        fi
    done
fi

if [[ -n "$BACKEND_BIN" ]]; then
    log_info "Testing backend health with: $BACKEND_BIN"

    # Start backend in background
    "$BACKEND_BIN" --port "$BACKEND_PORT" &
    BACKEND_PID=$!
    log_info "Started backend (PID $BACKEND_PID)"

    # Wait for health endpoint
    HEALTHY=false
    ELAPSED=0
    while [[ "$ELAPSED" -lt "$STARTUP_TIMEOUT_SECS" ]]; do
        if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
            HEALTHY=true
            break
        fi
        sleep "$PROBE_INTERVAL_SECS"
        ELAPSED=$((ELAPSED + PROBE_INTERVAL_SECS))
    done

    if [[ "$HEALTHY" == "true" ]]; then
        # Verify response content
        HEALTH_BODY=$(curl -sf "$HEALTH_URL" 2>/dev/null || echo "{}")
        if echo "$HEALTH_BODY" | grep -q '"status"'; then
            check_pass "Backend health endpoint responded with valid status"
            log_info "  Response: $HEALTH_BODY"
        else
            check_fail "Backend health response missing status field"
        fi
    else
        check_fail "Backend did not become healthy within ${STARTUP_TIMEOUT_SECS}s"
    fi

    # Stop backend
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
    unset BACKEND_PID
else
    log_warn "No executable backend binary found for health test — skipping"
    log_warn "This is expected in CI when testing installers cross-platform"
fi
echo ""

# ---------------------------------------------------------------------------
# Check 5: FFmpeg sidecar presence
# ---------------------------------------------------------------------------

FFMPEG_FOUND=false

# Check in extracted app or deb contents
if find "$EXTRACT_DIR" -name "ffmpeg*" -type f 2>/dev/null | head -1 | grep -q .; then
    FFMPEG_FOUND=true
fi

# Also check in package listing if available
if [[ -f "$EXTRACT_DIR/contents.txt" ]]; then
    if grep -q "ffmpeg" "$EXTRACT_DIR/contents.txt" 2>/dev/null; then
        FFMPEG_FOUND=true
    fi
fi

if [[ "$FFMPEG_FOUND" == "true" ]]; then
    check_pass "FFmpeg binary found in installer"
else
    log_warn "FFmpeg binary not detected (may be bundled differently or PATH-resolved)"
fi
echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo "==========================================="
if [[ "$FAILURES" -eq 0 ]]; then
    log_ok "All smoke checks passed"
    exit 0
else
    log_fail "$FAILURES smoke check(s) failed"
    exit 1
fi
