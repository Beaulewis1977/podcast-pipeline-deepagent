import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  BACKEND_PORT,
  HEALTH_POLL_INTERVAL_MS,
  STAGE_ORDER,
  type BackendStatus,
  type JobDetail,
  type JobSummary,
  type RuntimeDiagnostics,
  type SidecarStatus,
  type StageName,
  bootBackend,
  checkHealth,
  createJob,
  deleteJob,
  getJob,
  getRuntimeDiagnostics,
  getSidecarStatus,
  listJobs,
  reconcileJobs,
  resumeJob,
  runJob,
  stopSidecar,
} from "./lib/backend";
import {
  type RecoveryStatus,
  type ResumableJob,
  checkRecovery,
} from "./lib/recovery";

const FINAL_STAGE: StageName = "render";

function isJobNotFoundError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  return error.message.includes("(404)") || error.message.includes("Job not found");
}

function App() {
  const [status, setStatus] = useState<BackendStatus>("disconnected");
  const [sidecar, setSidecar] = useState<SidecarStatus | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJobDetail, setSelectedJobDetail] = useState<JobDetail | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [activity, setActivity] = useState<string | null>(null);
  const [activityKind, setActivityKind] = useState<"info" | "error">("info");
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [recoveryStatus, setRecoveryStatus] = useState<RecoveryStatus | null>(
    null,
  );
  const [runtimeDiagnostics, setRuntimeDiagnostics] =
    useState<RuntimeDiagnostics | null>(null);
  const [createVideoPath, setCreateVideoPath] = useState("");
  const [createJobName, setCreateJobName] = useState("");
  const [runUntilByJob, setRunUntilByJob] = useState<
    Record<string, StageName>
  >({});
  const [resumeFromByJob, setResumeFromByJob] = useState<
    Record<string, StageName>
  >({});
  const bootAttempted = useRef(false);
  const selectedJobIdRef = useRef<string | null>(null);

  const resumableByJob = useMemo(() => {
    const entries = recoveryStatus?.resumable_jobs ?? [];
    return new Map(entries.map((job) => [job.job_id, job]));
  }, [recoveryStatus]);

  const clearSelectedJob = useCallback(() => {
    selectedJobIdRef.current = null;
    setSelectedJobId(null);
    setSelectedJobDetail(null);
  }, []);

  const selectJob = useCallback((jobId: string) => {
    selectedJobIdRef.current = jobId;
    setSelectedJobId(jobId);
  }, []);

  const markInfo = useCallback((message: string) => {
    setActivity(message);
    setActivityKind("info");
    setError(null);
  }, []);

  const markError = useCallback((message: string) => {
    setActivity(message);
    setActivityKind("error");
    setError(message);
  }, []);

  const pollHealth = useCallback(async () => {
    const health = await checkHealth();
    if (health !== null) {
      setStatus("connected");
      return true;
    }
    setStatus("disconnected");
    return false;
  }, []);

  const refreshRecovery = useCallback(async () => {
    if (status !== "connected") {
      return;
    }
    try {
      const recovery = await checkRecovery();
      setRecoveryStatus(recovery);
    } catch {
      // Non-critical in monitor mode.
    }
  }, [status]);

  const refreshRuntimeDiagnostics = useCallback(async () => {
    if (status !== "connected") {
      return;
    }
    try {
      const diagnostics = await getRuntimeDiagnostics();
      setRuntimeDiagnostics(diagnostics);
    } catch {
      setRuntimeDiagnostics(null);
    }
  }, [status]);

  const syncJobControls = useCallback(
    (data: JobSummary[]) => {
      setRunUntilByJob((prev) => {
        const next: Record<string, StageName> = {};
        for (const job of data) {
          next[job.job_id] = prev[job.job_id] ?? FINAL_STAGE;
        }
        return next;
      });

      setResumeFromByJob((prev) => {
        const next: Record<string, StageName> = {};
        for (const job of data) {
          const resumable = resumableByJob.get(job.job_id);
          if (resumable && isStageName(resumable.resume_stage)) {
            next[job.job_id] = prev[job.job_id] ?? resumable.resume_stage;
          } else {
            next[job.job_id] = prev[job.job_id] ?? "ingest";
          }
        }
        return next;
      });
    },
    [resumableByJob],
  );

  const fetchSelectedJobDetail = useCallback(async (jobId: string) => {
    return getJob(jobId);
  }, []);

  const refreshJobsAndDetails = useCallback(async () => {
    if (status !== "connected") {
      return;
    }

    setIsRefreshing(true);
    try {
      const data = await listJobs();
      setJobs(data);
      syncJobControls(data);

      const currentSelectedJobId = selectedJobIdRef.current;
      if (currentSelectedJobId !== null) {
        const stillExists = data.some((job) => job.job_id === currentSelectedJobId);
        if (!stillExists) {
          clearSelectedJob();
        } else {
          try {
            const detail = await fetchSelectedJobDetail(currentSelectedJobId);
            if (selectedJobIdRef.current === currentSelectedJobId) {
              setSelectedJobDetail(detail);
            }
          } catch (error) {
            // A selected job can disappear between list and detail fetch.
            if (isJobNotFoundError(error)) {
              clearSelectedJob();
            } else {
              throw error;
            }
          }
        }
      }
      setError(null);
    } finally {
      setIsRefreshing(false);
    }
  }, [clearSelectedJob, fetchSelectedJobDetail, status, syncJobControls]);

  const runAction = useCallback(
    async (actionKey: string, fn: () => Promise<string>) => {
      setActiveAction(actionKey);
      setActivity(null);
      try {
        const message = await fn();
        markInfo(message);
        await refreshJobsAndDetails();
        await refreshRecovery();
        await refreshRuntimeDiagnostics();
      } catch (err) {
        markError(
          err instanceof Error ? err.message : "Operation failed unexpectedly",
        );
      } finally {
        setActiveAction(null);
      }
    },
    [
      markError,
      markInfo,
      refreshJobsAndDetails,
      refreshRecovery,
      refreshRuntimeDiagnostics,
    ],
  );

  const openJobDetails = useCallback(
    async (jobId: string) => {
      await runAction(`detail:${jobId}`, async () => {
        selectJob(jobId);
        const detail = await fetchSelectedJobDetail(jobId);
        if (selectedJobIdRef.current === jobId) {
          setSelectedJobDetail(detail);
        }
        return `Loaded details for ${jobId}`;
      });
    },
    [fetchSelectedJobDetail, runAction, selectJob],
  );

  const handleCreateJob = useCallback(async () => {
    const videoPath = createVideoPath.trim();
    if (!videoPath) {
      markError("Video path is required to create a job.");
      return;
    }

    await runAction("create-job", async () => {
      const created = await createJob(videoPath, createJobName.trim() || undefined);
      setCreateVideoPath("");
      setCreateJobName("");
      selectJob(created.job_id);
      return `Created job ${created.job_id}`;
    });
  }, [createJobName, createVideoPath, markError, runAction, selectJob]);

  const handleRunFull = useCallback(
    async (jobId: string) => {
      await runAction(`run-full:${jobId}`, async () => {
        const result = await runJob(jobId, { background: true });
        return result.message;
      });
    },
    [runAction],
  );

  const handleRunToStage = useCallback(
    async (jobId: string) => {
      const untilStage = runUntilByJob[jobId] ?? FINAL_STAGE;
      await runAction(`run-stage:${jobId}`, async () => {
        const result = await runJob(jobId, {
          untilStage,
          background: true,
        });
        return result.message;
      });
    },
    [runAction, runUntilByJob],
  );

  const handleResume = useCallback(
    async (jobId: string, fallbackStage?: StageName) => {
      const fromStage = resumeFromByJob[jobId] ?? fallbackStage ?? "ingest";
      await runAction(`resume:${jobId}`, async () => {
        const result = await resumeJob(jobId, {
          fromStage,
          untilStage: FINAL_STAGE,
          background: true,
        });
        return result.message;
      });
    },
    [resumeFromByJob, runAction],
  );

  const handleDelete = useCallback(
    async (jobId: string) => {
      const confirmed = window.confirm(
        `Delete job ${jobId} and all generated files?`,
      );
      if (!confirmed) {
        return;
      }

      await runAction(`delete:${jobId}`, async () => {
        if (selectedJobIdRef.current === jobId) {
          clearSelectedJob();
        }
        const result = await deleteJob(jobId);
        return result.message || `Deleted job ${result.job_id}`;
      });
    },
    [clearSelectedJob, runAction],
  );

  const handleRetry = useCallback(async () => {
    setStatus("connecting");
    setActivity(null);
    const connected = await pollHealth();
    if (connected) {
      markInfo("Backend connection restored.");
      await refreshJobsAndDetails();
      await refreshRecovery();
      await refreshRuntimeDiagnostics();
    } else {
      markError(`Backend unreachable at http://127.0.0.1:${BACKEND_PORT}`);
    }
  }, [
    markError,
    markInfo,
    pollHealth,
    refreshJobsAndDetails,
    refreshRecovery,
    refreshRuntimeDiagnostics,
  ]);

  const handleReconcile = useCallback(async () => {
    await runAction("reconcile", async () => {
      const corrected = await reconcileJobs();
      return corrected === 0
        ? "Reconcile complete: no stale runtime entries found."
        : `Reconcile complete: corrected ${corrected} stale runtime entr${corrected === 1 ? "y" : "ies"}.`;
    });
  }, [runAction]);

  const refreshSidecarStatus = useCallback(async () => {
    try {
      const current = await getSidecarStatus();
      setSidecar(current);
    } catch {
      // Running outside Tauri context (web-only dev mode).
    }
  }, []);

  const dismissRecovery = useCallback(() => {
    setRecoveryStatus(null);
  }, []);

  useEffect(() => {
    if (bootAttempted.current) {
      return;
    }
    bootAttempted.current = true;

    let cancelled = false;

    async function boot() {
      setStatus("connecting");
      try {
        const result = await bootBackend();
        if (cancelled) {
          return;
        }
        setSidecar(result.sidecar);
        if (result.health !== null) {
          setStatus("connected");
          setError(null);
          markInfo("Backend sidecar is healthy.");
          return;
        }
        setStatus("disconnected");
        markError("Backend did not become ready within startup timeout.");
      } catch (err) {
        if (cancelled) {
          return;
        }
        const healthy = await checkHealth();
        if (healthy !== null) {
          setStatus("connected");
          markInfo("Connected to an already-running backend service.");
        } else {
          setStatus("disconnected");
          markError(
            err instanceof Error ? err.message : "Sidecar startup failed",
          );
        }
      }
    }

    void boot();
    return () => {
      cancelled = true;
    };
  }, [markError, markInfo]);

  useEffect(() => {
    if (status !== "connected") {
      return;
    }
    void refreshJobsAndDetails();
    void refreshRecovery();
    void refreshRuntimeDiagnostics();
  }, [refreshJobsAndDetails, refreshRecovery, refreshRuntimeDiagnostics, status]);

  useEffect(() => {
    const interval = setInterval(() => {
      void pollHealth();
      void refreshJobsAndDetails();
      void refreshRuntimeDiagnostics();
    }, HEALTH_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [pollHealth, refreshJobsAndDetails, refreshRuntimeDiagnostics]);

  useEffect(() => {
    const handleUnload = () => {
      void stopSidecar().catch(() => {});
    };
    window.addEventListener("beforeunload", handleUnload);
    return () => window.removeEventListener("beforeunload", handleUnload);
  }, []);

  const hasResumableJobs =
    recoveryStatus !== null && recoveryStatus.resumable_jobs.length > 0;

  return (
    <div className="container">
      <header>
        <h1>Podcast Pipeline</h1>
        <h2>Desktop Control Panel</h2>
      </header>

      {activity && (
        <section
          className="status-panel"
          style={{
            borderColor:
              activityKind === "error" ? "var(--error)" : "var(--success)",
            marginBottom: "1rem",
          }}
        >
          <div className="status-row">
            <span
              className={`status-dot ${activityKind === "error" ? "disconnected" : "connected"}`}
            />
            <span className="status-label">
              {activityKind === "error" ? "Error" : "Status"}
            </span>
            <span className="status-value">{activity}</span>
          </div>
        </section>
      )}

      {hasResumableJobs && recoveryStatus && (
        <section className="status-panel">
          <div className="status-row" style={{ marginBottom: "0.75rem" }}>
            <span className="status-dot connecting" />
            <span className="status-label">Recovery</span>
            <span className="status-value">
              {recoveryStatus.resumable_jobs.length} interrupted{" "}
              {recoveryStatus.resumable_jobs.length === 1 ? "job" : "jobs"}{" "}
              available for resume
              {recoveryStatus.corrected > 0 &&
                ` (${recoveryStatus.corrected} stale entries corrected)`}
            </span>
            <button
              className="btn"
              style={{ marginLeft: "auto" }}
              onClick={dismissRecovery}
            >
              Dismiss
            </button>
          </div>
          <ul className="job-list">
            {recoveryStatus.resumable_jobs.map((job) => (
              <li key={job.job_id} className="job-item">
                <div className="job-item-header">
                  <span className="job-id">{job.job_id}</span>
                  <span className="job-stage">resume from {job.resume_stage}</span>
                </div>
                <div style={{ marginBottom: "0.75rem", fontSize: "0.85rem" }}>
                  Done: {job.completed_stages.join(", ") || "none"}
                  {job.failed_stages.length > 0 &&
                    ` | Failed: ${job.failed_stages.join(", ")}`}
                  {job.interrupted && " | interrupted runtime detected"}
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button
                    className="btn"
                    onClick={() =>
                      void handleResume(
                        job.job_id,
                        isStageName(job.resume_stage) ? job.resume_stage : undefined,
                      )
                    }
                    disabled={activeAction === `resume:${job.job_id}`}
                  >
                    {activeAction === `resume:${job.job_id}`
                      ? "Resuming..."
                      : "Resume Job"}
                  </button>
                  <button
                    className="btn"
                    onClick={() => void openJobDetails(job.job_id)}
                    disabled={activeAction === `detail:${job.job_id}`}
                  >
                    Details
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="status-panel">
        <div className="status-row">
          <span className="status-dot connecting" />
          <span className="status-label">Recovery</span>
          <span className="status-value">
            {runtimeDiagnostics
              ? `${runtimeDiagnostics.active_jobs.length} active / ${runtimeDiagnostics.stale_jobs.length} stale / ${runtimeDiagnostics.orphaned_jobs.length} orphaned`
              : "Runtime diagnostics unavailable"}
          </span>
        </div>
        {runtimeDiagnostics && runtimeDiagnostics.jobs.length > 0 && (
          <div style={{ marginTop: "0.75rem", display: "grid", gap: "0.35rem" }}>
            {runtimeDiagnostics.jobs.map((job) => (
              <div key={`runtime-${job.job_id}`} className="status-row">
                <span
                  className={`status-dot ${
                    job.stale || job.orphaned ? "disconnected" : "connected"
                  }`}
                />
                <span className="status-label">{job.job_id}</span>
                <span className="status-value">
                  {job.status}
                  {job.last_known_stage ? ` @ ${job.last_known_stage}` : ""}
                  {job.stale && " • stale"}
                  {job.orphaned && " • orphaned"}
                </span>
              </div>
            ))}
          </div>
        )}
        {(runtimeDiagnostics?.stale_jobs.length ?? 0) > 0 && (
          <div style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
            Stale jobs: {runtimeDiagnostics?.stale_jobs.join(", ")}
          </div>
        )}
        {(runtimeDiagnostics?.orphaned_jobs.length ?? 0) > 0 && (
          <div style={{ marginTop: "0.25rem", fontSize: "0.85rem" }}>
            Orphaned jobs: {runtimeDiagnostics?.orphaned_jobs.join(", ")}
          </div>
        )}
        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem" }}>
          <button
            className="btn"
            onClick={() => void handleReconcile()}
            disabled={activeAction === "reconcile"}
          >
            {activeAction === "reconcile" ? "Reconciling..." : "Reconcile Jobs"}
          </button>
          <button className="btn" onClick={() => void refreshRuntimeDiagnostics()}>
            Refresh Diagnostics
          </button>
        </div>
      </section>

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
                ? `PID ${sidecar.pid ?? "?"} on port ${sidecar.port}`
                : "Not running"}
            </span>
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
          <button className="btn" onClick={() => void handleRetry()}>
            Retry Connection
          </button>
          <button className="btn" onClick={() => void refreshSidecarStatus()}>
            Refresh Sidecar
          </button>
          <button
            className="btn"
            onClick={() => void refreshJobsAndDetails()}
            disabled={isRefreshing}
          >
            {isRefreshing ? "Refreshing..." : "Refresh Jobs"}
          </button>
        </div>
      </section>

      <section className="status-panel">
        <h2>Create Job</h2>
        <div style={{ display: "grid", gap: "0.75rem" }}>
          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
              Video Path
            </span>
            <input
              value={createVideoPath}
              onChange={(event) => setCreateVideoPath(event.target.value)}
              placeholder="/absolute/path/to/video.mp4"
              style={inputStyle}
            />
          </label>
          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
              Job Name (optional)
            </span>
            <input
              value={createJobName}
              onChange={(event) => setCreateJobName(event.target.value)}
              placeholder="episode-042"
              style={inputStyle}
            />
          </label>
          <div>
            <button
              className="btn btn-primary"
              onClick={() => void handleCreateJob()}
              disabled={status !== "connected" || activeAction === "create-job"}
            >
              {activeAction === "create-job" ? "Creating..." : "Create Job"}
            </button>
          </div>
        </div>
      </section>

      <section>
        <h2>Recent Jobs</h2>
        {status !== "connected" ? (
          <div className="empty-state">Connect to backend to manage jobs.</div>
        ) : jobs.length === 0 ? (
          <div className="empty-state">No jobs found.</div>
        ) : (
          <ul className="job-list">
            {jobs.map((job) => (
              <li key={job.job_id} className="job-item">
                <div className="job-item-header">
                  <span className="job-id">{job.job_id}</span>
                  <span className="job-stage">{activeStageLabel(job)}</span>
                </div>
                <div
                  style={{
                    marginBottom: "0.75rem",
                    fontSize: "0.8rem",
                    color: "var(--text-secondary)",
                  }}
                >
                  {job.status} &middot; {toLocalTimestamp(job.created)}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  <button
                    className="btn"
                    onClick={() => void openJobDetails(job.job_id)}
                    disabled={activeAction === `detail:${job.job_id}`}
                  >
                    {selectedJobId === job.job_id ? "Viewing" : "Details"}
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={() => void handleRunFull(job.job_id)}
                    disabled={activeAction === `run-full:${job.job_id}`}
                  >
                    {activeAction === `run-full:${job.job_id}`
                      ? "Submitting..."
                      : "Run Full"}
                  </button>
                  <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                    <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                      Until
                    </span>
                    <select
                      value={runUntilByJob[job.job_id] ?? FINAL_STAGE}
                      onChange={(event) =>
                        updateStageSelection(event.target.value, (stage) => {
                          setRunUntilByJob((prev) => ({ ...prev, [job.job_id]: stage }));
                        })
                      }
                      style={selectStyle}
                    >
                      {STAGE_ORDER.map((stageName) => (
                        <option key={`run-${job.job_id}-${stageName}`} value={stageName}>
                          {stageName}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="btn"
                    onClick={() => void handleRunToStage(job.job_id)}
                    disabled={activeAction === `run-stage:${job.job_id}`}
                  >
                    {activeAction === `run-stage:${job.job_id}`
                      ? "Submitting..."
                      : "Run To Stage"}
                  </button>
                  <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                    <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                      Resume
                    </span>
                    <select
                      value={resumeFromByJob[job.job_id] ?? "ingest"}
                      onChange={(event) =>
                        updateStageSelection(event.target.value, (stage) => {
                          setResumeFromByJob((prev) => ({
                            ...prev,
                            [job.job_id]: stage,
                          }));
                        })
                      }
                      style={selectStyle}
                    >
                      {STAGE_ORDER.map((stageName) => (
                        <option
                          key={`resume-${job.job_id}-${stageName}`}
                          value={stageName}
                        >
                          {stageName}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="btn"
                    onClick={() =>
                      void handleResume(
                        job.job_id,
                        resolveResumeStage(resumableByJob.get(job.job_id)),
                      )
                    }
                    disabled={activeAction === `resume:${job.job_id}`}
                  >
                    {activeAction === `resume:${job.job_id}`
                      ? "Submitting..."
                      : "Resume"}
                  </button>
                  <button
                    className="btn"
                    style={{ borderColor: "var(--error)" }}
                    onClick={() => void handleDelete(job.job_id)}
                    disabled={activeAction === `delete:${job.job_id}`}
                  >
                    {activeAction === `delete:${job.job_id}`
                      ? "Deleting..."
                      : "Delete"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selectedJobDetail && (
        <section className="status-panel" style={{ marginTop: "1.5rem" }}>
          <h2>Job Detail</h2>
          <div className="status-row">
            <span className="status-label">Job</span>
            <span className="status-value">{selectedJobDetail.job_id}</span>
          </div>
          <div className="status-row">
            <span className="status-label">Status</span>
            <span className="status-value">{selectedJobDetail.status}</span>
          </div>
          <div className="status-row">
            <span className="status-label">Created</span>
            <span className="status-value">
              {toLocalTimestamp(selectedJobDetail.created_at)}
            </span>
          </div>
          <div className="status-row">
            <span className="status-label">Updated</span>
            <span className="status-value">
              {toLocalTimestamp(selectedJobDetail.updated_at)}
            </span>
          </div>
          <div style={{ marginTop: "0.75rem", display: "grid", gap: "0.5rem" }}>
            {STAGE_ORDER.map((stageName) => {
              const stage = selectedJobDetail.stages[stageName];
              return (
                <div key={`detail-${stageName}`} className="status-row">
                  <span
                    className={`status-dot ${
                      stage?.status === "complete"
                        ? "connected"
                        : stage?.status === "running" || stage?.status === "waiting"
                          ? "connecting"
                          : "disconnected"
                    }`}
                  />
                  <span className="status-label">{stageName}</span>
                  <span className="status-value">
                    {stage?.status ?? "pending"}
                    {stage?.progress_percent != null &&
                      ` (${stage.progress_percent}%)`}
                    {stage?.error && ` — ${stage.error}`}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}

const inputStyle: CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  color: "var(--text-primary)",
  borderRadius: "6px",
  padding: "0.5rem 0.65rem",
  fontSize: "0.9rem",
};

const selectStyle: CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  color: "var(--text-primary)",
  borderRadius: "6px",
  padding: "0.35rem 0.5rem",
  fontSize: "0.8rem",
};

function isStageName(value: string): value is StageName {
  return (STAGE_ORDER as readonly string[]).includes(value);
}

function updateStageSelection(
  raw: string,
  apply: (stage: StageName) => void,
): void {
  if (isStageName(raw)) {
    apply(raw);
  }
}

function resolveResumeStage(job: ResumableJob | undefined): StageName | undefined {
  if (!job) {
    return undefined;
  }
  return isStageName(job.resume_stage) ? job.resume_stage : undefined;
}

function activeStageLabel(job: JobSummary): string {
  const active = Object.entries(job.stages ?? {}).find(
    ([, stageStatus]) => stageStatus === "running" || stageStatus === "waiting",
  );
  return active?.[0] ?? job.status;
}

function toLocalTimestamp(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export default App;
