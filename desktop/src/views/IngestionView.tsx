/**
 * Ingestion Dashboard view — the primary job management interface.
 *
 * Features:
 * - System readiness banner (FFmpeg, whisper model, binary status)
 * - Native drag-and-drop via Tauri webview API (OS file paths, not browser File objects)
 * - Manual path input fallback for non-Tauri dev environments
 * - Job list with pipeline stage progress bars and status badges
 * - Per-job action buttons: Run Full, Resume, Delete
 * - Selected job detail panel with per-stage breakdown
 */

import { useState, useEffect, useCallback } from "react";
import { useJobs } from "../hooks/useJobs";
import { useJobDetail } from "../hooks/useJobDetail";
import { useSystemStatus } from "../hooks/useSystemStatus";
import {
  useCreateJob,
  useRunJob,
  useResumeJob,
  useDeleteJob,
} from "../hooks/useJobMutations";
import { useUIStore } from "../stores/uiStore";
import { STAGE_ORDER, type JobSummary } from "../lib/backend";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) {
    return iso;
  }
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) {
    return `${diffSec}s ago`;
  }
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) {
    return `${diffMin} min ago`;
  }
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) {
    return `${diffHr}h ago`;
  }
  return new Date(iso).toLocaleDateString();
}

type JobStatus = "running" | "complete" | "failed" | "pending" | string;

function statusVariant(
  status: JobStatus,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "complete") return "default";
  if (status === "failed") return "destructive";
  if (status === "running") return "secondary";
  return "outline";
}

function statusLabel(status: JobStatus): string {
  if (status === "complete") return "complete";
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  if (status === "pending") return "pending";
  return status;
}

type StageStatus = "complete" | "running" | "failed" | "pending" | string;

function stageColor(stageStatus: StageStatus): string {
  if (stageStatus === "complete") return "bg-(--color-success)";
  if (stageStatus === "running") return "bg-(--color-warning) animate-pulse";
  if (stageStatus === "failed") return "bg-(--color-error)";
  return "bg-(--color-border)";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SystemReadinessBanner() {
  const { data, isLoading } = useSystemStatus();

  if (isLoading || !data) {
    return null;
  }

  if (data.ready) {
    return (
      <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-(--color-success)/10 border border-(--color-success)/30 text-sm">
        <span className="w-2 h-2 rounded-full bg-(--color-success) shrink-0" />
        <span className="text-(--color-success) font-medium">All systems ready</span>
        <span className="text-(--color-text-secondary) ml-2">
          {Object.entries(data.binaries)
            .map(([name]) => name)
            .join(", ")}
        </span>
      </div>
    );
  }

  return (
    <div className="px-4 py-3 rounded-lg bg-(--color-warning)/10 border border-(--color-warning)/30">
      <div className="flex items-center gap-2 mb-2">
        <span className="w-2 h-2 rounded-full bg-(--color-warning) shrink-0 animate-pulse" />
        <span className="text-(--color-warning) font-medium text-sm">
          System not ready
        </span>
      </div>
      <div className="grid gap-1 ml-4">
        {Object.entries(data.binaries).map(([name, info]) => (
          <div key={name} className="flex items-center gap-2 text-xs">
            <span
              className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                info.status === "ok"
                  ? "bg-(--color-success)"
                  : "bg-(--color-error)"
              }`}
            />
            <span className="text-(--color-text-secondary)">
              {name}
              {info.path && (
                <span className="text-(--color-text-secondary)/60 ml-1">
                  ({info.path})
                </span>
              )}
            </span>
          </div>
        ))}
        <div className="flex items-center gap-2 text-xs mt-1">
          <span
            className={`w-1.5 h-1.5 rounded-full shrink-0 ${
              data.model.status === "ready"
                ? "bg-(--color-success)"
                : "bg-(--color-warning)"
            }`}
          />
          <span className="text-(--color-text-secondary)">
            whisper model: {data.model.name} ({data.model.status})
          </span>
        </div>
      </div>
      {data.issues.length > 0 && (
        <ul className="mt-2 ml-4 text-xs text-(--color-warning) space-y-0.5">
          {data.issues.map((issue) => (
            <li key={issue}>• {issue}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pipeline stage bar
// ---------------------------------------------------------------------------

function PipelineStageBar({ stages }: { stages: Record<string, string> }) {
  return (
    <div className="flex gap-1 mt-2">
      {STAGE_ORDER.map((stageName) => {
        const stageStatus = stages[stageName] ?? "pending";
        return (
          <div
            key={stageName}
            className="flex-1 flex flex-col gap-0.5"
            title={`${stageName}: ${stageStatus}`}
          >
            <div
              className={`h-1.5 rounded-full ${stageColor(stageStatus)}`}
            />
            <span className="text-[9px] text-(--color-text-secondary) text-center truncate">
              {stageName.slice(0, 5)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Job card
// ---------------------------------------------------------------------------

interface JobCardProps {
  job: JobSummary;
  isSelected: boolean;
  onSelect: (jobId: string) => void;
}

function JobCard({ job, isSelected, onSelect }: JobCardProps) {
  const runJob = useRunJob();
  const resumeJob = useResumeJob();
  const deleteJob = useDeleteJob();

  const handleRun = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      runJob.mutate({ jobId: job.job_id });
    },
    [runJob, job.job_id],
  );

  const handleResume = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      resumeJob.mutate({ jobId: job.job_id });
    },
    [resumeJob, job.job_id],
  );

  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const confirmed = window.confirm(
        `Delete job ${job.job_id} and all generated files?`,
      );
      if (confirmed) {
        deleteJob.mutate(job.job_id);
      }
    },
    [deleteJob, job.job_id],
  );

  const isRunning =
    runJob.isPending ||
    resumeJob.isPending ||
    deleteJob.isPending;

  return (
    <div
      onClick={() => onSelect(job.job_id)}
      className={`
        bg-(--color-bg-card) rounded-lg p-4 border border-(--color-border)
        cursor-pointer transition-all duration-150 hover:border-(--color-accent)/50
        ${isSelected ? "ring-2 ring-(--color-accent)" : ""}
      `}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="font-mono text-xs text-(--color-accent) truncate">
          {job.job_id}
        </span>
        <Badge variant={statusVariant(job.status)} className="shrink-0 text-xs">
          {statusLabel(job.status)}
        </Badge>
      </div>

      <div className="text-xs text-(--color-text-secondary) mb-2">
        {relativeTime(job.created)}
      </div>

      <PipelineStageBar stages={job.stages} />

      <div
        className="flex flex-wrap gap-1.5 mt-3"
        onClick={(e) => e.stopPropagation()}
      >
        <Button
          size="sm"
          variant="default"
          onClick={handleRun}
          disabled={isRunning || job.status === "running"}
          className="text-xs h-7"
        >
          {runJob.isPending ? "Starting..." : "Run Full"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={handleResume}
          disabled={isRunning || job.status === "pending"}
          className="text-xs h-7"
        >
          {resumeJob.isPending ? "Resuming..." : "Resume"}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={handleDelete}
          disabled={isRunning}
          className="text-xs h-7"
        >
          {deleteJob.isPending ? "Deleting..." : "Delete"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Selected job detail panel
// ---------------------------------------------------------------------------

function JobDetailPanel({ jobId }: { jobId: string }) {
  const { data, isLoading } = useJobDetail(jobId);
  const setSelectedJob = useUIStore((s) => s.setSelectedJob);

  if (isLoading || !data) {
    return (
      <div className="bg-(--color-bg-card) rounded-lg p-4 border border-(--color-border)">
        <div className="animate-pulse space-y-2">
          <div className="h-4 bg-(--color-border) rounded w-1/3" />
          <div className="h-3 bg-(--color-border) rounded w-2/3" />
          <div className="h-3 bg-(--color-border) rounded w-1/2" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-(--color-bg-card) rounded-lg p-4 border border-(--color-border) space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-(--color-text-primary)">
          Job Detail
        </h3>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setSelectedJob(null)}
          className="text-xs h-6 px-2"
        >
          Close
        </Button>
      </div>

      <div className="space-y-1.5 text-xs">
        <div className="flex gap-2">
          <span className="text-(--color-text-secondary) w-20 shrink-0">Job ID</span>
          <span className="font-mono text-(--color-accent) truncate">{data.job_id}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-(--color-text-secondary) w-20 shrink-0">Input file</span>
          <span className="truncate text-(--color-text-primary)">{data.input_file}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-(--color-text-secondary) w-20 shrink-0">Status</span>
          <Badge variant={statusVariant(data.status)} className="text-[10px] h-4">
            {data.status}
          </Badge>
        </div>
        <div className="flex gap-2">
          <span className="text-(--color-text-secondary) w-20 shrink-0">Created</span>
          <span className="text-(--color-text-primary)">{relativeTime(data.created_at)}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-(--color-text-secondary) w-20 shrink-0">Updated</span>
          <span className="text-(--color-text-primary)">{relativeTime(data.updated_at)}</span>
        </div>
      </div>

      <div className="border-t border-(--color-border) pt-2 space-y-1.5">
        <p className="text-xs text-(--color-text-secondary) font-medium mb-1">
          Stages
        </p>
        {STAGE_ORDER.map((stageName) => {
          const stage = data.stages[stageName];
          const st = stage?.status ?? "pending";
          return (
            <div key={stageName} className="flex items-start gap-2 text-xs">
              <span
                className={`w-1.5 h-1.5 rounded-full mt-0.5 shrink-0 ${stageColor(st)}`}
              />
              <span className="text-(--color-text-secondary) w-20 shrink-0">
                {stageName}
              </span>
              <div className="flex-1 min-w-0">
                <span className="text-(--color-text-primary)">{st}</span>
                {stage?.progress_percent != null && (
                  <span className="text-(--color-text-secondary) ml-1">
                    ({stage.progress_percent}%)
                  </span>
                )}
                {stage?.progress_message && (
                  <span className="text-(--color-text-secondary) ml-1 truncate block">
                    {stage.progress_message}
                  </span>
                )}
                {stage?.error && (
                  <span className="text-(--color-error) block truncate">
                    {stage.error}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// IngestionView
// ---------------------------------------------------------------------------

export function IngestionView() {
  const { data: jobs, isLoading, isError } = useJobs();
  const { selectedJobId, setSelectedJob } = useUIStore();
  const createJobMutation = useCreateJob();

  const [dragOver, setDragOver] = useState(false);
  const [showManualInput, setShowManualInput] = useState(false);
  const [manualPath, setManualPath] = useState("");
  const [manualName, setManualName] = useState("");

  // Native Tauri drag-drop via dynamic import (graceful fallback for dev browser).
  //
  // createJobMutation is intentionally omitted from the dependency array:
  // TanStack Query's useMutation returns a stable `mutate` reference, so the
  // onDragDropEvent callback never captures a stale closure. Cleanup of the
  // getCurrentWebview / onDragDropEvent listener is handled via the local
  // `unlisten` variable returned from the async setup block.
  useEffect(() => {
    let unlisten: (() => void) | null = null;

    void (async () => {
      try {
        const { getCurrentWebview } = await import("@tauri-apps/api/webview");
        unlisten = await getCurrentWebview().onDragDropEvent((event) => {
          if (event.payload.type === "enter" || event.payload.type === "over") {
            setDragOver(true);
          } else if (event.payload.type === "drop") {
            setDragOver(false);
            for (const path of event.payload.paths) {
              createJobMutation.mutate({ videoPath: path });
            }
          } else if (event.payload.type === "leave") {
            setDragOver(false);
          }
        });
      } catch {
        // Not in Tauri context — show manual input as primary entry point
        setShowManualInput(true);
      }
    })();

    return () => {
      unlisten?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleManualCreate = useCallback(() => {
    const path = manualPath.trim();
    if (!path) return;
    createJobMutation.mutate(
      { videoPath: path, name: manualName.trim() || undefined },
      {
        onSuccess: () => {
          setManualPath("");
          setManualName("");
        },
      },
    );
  }, [createJobMutation, manualName, manualPath]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        handleManualCreate();
      }
    },
    [handleManualCreate],
  );

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* System Readiness */}
      <SystemReadinessBanner />

      {/* Drop Zone */}
      <div
        className={`
          min-h-48 flex flex-col items-center justify-center rounded-xl
          border-2 border-dashed transition-all duration-150 p-6 gap-3
          ${
            dragOver
              ? "border-(--color-accent) bg-(--color-accent)/5"
              : "border-(--color-border) bg-(--color-bg-secondary)/40"
          }
        `}
      >
        <div className="text-center">
          <p className="text-(--color-text-primary) text-sm font-medium">
            Drop video files here to create jobs
          </p>
          <p className="text-(--color-text-secondary) text-xs mt-1">
            Supports .mp4, .mov, .mkv, .webm
          </p>
        </div>

        {createJobMutation.isPending && (
          <div className="flex items-center gap-2 text-xs text-(--color-warning)">
            <span className="animate-spin inline-block w-3 h-3 border border-t-transparent border-(--color-warning) rounded-full" />
            Creating job...
          </div>
        )}

        {createJobMutation.isError && (
          <p className="text-xs text-(--color-error)">
            {createJobMutation.error.message}
          </p>
        )}

        {!showManualInput && (
          <button
            type="button"
            onClick={() => setShowManualInput(true)}
            className="text-xs text-(--color-text-secondary) underline underline-offset-2 hover:text-(--color-accent) transition-colors"
          >
            or enter path manually
          </button>
        )}
      </div>

      {/* Manual input — always visible once shown */}
      {showManualInput && (
        <div className="flex flex-col gap-2 p-3 rounded-lg bg-(--color-bg-secondary)/60 border border-(--color-border)">
          <p className="text-xs text-(--color-text-secondary) font-medium">
            Manual job creation
          </p>
          <input
            type="text"
            value={manualPath}
            onChange={(e) => setManualPath(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="/absolute/path/to/video.mp4"
            className="
              w-full px-3 py-1.5 text-xs rounded-md
              bg-(--color-bg-card) border border-(--color-border)
              text-(--color-text-primary) placeholder:text-(--color-text-secondary)/50
              focus:outline-none focus:border-(--color-accent)/60
            "
          />
          <input
            type="text"
            value={manualName}
            onChange={(e) => setManualName(e.target.value)}
            placeholder="Job name (optional)"
            className="
              w-full px-3 py-1.5 text-xs rounded-md
              bg-(--color-bg-card) border border-(--color-border)
              text-(--color-text-primary) placeholder:text-(--color-text-secondary)/50
              focus:outline-none focus:border-(--color-accent)/60
            "
          />
          <Button
            size="sm"
            variant="default"
            onClick={handleManualCreate}
            disabled={!manualPath.trim() || createJobMutation.isPending}
            className="self-start text-xs h-7"
          >
            {createJobMutation.isPending ? "Creating..." : "Create Job"}
          </Button>
        </div>
      )}

      {/* Job list */}
      <div className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wider px-0.5">
          Jobs
          {jobs && jobs.length > 0 && (
            <span className="ml-2 text-(--color-accent)">{jobs.length}</span>
          )}
        </h2>

        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-24 rounded-lg bg-(--color-bg-card) border border-(--color-border) animate-pulse"
              />
            ))}
          </div>
        )}

        {isError && (
          <div className="px-4 py-3 rounded-lg bg-(--color-error)/10 border border-(--color-error)/30 text-xs text-(--color-error)">
            Failed to load jobs. Backend may be unavailable.
          </div>
        )}

        {!isLoading && !isError && jobs?.length === 0 && (
          <div className="py-8 text-center text-xs text-(--color-text-secondary)">
            No jobs yet. Drop a video file above to get started.
          </div>
        )}

        {!isLoading &&
          jobs?.map((job) => (
            <JobCard
              key={job.job_id}
              job={job}
              isSelected={selectedJobId === job.job_id}
              onSelect={setSelectedJob}
            />
          ))}
      </div>

      {/* Selected job detail */}
      {selectedJobId !== null && <JobDetailPanel jobId={selectedJobId} />}
    </div>
  );
}
