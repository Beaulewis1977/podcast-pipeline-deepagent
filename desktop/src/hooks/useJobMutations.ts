/**
 * TanStack Query mutation hooks for job lifecycle operations.
 *
 * Each hook wraps a single backend operation and invalidates the
 * ['jobs'] query cache on success so the job list stays current
 * without manual refresh calls.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  createJob,
  runJob,
  resumeJob,
  deleteJob,
  type CreateJobResponse,
  type LifecycleActionResponse,
  type RunJobOptions,
  type ResumeJobOptions,
} from "../lib/backend";

// ---------------------------------------------------------------------------
// useCreateJob
// ---------------------------------------------------------------------------

export interface CreateJobVariables {
  videoPath: string;
  name?: string;
}

/**
 * Mutation hook to create a new job from a video file path.
 *
 * Invalidates the jobs list on success so the new job appears immediately.
 */
export function useCreateJob() {
  const queryClient = useQueryClient();
  return useMutation<CreateJobResponse, Error, CreateJobVariables>({
    mutationFn: ({ videoPath, name }: CreateJobVariables) =>
      createJob(videoPath, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

// ---------------------------------------------------------------------------
// useRunJob
// ---------------------------------------------------------------------------

export interface RunJobVariables {
  jobId: string;
  options?: RunJobOptions;
}

/**
 * Mutation hook to trigger a full pipeline run for a job.
 *
 * Always runs in background mode so the UI stays responsive.
 * Invalidates the jobs list on success.
 */
export function useRunJob() {
  const queryClient = useQueryClient();
  return useMutation<LifecycleActionResponse, Error, RunJobVariables>({
    mutationFn: ({ jobId, options }: RunJobVariables) =>
      runJob(jobId, { background: true, ...options }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

// ---------------------------------------------------------------------------
// useResumeJob
// ---------------------------------------------------------------------------

export interface ResumeJobVariables {
  jobId: string;
  options?: ResumeJobOptions;
}

/**
 * Mutation hook to resume a job from the first incomplete stage or
 * a specific requested stage.
 *
 * Always runs in background mode. Invalidates the jobs list on success.
 */
export function useResumeJob() {
  const queryClient = useQueryClient();
  return useMutation<LifecycleActionResponse, Error, ResumeJobVariables>({
    mutationFn: ({ jobId, options }: ResumeJobVariables) =>
      resumeJob(jobId, { background: true, ...options }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

// ---------------------------------------------------------------------------
// useDeleteJob
// ---------------------------------------------------------------------------

/**
 * Mutation hook to delete a job and all its generated artifacts.
 *
 * Invalidates both the jobs list and the specific job detail query on success.
 */
export function useDeleteJob() {
  const queryClient = useQueryClient();
  return useMutation<{ job_id: string; deleted: boolean; message: string }, Error, string>({
    mutationFn: (jobId: string) => deleteJob(jobId),
    onSuccess: (_data, jobId) => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.removeQueries({ queryKey: ["jobs", jobId] });
    },
  });
}
