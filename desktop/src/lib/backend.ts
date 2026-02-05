/**
 * Backend service client for the Podcast Pipeline desktop app.
 *
 * Provides typed functions for:
 * - Sidecar lifecycle control (start/stop/status via Tauri commands)
 * - Health endpoint polling against the local backend service
 * - Job API calls (list, create, run)
 *
 * All HTTP calls target the local backend at 127.0.0.1:BACKEND_PORT.
 */

import { invoke } from "@tauri-apps/api/core";

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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Connection state for the backend sidecar service. */
export type BackendStatus = "disconnected" | "connecting" | "connected";

/** Response shape from the backend GET /health endpoint. */
export interface HealthResponse {
  status: string;
  version: string | null;
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
  current_stage: string | null;
  created_at: string;
}

/** Request body for POST /jobs. */
export interface CreateJobRequest {
  input_path: string;
}

/** Response shape from POST /jobs. */
export interface CreateJobResponse {
  job_id: string;
  jobs_dir: string;
}

// ---------------------------------------------------------------------------
// Sidecar lifecycle (Tauri invoke)
// ---------------------------------------------------------------------------

/**
 * Start the backend sidecar process via Tauri command.
 *
 * This invokes the Rust `start_sidecar` command which spawns the
 * `binaries/podcast-backend` sidecar with the configured port.
 */
export async function startSidecar(): Promise<SidecarStatus> {
  return invoke<SidecarStatus>("start_sidecar");
}

/**
 * Stop the backend sidecar process via Tauri command.
 *
 * Sends SIGTERM (Unix) or TerminateProcess (Windows) to the sidecar.
 */
export async function stopSidecar(): Promise<SidecarStatus> {
  return invoke<SidecarStatus>("stop_sidecar");
}

/** Query the current sidecar process status without side effects. */
export async function getSidecarStatus(): Promise<SidecarStatus> {
  return invoke<SidecarStatus>("sidecar_status");
}

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------

/**
 * Probe the backend health endpoint.
 *
 * Returns the health response on success, or null if the backend is
 * unreachable or returns a non-OK status.
 */
export async function checkHealth(): Promise<HealthResponse | null> {
  try {
    const res = await fetch(`${BASE_URL}/health`);
    if (!res.ok) return null;
    const data: HealthResponse = await res.json();
    return data.status === "ok" ? data : null;
  } catch {
    return null;
  }
}

/**
 * Wait for the backend to become healthy after sidecar startup.
 *
 * Polls the health endpoint at short intervals until it responds with
 * status "ok" or the timeout expires. Returns the health response on
 * success, or null on timeout.
 */
export async function waitForReady(): Promise<HealthResponse | null> {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;

  while (Date.now() < deadline) {
    const health = await checkHealth();
    if (health !== null) return health;
    await sleep(STARTUP_PROBE_INTERVAL_MS);
  }

  return null;
}

// ---------------------------------------------------------------------------
// Job API
// ---------------------------------------------------------------------------

/** Fetch the list of all jobs from the backend. */
export async function listJobs(): Promise<JobSummary[]> {
  const res = await fetch(`${BASE_URL}/jobs`);
  if (!res.ok) {
    throw new Error(`Failed to list jobs: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/** Create a new job on the backend. */
export async function createJob(
  input_path: string,
): Promise<CreateJobResponse> {
  const body: CreateJobRequest = { input_path };
  const res = await fetch(`${BASE_URL}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Failed to create job: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/** Trigger a job run on the backend. */
export async function runJob(jobId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/run`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`Failed to run job: ${res.status} ${res.statusText}`);
  }
}

/** Get the status of a single job. */
export async function getJob(jobId: string): Promise<JobSummary> {
  const res = await fetch(
    `${BASE_URL}/jobs/${encodeURIComponent(jobId)}`,
  );
  if (!res.ok) {
    throw new Error(`Failed to get job: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Orchestration helper
// ---------------------------------------------------------------------------

/**
 * Full startup sequence: start sidecar, wait for health, return status.
 *
 * This is the primary entry point for the App component on mount.
 * It attempts to start the sidecar process and waits for the backend
 * to become healthy before returning.
 *
 * @returns Object with sidecar status and health response. If health
 *          is null, the backend did not become ready within the timeout.
 */
export async function bootBackend(): Promise<{
  sidecar: SidecarStatus;
  health: HealthResponse | null;
}> {
  const sidecar = await startSidecar();
  const health = await waitForReady();
  return { sidecar, health };
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
