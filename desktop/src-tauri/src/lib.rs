mod recovery;

use serde::Serialize;
use std::sync::Mutex;
use tauri::State;
use tauri_plugin_shell::ShellExt;

/// Sidecar process state shared across commands.
#[derive(Default)]
pub struct SidecarState {
    /// PID of the running backend sidecar process (None if not running).
    pid: Mutex<Option<u32>>,
}

/// Status of the backend sidecar process.
#[derive(Serialize, Clone)]
pub struct SidecarStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub port: u16,
}

/// Default backend service port matching the Python service default.
const BACKEND_PORT: u16 = 8787;

/// Start the backend sidecar process.
///
/// Launches the `binaries/podcast-backend` sidecar with `--port` argument.
/// Returns the sidecar status after launch attempt.
#[tauri::command]
async fn start_sidecar(
    app: tauri::AppHandle,
    state: State<'_, SidecarState>,
) -> Result<SidecarStatus, String> {
    // Check if already running (verify the process is still alive)
    {
        let mut pid_guard = state.pid.lock().map_err(|e| e.to_string())?;
        if let Some(pid) = *pid_guard {
            #[cfg(unix)]
            let alive = unsafe { libc::kill(pid as i32, 0) == 0 };
            #[cfg(not(unix))]
            let alive = true; // Rely on health endpoint for Windows liveness
            if alive {
                return Ok(SidecarStatus {
                    running: true,
                    pid: Some(pid),
                    port: BACKEND_PORT,
                });
            }
            // Process died unexpectedly; clear stale PID and fall through to restart
            *pid_guard = None;
        }
    }

    let shell = app.shell();
    let sidecar_cmd = shell
        .sidecar("binaries/podcast-backend")
        .map_err(|e| format!("Failed to create sidecar command: {e}"))?
        .args(["--port", &BACKEND_PORT.to_string()]);

    let (mut _rx, child) = sidecar_cmd
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {e}"))?;

    let child_pid = child.pid();

    {
        let mut pid_guard = state.pid.lock().map_err(|e| e.to_string())?;
        *pid_guard = Some(child_pid);
    }

    Ok(SidecarStatus {
        running: true,
        pid: Some(child_pid),
        port: BACKEND_PORT,
    })
}

/// Stop the backend sidecar process.
///
/// Kills the sidecar if it is currently running and clears tracked state.
#[tauri::command]
async fn stop_sidecar(
    state: State<'_, SidecarState>,
) -> Result<SidecarStatus, String> {
    let mut pid_guard = state.pid.lock().map_err(|e| e.to_string())?;

    if let Some(pid) = *pid_guard {
        // Use SIGTERM via kill on Unix; on Windows this sends TerminateProcess
        #[cfg(unix)]
        {
            // SAFETY: pid is a valid process ID obtained from child.pid() during
            // spawn, and SIGTERM is a standard signal that is always safe to send.
            let ret = unsafe { libc::kill(pid as i32, libc::SIGTERM) };
            if ret != 0 {
                eprintln!(
                    "Failed to terminate sidecar PID {pid}: {}",
                    std::io::Error::last_os_error()
                );
            }
        }
        #[cfg(not(unix))]
        {
            if let Err(e) = std::process::Command::new("taskkill")
                .args(["/PID", &pid.to_string(), "/F"])
                .status()
            {
                eprintln!("Failed to terminate sidecar PID {pid}: {e}");
            }
        }

        *pid_guard = None;
    }

    Ok(SidecarStatus {
        running: false,
        pid: None,
        port: BACKEND_PORT,
    })
}

/// Get current sidecar status without changing state.
///
/// Reports stored PID state. Use the backend health endpoint for
/// authoritative liveness verification.
#[tauri::command]
async fn sidecar_status(
    state: State<'_, SidecarState>,
) -> Result<SidecarStatus, String> {
    let pid_guard = state.pid.lock().map_err(|e| e.to_string())?;

    Ok(SidecarStatus {
        running: pid_guard.is_some(),
        pid: *pid_guard,
        port: BACKEND_PORT,
    })
}

/// Build and run the Tauri application.
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState::default())
        .invoke_handler(tauri::generate_handler![
            start_sidecar,
            stop_sidecar,
            sidecar_status,
            recovery::check_recovery,
            recovery::trigger_resume,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
