/**
 * Desktop recovery status handling and resume actions.
 *
 * After the backend sidecar becomes healthy on app startup, the recovery
 * module queries for interrupted jobs and provides typed helpers for
 * the UI to display and trigger resume actions.
 *
 * Two execution paths:
 * 1. **Tauri context**: Uses invoke commands backed by Rust HTTP calls.
 * 2. **Dev/browser context**: Falls back to direct fetch against the
 *    local backend (same endpoints, no Tauri shell layer).
 */

import { invoke } from "@tauri-apps/api/core";
import { BACKEND_PORT } from "./backend";

const BASE_URL = `http://127.0.0.1:${BACKEND_PORT}`;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A single resumable job returned by the backend. */
export interface ResumableJob {
  job_id: string;
  status: string;
  resume_stage: string;
  completed_stages: string[];
  failed_stages: string[];
  interrupted: boolean;
}

/** Combined recovery status after startup reconciliation. */
export interface RecoveryStatus {
  /** Number of jobs that had stale runtime metadata corrected. */
  corrected: number;
  /** Jobs that can be resumed. */
  resumable_jobs: ResumableJob[];
}

/** Result of a resume action. */
export interface ResumeResult {
  job_id: string;
  status: string;
  message: string;
}

// ---------------------------------------------------------------------------
// Recovery queries
// ---------------------------------------------------------------------------

/**
 * Check for recoverable jobs after sidecar startup.
 *
 * Tries the Tauri invoke path first (Rust -> backend HTTP).
 * Falls back to direct fetch for dev/browser mode.
 */
export async function checkRecovery(): Promise<RecoveryStatus> {
  try {
    return await invoke<RecoveryStatus>("check_recovery");
  } catch {
    // Outside Tauri context -- fall back to direct HTTP
    return checkRecoveryDirect();
  }
}

/**
 * Direct HTTP fallback for recovery check (dev mode).
 *
 * Calls POST /jobs/reconcile then GET /jobs/resumable on the
 * local backend without going through Tauri invoke.
 */
async function checkRecoveryDirect(): Promise<RecoveryStatus> {
  let corrected = 0;
  let resumable_jobs: ResumableJob[] = [];

  try {
    const reconcileRes = await fetch(`${BASE_URL}/jobs/reconcile`, {
      method: "POST",
    });
    if (reconcileRes.ok) {
      const data = await reconcileRes.json();
      corrected = data.corrected ?? 0;
    }
  } catch {
    // Backend not reachable -- return empty recovery status
    return { corrected: 0, resumable_jobs: [] };
  }

  try {
    const resumableRes = await fetch(`${BASE_URL}/jobs/resumable`);
    if (resumableRes.ok) {
      const data = await resumableRes.json();
      resumable_jobs = data.jobs ?? [];
    }
  } catch {
    // Non-critical: resumable list unavailable
  }

  return { corrected, resumable_jobs };
}

// ---------------------------------------------------------------------------
// Resume actions
// ---------------------------------------------------------------------------

/**
 * Resume a specific interrupted job.
 *
 * Tries the Tauri invoke path first, falls back to direct HTTP.
 *
 * @param jobId  - The job identifier to resume.
 * @param fromStage - Optional specific stage to resume from.
 */
export async function triggerResume(
  jobId: string,
  fromStage?: string,
): Promise<ResumeResult> {
  try {
    return await invoke<ResumeResult>("trigger_resume", {
      jobId,
      fromStage: fromStage ?? null,
    });
  } catch {
    // Outside Tauri context -- fall back to direct HTTP
    return triggerResumeDirect(jobId, fromStage);
  }
}

/**
 * Direct HTTP fallback for resume trigger (dev mode).
 */
async function triggerResumeDirect(
  jobId: string,
  fromStage?: string,
): Promise<ResumeResult> {
  const body: Record<string, unknown> = { background: true };
  if (fromStage) {
    body.from_stage = fromStage;
  }

  const res = await fetch(
    `${BASE_URL}/jobs/${encodeURIComponent(jobId)}/resume`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Resume failed (${res.status}): ${text}`);
  }

  return res.json();
}
