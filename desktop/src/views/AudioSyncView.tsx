/**
 * Audio Sync Editor view for the Podcast Pipeline desktop app.
 *
 * Displays a waveform visualization for the selected job's primary audio
 * using wavesurfer.js v7, with sync offset controls for correcting timing
 * mismatches between audio and video tracks.
 *
 * Key technical notes:
 * - WaveSurfer instance is held in a ref (NOT state) to avoid re-render loops
 * - Audio file paths MUST be converted via convertFileSrc before loading —
 *   Tauri's security model rejects raw file:// and absolute paths
 * - Cleanup via ws.destroy() is mandatory to prevent memory leaks
 */

import { useRef, useState, useEffect, useCallback } from "react";
import WaveSurfer from "wavesurfer.js";
import { convertFileSrc } from "@tauri-apps/api/core";
import { useUIStore } from "../stores/uiStore";
import { useSidecarStore } from "../stores/sidecarStore";
import { useJobDetail } from "../hooks/useJobDetail";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatMs(ms: number): string {
  const sign = ms >= 0 ? "+" : "-";
  const abs = Math.abs(ms);
  if (abs >= 1000) {
    return `${sign}${(abs / 1000).toFixed(2)}s`;
  }
  return `${sign}${abs}ms`;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

/**
 * Attempt to extract the primary audio file path from job stage outputs.
 * The ingest stage places audio files in its outputs array.
 */
function extractAudioPath(outputs: string[]): string | null {
  const audioExtensions = [".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"];
  return (
    outputs.find((o) =>
      audioExtensions.some((ext) => o.toLowerCase().endsWith(ext)),
    ) ?? null
  );
}

/**
 * Attempt to extract auto-detected sync offset from job outputs.
 * Returns null if no sync artifact is found.
 */
function extractAutoOffset(outputs: string[]): number | null {
  // Look for sync_artifact.json or offset markers in output file names
  const syncFile = outputs.find(
    (o) => o.includes("sync") && o.endsWith(".json"),
  );
  // Without actually reading the file here, we just note it exists.
  // The real implementation would parse the file via backend API.
  // For now return null (the sync JSON reading would require an extra fetch).
  if (syncFile) {
    return null; // Would be populated from sync_artifact.json contents
  }
  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AudioSyncView() {
  const selectedJobId = useUIStore((s) => s.selectedJobId);
  const { data: job, isLoading, isError } = useJobDetail(selectedJobId);

  const { status: backendStatus } = useSidecarStore();
  const backendConnected = backendStatus === "connected";

  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  // Local preview state — tracks whether the current offsetMs has been "applied"
  // locally. Not persisted; real persistence requires a backend mutation (TODO below).
  const [previewApplied, setPreviewApplied] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [zoom, setZoom] = useState(50);
  const [waveError, setWaveError] = useState<string | null>(null);

  // Derive audio file path from job detail
  const ingestOutputs = job?.stages?.["ingest"]?.outputs ?? [];
  const audioFilePath = extractAudioPath(ingestOutputs);
  const ingestStatus = job?.stages?.["ingest"]?.status ?? null;

  // Auto-detected sync offset from all stage outputs
  const allOutputs = Object.values(job?.stages ?? {}).flatMap(
    (stage) => stage.outputs,
  );
  const autoOffset = extractAutoOffset(allOutputs);

  // Manual offset state (initialized from auto-detected value when available)
  const [offsetMs, setOffsetMs] = useState<number>(autoOffset ?? 0);

  // Sync local offset state whenever the auto-detected value changes or a new job is selected.
  // Reset to 0 when no auto-offset is available so manual offsets do not carry across jobs.
  useEffect(() => {
    setOffsetMs(autoOffset ?? 0);
  }, [autoOffset, selectedJobId]);

  // Wavesurfer instance lifecycle.
  // Early-return until ingest completes — the container may not yet be mounted
  // in the DOM when this effect first runs for a job still being ingested.
  useEffect(() => {
    if (ingestStatus !== "complete") return;
    if (!containerRef.current || !audioFilePath) return;

    setWaveError(null);

    // CRITICAL: Convert file path to Tauri-safe URL before loading
    let audioUrl: string;
    try {
      audioUrl = convertFileSrc(audioFilePath);
    } catch {
      setWaveError(`Failed to convert file path: ${audioFilePath}`);
      return;
    }

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: "var(--color-text-secondary)",
      progressColor: "var(--color-accent)",
      cursorColor: "var(--color-accent-hover)",
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      height: 128,
      normalize: true,
      backend: "WebAudio",
    });

    ws.on("ready", (dur: number) => {
      setDuration(dur);
      setCurrentTime(0);
      setIsPlaying(false);
    });

    ws.on("audioprocess", (time: number) => {
      setCurrentTime(time);
    });

    ws.on("play", () => setIsPlaying(true));
    ws.on("pause", () => setIsPlaying(false));
    ws.on("finish", () => {
      setIsPlaying(false);
      setCurrentTime(0);
    });

    ws.on("error", (err: Error) => {
      setWaveError(`Waveform failed to load: ${err.message}`);
    });

    ws.load(audioUrl);
    wsRef.current = ws;

    return () => {
      ws.destroy();
      wsRef.current = null;
      setIsPlaying(false);
      setCurrentTime(0);
      setDuration(0);
    };
  }, [audioFilePath, ingestStatus]);

  // Apply zoom changes to wavesurfer instance
  useEffect(() => {
    if (wsRef.current) {
      wsRef.current.zoom(zoom);
    }
  }, [zoom]);

  const handlePlayPause = useCallback(() => {
    wsRef.current?.playPause();
  }, []);

  const handleResetOffset = useCallback(() => {
    setOffsetMs(autoOffset ?? 0);
  }, [autoOffset]);

  // ---------------------------------------------------------------------------
  // Render: No job selected
  // ---------------------------------------------------------------------------

  if (!selectedJobId) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="text-center space-y-3">
          <div className="text-4xl opacity-30">~</div>
          <p className="text-(--color-text-secondary) text-lg">
            Select a job from the Ingestion view
          </p>
          <p className="text-(--color-text-secondary) text-sm opacity-60">
            Audio waveform and sync controls appear here
          </p>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Loading
  // ---------------------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <p className="text-(--color-text-secondary) animate-pulse">
          Loading job details...
        </p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Error
  // ---------------------------------------------------------------------------

  if (isError || !job) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <p className="text-(--color-error)">
          Failed to load job details for {selectedJobId}
        </p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Job loaded but ingest not complete
  // ---------------------------------------------------------------------------

  const ingestDone = ingestStatus === "complete";

  return (
    <div className="space-y-5 max-w-5xl">
      {/* Header */}
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-xl font-semibold text-(--color-text-primary)">
            Audio Sync Editor
          </h2>
          <p className="text-sm text-(--color-text-secondary) mt-0.5">
            Job:{" "}
            <span className="font-mono text-xs text-(--color-accent)">
              {selectedJobId}
            </span>
          </p>
        </div>
        <div className="text-sm text-(--color-text-secondary)">
          Ingest:{" "}
          <span
            className={
              ingestDone
                ? "text-(--color-success)"
                : "text-(--color-warning)"
            }
          >
            {ingestStatus ?? "pending"}
          </span>
        </div>
      </div>

      {/* Waveform Display Area */}
      <div className="bg-(--color-bg-card) rounded-lg p-4 border border-(--color-border)">
        {!ingestDone ? (
          <div className="flex flex-col items-center justify-center h-32 space-y-2">
            <p className="text-(--color-text-secondary) text-sm">
              Audio available after ingest stage completes
            </p>
            {ingestStatus === "running" && (
              <p className="text-(--color-warning) text-xs animate-pulse">
                Ingest in progress...
              </p>
            )}
          </div>
        ) : waveError ? (
          <div className="flex flex-col items-center justify-center h-32 space-y-2">
            <p className="text-(--color-error) text-sm">{waveError}</p>
            {audioFilePath && (
              <p className="text-(--color-text-secondary) text-xs font-mono break-all">
                {audioFilePath}
              </p>
            )}
          </div>
        ) : !audioFilePath ? (
          <div className="flex flex-col items-center justify-center h-32 space-y-2">
            <p className="text-(--color-text-secondary) text-sm">
              No audio file found in ingest outputs
            </p>
            <p className="text-(--color-text-secondary) text-xs opacity-60">
              Audio waveform preview will appear here when available
            </p>
          </div>
        ) : (
          <div
            ref={containerRef}
            className="w-full"
            aria-label="Audio waveform"
          />
        )}
      </div>

      {/* Playback Controls (only when audio is available) */}
      {ingestDone && audioFilePath && !waveError && (
        <div className="bg-(--color-bg-card) rounded-lg px-4 py-3 border border-(--color-border) flex items-center gap-4">
          <button
            onClick={handlePlayPause}
            className="px-4 py-1.5 rounded-md bg-(--color-accent) hover:bg-(--color-accent-hover) text-white text-sm font-medium transition-colors"
          >
            {isPlaying ? "Pause" : "Play"}
          </button>
          <span className="text-sm text-(--color-text-secondary) font-mono tabular-nums">
            {formatDuration(currentTime)} / {formatDuration(duration)}
          </span>
          <div className="flex items-center gap-2 ml-auto">
            <label className="text-xs text-(--color-text-secondary)">
              Zoom
            </label>
            <input
              type="range"
              min={1}
              max={200}
              step={1}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
              className="w-24 accent-(--color-accent)"
              aria-label="Waveform zoom"
            />
            <span className="text-xs text-(--color-text-secondary) w-8 tabular-nums">
              {zoom}x
            </span>
          </div>
        </div>
      )}

      {/* Sync Controls */}
      <div className="bg-(--color-bg-card) rounded-lg p-4 border border-(--color-border) space-y-4">
        <h3 className="text-sm font-semibold text-(--color-text-primary)">
          Audio Sync Offset
        </h3>

        {autoOffset !== null && (
          <div className="text-sm text-(--color-text-secondary) bg-(--color-bg-secondary) rounded px-3 py-2">
            Auto-detected offset:{" "}
            <span className="font-mono text-(--color-accent)">
              {formatMs(autoOffset)}
            </span>
          </div>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm text-(--color-text-secondary)">
              Manual offset
            </label>
            <span className="text-sm font-mono font-semibold text-(--color-text-primary) tabular-nums">
              {formatMs(offsetMs)}
            </span>
          </div>
          <input
            type="range"
            min={-5000}
            max={5000}
            step={1}
            value={offsetMs}
            onChange={(e) => { setOffsetMs(Number(e.target.value)); setPreviewApplied(false); }}
            className="w-full accent-(--color-accent)"
            aria-label="Sync offset slider"
          />
          <div className="flex justify-between text-xs text-(--color-text-secondary) opacity-60">
            <span>-5000ms</span>
            <span>0ms</span>
            <span>+5000ms</span>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex gap-3">
            {/*
              TODO: wire real persist mutation once the backend endpoint is available:
                useOffsetMutation().mutate({ jobId: selectedJobId, offsetMs })
              Until then, "Apply" stores the preview locally only — no backend call is made.
            */}
            <button
              onClick={() => setPreviewApplied(true)}
              disabled={!backendConnected}
              className="px-4 py-1.5 rounded-md border border-(--color-border) text-(--color-text-secondary) hover:text-(--color-text-primary) text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Apply Offset
            </button>
            <button
              onClick={handleResetOffset}
              className="px-4 py-1.5 rounded-md border border-(--color-border) text-(--color-text-secondary) hover:text-(--color-text-primary) text-sm transition-colors"
            >
              Reset
            </button>
          </div>
          {previewApplied && (
            <p className="text-xs text-(--color-warning)">
              Preview only — offset is not persisted. Backend sync mutation will be
              wired in a future update.
            </p>
          )}
        </div>
      </div>

      {/* Track Info Panel */}
      <div className="bg-(--color-bg-card) rounded-lg p-4 border border-(--color-border)">
        <h3 className="text-sm font-semibold text-(--color-text-primary) mb-3">
          Track Info
        </h3>
        <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
          <div>
            <span className="text-(--color-text-secondary)">
              Input file
            </span>
            <p className="font-mono text-xs text-(--color-text-primary) break-all mt-0.5">
              {job.input_file}
            </p>
          </div>
          <div>
            <span className="text-(--color-text-secondary)">
              Job status
            </span>
            <p className="text-(--color-text-primary) mt-0.5">
              {job.status}
            </p>
          </div>
          {duration > 0 && (
            <div>
              <span className="text-(--color-text-secondary)">
                Duration
              </span>
              <p className="text-(--color-text-primary) mt-0.5">
                {formatDuration(duration)}
              </p>
            </div>
          )}
          {audioFilePath && (
            <div>
              <span className="text-(--color-text-secondary)">
                Audio file
              </span>
              <p className="font-mono text-xs text-(--color-text-primary) break-all mt-0.5">
                {audioFilePath}
              </p>
            </div>
          )}
          <div>
            <span className="text-(--color-text-secondary)">
              Ingest outputs
            </span>
            <p className="text-(--color-text-primary) mt-0.5">
              {ingestOutputs.length} file{ingestOutputs.length !== 1 ? "s" : ""}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
