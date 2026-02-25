/**
 * Branding Studio view for the Podcast Pipeline desktop app.
 *
 * Two-panel layout:
 * - Left (60%): Brand profile editor — brand identity, visual identity, caption style
 * - Right (40%): Export settings — platform targets, thumbnail settings, sound kit
 *
 * All form state is local (useState) since brand profiles don't have a REST
 * CRUD API endpoint yet. Values are initialized from job detail metadata
 * where available.
 */

import { useState, useCallback } from "react";
import { useUIStore } from "../stores/uiStore";
import { useJobDetail } from "../hooks/useJobDetail";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

interface ExportTarget {
  id: string;
  label: string;
  description: string;
  defaultEnabled: boolean;
}

const EXPORT_TARGETS: ExportTarget[] = [
  {
    id: "youtube",
    label: "YouTube",
    description: "1080p H.264, AAC audio, MP4 container",
    defaultEnabled: true,
  },
  {
    id: "youtube_ultra",
    label: "YouTube Ultra",
    description: "4K HEVC 10-bit, HDR-ready, MP4 container",
    defaultEnabled: false,
  },
  {
    id: "spotify",
    label: "Spotify Podcast",
    description: "Audio-only MP3, 320kbps",
    defaultEnabled: true,
  },
  {
    id: "spotify_video",
    label: "Spotify Video",
    description: "1080p H.264, MP4 container, 9:16 optional",
    defaultEnabled: false,
  },
  {
    id: "apple",
    label: "Apple Podcast",
    description: "Audio-only AAC, M4A container",
    defaultEnabled: false,
  },
  {
    id: "apple_video",
    label: "Apple Video",
    description: "1080p H.264, MOV container",
    defaultEnabled: false,
  },
  {
    id: "apple_hls",
    label: "Apple HLS",
    description: "Adaptive bitrate HLS for Apple platforms",
    defaultEnabled: false,
  },
  {
    id: "tiktok",
    label: "TikTok",
    description: "1080x1920 vertical, H.264, MP4",
    defaultEnabled: false,
  },
  {
    id: "instagram_reels",
    label: "Instagram Reels",
    description: "1080x1920 vertical, H.264, MP4",
    defaultEnabled: false,
  },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BrandProfile {
  name: string;
  brandVoice: string;
  logoPath: string;
  primaryColor: string;
  font: string;
}

interface CaptionStyle {
  aspectRatio: "16:9" | "9:16" | "1:1";
  captionPosition: "top" | "center" | "bottom";
  fontSize: number;
  highlightColor: string;
}

interface ThumbnailSettings {
  autoGenerate: boolean;
  count: number;
  includeBrandingOverlay: boolean;
}

interface SoundKitSettings {
  enableStingers: boolean;
  enableAutoDucking: boolean;
  stingerVolume: number;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface FormLabelProps {
  children: React.ReactNode;
  htmlFor?: string;
}

function FormLabel({ children, htmlFor }: FormLabelProps) {
  return (
    <label
      htmlFor={htmlFor}
      className="block text-sm text-[var(--color-text-secondary)] mb-1"
    >
      {children}
    </label>
  );
}

interface TextInputProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

function TextInput({ id, value, onChange, placeholder, className }: TextInputProps) {
  return (
    <input
      id={id}
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-md px-3 py-2 text-[var(--color-text-primary)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition-colors ${className ?? ""}`}
    />
  );
}

interface SectionCardProps {
  title: string;
  children: React.ReactNode;
}

function SectionCard({ title, children }: SectionCardProps) {
  return (
    <div className="bg-[var(--color-bg-card)] rounded-lg p-5 border border-[var(--color-border)]">
      <h3 className="text-lg font-semibold mb-4 text-[var(--color-text-primary)]">
        {title}
      </h3>
      {children}
    </div>
  );
}

interface ToggleProps {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}

function Toggle({ id, checked, onChange, label }: ToggleProps) {
  return (
    <label
      htmlFor={id}
      className="flex items-center gap-3 cursor-pointer select-none"
    >
      <div className="relative">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only"
        />
        <div
          className={`w-10 h-5 rounded-full transition-colors ${
            checked
              ? "bg-[var(--color-accent)]"
              : "bg-[var(--color-border)]"
          }`}
        />
        <div
          className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
            checked ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </div>
      <span className="text-sm text-[var(--color-text-primary)]">{label}</span>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BrandingView() {
  const selectedJobId = useUIStore((s) => s.selectedJobId);
  const { data: job } = useJobDetail(selectedJobId);

  // Brand profile state (local — no REST CRUD endpoint yet)
  const [profile, setProfile] = useState<BrandProfile>({
    name: "My Podcast Brand",
    brandVoice:
      "Professional and informative with a friendly tone. Speaks directly to practitioners who want actionable insights.",
    logoPath: "",
    primaryColor: "#e94560",
    font: "Inter",
  });

  // Caption style state
  const [captionStyle, setCaptionStyle] = useState<CaptionStyle>({
    aspectRatio: "16:9",
    captionPosition: "bottom",
    fontSize: 28,
    highlightColor: "#e94560",
  });

  // Export targets state (indexed by target id)
  const [enabledTargets, setEnabledTargets] = useState<Record<string, boolean>>(
    () =>
      Object.fromEntries(
        EXPORT_TARGETS.map((t) => [t.id, t.defaultEnabled]),
      ),
  );

  // Thumbnail settings
  const [thumbnailSettings, setThumbnailSettings] =
    useState<ThumbnailSettings>({
      autoGenerate: true,
      count: 3,
      includeBrandingOverlay: true,
    });

  // Sound kit settings
  const [soundKitSettings, setSoundKitSettings] = useState<SoundKitSettings>({
    enableStingers: false,
    enableAutoDucking: false,
    stingerVolume: 70,
  });

  // Save state (in-memory only for now)
  const [saveStatus, setSaveStatus] = useState<
    "idle" | "saved" | "saving"
  >("idle");

  const handleSaveProfile = useCallback(() => {
    setSaveStatus("saving");
    // Simulate save — backend endpoint not available yet
    setTimeout(() => {
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    }, 300);
  }, []);

  const updateProfile = useCallback(
    <K extends keyof BrandProfile>(key: K, value: BrandProfile[K]) => {
      setProfile((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const updateCaptionStyle = useCallback(
    <K extends keyof CaptionStyle>(key: K, value: CaptionStyle[K]) => {
      setCaptionStyle((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const toggleExportTarget = useCallback((targetId: string) => {
    setEnabledTargets((prev) => ({ ...prev, [targetId]: !prev[targetId] }));
  }, []);

  const enabledCount = Object.values(enabledTargets).filter(Boolean).length;

  return (
    <div className="space-y-5">
      {/* Page header */}
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">
            Branding Studio
          </h2>
          {selectedJobId ? (
            <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">
              Job:{" "}
              <span className="font-mono text-xs text-[var(--color-accent)]">
                {selectedJobId}
              </span>
              {job ? ` — ${job.status}` : ""}
            </p>
          ) : (
            <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">
              No job selected — editing global brand defaults
            </p>
          )}
        </div>

        <button
          onClick={handleSaveProfile}
          disabled={saveStatus === "saving"}
          className="px-4 py-1.5 rounded-md bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white text-sm font-medium transition-colors disabled:opacity-60"
        >
          {saveStatus === "saving"
            ? "Saving..."
            : saveStatus === "saved"
              ? "Saved!"
              : "Save Profile"}
        </button>
      </div>

      {/* Two-panel grid */}
      <div className="grid grid-cols-[3fr_2fr] gap-6">
        {/* LEFT PANEL: Brand Profile */}
        <div className="space-y-5">
          {/* Brand Identity */}
          <SectionCard title="Brand Identity">
            <div className="space-y-4">
              <div>
                <FormLabel htmlFor="brand-name">Brand Name</FormLabel>
                <TextInput
                  id="brand-name"
                  value={profile.name}
                  onChange={(v) => updateProfile("name", v)}
                  placeholder="My Podcast Brand"
                />
              </div>

              <div>
                <FormLabel htmlFor="brand-voice">Brand Voice</FormLabel>
                <textarea
                  id="brand-voice"
                  value={profile.brandVoice}
                  onChange={(e) => updateProfile("brandVoice", e.target.value)}
                  rows={4}
                  placeholder="Describe your brand's tone and personality..."
                  className="w-full bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-md px-3 py-2 text-[var(--color-text-primary)] text-sm resize-y focus:outline-none focus:border-[var(--color-accent)] transition-colors"
                />
                <p className="text-xs text-[var(--color-text-secondary)] mt-1 opacity-70">
                  This voice description is injected into AI analysis prompts
                </p>
              </div>
            </div>
          </SectionCard>

          {/* Visual Identity */}
          <SectionCard title="Visual Identity">
            <div className="space-y-4">
              <div>
                <FormLabel htmlFor="logo-path">Logo File Path</FormLabel>
                <div className="flex gap-2">
                  <TextInput
                    id="logo-path"
                    value={profile.logoPath}
                    onChange={(v) => updateProfile("logoPath", v)}
                    placeholder="/path/to/logo.png"
                    className="flex-1"
                  />
                  <button className="px-3 py-2 rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] text-sm transition-colors whitespace-nowrap">
                    Browse
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <FormLabel htmlFor="primary-color">Primary Color</FormLabel>
                  <div className="flex gap-2 items-center">
                    <input
                      id="primary-color"
                      type="color"
                      value={profile.primaryColor}
                      onChange={(e) =>
                        updateProfile("primaryColor", e.target.value)
                      }
                      className="w-10 h-9 rounded cursor-pointer border border-[var(--color-border)] bg-transparent p-0.5"
                    />
                    <TextInput
                      value={profile.primaryColor}
                      onChange={(v) => updateProfile("primaryColor", v)}
                      placeholder="#e94560"
                    />
                  </div>
                </div>

                <div>
                  <FormLabel htmlFor="brand-font">Font</FormLabel>
                  <TextInput
                    id="brand-font"
                    value={profile.font}
                    onChange={(v) => updateProfile("font", v)}
                    placeholder="Inter"
                  />
                </div>
              </div>

              {/* Brand preview card */}
              <div
                className="rounded-md p-4 border border-[var(--color-border)] text-center"
                style={{ backgroundColor: profile.primaryColor + "1a" }}
              >
                <p
                  className="font-bold text-lg"
                  style={{
                    color: profile.primaryColor,
                    fontFamily: profile.font,
                  }}
                >
                  {profile.name || "Brand Name Preview"}
                </p>
                <p className="text-xs text-[var(--color-text-secondary)] mt-1">
                  Brand preview
                </p>
              </div>
            </div>
          </SectionCard>

          {/* Caption Style */}
          <SectionCard title="Caption Style">
            <div className="space-y-4">
              <div>
                <FormLabel>Aspect Ratio</FormLabel>
                <div className="flex gap-3">
                  {(["16:9", "9:16", "1:1"] as const).map((ratio) => (
                    <label
                      key={ratio}
                      className="flex items-center gap-1.5 cursor-pointer"
                    >
                      <input
                        type="radio"
                        name="aspect-ratio"
                        value={ratio}
                        checked={captionStyle.aspectRatio === ratio}
                        onChange={() =>
                          updateCaptionStyle("aspectRatio", ratio)
                        }
                        className="accent-[var(--color-accent)]"
                      />
                      <span className="text-sm text-[var(--color-text-primary)]">
                        {ratio}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <FormLabel>Caption Position</FormLabel>
                <div className="flex gap-3">
                  {(["top", "center", "bottom"] as const).map((pos) => (
                    <label
                      key={pos}
                      className="flex items-center gap-1.5 cursor-pointer"
                    >
                      <input
                        type="radio"
                        name="caption-position"
                        value={pos}
                        checked={captionStyle.captionPosition === pos}
                        onChange={() =>
                          updateCaptionStyle("captionPosition", pos)
                        }
                        className="accent-[var(--color-accent)]"
                      />
                      <span className="text-sm text-[var(--color-text-primary)] capitalize">
                        {pos}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <FormLabel>Font Size</FormLabel>
                  <span className="text-sm text-[var(--color-text-primary)] font-mono tabular-nums">
                    {captionStyle.fontSize}px
                  </span>
                </div>
                <input
                  type="range"
                  min={16}
                  max={48}
                  step={1}
                  value={captionStyle.fontSize}
                  onChange={(e) =>
                    updateCaptionStyle("fontSize", Number(e.target.value))
                  }
                  className="w-full accent-[var(--color-accent)]"
                  aria-label="Caption font size"
                />
              </div>

              <div>
                <FormLabel htmlFor="highlight-color">
                  Word Highlight Color
                </FormLabel>
                <div className="flex gap-2 items-center">
                  <input
                    id="highlight-color"
                    type="color"
                    value={captionStyle.highlightColor}
                    onChange={(e) =>
                      updateCaptionStyle("highlightColor", e.target.value)
                    }
                    className="w-10 h-9 rounded cursor-pointer border border-[var(--color-border)] bg-transparent p-0.5"
                  />
                  <TextInput
                    value={captionStyle.highlightColor}
                    onChange={(v) => updateCaptionStyle("highlightColor", v)}
                    placeholder="#e94560"
                  />
                </div>
              </div>
            </div>
          </SectionCard>
        </div>

        {/* RIGHT PANEL: Export Settings */}
        <div className="space-y-5">
          {/* Export Targets */}
          <SectionCard title={`Export Targets (${enabledCount} enabled)`}>
            <div className="space-y-3">
              {EXPORT_TARGETS.map((target) => (
                <label
                  key={target.id}
                  className="flex items-start gap-3 cursor-pointer group"
                >
                  <input
                    type="checkbox"
                    checked={enabledTargets[target.id] ?? false}
                    onChange={() => toggleExportTarget(target.id)}
                    className="mt-0.5 accent-[var(--color-accent)]"
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-[var(--color-text-primary)] font-medium leading-snug">
                      {target.label}
                    </p>
                    <p className="text-xs text-[var(--color-text-secondary)] opacity-70 mt-0.5">
                      {target.description}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          </SectionCard>

          {/* Thumbnail Settings */}
          <SectionCard title="Thumbnail Settings">
            <div className="space-y-4">
              <Toggle
                id="auto-thumbnails"
                checked={thumbnailSettings.autoGenerate}
                onChange={(v) =>
                  setThumbnailSettings((prev) => ({
                    ...prev,
                    autoGenerate: v,
                  }))
                }
                label="Auto-generate thumbnails"
              />

              {thumbnailSettings.autoGenerate && (
                <>
                  <div>
                    <FormLabel htmlFor="thumbnail-count">
                      Thumbnail count
                    </FormLabel>
                    <input
                      id="thumbnail-count"
                      type="number"
                      min={1}
                      max={5}
                      value={thumbnailSettings.count}
                      onChange={(e) =>
                        setThumbnailSettings((prev) => ({
                          ...prev,
                          count: Math.max(1, Math.min(5, Number(e.target.value))),
                        }))
                      }
                      className="w-20 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-md px-3 py-2 text-[var(--color-text-primary)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition-colors"
                    />
                  </div>

                  <Toggle
                    id="branding-overlay"
                    checked={thumbnailSettings.includeBrandingOverlay}
                    onChange={(v) =>
                      setThumbnailSettings((prev) => ({
                        ...prev,
                        includeBrandingOverlay: v,
                      }))
                    }
                    label="Include branding overlay"
                  />
                </>
              )}
            </div>
          </SectionCard>

          {/* Sound Kit Settings */}
          <SectionCard title="Sound Kit">
            <div className="space-y-4">
              <Toggle
                id="enable-stingers"
                checked={soundKitSettings.enableStingers}
                onChange={(v) =>
                  setSoundKitSettings((prev) => ({
                    ...prev,
                    enableStingers: v,
                  }))
                }
                label="Enable intro/outro stingers"
              />

              <Toggle
                id="enable-ducking"
                checked={soundKitSettings.enableAutoDucking}
                onChange={(v) =>
                  setSoundKitSettings((prev) => ({
                    ...prev,
                    enableAutoDucking: v,
                  }))
                }
                label="Enable auto-ducking"
              />

              {soundKitSettings.enableStingers && (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <FormLabel>Stinger volume</FormLabel>
                    <span className="text-sm text-[var(--color-text-primary)] font-mono tabular-nums">
                      {soundKitSettings.stingerVolume}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={100}
                    step={1}
                    value={soundKitSettings.stingerVolume}
                    onChange={(e) =>
                      setSoundKitSettings((prev) => ({
                        ...prev,
                        stingerVolume: Number(e.target.value),
                      }))
                    }
                    className="w-full accent-[var(--color-accent)]"
                    aria-label="Stinger volume"
                  />
                </div>
              )}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
