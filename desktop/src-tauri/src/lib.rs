mod recovery;

use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use tauri::State;
use tauri_plugin_shell::ShellExt;

/// Whether Tauri spawned the sidecar itself (and therefore owns its lifetime).
///
/// When `true` the `stop_sidecar` command is allowed to kill the backend
/// process.  When `false` the backend was already running before Tauri
/// started (e.g. launched by Streamlit or a developer terminal), so Tauri
/// must not terminate it on shutdown.
///
/// Set to `true` after a successful sidecar spawn; set to `false` when the
/// pre-spawn health check finds an already-running backend, or after the
/// sidecar is terminated.
static TAURI_OWNS_SIDECAR: AtomicBool = AtomicBool::new(false);

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

/// Check whether the backend HTTP service is already up and healthy.
///
/// Performs a single GET request to the `/health` endpoint with a 2-second
/// timeout.  Returns `true` only when the response is HTTP 2xx **and** the
/// body contains the string `"ok"`, matching the
/// `HealthResponse { status: "ok" }` payload returned by the FastAPI backend.
///
/// All errors (connection refused, timeout, non-2xx status, body mismatch)
/// are treated as "not healthy" and return `false` — this is a best-effort
/// check, not a hard failure path.
async fn backend_is_healthy() -> bool {
    let client = match reqwest::ClientBuilder::new()
        .timeout(std::time::Duration::from_secs(2))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };

    let url = format!("http://127.0.0.1:{BACKEND_PORT}/health");
    match client.get(&url).send().await {
        Ok(response) if response.status().is_success() => match response.text().await {
            Ok(body) => body.contains("\"ok\""),
            Err(_) => false,
        },
        _ => false,
    }
}

/// Start the backend sidecar process.
///
/// Launches the `binaries/podcast-backend` sidecar with `--port` argument.
/// Returns the sidecar status after launch attempt.
///
/// Before attempting to spawn, performs a pre-flight health check against
/// the backend's `/health` endpoint.  If the backend is already healthy
/// (e.g. started by a developer terminal or Streamlit), Tauri will attach
/// to it without spawning a second process and without taking ownership of
/// its lifetime (`TAURI_OWNS_SIDECAR` remains `false`).
#[tauri::command]
async fn start_sidecar(
    app: tauri::AppHandle,
    state: State<'_, SidecarState>,
) -> Result<SidecarStatus, String> {
    // Pre-spawn coexistence check: if the backend is already responding to
    // health requests, attach to it without spawning a duplicate process.
    // We must NOT own the sidecar in this case — the backend was started
    // externally and must outlive Tauri's own lifecycle.
    if backend_is_healthy().await {
        TAURI_OWNS_SIDECAR.store(false, Ordering::SeqCst);
        return Ok(SidecarStatus {
            running: true,
            pid: None,
            port: BACKEND_PORT,
        });
    }

    // Hold the lock through check → spawn → assign to prevent double-spawn races.
    let mut pid_guard = state.pid.lock().map_err(|e| e.to_string())?;

    // Check if already running (verify the process is still alive)
    if let Some(pid) = *pid_guard {
        #[cfg(unix)]
        let alive = unsafe { libc::kill(pid as i32, 0) == 0 };
        #[cfg(not(unix))]
        let alive = std::process::Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV"])
            .output()
            .ok()
            .map(|out| {
                let stdout = String::from_utf8_lossy(&out.stdout);
                stdout.contains(&format!("\"{pid}\""))
            })
            .unwrap_or(false);
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

    let shell = app.shell();
    let sidecar_cmd = shell
        .sidecar("binaries/podcast-backend")
        .map_err(|e| format!("Failed to create sidecar command: {e}"))?
        .args(["--port", &BACKEND_PORT.to_string()]);

    let (mut _rx, child) = sidecar_cmd
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {e}"))?;

    let child_pid = child.pid();
    *pid_guard = Some(child_pid);

    // We spawned this process; we own its lifetime and are responsible for
    // terminating it on shutdown.
    TAURI_OWNS_SIDECAR.store(true, Ordering::SeqCst);

    Ok(SidecarStatus {
        running: true,
        pid: Some(child_pid),
        port: BACKEND_PORT,
    })
}

/// Stop the backend sidecar process.
///
/// Kills the sidecar only if Tauri owns it (`TAURI_OWNS_SIDECAR == true`).
/// When the backend was started externally (e.g. by Streamlit or a developer
/// terminal), Tauri attached to it without spawning — it must not terminate
/// a process it did not create.  In that case this command returns a
/// "not running" status immediately without sending any signal.
#[tauri::command]
async fn stop_sidecar(state: State<'_, SidecarState>) -> Result<SidecarStatus, String> {
    // Ownership gate: only the process that spawned the sidecar may kill it.
    if !TAURI_OWNS_SIDECAR.load(Ordering::SeqCst) {
        return Ok(SidecarStatus {
            running: false,
            pid: None,
            port: BACKEND_PORT,
        });
    }

    let mut pid_guard = state.pid.lock().map_err(|e| e.to_string())?;

    if let Some(pid) = *pid_guard {
        // Use SIGTERM via kill on Unix; on Windows this sends TerminateProcess.
        // Only clear the tracked PID when termination succeeds or the
        // process is already gone (ESRCH / not found).
        #[cfg(unix)]
        {
            // SAFETY: pid is a valid process ID obtained from child.pid() during
            // spawn, and SIGTERM is a standard signal that is always safe to send.
            let ret = unsafe { libc::kill(pid as i32, libc::SIGTERM) };
            if ret != 0 {
                let err = std::io::Error::last_os_error();
                // ESRCH = no such process — already exited, treat as success
                if err.raw_os_error() != Some(libc::ESRCH) {
                    return Err(format!("Failed to terminate sidecar PID {pid}: {err}"));
                }
            }
        }
        #[cfg(not(unix))]
        {
            match std::process::Command::new("taskkill")
                .args(["/PID", &pid.to_string(), "/F"])
                .status()
            {
                Ok(status) if status.success() => {}
                Ok(status) => {
                    // taskkill failed — check if process is already gone
                    let still_alive = std::process::Command::new("tasklist")
                        .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV"])
                        .output()
                        .ok()
                        .map(|out| {
                            let stdout = String::from_utf8_lossy(&out.stdout);
                            stdout.contains(&format!("\"{pid}\""))
                        })
                        .unwrap_or(false);
                    if still_alive {
                        return Err(format!(
                            "taskkill exited with {status} for sidecar PID {pid}"
                        ));
                    }
                }
                Err(e) => {
                    return Err(format!("Failed to run taskkill for sidecar PID {pid}: {e}"));
                }
            }
        }

        *pid_guard = None;

        // We have successfully terminated the sidecar we owned; release ownership.
        TAURI_OWNS_SIDECAR.store(false, Ordering::SeqCst);
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
async fn sidecar_status(state: State<'_, SidecarState>) -> Result<SidecarStatus, String> {
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
