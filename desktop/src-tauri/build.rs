//! Build-time validation for sidecar binaries.
//!
//! Before Tauri compiles the application bundle, this build script checks
//! that all required sidecar binaries exist in `src-tauri/binaries/` with
//! the correct target-triple naming convention.  If a required binary is
//! missing, the build fails early with an actionable error message pointing
//! the developer at the `prepare-sidecars.mjs` script.

use std::env;
use std::path::PathBuf;

/// Sidecar binaries that MUST be present for a production bundle.
///
/// Each entry is `(logical_name, required)`.
const SIDECARS: &[(&str, bool)] = &[
    ("podcast-backend", true),
    ("ffmpeg", true),
    ("ffprobe", false),
];

fn main() {
    // Always run the standard Tauri build codegen.
    tauri_build::build();

    // --- Sidecar binary validation ---

    // Always register this so Cargo re-runs when the env var is added/removed.
    println!("cargo:rerun-if-env-changed=SKIP_SIDECAR_CHECK");

    // Skip validation when SKIP_SIDECAR_CHECK is set (CI, dev iteration).
    if env::var("SKIP_SIDECAR_CHECK").is_ok() {
        println!("cargo:warning=SKIP_SIDECAR_CHECK set - skipping sidecar binary validation");
        return;
    }

    let target = env::var("TARGET").unwrap_or_else(|_| {
        // Fallback: construct from individual vars Cargo always sets.
        let arch = env::var("CARGO_CFG_TARGET_ARCH").unwrap_or_default();
        let os = env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
        let env_name = env::var("CARGO_CFG_TARGET_ENV").unwrap_or_default();
        let vendor = match os.as_str() {
            "linux" => "unknown",
            "macos" => "apple",
            "windows" => "pc",
            _ => "unknown",
        };
        let os_label = match os.as_str() {
            "macos" => "darwin".to_string(),
            "windows" => format!("windows-{env_name}"),
            _ => format!("{os}-{env_name}"),
        };
        format!("{arch}-{vendor}-{os_label}")
    });

    let ext = if env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        ".exe"
    } else {
        ""
    };

    // binaries/ lives next to build.rs (inside src-tauri/)
    let binaries_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap()).join("binaries");

    let mut missing_required: Vec<String> = Vec::new();

    for &(name, required) in SIDECARS {
        let expected = binaries_dir.join(format!("{name}-{target}{ext}"));

        if expected.exists() {
            println!(
                "cargo:warning=sidecar OK: {}",
                expected.file_name().unwrap().to_string_lossy()
            );
        } else if required {
            missing_required.push(format!(
                "  - {name}: expected at {}\n    Run: node desktop/scripts/prepare-sidecars.mjs",
                expected.display()
            ));
        } else {
            println!("cargo:warning=sidecar SKIP (optional): {name}-{target}{ext}");
        }
    }

    if !missing_required.is_empty() {
        let msg = format!(
            "\n\nRequired sidecar binaries are missing for target '{target}':\n\n{}\n\n\
             To fix:\n\
             1. Build the podcast-backend: uv run pyinstaller ...\n\
             2. Ensure ffmpeg is installed and on PATH\n\
             3. Run: node desktop/scripts/prepare-sidecars.mjs\n\
             \n\
             Or set SKIP_SIDECAR_CHECK=1 to skip this check during development.\n",
            missing_required.join("\n")
        );
        panic!("{msg}");
    }

    // Re-run this check when binaries dir or individual sidecar files change.
    println!("cargo:rerun-if-changed={}", binaries_dir.display());
    for &(name, _) in SIDECARS {
        println!(
            "cargo:rerun-if-changed={}",
            binaries_dir.join(format!("{name}-{target}{ext}")).display()
        );
    }
}
