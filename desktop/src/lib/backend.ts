/**
 * Backend service client for the Podcast Pipeline desktop app.
 *
 * Exposes typed lifecycle methods for:
 * - backend sidecar lifecycle (Tauri invoke commands)
 * - job lifecycle operations (create, run, resume, delete, detail)
 * - recovery diagnostics (reconcile + runtime state)
 *
 * HTTP calls target the local backend at ``127.0.0.1:${BACKEND_PORT}``.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Default backend service port matching Python service and Rust sidecar config. */
export const BACKEND_PORT = 8787;

const BASE_URL = `http://127.0.0.1:${BACKEND_PORT}`;

/** Interval in milliseconds between health polls. */
export const HEALTH_POLL_INTERVAL_MS = 5_000;

/** Maximum time to wait for backend readiness after sidecar start. */
const STARTUP_TIMEOUT_MS = 15_000;

/** Interval between readiness probes during startup. */
const STARTUP_PROBE_INTERVAL_MS = 500;

export const STAGE_ORDER = [
  "ingest",
  "transcribe",
  "analyze",
  "review",
  "render",
] as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Valid stage names supported by the backend service. */
export type StageName = (typeof STAGE_ORDER)[number];

/** Connection state for the backend sidecar service. */
export type BackendStatus = "disconnected" | "connecting" | "connected";

/** Response shape from the backend GET /health endpoint. */
export interface HealthResponse {
  status: string;
}

/** Sidecar status returned by Rust commands. */
export interface SidecarStatus {
  running: boolean;
  pid: number | null;
  port: number;
}

/** Minimal job summary returned from backend GET /jobs endpoint. */
export interface JobSummary {
  job_id: string;
  status: string;
  created: string;
  stages: Record<string, string>;
}

/** Stage detail returned from GET /jobs/{job_id}. */
export interface JobStageDetail {
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  outputs: string[];
  error?: string | null;
  progress_percent?: number | null;
  progress_message?: string | null;
}

/** Full job detail returned from backend GET /jobs/{job_id}. */
export interface JobDetail {
  job_id: string;
  status: string;
  input_file: string;
  created_at: string;
  updated_at: string;
  stages: Record<string, JobStageDetail>;
  error?: string | null;
}

/** Request body for POST /jobs. */
interface CreateJobRequest {
  video_path: string;
  name?: string;
}

/** Response shape from POST /jobs. */
export interface CreateJobResponse {
  job_id: string;
  status: string;
  input_file: string;
  created_at: string;
}

/** Canonical response from run and resume lifecycle endpoints. */
export interface LifecycleActionResponse {
  job_id: string;
  status: string;
  message: string;
  started: boolean;
  completed: boolean;
  rejected: boolean;
}

/** Runtime metadata summary for a single job journal entry. */
export interface RuntimeJobStatus {
  job_id: string;
  status: string;
  pid: number;
  last_known_stage?: string | null;
  heartbeat: string;
  heartbeat_age_seconds?: number | null;
  stale: boolean;
  orphaned: boolean;
}

/** Response shape from GET /system/runtime. */
export interface RuntimeDiagnostics {
  active_jobs: string[];
  stale_jobs: string[];
  orphaned_jobs: string[];
  jobs: RuntimeJobStatus[];
}

/** Request options for job run operations. */
export interface RunJobOptions {
  stage?: StageName;
  untilStage?: StageName;
  background?: boolean;
}

/** Request options for job resume operations. */
export interface ResumeJobOptions {
  fromStage?: StageName;
  untilStage?: StageName;
  background?: boolean;
}

interface ListJobsResponse {
  jobs: JobSummary[];
}

interface BackgroundRunResponse {
  job_id: string;
  accepted: boolean;
  message: string;
}

interface DeleteJobResponse {
  job_id: string;
  deleted: boolean;
  message: string;
}

type InvokeFn = <T>(
  command: string,
  args?: Record<string, unknown>,
) => Promise<T>;

let cachedInvoke: InvokeFn | null = null;

/**
 * Returns true when running inside a Tauri webview (desktop app).
 * Returns false when running in a plain browser (Vite dev server, tests).
 *
 * Tauri v2 injects ``window.__TAURI_INTERNALS__`` before any JS runs.
 * Checking this synchronously avoids the hang caused by importing and calling
 * the Tauri invoke function outside the Tauri IPC bridge — the npm package
 * loads fine but the call never resolves in a plain browser context.
 */
function isTauriContext(): boolean {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in window
  );
}

// ---------------------------------------------------------------------------
// Sidecar lifecycle (Tauri invoke)
// ---------------------------------------------------------------------------

async function tauriInvoke<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauriContext()) {
    throw new Error("Tauri IPC is unavailable — not running inside a Tauri webview");
  }

  if (cachedInvoke === null) {
    const tauri = await import("@tauri-apps/api/core");
    cachedInvoke = tauri.invoke as InvokeFn;
  }

  return cachedInvoke<T>(command, args);
}

/**
 * Start the backend sidecar process via Tauri command.
 *
 * Invokes the Rust ``start_sidecar`` command.
 */
export async function startSidecar(): Promise<SidecarStatus> {
  return tauriInvoke<SidecarStatus>("start_sidecar");
}

/**
 * Stop the backend sidecar process via Tauri command.
 *
 * Invokes the Rust ``stop_sidecar`` command.
 */
export async function stopSidecar(): Promise<SidecarStatus> {
  return tauriInvoke<SidecarStatus>("stop_sidecar");
}

/** Query the current sidecar process status without side effects. */
export async function getSidecarStatus(): Promise<SidecarStatus> {
  return tauriInvoke<SidecarStatus>("sidecar_status");
}

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------

/**
 * Probe the backend health endpoint.
 *
 * Returns the health response on success, or ``null`` when unreachable.
 */
export async function checkHealth(): Promise<HealthResponse | null> {
  try {
    const data = await requestJson<HealthResponse>("/health");
    return data.status === "ok" ? data : null;
  } catch {
    return null;
  }
}

/**
 * Wait for the backend to become healthy after sidecar startup.
 *
 * Polls the health endpoint at short intervals until it responds with
 * status ``ok`` or the timeout expires.
 */
export async function waitForReady(): Promise<HealthResponse | null> {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;

  while (Date.now() < deadline) {
    const health = await checkHealth();
    if (health !== null) {
      return health;
    }
    await sleep(STARTUP_PROBE_INTERVAL_MS);
  }

  return null;
}

// ---------------------------------------------------------------------------
// Job lifecycle API
// ---------------------------------------------------------------------------

/** Fetch the list of all jobs from the backend. */
export async function listJobs(): Promise<JobSummary[]> {
  const payload = await requestJson<ListJobsResponse>("/jobs");
  return payload.jobs ?? [];
}

/** Create a new job on the backend. */
export async function createJob(
  videoPath: string,
  name?: string,
): Promise<CreateJobResponse> {
  const body: CreateJobRequest = { video_path: videoPath };
  if (name && name.trim().length > 0) {
    body.name = name.trim();
  }
  return requestJson<CreateJobResponse>("/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Trigger a run for the specified job. */
export async function runJob(
  jobId: string,
  options: RunJobOptions = {},
): Promise<LifecycleActionResponse> {
  const payload: Record<string, unknown> = {};
  if (options.stage) {
    payload.stage = options.stage;
  }
  if (options.untilStage) {
    payload.until_stage = options.untilStage;
  }

  if (options.background) {
    const background = await requestJson<BackgroundRunResponse>(
      `/jobs/${encodeURIComponent(jobId)}/run/background`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
    return {
      job_id: background.job_id,
      status: background.accepted ? "running" : "failed",
      message: background.message,
      started: background.accepted,
      completed: false,
      rejected: !background.accepted,
    };
  }

  return requestJson<LifecycleActionResponse>(
    `/jobs/${encodeURIComponent(jobId)}/run`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

/** Resume a job from the first incomplete stage or requested stage. */
export async function resumeJob(
  jobId: string,
  options: ResumeJobOptions = {},
): Promise<LifecycleActionResponse> {
  const payload: Record<string, unknown> = {
    background: options.background ?? false,
  };
  if (options.fromStage) {
    payload.from_stage = options.fromStage;
  }
  if (options.untilStage) {
    payload.until_stage = options.untilStage;
  }

  return requestJson<LifecycleActionResponse>(
    `/jobs/${encodeURIComponent(jobId)}/resume`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

/** Get detailed status for a single job. */
export async function getJob(jobId: string): Promise<JobDetail> {
  return requestJson<JobDetail>(`/jobs/${encodeURIComponent(jobId)}`);
}

/** Delete a job and all its artifacts. */
export async function deleteJob(jobId: string): Promise<DeleteJobResponse> {
  return requestJson<DeleteJobResponse>(`/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
}

/** Trigger reconciliation of stale runtime metadata. */
export async function reconcileJobs(): Promise<number> {
  const payload = await requestJson<{ corrected?: number }>("/jobs/reconcile", {
    method: "POST",
  });
  return payload.corrected ?? 0;
}

/** Fetch stale/orphan runtime diagnostics from the backend. */
export async function getRuntimeDiagnostics(): Promise<RuntimeDiagnostics> {
  return requestJson<RuntimeDiagnostics>("/system/runtime");
}

// ---------------------------------------------------------------------------
// Orchestration helper
// ---------------------------------------------------------------------------

/**
 * Full startup sequence: start sidecar (Tauri mode) or probe health (dev mode).
 *
 * In Tauri desktop mode: invokes ``start_sidecar``, which already performs a
 * pre-spawn health check (coexistence); then waits for readiness.
 *
 * In plain browser mode (Vite dev server, ``pnpm dev``): Tauri IPC is not
 * available, so we skip sidecar management entirely and probe the backend
 * directly. Start the backend manually in this case:
 *   ``uv run python src/podcast_pipeline/service/cli.py``
 */
export async function bootBackend(): Promise<{
  sidecar: SidecarStatus;
  health: HealthResponse | null;
}> {
  const noSidecar: SidecarStatus = { running: false, pid: null, port: BACKEND_PORT };

  // Always probe health first — works in all modes:
  //   • Vite dev mode: connects immediately if backend is running manually
  //   • Tauri coexistence: connects without spawning a duplicate sidecar
  //   • Tauri cold start: falls through to sidecar spawn below
  const existingHealth = await checkHealth();
  if (existingHealth !== null) {
    return { sidecar: noSidecar, health: existingHealth };
  }

  // Backend is not reachable. Spawn a sidecar if inside Tauri; otherwise report
  // disconnected so the UI can show "start the backend" instructions.
  if (!isTauriContext()) {
    return { sidecar: noSidecar, health: null };
  }

  const sidecar = await startSidecar();
  const health = await waitForReady();
  return { sidecar, health };
}

// ---------------------------------------------------------------------------
// Internal HTTP helpers
// ---------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function detailToMessage(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim().length > 0) {
    return detail.trim();
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (isRecord(item) && typeof item.msg === "string") {
          return item.msg;
        }
        return null;
      })
      .filter((item): item is string => Boolean(item && item.trim().length > 0));
    if (messages.length > 0) {
      return messages.join("; ");
    }
    return null;
  }

  if (isRecord(detail)) {
    try {
      return JSON.stringify(detail);
    } catch {
      return null;
    }
  }

  return null;
}

function buildApiError(
  method: string,
  path: string,
  response: Response,
  payload: unknown,
): Error {
  let detail = detailToMessage(payload);
  if (detail === null && isRecord(payload)) {
    detail = detailToMessage(payload.detail);
  }
  if (detail === null || detail.length === 0) {
    detail = response.statusText || "Unknown error";
  }
  return new Error(
    `${method.toUpperCase()} ${path} failed (${response.status}): ${detail}`,
  );
}

async function readResponsePayload(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers ?? {});
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      method,
      headers,
    });
  } catch (err) {
    throw new Error(
      `${method} ${path} failed: ${err instanceof Error ? err.message : "network error"}`,
    );
  }

  const payload = await readResponsePayload(response);
  if (!response.ok) {
    throw buildApiError(method, path, response, payload);
  }

  if (payload === null) {
    return {} as T;
  }
  return payload as T;
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
