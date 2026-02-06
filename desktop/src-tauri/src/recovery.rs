//! Desktop startup recovery hooks for crash-interrupted pipeline jobs.
//!
//! After the sidecar backend becomes healthy, the frontend can call
//! [`check_recovery`] to query the backend for resumable jobs and
//! [`trigger_resume`] to resume a specific interrupted job.
//!
//! The actual reconciliation logic lives in the Python backend
//! (`recovery.py`); this module provides Tauri command wrappers so the
//! frontend can drive the recovery flow through invoke calls.

use serde::{Deserialize, Serialize};

/// Single resumable job as returned by the backend `GET /jobs/resumable`.
#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct ResumableJob {
    pub job_id: String,
    pub status: String,
    pub resume_stage: String,
    pub completed_stages: Vec<String>,
    pub failed_stages: Vec<String>,
    pub interrupted: bool,
}

/// Wrapper for the backend `/jobs/resumable` response.
#[derive(Deserialize)]
struct ResumableJobsResponse {
    jobs: Vec<ResumableJob>,
}

/// Result returned by [`trigger_resume`].
#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct ResumeResult {
    pub job_id: String,
    pub status: String,
    pub message: String,
}

/// Backend reconciliation summary from `POST /jobs/reconcile`.
#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct ReconcileResult {
    pub corrected: u32,
}

/// Combined recovery status returned to the frontend on startup.
#[derive(Serialize, Clone, Debug)]
pub struct RecoveryStatus {
    /// Number of jobs that had stale runtime metadata corrected.
    pub corrected: u32,
    /// Jobs that can be resumed after reconciliation.
    pub resumable_jobs: Vec<ResumableJob>,
}

/// Default backend service port (must match Python and TS constants).
const BACKEND_PORT: u16 = 8787;

fn backend_url(path: &str) -> String {
    format!("http://127.0.0.1:{BACKEND_PORT}{path}")
}

/// Check for recoverable jobs after sidecar startup.
///
/// Triggers backend reconciliation first, then fetches the list of
/// resumable jobs.  Returns a [`RecoveryStatus`] combining both.
#[tauri::command]
pub async fn check_recovery() -> Result<RecoveryStatus, String> {
    let client = reqwest::Client::new();

    // Step 1: Force reconciliation of stale runtime metadata.
    let reconcile_resp = client
        .post(backend_url("/jobs/reconcile"))
        .send()
        .await
        .map_err(|e| format!("Reconcile request failed: {e}"))?;

    let corrected = if reconcile_resp.status().is_success() {
        reconcile_resp
            .json::<ReconcileResult>()
            .await
            .map(|r| r.corrected)
            .unwrap_or(0)
    } else {
        0
    };

    // Step 2: Fetch resumable jobs.
    let resumable_resp = client
        .get(backend_url("/jobs/resumable"))
        .send()
        .await
        .map_err(|e| format!("Resumable jobs request failed: {e}"))?;

    let resumable_jobs = if resumable_resp.status().is_success() {
        resumable_resp
            .json::<ResumableJobsResponse>()
            .await
            .map(|r| r.jobs)
            .unwrap_or_default()
    } else {
        Vec::new()
    };

    Ok(RecoveryStatus {
        corrected,
        resumable_jobs,
    })
}

/// Resume a specific interrupted job via the backend API.
///
/// Calls `POST /jobs/{job_id}/resume` with optional `from_stage` and
/// `background=true` for non-blocking execution.
#[tauri::command]
pub async fn trigger_resume(
    job_id: String,
    from_stage: Option<String>,
) -> Result<ResumeResult, String> {
    let client = reqwest::Client::new();
    let url = backend_url(&format!("/jobs/{}/resume", job_id));

    let mut body = serde_json::json!({ "background": true });
    if let Some(stage) = from_stage {
        body["from_stage"] = serde_json::Value::String(stage);
    }

    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Resume request failed: {e}"))?;

    if !resp.status().is_success() {
        let status = resp.status().as_u16();
        let text = resp.text().await.unwrap_or_default();
        return Err(format!("Resume failed ({status}): {text}"));
    }

    resp.json::<ResumeResult>()
        .await
        .map_err(|e| format!("Failed to parse resume response: {e}"))
}
