/**
 * Top header bar for the Podcast Pipeline desktop app.
 *
 * Displays the application title on the left and a sidecar connection
 * status indicator on the right. The indicator uses color and animation
 * to communicate backend reachability at a glance:
 *   - Green solid: connected
 *   - Amber pulsing: connecting
 *   - Red solid: disconnected
 */

import { useSidecarStore } from "../../stores/sidecarStore";

type StatusConfig = {
  label: string;
  dotClass: string;
};

function getStatusConfig(
  status: "disconnected" | "connecting" | "connected",
): StatusConfig {
  switch (status) {
    case "connected":
      return {
        label: "Connected",
        dotClass: "bg-[var(--color-success)]",
      };
    case "connecting":
      return {
        label: "Connecting…",
        dotClass: "bg-[var(--color-warning)] animate-pulse",
      };
    case "disconnected":
      return {
        label: "Disconnected",
        dotClass: "bg-[var(--color-error)]",
      };
  }
}

export function Header() {
  const status = useSidecarStore((state) => state.status);
  const config = getStatusConfig(status);

  return (
    <header className="flex items-center justify-between px-6 h-14 border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)] shrink-0">
      <span className="text-lg font-semibold text-[var(--color-text-primary)]">
        Podcast Pipeline
      </span>

      <div className="flex items-center gap-2">
        <span
          className={`inline-block w-2.5 h-2.5 rounded-full ${config.dotClass}`}
          aria-hidden="true"
        />
        <span className="text-sm text-[var(--color-text-secondary)]">
          {config.label}
        </span>
      </div>
    </header>
  );
}
