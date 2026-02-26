# Phase 13: Hybrid UI/UX & Transcript-First Editor — Detailed EPC

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Research & Planning Only
**Supersedes:** `14-PHASE-13-HYBRID-UI-UX.md` (skeleton)
**Depends on:** Phase 11 (multi-cam/B-roll data models exist)
**Reference:** `11-AI-PODCAST-STUDIO-ARCHITECTURE-opus.md` (EPC-4 + EPC-6)

---

## 1. Goal

Build the production UI layer for the AI Podcast Studio:

1. **Transcript-first editor** — word-level clickable transcript that drives the edit plan
2. **Multi-cam timeline** — visual lane-based timeline showing camera assignments + B-roll
3. **Co-Pilot panel** — floating chat + voice interface for natural language editing
4. **WebSocket state sync** — real-time bidirectional sync between Streamlit and Tauri
5. **Preview playback** — in-browser video preview with timeline scrubbing

---

## 2. Current State Analysis

### 2.1 Existing UI Components

| Component | Platform | Location | Current State |
|-----------|----------|----------|---------------|
| IngestionView | Tauri | `desktop/src/views/IngestionView.tsx` | Drag-drop single file, pipeline status, stage progress bars |
| TranscriptView | Tauri | `desktop/src/views/TranscriptView.tsx` | Filler word toggle, speaker labels, stats footer |
| AudioSyncView | Tauri | `desktop/src/views/AudioSyncView.tsx` | Wavesurfer.js waveform, sync offset slider |
| BrandingView | Tauri | `desktop/src/views/BrandingView.tsx` | Brand profile form, export platform targets |
| Dashboard | Streamlit | `ui/` pages | Job list, status, review, marketing editor, Brand Studio |
| Filler Review | Streamlit | `ui/` | Category-grouped filler cards with keep/remove controls |

### 2.2 What Needs to Be Built

| Component | Platform | Purpose |
|-----------|----------|---------|
| **TranscriptEditor** | Both | Word-level click-to-cut/keep with visual highlighting |
| **MultiCamTimeline** | Both | Lane-based timeline: cameras, B-roll, audio, captions |
| **CoPilotPanel** | Both | Floating chat + voice with streaming responses |
| **VideoPreview** | Both | In-browser video playback synced to transcript/timeline |
| **WebSocketHub** | FastAPI | Real-time state broadcast between all connected clients |
| **SyncBridge** | Both | Client-side WS connection + state reconciliation |

---

## 3. Transcript-First Editor

### 3.1 Design Principles

The transcript IS the edit. Every word in the transcript maps to a time range in the video:

- **Click a word** → toggle cut/keep for that word's time range
- **Drag-select words** → create a cut/keep range
- **Filler words** pre-highlighted (orange) based on existing filler detection
- **Speaker labels** in left margin from diarization
- **Active word** highlighted during playback (karaoke-style)
- **Camera indicator** shows which cam is active for each word's time range

### 3.2 Data Source

Word-level timing comes from `word_alignment.json` (already produced by transcribe stage):

```json
{
  "words": [
    {"word": "Welcome", "start": 0.0, "end": 0.45},
    {"word": "to", "start": 0.45, "end": 0.52},
    {"word": "the", "start": 0.52, "end": 0.58},
    {"word": "show", "start": 0.58, "end": 0.89}
  ]
}
```

### 3.3 Tauri Implementation

```tsx
// desktop/src/components/TranscriptEditor.tsx

interface WordSpan {
  word: string;
  start: number;
  end: number;
  isFiller: boolean;
  isSelected: boolean;  // true = keep, false = cut
  speaker: string;
  activeCam: string;    // which camera is showing during this word
}

function TranscriptEditor({
  words,
  onSelectionChange,
  currentTime,
  cameraPlan,
}: TranscriptEditorProps) {
  // Each word is a clickable <span> with:
  // - Background color: green (keep), red (cut), orange (filler)
  // - Border bottom: active camera color
  // - Highlight animation: current word during playback
  // - Drag selection for range operations

  return (
    <div className="transcript-editor">
      {groupBySpeaker(words).map(group => (
        <div key={group.speaker} className="speaker-block">
          <span className="speaker-label">{group.speaker}</span>
          <div className="words">
            {group.words.map(w => (
              <WordSpanComponent
                key={`${w.start}-${w.word}`}
                word={w}
                isActive={currentTime >= w.start && currentTime < w.end}
                onClick={() => toggleWord(w)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

### 3.4 Streamlit Implementation

Streamlit's execution model (full re-render on interaction) makes a true click-per-word editor challenging. Options:

1. **Streamlit custom component** (React) — embed the same React TranscriptEditor as a Streamlit component. This is the recommended approach.
2. **st.markdown + callbacks** — render words as colored HTML spans, use `st.button` per-word (impractical for 10,000+ words).
3. **Polling bridge** — Streamlit reads the latest edit state from the FastAPI backend, which Tauri also writes to.

**Recommendation:** Option 1 (custom component) for the editor, Option 3 (polling) for sync.

---

## 4. Multi-Cam Timeline

### 4.1 Lane Structure

```
┌──────────────────────────────────────────────────────────┐
│  Timeline: 0:00:00 ─────────────────────────── 1:00:00   │
├──────────────────────────────────────────────────────────┤
│  🎬 Camera  │ [  CAM 1  ][  CAM 2  ][ CAM 1 ][ CAM 2 ] │
│  📹 B-Roll  │           [cityscape]          [office]    │
│  🔊 Audio   │ [========= PRIMARY AUDIO ================] │
│  💬 Caption │ [  Welcome to... ][ Today we... ][ ... ]   │
│  ✂️ Cuts    │     X            X       X                 │
└──────────────────────────────────────────────────────────┘
```

### 4.2 Timeline Component

```tsx
// desktop/src/components/MultiCamTimeline.tsx

interface TimelineLane {
  id: string;
  label: string;
  icon: string;
  segments: TimelineSegment[];
  color: string;
}

interface TimelineSegment {
  start_s: number;
  end_s: number;
  label: string;
  color: string;
  draggable: boolean;  // can edges be dragged to adjust timing
}

function MultiCamTimeline({
  cameraPlan,
  brollInserts,
  editPlan,
  duration_s,
  currentTime,
  onSegmentClick,
  onSegmentDrag,
}: TimelineProps) {
  // Canvas-based or div-based timeline with:
  // - Horizontal scroll for long episodes
  // - Zoom in/out (1px = 0.1s at max zoom, 1px = 10s at min zoom)
  // - Playhead line at currentTime
  // - Drag segment edges to adjust switch points
  // - Click segment to select/edit properties
  // - Right-click context menu for add/remove
}
```

---

## 5. Co-Pilot Panel

### 5.1 Floating Panel Design

The Co-Pilot is a floating panel (like a chat widget) that can be:
- **Pinned** to the right sidebar
- **Floating** as a draggable overlay
- **Minimized** to an icon in the corner

### 5.2 Chat Interface

```tsx
// desktop/src/components/CoPilotPanel.tsx

function CoPilotPanel({ jobId }: { jobId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isListening, setIsListening] = useState(false);
  const ws = useWebSocket(`/copilot/ws/${jobId}`);
  const { startListening, stopListening } = useVoiceCommands(
    (text) => sendCommand(text)
  );

  const sendCommand = async (text: string) => {
    // Add user message
    setMessages(prev => [...prev, { role: "user", content: text }]);

    // Send via WebSocket for streaming response
    ws.send(JSON.stringify({ type: "command", text }));
  };

  // Voice button: hold to speak, release to send
  // Chat input: type + Enter
  // Streaming response with edit previews
  // "Apply" button on each suggestion
  // "Auto-Edit" mode button
}
```

### 5.3 Command Examples in UI

The panel shows suggested commands as quick-action chips:

```
💡 Try these:
• "Switch to camera 2 when Sarah speaks"
• "Cut the awkward pause at 5:30"
• "Add B-roll of the city during the travel discussion"
• "Auto-edit this episode"
• "Apply the YouTube branding kit"
```

---

## 6. WebSocket State Sync Hub

### 6.1 Server Implementation

```python
# service/ws_hub.py

class WebSocketHub:
    """Real-time state sync hub for multi-client editing.

    Maintains rooms per job_id. All connected clients receive
    broadcast of edit operations from any other client.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, job_id: str, ws: WebSocket) -> None:
        await ws.accept()
        if job_id not in self._rooms:
            self._rooms[job_id] = set()
        self._rooms[job_id].add(ws)

    async def disconnect(self, job_id: str, ws: WebSocket) -> None:
        self._rooms.get(job_id, set()).discard(ws)

    async def broadcast(
        self,
        job_id: str,
        message: dict,
        exclude: WebSocket | None = None,
    ) -> None:
        """Broadcast a message to all clients in a room except sender."""
        room = self._rooms.get(job_id, set())
        dead: list[WebSocket] = []
        for client in room:
            if client is exclude:
                continue
            try:
                await client.send_json(message)
            except Exception:
                dead.append(client)
        for ws in dead:
            room.discard(ws)
```

### 6.2 Message Protocol

```json
// Client → Server
{"type": "edit", "payload": {"action": "cam_switch", "cam_id": "cam_2", "at_s": 45.2}}
{"type": "cursor", "payload": {"time_s": 120.5, "client_id": "tauri_main"}}
{"type": "ping"}

// Server → Clients (broadcast)
{"type": "edit", "payload": {...}, "from": "streamlit_user1", "timestamp": "2026-02-26T..."}
{"type": "state_update", "payload": {"camera_plan": {...}}}
{"type": "pong"}
```

### 6.3 Conflict Resolution

- **Last-write-wins** for non-overlapping edits (different time ranges)
- **Timestamp-based merge** for overlapping edits
- **Server-authoritative** state — clients re-fetch full state on reconnect
- **No real-time collaborative cursors** (deferred to v2)

### 6.4 Streamlit Integration

Streamlit cannot maintain a persistent WebSocket due to its re-execution model. Two approaches:

1. **Polling fallback** — `st.experimental_fragment` with 500ms polling of `/jobs/{id}/state`
2. **Custom component** — React component with WebSocket + `Streamlit.setComponentValue()` bridge

**Recommendation:** Polling fallback for MVP, custom component for v2.

---

## 7. Video Preview

### 7.1 In-Browser Playback

```tsx
// desktop/src/components/VideoPreview.tsx

function VideoPreview({
  videoPath,
  currentTime,
  onTimeUpdate,
}: VideoPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  // In Tauri: use convertFileSrc() for local file access
  // In Streamlit: serve via FastAPI static file endpoint
  const src = convertFileSrc(videoPath);

  return (
    <video
      ref={videoRef}
      src={src}
      onTimeUpdate={(e) => onTimeUpdate(e.currentTarget.currentTime)}
      controls
    />
  );
}
```

### 7.2 Timeline Sync

- Video `currentTime` drives transcript active-word highlighting
- Transcript word click seeks video to `word.start`
- Timeline playhead follows video position
- All sync is local (no server round-trip for playback)

---

## 8. Estimated Plan Breakdown

| Plan | Scope | Dependencies |
|------|-------|-------------|
| **13-01** | `service/ws_hub.py` — WebSocket hub with rooms, broadcast, connect/disconnect | None |
| **13-02** | `service/routes/ws.py` — FastAPI WebSocket endpoint, message protocol | 13-01 |
| **13-03** | Tauri: `TranscriptEditor` component — word-level click/drag editing | Phase 11 models |
| **13-04** | Tauri: `MultiCamTimeline` component — lane-based visual timeline | Phase 11 models |
| **13-05** | Tauri: `CoPilotPanel` component — chat + voice + streaming responses | Phase 12 copilot |
| **13-06** | Tauri: `VideoPreview` component — in-browser playback with timeline sync | 13-03, 13-04 |
| **13-07** | Tauri: `useWebSocket` hook — client-side WS connection + state sync | 13-02 |
| **13-08** | Streamlit: transcript editor (custom component or polling bridge) | 13-02 |
| **13-09** | Integration tests — WS sync, edit propagation, cross-client state | All above |

---

## 9. Success Criteria

| # | Criterion | Measurement |
|---|-----------|-------------|
| 1 | Word-click in transcript toggles cut/keep in edit plan | Click word → edit_plan.json updated |
| 2 | Multi-cam timeline displays camera lanes accurately | Visual match to camera_plan.json |
| 3 | Timeline segment drag adjusts switch points | Drag edge → camera_plan.json updated |
| 4 | Co-Pilot chat sends commands and receives structured responses | Submit "switch to cam 2" → CamSwitchCmd returned |
| 5 | Voice command pipeline works in Chromium | Speak → text → command → response |
| 6 | WebSocket broadcasts edits to all clients | Edit in Tauri → appears in Streamlit within 500ms |
| 7 | Video preview syncs with transcript position | Click word → video seeks to word.start |
| 8 | All existing tests pass | Zero regressions |

---

## 10. Platform-Specific Limitations

| Feature | Chrome/Edge | Tauri (Linux) | Streamlit | Mitigation |
|---------|-------------|---------------|-----------|------------|
| Voice commands | ✅ Full | ❌ WebKitGTK no SpeechRecognition | ❌ Server-side | Text-only fallback with mic icon disabled |
| WebSocket sync | ✅ Native | ✅ Native | ⚠️ Polling | 500ms poll in Streamlit; WS in custom component |
| Video preview | ✅ Full | ✅ convertFileSrc | ⚠️ Server stream | FastAPI static file serving for Streamlit |
| Drag-select words | ✅ Full | ✅ Full | ❌ Re-render | Custom component required for Streamlit |
| Timeline drag | ✅ Canvas/SVG | ✅ Canvas/SVG | ❌ Not feasible | Streamlit uses input fields for timing |

---

*This document is a research and planning artifact. No implementation changes should be made based on this document without explicit user approval and per-phase plan creation.*
