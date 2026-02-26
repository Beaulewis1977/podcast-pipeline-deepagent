/**
 * Transcript Timeline view — content review interface for completed jobs.
 *
 * Features:
 * - Reads selectedJobId from uiStore
 * - Shows transcription stage progress when job is still processing
 * - Filler word toggle: show/hide with visual highlighting
 * - Speaker labels as colored badges above paragraphs
 * - Timestamps on the left margin (mm:ss)
 * - Stats footer: duration, word count, speaker count, filler %
 * - Graceful degradation at every state (no job, no transcript, loading)
 */

import {
  useState,
  useMemo,
  useCallback,
  useRef,
  useEffect,
} from "react";
import { useUIStore } from "../stores/uiStore";
import { useJobDetail } from "../hooks/useJobDetail";
import { BACKEND_PORT, STAGE_ORDER } from "../lib/backend";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

// ---------------------------------------------------------------------------
// Transcript data types
// ---------------------------------------------------------------------------

export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
  is_filler?: boolean;
  filler_category?: string;
}

export interface TranscriptSegment {
  text: string;
  start: number;
  end: number;
  speaker?: string;
  words?: TranscriptWord[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Derive a stable per-speaker color class based on speaker label hash. */
function speakerColorClass(speaker: string): string {
  const colors = [
    "text-blue-400",
    "text-purple-400",
    "text-emerald-400",
    "text-orange-400",
    "text-pink-400",
    "text-cyan-400",
  ];
  let hash = 0;
  for (let i = 0; i < speaker.length; i++) {
    hash = (hash * 31 + speaker.charCodeAt(i)) | 0;
  }
  return colors[Math.abs(hash) % colors.length];
}

/** Determine filler categories present in the segment data. */
function collectFillerCategories(segments: TranscriptSegment[]): string[] {
  const cats = new Set<string>();
  for (const seg of segments) {
    for (const word of seg.words ?? []) {
      if (word.is_filler && word.filler_category) {
        cats.add(word.filler_category);
      }
    }
  }
  return Array.from(cats).sort();
}

function isStageComplete(stageStatus: string | undefined): boolean {
  return stageStatus === "complete";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8 text-center">
      <p className="text-sm text-(--color-text-secondary)">{message}</p>
    </div>
  );
}

function TranscriptSegmentRow({
  segment,
  showFillers,
  fillerFilter,
}: {
  segment: TranscriptSegment;
  showFillers: boolean;
  fillerFilter: string;
}) {
  const words = segment.words;

  const renderWords = useMemo(() => {
    if (!words || words.length === 0) {
      return <span>{segment.text}</span>;
    }

    return words.map((word, i) => {
      const isFiller = word.is_filler === true;
      const categoryMatch =
        fillerFilter === "all" ||
        (word.filler_category?.toLowerCase() === fillerFilter.toLowerCase());

      if (isFiller && categoryMatch) {
        if (!showFillers) {
          return (
            <span
              key={i}
              className="opacity-30 line-through"
            >
              {word.word}{" "}
            </span>
          );
        }
        return (
          <span
            key={i}
            className="bg-(--color-warning)/20 text-(--color-warning) rounded px-1 mx-0.5"
          >
            {word.word}
          </span>
        );
      }

      return (
        <span key={i}>
          {word.word}{" "}
        </span>
      );
    });
  }, [words, segment.text, showFillers, fillerFilter]);

  return (
    <div className="flex gap-4 py-2 border-b border-(--color-border)/30">
      {/* Timestamp */}
      <div className="w-12 shrink-0 text-[10px] text-(--color-text-secondary) font-mono pt-0.5">
        {formatTime(segment.start)}
      </div>
      {/* Content */}
      <div className="flex-1 min-w-0">
        {segment.speaker && (
          <div className="mb-1">
            <span
              className={`text-[10px] font-semibold ${speakerColorClass(segment.speaker)}`}
            >
              {segment.speaker}
            </span>
          </div>
        )}
        <p className="text-sm text-(--color-text-primary) leading-relaxed">
          {renderWords}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats footer
// ---------------------------------------------------------------------------

function TranscriptStats({
  segments,
  fillerFilter,
}: {
  segments: TranscriptSegment[];
  fillerFilter: string;
}) {
  const stats = useMemo(() => {
    let totalWords = 0;
    let fillerWords = 0;
    let maxEnd = 0;
    const speakers = new Set<string>();

    for (const seg of segments) {
      if (seg.speaker) speakers.add(seg.speaker);
      if (seg.end > maxEnd) maxEnd = seg.end;

      const words = seg.words;
      if (words && words.length > 0) {
        totalWords += words.length;
        for (const w of words) {
          if (
            w.is_filler &&
            (fillerFilter === "all" ||
              w.filler_category?.toLowerCase() === fillerFilter.toLowerCase())
          ) {
            fillerWords++;
          }
        }
      } else {
        // Estimate word count from text
        totalWords += seg.text.split(/\s+/).filter(Boolean).length;
      }
    }

    const fillerPct =
      totalWords > 0 ? ((fillerWords / totalWords) * 100).toFixed(1) : "0.0";

    return {
      duration: formatTime(maxEnd),
      wordCount: totalWords,
      speakerCount: speakers.size,
      fillerCount: fillerWords,
      fillerPct,
    };
  }, [segments, fillerFilter]);

  return (
    <div className="flex flex-wrap gap-4 px-4 py-2 border-t border-(--color-border) text-xs text-(--color-text-secondary)">
      <span>Duration: {stats.duration}</span>
      <span>Words: {stats.wordCount.toLocaleString()}</span>
      {stats.speakerCount > 0 && (
        <span>Speakers: {stats.speakerCount}</span>
      )}
      <span>
        Fillers: {stats.fillerCount} ({stats.fillerPct}%)
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TranscriptView
// ---------------------------------------------------------------------------

export function TranscriptView() {
  const selectedJobId = useUIStore((s) => s.selectedJobId);
  const { data: jobDetail, isLoading } = useJobDetail(selectedJobId);

  const [showFillers, setShowFillers] = useState(true);
  const [fillerFilter, setFillerFilter] = useState("all");
  const [transcriptData, setTranscriptData] = useState<
    TranscriptSegment[] | null
  >(null);
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Attempt to load transcript from the backend job outputs endpoint.
  // Falls back gracefully if the endpoint is unavailable.
  useEffect(() => {
    if (!selectedJobId || !jobDetail) {
      setTranscriptData(null);
      return;
    }

    const transcribeStage = jobDetail.stages["transcribe"];
    if (!isStageComplete(transcribeStage?.status)) {
      setTranscriptData(null);
      return;
    }

    // Check if transcript.json is listed in the stage outputs
    const outputs = transcribeStage?.outputs ?? [];
    const hasTranscriptOutput = outputs.some(
      (o) => o.endsWith("transcript.json") || o.includes("transcript"),
    );

    if (!hasTranscriptOutput) {
      return;
    }

    setLoadingTranscript(true);
    void (async () => {
      try {
        const resp = await fetch(
          `http://127.0.0.1:${BACKEND_PORT}/jobs/${encodeURIComponent(selectedJobId)}/outputs/transcribe/transcript.json`,
        );
        if (resp.ok) {
          const raw = (await resp.json()) as
            | TranscriptSegment[]
            | { segments: TranscriptSegment[] };

          if (Array.isArray(raw)) {
            setTranscriptData(raw);
          } else if (raw && "segments" in raw && Array.isArray(raw.segments)) {
            setTranscriptData(raw.segments);
          }
        }
      } catch {
        // Endpoint unavailable — transcript view shows stage outputs list
      } finally {
        setLoadingTranscript(false);
      }
    })();
  }, [selectedJobId, jobDetail]);

  // Filler categories extracted from loaded transcript
  const fillerCategories = useMemo(
    () => (transcriptData ? collectFillerCategories(transcriptData) : []),
    [transcriptData],
  );

  // Total filler count for display badge
  const fillerCount = useMemo(() => {
    if (!transcriptData) return 0;
    let count = 0;
    for (const seg of transcriptData) {
      for (const w of seg.words ?? []) {
        if (w.is_filler) count++;
      }
    }
    return count;
  }, [transcriptData]);

  const handleToggleFillers = useCallback(() => {
    setShowFillers((prev) => !prev);
  }, []);

  // --------------------------------------------------------------------------
  // Render: no job selected
  // --------------------------------------------------------------------------

  if (!selectedJobId) {
    return (
      <div className="flex h-full flex-col">
        <EmptyState message="Select a job from the Ingestion view to view its transcript." />
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // Render: loading job detail
  // --------------------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="flex h-full flex-col p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-(--color-border) rounded w-1/2" />
          <div className="h-3 bg-(--color-border) rounded w-1/3" />
        </div>
      </div>
    );
  }

  if (!jobDetail) {
    return (
      <div className="flex h-full flex-col">
        <EmptyState message="Job not found." />
      </div>
    );
  }

  const transcribeStage = jobDetail.stages["transcribe"];
  const analyzeStage = jobDetail.stages["analyze"];

  // --------------------------------------------------------------------------
  // Render: transcription in progress
  // --------------------------------------------------------------------------

  if (!isStageComplete(transcribeStage?.status)) {
    const progress = transcribeStage?.progress_percent ?? null;
    const stageStatus = transcribeStage?.status ?? "pending";

    return (
      <div className="flex h-full flex-col p-4 gap-4">
        <div>
          <h2 className="text-sm font-semibold text-(--color-text-primary) mb-1">
            Transcript
          </h2>
          <p className="text-xs text-(--color-text-secondary)">
            Job: <span className="font-mono text-(--color-accent)">{selectedJobId}</span>
          </p>
        </div>

        <div className="px-4 py-3 rounded-lg bg-(--color-warning)/10 border border-(--color-warning)/30 space-y-2">
          <div className="flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-full bg-(--color-warning) animate-pulse shrink-0" />
            <span className="text-(--color-warning) font-medium">
              Transcription{" "}
              {stageStatus === "running" ? "in progress" : `(${stageStatus})`}
            </span>
          </div>
          {progress !== null && (
            <Progress value={progress} className="h-1.5" />
          )}
          {transcribeStage?.progress_message && (
            <p className="text-xs text-(--color-text-secondary)">
              {transcribeStage.progress_message}
            </p>
          )}
        </div>

        {/* Show all stage statuses for context */}
        <div className="space-y-1">
          {STAGE_ORDER.map((stageName) => {
            const st = jobDetail.stages[stageName]?.status ?? "pending";
            return (
              <div key={stageName} className="flex items-center gap-2 text-xs">
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    st === "complete"
                      ? "bg-(--color-success)"
                      : st === "running"
                        ? "bg-(--color-warning) animate-pulse"
                        : st === "failed"
                          ? "bg-(--color-error)"
                          : "bg-(--color-border)"
                  }`}
                />
                <span className="text-(--color-text-secondary) w-20">{stageName}</span>
                <span className="text-(--color-text-primary)">{st}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // Render: transcription complete, no transcript data loaded yet
  // --------------------------------------------------------------------------

  if (loadingTranscript) {
    return (
      <div className="flex h-full flex-col p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-(--color-border) rounded w-2/3" />
          <div className="h-3 bg-(--color-border) rounded w-full" />
          <div className="h-3 bg-(--color-border) rounded w-4/5" />
        </div>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // Render: fallback — show stage outputs list when transcript isn't loadable
  // --------------------------------------------------------------------------

  if (!transcriptData) {
    const outputs = transcribeStage?.outputs ?? [];

    return (
      <div className="flex h-full flex-col p-4 gap-4">
        <div>
          <h2 className="text-sm font-semibold text-(--color-text-primary) mb-1">
            Transcript
          </h2>
          <div className="flex items-center gap-2">
            <p className="text-xs text-(--color-text-secondary)">
              Job:{" "}
              <span className="font-mono text-(--color-accent)">
                {selectedJobId}
              </span>
            </p>
            <Badge variant="default" className="text-[10px] h-4">
              transcribed
            </Badge>
            {isStageComplete(analyzeStage?.status) && (
              <Badge variant="secondary" className="text-[10px] h-4">
                analyzed
              </Badge>
            )}
          </div>
        </div>

        <div className="px-4 py-3 rounded-lg bg-(--color-bg-secondary)/60 border border-(--color-border) space-y-2">
          <p className="text-xs text-(--color-text-secondary) font-medium">
            Transcript outputs
          </p>
          {outputs.length === 0 ? (
            <p className="text-xs text-(--color-text-secondary)">
              No output files listed for transcribe stage.
            </p>
          ) : (
            <ul className="space-y-0.5">
              {outputs.map((output) => (
                <li
                  key={output}
                  className="text-xs font-mono text-(--color-text-primary) truncate"
                >
                  {output}
                </li>
              ))}
            </ul>
          )}
        </div>

        <p className="text-xs text-(--color-text-secondary)">
          Transcript content is available in the output files listed above.
          Live preview will be available when the backend exposes a transcript
          serve endpoint.
        </p>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // Render: full transcript view
  // --------------------------------------------------------------------------

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-4 pb-2 shrink-0 space-y-1">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-(--color-text-primary)">
            Transcript
          </h2>
          <p className="text-xs text-(--color-text-secondary) font-mono">
            {selectedJobId}
          </p>
        </div>
      </div>

      {/* Filler control bar */}
      <div className="px-4 py-2 shrink-0 flex flex-wrap items-center gap-3 border-b border-(--color-border) bg-(--color-bg-secondary)/40">
        <div className="flex items-center gap-2">
          <button
            type="button"
            role="switch"
            aria-checked={showFillers}
            onClick={handleToggleFillers}
            className={`
              relative w-8 h-4 rounded-full transition-colors duration-150
              ${showFillers ? "bg-(--color-accent)" : "bg-(--color-border)"}
            `}
          >
            <span
              className={`
                absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform duration-150
                ${showFillers ? "translate-x-4" : "translate-x-0.5"}
              `}
            />
          </button>
          <span className="text-xs text-(--color-text-secondary)">
            Show Filler Words
          </span>
          {fillerCount > 0 && (
            <Badge variant="outline" className="text-[10px] h-4">
              {fillerCount} fillers
            </Badge>
          )}
        </div>

        {fillerCategories.length > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-(--color-text-secondary)">
              Category:
            </span>
            <select
              value={fillerFilter}
              onChange={(e) => setFillerFilter(e.target.value)}
              className="
                text-xs px-2 py-0.5 rounded-md bg-(--color-bg-card)
                border border-(--color-border) text-(--color-text-primary)
                focus:outline-none focus:border-(--color-accent)/60
              "
            >
              <option value="all">All</option>
              {fillerCategories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat.charAt(0).toUpperCase() + cat.slice(1)}
                </option>
              ))}
            </select>
          </div>
        )}

        {isStageComplete(analyzeStage?.status) && (
          <Badge variant="secondary" className="text-[10px] h-4 ml-auto">
            analyzed
          </Badge>
        )}
      </div>

      {/* Transcript body — scrollable */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-2"
      >
        {transcriptData.length === 0 ? (
          <p className="text-xs text-(--color-text-secondary) py-4 text-center">
            No transcript segments found.
          </p>
        ) : (
          transcriptData.map((segment, idx) => (
            <TranscriptSegmentRow
              key={idx}
              segment={segment}
              showFillers={showFillers}
              fillerFilter={fillerFilter}
            />
          ))
        )}
      </div>

      {/* Stats footer */}
      <div className="shrink-0">
        <TranscriptStats segments={transcriptData} fillerFilter={fillerFilter} />
      </div>

      {/* Scroll to top */}
      <div className="px-4 pb-3 shrink-0">
        <Button
          size="sm"
          variant="ghost"
          className="text-xs h-6 text-(--color-text-secondary)"
          onClick={() =>
            scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" })
          }
        >
          Back to top
        </Button>
      </div>
    </div>
  );
}
