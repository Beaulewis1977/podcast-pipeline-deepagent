/**
 * Navigation sidebar for the Podcast Pipeline desktop app.
 *
 * Provides 4 navigation tabs mapping to the main pipeline views:
 *   - Ingestion: ingest raw recordings
 *   - Audio Sync: waveform review and alignment
 *   - Transcript: transcript editing and review
 *   - Branding: titles, thumbnails, and export
 *
 * Collapses to icon-only mode (w-16) when sidebarCollapsed is true,
 * showing full labels when expanded (w-60). A job count badge at the
 * bottom provides quick-glance context.
 */

import { Inbox, AudioLines, FileText, Palette } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useUIStore, type ActiveView } from "../../stores/uiStore";
import { useJobs } from "../../hooks/useJobs";

interface NavItem {
  view: ActiveView;
  label: string;
  Icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { view: "ingestion", label: "Ingestion", Icon: Inbox },
  { view: "audio", label: "Audio Sync", Icon: AudioLines },
  { view: "transcript", label: "Transcript", Icon: FileText },
  { view: "branding", label: "Branding", Icon: Palette },
];

export function Sidebar() {
  const activeView = useUIStore((state) => state.activeView);
  const sidebarCollapsed = useUIStore((state) => state.sidebarCollapsed);
  const setActiveView = useUIStore((state) => state.setActiveView);

  const { data: jobs } = useJobs();
  const jobCount = jobs?.length ?? 0;

  const sidebarWidth = sidebarCollapsed ? "w-16" : "w-60";

  return (
    <aside
      className={`${sidebarWidth} flex flex-col shrink-0 border-r border-(--color-border) bg-(--color-bg-secondary) transition-all duration-200`}
    >
      {/* Navigation items */}
      <nav className="flex flex-col gap-1 p-2 flex-1">
        {NAV_ITEMS.map(({ view, label, Icon }) => {
          const isActive = activeView === view;
          return (
            <Button
              key={view}
              variant="ghost"
              className={`w-full justify-start gap-3 px-3 ${
                isActive
                  ? "bg-(--color-accent) text-white hover:bg-(--color-accent-hover) hover:text-white"
                  : "text-(--color-text-secondary) hover:bg-(--color-bg-card) hover:text-(--color-text-primary)"
              } ${sidebarCollapsed ? "px-0 justify-center" : ""}`}
              onClick={() => setActiveView(view)}
              title={sidebarCollapsed ? label : undefined}
            >
              <Icon className="shrink-0" size={18} />
              {!sidebarCollapsed && (
                <span className="truncate text-sm">{label}</span>
              )}
            </Button>
          );
        })}
      </nav>

      {/* Job count badge at the bottom */}
      <div className="p-3 border-t border-(--color-border)">
        {sidebarCollapsed ? (
          <div
            className="flex items-center justify-center"
            title={`${jobCount} job${jobCount !== 1 ? "s" : ""}`}
          >
            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-(--color-bg-card) text-(--color-text-secondary) text-xs">
              {jobCount}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-1">
            <span className="text-xs text-(--color-text-secondary)">
              {jobCount} job{jobCount !== 1 ? "s" : ""}
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
