import { useState, useEffect, useCallback, useRef } from "react";
import {
  type BackendStatus,
  type JobSummary,
  type SidecarStatus,
  checkHealth,
  listJobs,
  bootBackend,
  stopSidecar,
  getSidecarStatus,
  HEALTH_POLL_INTERVAL_MS,
} from "./lib/backend";
import {
  type RecoveryStatus,
  type ResumableJob,
  checkRecovery,
  triggerResume,
} from "./lib/recovery";

function App() {
  const [status, setStatus] = useState<BackendStatus>("disconnected");
  const [version, setVersion] = useState<string | null>(null);
  const [sidecar, setSidecar] = useState<SidecarStatus | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [recoveryStatus, setRecoveryStatus] =
    useState<RecoveryStatus | null>(null);
  const [resumingJobId, setResumingJobId] = useState<string | null>(null);
  const bootAttempted = useRef(false);

  /** Probe the backend health endpoint using the backend client. */
  const pollHealth = useCallback(async () => {
    const health = await checkHealth();
    if (health !== null) {
      setStatus("connected");
      setVersion(health.version);
      setError(null);
    } else {
      setStatus("disconnected");
      setError("Backend unreachable");
    }
  }, []);

  /** Fetch the job list from the backend using the backend client. */
  const fetchJobs = useCallback(async () => {
    if (status !== "connected") return;
    try {
      const data = await listJobs();
      setJobs(data);
    } catch {
      // Non-critical: job list will update on next poll
    }
  }, [status]);

  /** Run recovery check after backend becomes connected. */
  const runRecoveryCheck = useCallback(async () => {
    try {
      const recovery = await checkRecovery();
      setRecoveryStatus(recovery);
    } catch {
      // Recovery check is non-critical; proceed without it
    }
  }, []);

  /** Resume a specific interrupted job. */
  const handleResume = useCallback(
    async (job: ResumableJob) => {
      setResumingJobId(job.job_id);
      try {
        await triggerResume(job.job_id, job.resume_stage);
        // Remove resumed job from the recovery list
        setRecoveryStatus((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            resumable_jobs: prev.resumable_jobs.filter(
              (j) => j.job_id !== job.job_id,
            ),
          };
        });
        // Refresh jobs list to reflect the resumed job
        await fetchJobs();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : `Failed to resume ${job.job_id}`,
        );
      } finally {
        setResumingJobId(null);
      }
    },
    [fetchJobs],
  );

  /** Dismiss the recovery banner without resuming. */
  const dismissRecovery = useCallback(() => {
    setRecoveryStatus(null);
  }, []);

  /** Boot the backend sidecar on first mount. */
  useEffect(() => {
    if (bootAttempted.current) return;
    bootAttempted.current = true;

    let cancelled = false;

    async function boot() {
      setStatus("connecting");
      try {
        const result = await bootBackend();
        if (cancelled) return;
        setSidecar(result.sidecar);
        if (result.health !== null) {
          setStatus("connected");
          setVersion(result.health.version);
          setError(null);
        } else {
          setStatus("disconnected");
          setError("Backend did not become ready within timeout");
        }
      } catch (err) {
        if (cancelled) return;
        // Sidecar invoke failed -- likely running outside Tauri (dev mode).
        // Fall back to direct health polling.
        setError(
          err instanceof Error ? err.message : "Sidecar start failed",
        );
        // Try health check directly in case backend is already running
        const health = await checkHealth();
        if (!cancelled && health !== null) {
          setStatus("connected");
          setVersion(health.version);
          setError(null);
        } else if (!cancelled) {
          setStatus("disconnected");
        }
      }
    }

    boot();
    return () => {
      cancelled = true;
    };
  }, []);

  // Run recovery check once backend is connected
  useEffect(() => {
    if (status === "connected") {
      runRecoveryCheck();
    }
  }, [status, runRecoveryCheck]);

  // Health polling after initial boot
  useEffect(() => {
    const interval = setInterval(pollHealth, HEALTH_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [pollHealth]);

  // Fetch jobs whenever backend becomes connected
  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Shutdown sidecar on window unload
  useEffect(() => {
    const handleUnload = () => {
      stopSidecar().catch(() => {});
    };
    window.addEventListener("beforeunload", handleUnload);
    return () => window.removeEventListener("beforeunload", handleUnload);
  }, []);

  /** Manually retry the connection via health check. */
  const handleRetry = useCallback(async () => {
    setStatus("connecting");
    setError(null);
    const health = await checkHealth();
    if (health !== null) {
      setStatus("connected");
      setVersion(health.version);
    } else {
      setStatus("disconnected");
      setError("Backend unreachable");
    }
  }, []);

  /** Refresh sidecar status from Rust state. */
  const refreshSidecarStatus = useCallback(async () => {
    try {
      const s = await getSidecarStatus();
      setSidecar(s);
    } catch {
      // Not in Tauri context
    }
  }, []);

  const hasResumableJobs =
    recoveryStatus !== null && recoveryStatus.resumable_jobs.length > 0;

  return (
    <div className="container">
      <header>
        <h1>Podcast Pipeline</h1>
        <h2>Desktop Control Panel</h2>
      </header>

      {/* Recovery banner */}
      {hasResumableJobs && (
        <section className="recovery-banner">
          <div className="recovery-header">
            <strong>
              Recovery: {recoveryStatus.resumable_jobs.length} interrupted{" "}
              {recoveryStatus.resumable_jobs.length === 1 ? "job" : "jobs"}{" "}
              found
            </strong>
            {recoveryStatus.corrected > 0 && (
              <span className="recovery-corrected">
                ({recoveryStatus.corrected} stale{" "}
                {recoveryStatus.corrected === 1 ? "entry" : "entries"}{" "}
                corrected)
              </span>
            )}
            <button
              className="btn btn-small"
              onClick={dismissRecovery}
              style={{ marginLeft: "auto" }}
            >
              Dismiss
            </button>
          </div>
          <ul className="recovery-list">
            {recoveryStatus.resumable_jobs.map((job) => (
              <li key={job.job_id} className="recovery-item">
                <div className="recovery-item-info">
                  <span className="job-id">{job.job_id}</span>
                  <span className="recovery-detail">
                    Resume from: <strong>{job.resume_stage}</strong>
                    {job.interrupted && " (interrupted)"}
                  </span>
                  <span className="recovery-stages">
                    Done: {job.completed_stages.join(", ") || "none"}
                    {job.failed_stages.length > 0 &&
                      ` | Failed: ${job.failed_stages.join(", ")}`}
                  </span>
                </div>
                <button
                  className="btn"
                  onClick={() => handleResume(job)}
                  disabled={resumingJobId === job.job_id}
                >
                  {resumingJobId === job.job_id ? "Resuming..." : "Resume"}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Backend status panel */}
      <section className="status-panel">
        <div className="status-row">
          <span className={`status-dot ${status}`} />
          <span className="status-label">Backend</span>
          <span className="status-value">
            {status === "connected"
              ? "Connected"
              : status === "connecting"
                ? "Connecting..."
                : "Disconnected"}
          </span>
        </div>
        {sidecar && (
          <div className="status-row">
            <span
              className={`status-dot ${sidecar.running ? "connected" : "disconnected"}`}
            />
            <span className="status-label">Sidecar</span>
            <span className="status-value">
              {sidecar.running
                ? `PID ${sidecar.pid} on port ${sidecar.port}`
                : "Not running"}
            </span>
          </div>
        )}
        {version && (
          <div className="status-row">
            <span className="status-dot connected" />
            <span className="status-label">Version</span>
            <span className="status-value">{version}</span>
          </div>
        )}
        {error && (
          <div className="status-row">
            <span className="status-dot disconnected" />
            <span className="status-label">Error</span>
            <span className="status-value">{error}</span>
          </div>
        )}
        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem" }}>
          <button className="btn" onClick={handleRetry}>
            Retry Connection
          </button>
          <button className="btn" onClick={refreshSidecarStatus}>
            Refresh Sidecar
          </button>
        </div>
      </section>

      {/* Job list panel */}
      <section>
        <h2>Recent Jobs</h2>
        {status !== "connected" ? (
          <div className="empty-state">
            Connect to backend to view jobs.
          </div>
        ) : jobs.length === 0 ? (
          <div className="empty-state">No jobs found.</div>
        ) : (
          <ul className="job-list">
            {jobs.map((job) => (
              <li key={job.job_id} className="job-item">
                <div className="job-item-header">
                  <span className="job-id">{job.job_id}</span>
                  <span className="job-stage">
                    {job.current_stage ?? job.status}
                  </span>
                </div>
                <div
                  style={{
                    fontSize: "0.8rem",
                    color: "var(--text-secondary)",
                  }}
                >
                  {job.status} &middot;{" "}
                  {new Date(job.created_at).toLocaleString()}
                </div>
              </li>
            ))}
          </ul>
        )}
        {status === "connected" && (
          <div style={{ marginTop: "0.75rem" }}>
            <button className="btn" onClick={fetchJobs}>
              Refresh Jobs
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

export default App;
