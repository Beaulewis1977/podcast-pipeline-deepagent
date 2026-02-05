import { useState, useEffect, useCallback } from "react";

/** Connection state for the backend sidecar service. */
type BackendStatus = "disconnected" | "connecting" | "connected";

/** Minimal job summary returned from backend /jobs endpoint. */
interface JobSummary {
  job_id: string;
  status: string;
  current_stage: string | null;
  created_at: string;
}

const BACKEND_PORT = 8787;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/health`;
const JOBS_URL = `http://127.0.0.1:${BACKEND_PORT}/jobs`;
const HEALTH_INTERVAL_MS = 5_000;

function App() {
  const [status, setStatus] = useState<BackendStatus>("disconnected");
  const [version, setVersion] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  /** Probe the backend health endpoint. */
  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(HEALTH_URL);
      if (!res.ok) {
        setStatus("disconnected");
        setError(`Health check returned ${res.status}`);
        return;
      }
      const data = await res.json();
      setStatus("ok" === data.status ? "connected" : "disconnected");
      setVersion(data.version ?? null);
      setError(null);
    } catch {
      setStatus("disconnected");
      setError("Backend unreachable");
    }
  }, []);

  /** Fetch the job list from the backend. */
  const fetchJobs = useCallback(async () => {
    if (status !== "connected") return;
    try {
      const res = await fetch(JOBS_URL);
      if (!res.ok) return;
      const data: JobSummary[] = await res.json();
      setJobs(data);
    } catch {
      // Non-critical: job list will update on next poll
    }
  }, [status]);

  // Start health polling on mount
  useEffect(() => {
    setStatus("connecting");
    checkHealth();
    const interval = setInterval(checkHealth, HEALTH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [checkHealth]);

  // Fetch jobs whenever backend becomes connected
  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  return (
    <div className="container">
      <header>
        <h1>Podcast Pipeline</h1>
        <h2>Desktop Control Panel</h2>
      </header>

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
        <div style={{ marginTop: "0.75rem" }}>
          <button
            className="btn"
            onClick={() => {
              setStatus("connecting");
              checkHealth();
            }}
          >
            Retry Connection
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
                <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                  {job.status} &middot; {new Date(job.created_at).toLocaleString()}
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
