# smoke-test-desktop.ps1
#
# Validates a built desktop installer artifact on Windows.
# Ensures the packaged app contains the backend sidecar, attempts
# to launch it, and verifies backend health within a reasonable timeout.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File desktop/scripts/smoke-test-desktop.ps1 [ARTIFACTS_DIR]
#
# Arguments:
#   ARTIFACTS_DIR  Directory containing installer artifacts (.msi, .exe)
#                  Defaults to "installer-artifacts/" in the current directory.
#
# Exit codes:
#   0  All smoke checks passed
#   1  One or more checks failed

param(
    [string]$ArtifactsDir = "installer-artifacts"
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

$BackendPort = 8787
$HealthUrl = "http://127.0.0.1:${BackendPort}/health"
$StartupTimeoutSecs = 20
$ProbeIntervalSecs = 1
$MinSizeBytes = 5000000  # 5 MB minimum

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

$Failures = 0
$BackendProcess = $null
$ExtractDir = $null

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Info  { param([string]$Msg) Write-Host "[INFO]  $Msg" }
function Write-Ok    { param([string]$Msg) Write-Host "[OK]    $Msg" -ForegroundColor Green }
function Write-Fail  { param([string]$Msg) Write-Host "[FAIL]  $Msg" -ForegroundColor Red; $script:Failures++ }
function Write-Warn  { param([string]$Msg) Write-Host "[WARN]  $Msg" -ForegroundColor Yellow }

function Invoke-Cleanup {
    if ($null -ne $script:BackendProcess -and -not $script:BackendProcess.HasExited) {
        Write-Info "Stopping backend (PID $($script:BackendProcess.Id))..."
        Stop-Process -Id $script:BackendProcess.Id -Force -ErrorAction SilentlyContinue
        $script:BackendProcess = $null
    }
    if ($null -ne $script:ExtractDir -and (Test-Path $script:ExtractDir)) {
        Remove-Item -Path $script:ExtractDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Info "Cleaned extraction directory"
    }
}

# Ensure cleanup on exit
trap { Invoke-Cleanup } EXIT

# ---------------------------------------------------------------------------
# Check 1: Artifact existence
# ---------------------------------------------------------------------------

Write-Info "=== Smoke Test: Desktop Installer Validation (Windows) ==="
Write-Info "Artifacts directory: $ArtifactsDir"
Write-Host ""

if (-not (Test-Path $ArtifactsDir)) {
    Write-Fail "Artifacts directory does not exist: $ArtifactsDir"
    exit 1
}

$InstallerFiles = @(
    Get-ChildItem -Path $ArtifactsDir -Recurse -File |
    Where-Object { $_.Extension -in @(".msi", ".exe", ".nsis") }
)

if ($InstallerFiles.Count -eq 0) {
    Write-Fail "No installer artifacts found in $ArtifactsDir"
    Write-Info "Directory contents:"
    Get-ChildItem -Path $ArtifactsDir -Recurse -File | ForEach-Object { Write-Info "  $($_.FullName)" }
    exit 1
}

Write-Ok "Found $($InstallerFiles.Count) installer artifact(s)"
foreach ($f in $InstallerFiles) {
    $SizeMB = [math]::Round($f.Length / 1MB, 1)
    Write-Info "  -> $($f.Name) (${SizeMB} MB)"
}
Write-Host ""

# ---------------------------------------------------------------------------
# Check 2: Installer size sanity
# ---------------------------------------------------------------------------

foreach ($f in $InstallerFiles) {
    if ($f.Length -lt $MinSizeBytes) {
        $SizeMB = [math]::Round($f.Length / 1MB, 1)
        Write-Fail "Installer too small (${SizeMB} MB): $($f.Name)"
    } else {
        $SizeMB = [math]::Round($f.Length / 1MB, 1)
        Write-Ok "Installer size OK (${SizeMB} MB): $($f.Name)"
    }
}
Write-Host ""

# ---------------------------------------------------------------------------
# Check 3: MSI content inspection (sidecar presence)
# ---------------------------------------------------------------------------

$SidecarFound = $false
$PrimaryInstaller = $InstallerFiles[0]

Write-Info "Inspecting artifact: $($PrimaryInstaller.Name)"

if ($PrimaryInstaller.Extension -eq ".msi") {
    Write-Info "Inspecting MSI contents..."
    try {
        # Use msiexec /a for administrative install (extract without running)
        $script:ExtractDir = Join-Path $env:TEMP "smoke-test-extract-$(Get-Random)"
        New-Item -Path $script:ExtractDir -ItemType Directory -Force | Out-Null

        $msiArgs = "/a `"$($PrimaryInstaller.FullName)`" /qn TARGETDIR=`"$script:ExtractDir`""
        $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru -NoNewWindow
        if ($proc.ExitCode -eq 0) {
            $backendFiles = Get-ChildItem -Path $script:ExtractDir -Recurse -File -Filter "podcast-backend*" -ErrorAction SilentlyContinue
            if ($backendFiles.Count -gt 0) {
                $SidecarFound = $true
            }
        } else {
            Write-Warn "MSI extraction returned exit code $($proc.ExitCode)"
        }
    } catch {
        Write-Warn "MSI inspection failed: $_"
    }
} elseif ($PrimaryInstaller.Extension -eq ".exe") {
    Write-Info "NSIS/EXE installer detected — checking file size as proxy"
    # NSIS installers cannot be easily extracted non-interactively.
    # Use size heuristic: a valid installer with sidecar should be >20MB
    if ($PrimaryInstaller.Length -gt 20000000) {
        $SidecarFound = $true
        Write-Info "  Size indicates bundled content present"
    }
}

if ($SidecarFound) {
    Write-Ok "Sidecar binary (podcast-backend) found/expected in installer"
} else {
    Write-Fail "Sidecar binary (podcast-backend) NOT detected in installer"
}
Write-Host ""

# ---------------------------------------------------------------------------
# Check 4: Backend sidecar health (if binary available)
# ---------------------------------------------------------------------------

$BackendBin = $null

# Check extracted contents
if ($null -ne $script:ExtractDir -and (Test-Path $script:ExtractDir)) {
    $candidates = Get-ChildItem -Path $script:ExtractDir -Recurse -File -Filter "podcast-backend*.exe" -ErrorAction SilentlyContinue
    if ($candidates.Count -gt 0) {
        $BackendBin = $candidates[0].FullName
    }
}

# Fallback: check sidecar binaries directory
if ($null -eq $BackendBin) {
    $fallback = Get-ChildItem -Path "desktop/src-tauri/binaries" -Filter "podcast-backend*.exe" -ErrorAction SilentlyContinue
    if ($fallback.Count -gt 0) {
        $BackendBin = $fallback[0].FullName
    }
}

if ($null -ne $BackendBin) {
    Write-Info "Testing backend health with: $BackendBin"

    try {
        $script:BackendProcess = Start-Process -FilePath $BackendBin `
            -ArgumentList "--port", "$BackendPort" `
            -PassThru -NoNewWindow -RedirectStandardOutput "NUL" -RedirectStandardError "NUL"

        Write-Info "Started backend (PID $($script:BackendProcess.Id))"

        $Healthy = $false
        $Elapsed = 0

        while ($Elapsed -lt $StartupTimeoutSecs) {
            try {
                $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2 -ErrorAction Stop
                if ($null -ne $response.status) {
                    $Healthy = $true
                    break
                }
            } catch {
                # Backend not ready yet
            }
            Start-Sleep -Seconds $ProbeIntervalSecs
            $Elapsed += $ProbeIntervalSecs
        }

        if ($Healthy) {
            Write-Ok "Backend health endpoint responded with valid status"
            Write-Info "  Status: $($response.status)"
        } else {
            Write-Fail "Backend did not become healthy within ${StartupTimeoutSecs}s"
        }

        # Stop backend
        if (-not $script:BackendProcess.HasExited) {
            Stop-Process -Id $script:BackendProcess.Id -Force -ErrorAction SilentlyContinue
        }
        $script:BackendProcess = $null
    } catch {
        Write-Fail "Backend startup failed: $_"
    }
} else {
    Write-Warn "No executable backend binary found for health test - skipping"
    Write-Warn "This is expected in CI when testing installers cross-platform"
}
Write-Host ""

# ---------------------------------------------------------------------------
# Check 5: FFmpeg sidecar presence
# ---------------------------------------------------------------------------

$FfmpegFound = $false

if ($null -ne $script:ExtractDir -and (Test-Path $script:ExtractDir)) {
    $ffmpegFiles = Get-ChildItem -Path $script:ExtractDir -Recurse -File -Filter "ffmpeg*" -ErrorAction SilentlyContinue
    if ($ffmpegFiles.Count -gt 0) {
        $FfmpegFound = $true
    }
}

if ($FfmpegFound) {
    Write-Ok "FFmpeg binary found in installer"
} else {
    Write-Warn "FFmpeg binary not detected (may be bundled differently or PATH-resolved)"
}
Write-Host ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

Write-Host "==========================================="
if ($Failures -eq 0) {
    Write-Ok "All smoke checks passed"
    Invoke-Cleanup
    exit 0
} else {
    Write-Fail "$Failures smoke check(s) failed"
    Invoke-Cleanup
    exit 1
}
