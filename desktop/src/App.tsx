/**
 * Root application component for the Podcast Pipeline desktop app.
 *
 * Responsibilities:
 * 1. Boot sequence — starts the backend sidecar and waits for health.
 * 2. Sidecar lifecycle — stops the sidecar when the window unloads.
 * 3. Recovery check — surfaces interrupted jobs in a dismissible banner.
 * 4. View routing — renders one of 4 views based on Zustand activeView.
 * 5. Layout — wraps connected content in AppShell (Header + Sidebar + main).
 *
 * All polling (jobs, health, system status) is delegated to TanStack Query hooks.
 * All connection state lives in useSidecarStore (no local useState for status).
 */

import { useCallback, useEffect, useState } from "react";

// Module-level flag — survives React StrictMode double-mount (where a useRef
// would be reset). Boot must only run once per page load.
let _bootStarted = false;
import { AppShell } from "./components/layout/AppShell";
import { IngestionView } from "./views/IngestionView";
import { AudioSyncView } from "./views/AudioSyncView";
import { TranscriptView } from "./views/TranscriptView";
import { BrandingView } from "./views/BrandingView";
import { useUIStore } from "./stores/uiStore";
import { useSidecarStore } from "./stores/sidecarStore";
import {
  BACKEND_PORT,
  bootBackend,
  checkHealth,
  stopSidecar,
} from "./lib/backend";
import { type RecoveryStatus, checkRecovery } from "./lib/recovery";

// ---------------------------------------------------------------------------
// View router
// ---------------------------------------------------------------------------

function ViewRouter({ activeView }: { activeView: string }) {
  switch (activeView) {
    case "audio":
      return <AudioSyncView />;
    case "transcript":
      return <TranscriptView />;
    case "branding":
      return <BrandingView />;
    case "ingestion":
    default:
      return <IngestionView />;
  }
}

// ---------------------------------------------------------------------------
// Boot screen (shown while backend is starting)
// ---------------------------------------------------------------------------

function BootScreen({ message }: { message: string }) {
  return (
    <div className="flex h-screen items-center justify-center bg-[var(--color-bg-primary)]">
      <div className="flex flex-col items-center gap-4 p-8 rounded-xl bg-[var(--color-bg-card)] border border-[var(--color-border)] shadow-lg max-w-sm w-full text-center">
        <div className="w-8 h-8 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
        <p className="text-sm text-[var(--color-text-primary)] font-medium">
          {message}
        </p>
        <p className="text-xs text-[var(--color-text-secondary)]">
          Starting backend sidecar&hellip;
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Connection error screen (shown when sidecar fails to start)
// ---------------------------------------------------------------------------

interface ConnectionErrorProps {
  errorMessage: string | null;
  onRetry: () => void;
}

function ConnectionError({ errorMessage, onRetry }: ConnectionErrorProps) {
  return (
    <div className="flex h-screen items-center justify-center bg-[var(--color-bg-primary)]">
      <div className="flex flex-col gap-4 p-8 rounded-xl bg-[var(--color-bg-card)] border border-[var(--color-error)]/40 shadow-lg max-w-sm w-full">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[var(--color-error)] shrink-0" />
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
            Backend unreachable
          </h2>
        </div>
        {errorMessage && (
          <p className="text-xs text-[var(--color-error)] leading-relaxed">
            {errorMessage}
          </p>
        )}
        <p className="text-xs text-[var(--color-text-secondary)]">
          Expected at{" "}
          <code className="font-mono">http://127.0.0.1:{BACKEND_PORT}</code>
        </p>
        <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed border-t border-[var(--color-border)] pt-3 mt-1">
          Start the backend in a separate terminal:
          <br />
          <code className="font-mono text-[var(--color-accent)] select-all">
            uv run python src/podcast_pipeline/service/cli.py
          </code>
          <br />
          Then click Retry Connection.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="
            mt-1 px-4 py-2 text-xs font-medium rounded-lg
            bg-[var(--color-accent)] text-white
            hover:opacity-90 transition-opacity
          "
        >
          Retry Connection
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recovery banner
// ---------------------------------------------------------------------------

interface RecoveryBannerProps {
  recovery: RecoveryStatus;
  onDismiss: () => void;
}

function RecoveryBanner({ recovery, onDismiss }: RecoveryBannerProps) {
  const { resumable_jobs, corrected } = recovery;

  return (
    <div className="mx-6 mt-4 p-4 rounded-lg bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/30">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[var(--color-warning)] animate-pulse shrink-0 mt-0.5" />
          <p className="text-xs font-semibold text-[var(--color-warning)]">
            {resumable_jobs.length} interrupted{" "}
            {resumable_jobs.length === 1 ? "job" : "jobs"} available for resume
            {corrected > 0 && ` (${corrected} stale entries corrected)`}
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors shrink-0"
        >
          Dismiss
        </button>
      </div>
      <ul className="space-y-1 ml-4">
        {resumable_jobs.map((job) => (
          <li key={job.job_id} className="text-xs text-[var(--color-text-secondary)]">
            <span className="font-mono text-[var(--color-accent)]">{job.job_id}</span>
            {" — "}
            resume from <span className="font-medium">{job.resume_stage}</span>
            {job.interrupted && " (interrupted runtime detected)"}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

function App() {
  const { status, error, setStatus, setSidecar, setError } = useSidecarStore();
  const { activeView } = useUIStore();

  const [recoveryStatus, setRecoveryStatus] = useState<RecoveryStatus | null>(null);

  // --- Boot sequence ---
  // Uses module-level _bootStarted so React StrictMode's double-invoke does not
  // cancel the async boot before it updates the Zustand store. Zustand setters
  // are safe to call after an apparent unmount — the store is global.
  useEffect(() => {
    if (_bootStarted) {
      return;
    }
    _bootStarted = true;

    async function boot() {
      setStatus("connecting");
      try {
        const result = await bootBackend();
        setSidecar(result.sidecar);
        if (result.health !== null) {
          setStatus("connected");
          setError(null);
        } else {
          setStatus("disconnected");
          setError("Backend did not become ready within startup timeout.");
        }
      } catch (err) {
        // Fallback: coexistence mode — backend already running externally
        const healthy = await checkHealth();
        if (healthy !== null) {
          setStatus("connected");
          setError(null);
        } else {
          setStatus("disconnected");
          setError(err instanceof Error ? err.message : "Sidecar startup failed");
        }
      }
    }

    void boot();
  }, [setError, setSidecar, setStatus]);

  // --- Recovery check after connection ---
  useEffect(() => {
    if (status !== "connected") {
      return;
    }
    void checkRecovery()
      .then((recovery) => {
        if (recovery.resumable_jobs.length > 0 || recovery.corrected > 0) {
          setRecoveryStatus(recovery);
        }
      })
      .catch(() => {
        // Non-critical — skip recovery banner if check fails
      });
  }, [status]);

  // --- Stop sidecar on window unload ---
  useEffect(() => {
    const handleUnload = () => {
      void stopSidecar().catch(() => {});
    };
    window.addEventListener("beforeunload", handleUnload);
    return () => window.removeEventListener("beforeunload", handleUnload);
  }, []);

  // --- Retry handler ---
  const handleRetry = useCallback(async () => {
    setStatus("connecting");
    const healthy = await checkHealth();
    if (healthy !== null) {
      setStatus("connected");
      setError(null);
    } else {
      setStatus("disconnected");
      setError(`Backend unreachable at http://127.0.0.1:${BACKEND_PORT}`);
    }
  }, [setError, setStatus]);

  // --- Loading state ---
  if (status === "connecting") {
    return <BootScreen message="Connecting to backend..." />;
  }

  // --- Error state ---
  if (status === "disconnected") {
    return <ConnectionError errorMessage={error} onRetry={() => void handleRetry()} />;
  }

  // --- Connected: full app shell ---
  return (
    <AppShell>
      {recoveryStatus !== null && (
        <RecoveryBanner
          recovery={recoveryStatus}
          onDismiss={() => setRecoveryStatus(null)}
        />
      )}
      <ViewRouter activeView={activeView} />
    </AppShell>
  );
}

export default App;
