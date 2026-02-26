# Phase 12: Gemini Co-Pilot & Veo 3.1 Studio — Detailed EPC

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Research & Planning Only
**Supersedes:** `13-PHASE-12-GEMINI-VEO-COPILOT.md` (skeleton)
**Depends on:** Phase 11 (multi-cam + B-roll infrastructure)
**Reference:** `11-AI-PODCAST-STUDIO-ARCHITECTURE-opus.md` (EPC-3 + partial EPC-2)

---

## 1. Goal

Implement a Gemini-powered intelligent editing assistant and Veo 3.1 video generation studio:

1. **Gemini Co-Pilot** — natural language chat + voice interface for video editing direction
2. **Structured edit instructions** — NL commands → typed JSON edit operations
3. **Agentic Auto-Edit mode** — Gemini analyzes full transcript + video → generates complete `camera_plan.json`
4. **Veo 3.1 B-roll generation** — AI-generated clips that visually match the main footage via reference images
5. **Veo 3.1 video extension** — extend short clips up to 141s via iterative 7s extensions
6. **Voice command pipeline** — Web Speech API → text → Co-Pilot → structured output

---

## 2. Current State Analysis

### 2.1 What Already Exists

| Component | File | Relevance |
|-----------|------|-----------|
| Gemini provider | `providers/gemini.py` | Uses `google-genai` SDK, handles upload caching, retry classification, response parsing |
| google-genai SDK | `pyproject.toml` core dep | **Same SDK used for Veo 3.1** (`client.models.generate_videos`) — no new package |
| Base provider | `providers/base.py` | `AnalysisProvider` protocol, prompt building, brand voice injection |
| FastAPI routes | `service/routes/` | REST pattern for job operations; WebSocket support in FastAPI |
| Camera plan model | (from Phase 11) | `CameraPlan`, `CamSegment`, `BrollInsert` typed models |
| Edit plan model | `models/edit_plan.py` | Existing cut/keep segment model for transcript-based editing |

### 2.2 What Doesn't Exist Yet

| Component | Purpose |
|-----------|---------|
| `copilot/engine.py` | NL command → structured edit instruction translator |
| `copilot/prompts.py` | System prompts, output schemas, command vocabulary |
| `copilot/commands.py` | Typed command models (CamSwitchCmd, InsertBrollCmd, etc.) |
| `providers/veo.py` | Veo 3.1 video generation wrapper using google-genai |
| `service/routes/copilot.py` | REST + WebSocket endpoints for Co-Pilot interaction |

---

## 3. Gemini Co-Pilot Architecture

### 3.1 Command Types

The Co-Pilot translates natural language into these typed commands:

```python
# copilot/commands.py

class CamSwitchCmd(BaseModel):
    """Switch to a different camera angle."""
    action: Literal["cam_switch"] = "cam_switch"
    cam_id: str                    # target camera asset_id
    at_s: float | None = None      # exact timestamp (if specified)
    trigger: Literal["manual", "speaker_change", "topic_change"] = "manual"
    speaker: str | None = None     # for speaker_change trigger
    transition: Literal["cut", "dissolve", "rife"] = "cut"

class InsertBrollCmd(BaseModel):
    """Insert a B-roll clip at a specific point."""
    action: Literal["insert_broll"] = "insert_broll"
    start_s: float
    end_s: float
    broll_id: str | None = None    # specific clip, or None for AI-generated
    topic: str | None = None       # content hint for AI generation
    audio_mode: Literal["main_only", "mixed"] = "main_only"

class CutSegmentCmd(BaseModel):
    """Remove a time range from the output."""
    action: Literal["cut"] = "cut"
    start_s: float
    end_s: float
    reason: str | None = None      # "filler", "silence", "off-topic"

class KeepSegmentCmd(BaseModel):
    """Explicitly mark a range as kept (undo a previous cut)."""
    action: Literal["keep"] = "keep"
    start_s: float
    end_s: float

class GenerateBrollCmd(BaseModel):
    """Request Veo 3.1 to generate a B-roll clip."""
    action: Literal["generate_broll"] = "generate_broll"
    prompt: str                    # description of desired B-roll
    duration_s: float = 8.0        # max 8s per Veo 3.1 clip
    style_match: bool = True       # use reference frame for style consistency
    reference_timestamp_s: float | None = None  # frame to use as style reference

class ApplyBrandingCmd(BaseModel):
    """Apply a specific branding kit to the output."""
    action: Literal["apply_branding"] = "apply_branding"
    kit_name: str                  # named branding profile
    platforms: list[str] | None = None  # specific platforms, or None for all

# Union type for all commands
EditCommand = (
    CamSwitchCmd | InsertBrollCmd | CutSegmentCmd |
    KeepSegmentCmd | GenerateBrollCmd | ApplyBrandingCmd
)
```

### 3.2 Co-Pilot Engine

```python
# copilot/engine.py

class CoPilotEngine:
    """Translates natural language editing commands into structured operations.

    The engine maintains conversation context including:
    - Current transcript with word timings
    - Available camera angles (from AssetRegistry)
    - B-roll inventory
    - Current camera plan state
    - Speaker diarization data
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._conversation_history: list[dict] = []

    async def process_command(
        self,
        user_input: str,
        context: EditContext,
    ) -> CoPilotResponse:
        """Process a natural language editing command.

        Args:
            user_input: The user's natural language command.
            context: Current editing state (transcript, cameras, plan).

        Returns:
            CoPilotResponse with structured commands and explanation.
        """
        system_prompt = build_copilot_system_prompt(context)
        messages = self._build_messages(user_input, system_prompt)

        response = self._client.models.generate_content(
            model=self._model,
            contents=messages,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CoPilotResponseSchema,
            ),
        )

        return self._parse_response(response.text)

    async def auto_edit(
        self,
        context: EditContext,
    ) -> CameraPlan:
        """Generate a complete camera plan from transcript + video analysis.

        This is the "Gemini Auto-Edit" mode — it analyzes the full
        transcript, speaker diarization, and video metadata to produce
        an optimal camera switching plan with B-roll suggestions.
        """
        system_prompt = build_auto_edit_prompt(context)
        # ... generates complete CameraPlan
```

### 3.3 System Prompts

```python
# copilot/prompts.py

COPILOT_SYSTEM_PROMPT = """You are an expert podcast video editor assistant.
You understand camera switching, B-roll placement, and editorial timing.

CONTEXT:
- Available cameras: {camera_list}
- Available B-roll clips: {broll_list}
- Speaker diarization: {speakers}
- Current edit state: {current_plan_summary}

RULES:
1. Always output valid JSON matching the EditCommand schema.
2. Use speaker names from diarization when the user references speakers.
3. Camera switches should happen at natural pause points (between sentences).
4. B-roll insertions should be 3-8 seconds (typical podcast cutaway length).
5. When unsure about timing, ask for clarification.
6. For "auto-edit" requests, generate a complete CameraPlan.

OUTPUT FORMAT:
{{
  "commands": [<list of EditCommand objects>],
  "explanation": "<brief explanation of what will change>",
  "confidence": <0.0-1.0 how confident you are in this edit>
}}
"""

AUTO_EDIT_PROMPT = """Analyze this podcast episode and generate an optimal
camera switching plan. Guidelines:

SWITCHING RULES:
- Switch to the speaking person's camera when they start a new thought.
- Hold on the listener's reaction for 3-5 seconds during dramatic moments.
- Don't switch more than once every 5 seconds (avoid jumpiness).
- Use the wide/primary camera for transitions between topics.

B-ROLL RULES:
- Insert B-roll when the conversation references external topics, places, or concepts.
- B-roll clips should be 3-8 seconds.
- Don't insert B-roll during emotionally intense conversation.
- Maximum 1 B-roll insert per 2-minute segment.

TRANSCRIPT:
{transcript_with_speakers}

CAMERAS:
{camera_descriptions}

B-ROLL INVENTORY:
{broll_inventory}

Generate a complete camera_plan.json following the CameraPlan schema.
"""
```

### 3.4 Response Schema

```python
# copilot/commands.py

class CoPilotResponse(BaseModel):
    """Structured response from the Co-Pilot engine."""
    commands: list[EditCommand]       # parsed edit commands
    explanation: str                  # human-readable explanation
    confidence: float                 # 0-1 confidence in the interpretation
    needs_clarification: bool = False # True if the command was ambiguous
    clarification_prompt: str | None = None  # follow-up question if ambiguous
```

---

## 4. Veo 3.1 Integration

### 4.1 Provider Implementation

```python
# providers/veo.py

class VeoProvider:
    """Veo 3.1 video generation via google-genai SDK.

    Capabilities (verified Feb 2026):
    - Text-to-video: 8s clips at 720p/1080p/4K
    - Reference-image style matching: up to 3 reference images
    - Video extension: up to 141s input → 7s extension (repeatable 20x at 720p)
    - Native audio generation (conversations, SFX)
    - Portrait (9:16) and landscape (16:9) modes
    """

    MODEL = "veo-3.1-generate-preview"
    FAST_MODEL = "veo-3.1-fast-generate-preview"

    def __init__(self, api_key: str, use_fast: bool = False) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = self.FAST_MODEL if use_fast else self.MODEL

    async def generate_broll(
        self,
        prompt: str,
        reference_frame: bytes | None = None,
        aspect_ratio: Literal["16:9", "9:16"] = "16:9",
        output_path: Path | None = None,
    ) -> Path:
        """Generate a B-roll clip matching the style of reference footage.

        Args:
            prompt: Description of desired B-roll content.
            reference_frame: JPEG/PNG bytes of a frame from the main
                video to use for style matching via reference_images.
            aspect_ratio: Output aspect ratio.
            output_path: Where to save the generated video.

        Returns:
            Path to the downloaded generated video file.
        """
        config = types.GenerateVideosConfig(
            number_of_videos=1,
            aspect_ratio=aspect_ratio,
        )

        # Style matching via reference image
        if reference_frame is not None:
            config.reference_images = [
                types.Image(image_bytes=reference_frame),
            ]

        operation = self._client.models.generate_videos(
            model=self._model,
            prompt=prompt,
            config=config,
        )

        # Poll for completion
        while not operation.done:
            await asyncio.sleep(5)
            operation = self._client.operations.get(operation)

        # Download result
        video = operation.result.generated_videos[0]
        if output_path is None:
            output_path = Path(tempfile.mktemp(suffix=".mp4"))
        self._client.files.download(file=video.video, path=str(output_path))
        return output_path

    async def extend_video(
        self,
        input_video: Path,
        prompt: str,
        extensions: int = 1,
    ) -> Path:
        """Extend a video clip by appending AI-generated continuation.

        Veo 3.1 supports extending videos up to 141s input with 7s
        extensions, repeatable up to 20 times (at 720p only).

        Args:
            input_video: Path to the input video to extend.
            prompt: Description of what should happen in the extension.
            extensions: Number of 7s extensions to append.

        Returns:
            Path to the extended video.
        """
        current_video = input_video
        for i in range(extensions):
            video_bytes = current_video.read_bytes()
            operation = self._client.models.generate_videos(
                model=self._model,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    video=types.Video(video_bytes=video_bytes),
                    number_of_videos=1,
                ),
            )
            while not operation.done:
                await asyncio.sleep(5)
                operation = self._client.operations.get(operation)

            extended = operation.result.generated_videos[0]
            output_path = current_video.with_stem(f"{current_video.stem}_ext{i+1}")
            self._client.files.download(file=extended.video, path=str(output_path))
            current_video = output_path

        return current_video
```

### 4.2 Reference Frame Extraction

To match B-roll style with the main video, extract a reference frame near the insertion point:

```python
def extract_reference_frame(
    video_path: Path,
    timestamp_s: float,
) -> bytes:
    """Extract a single frame as JPEG bytes for Veo reference_images."""
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        run_ffmpeg([
            "-ss", str(timestamp_s),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(tmp.name),
        ])
        return Path(tmp.name).read_bytes()
```

### 4.3 Config Extensions

```yaml
# config.yaml additions

copilot:
  enabled: false                    # master gate
  model: gemini-2.5-flash          # model for NL command processing
  auto_edit_model: gemini-2.5-pro  # more capable model for full auto-edit
  max_commands_per_turn: 10        # safety limit on commands per interaction
  voice_enabled: true              # enable Web Speech API input

veo:
  enabled: false                   # master gate
  model: veo-3.1-generate-preview  # or veo-3.1-fast-generate-preview
  use_fast: false                  # use the fast model (lower quality, faster)
  max_generations_per_job: 5       # cost control per job
  default_style_match: true        # always use reference frames
  cache_generated: true            # cache generated clips for reuse
```

---

## 5. Voice Command Pipeline

### 5.1 Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐
│  Microphone      │     │  Web Speech   │     │  Co-Pilot    │
│  (Browser/Tauri) │────→│  API (STT)   │────→│  Engine      │
│                  │     │  Continuous   │     │  (Gemini)    │
└─────────────────┘     └──────────────┘     └──────┬───────┘
                                                     │
                                                     ▼
                                              ┌──────────────┐
                                              │  Structured  │
                                              │  EditCommand │
                                              └──────────────┘
```

### 5.2 Browser Implementation

```typescript
// desktop/src/hooks/useVoiceCommands.ts

export function useVoiceCommands(onCommand: (text: string) => void) {
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const startListening = useCallback(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("Speech recognition not supported");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const last = event.results[event.results.length - 1];
      if (last.isFinal) {
        onCommand(last[0].transcript);
      }
    };

    recognition.start();
    recognitionRef.current = recognition;
    setIsListening(true);
  }, [onCommand]);

  // ... stop, cleanup
}
```

**Platform notes:**
- Works in Chrome, Edge, and Chromium-based browsers (including Tauri WebView)
- Does NOT work in Firefox (no SpeechRecognition API)
- Tauri on Linux uses WebKitGTK which does NOT support SpeechRecognition — voice degrades to text-only
- Requires HTTPS or localhost (Tauri satisfies this via `tauri://`)

---

## 6. FastAPI Endpoints

### 6.1 REST Endpoints

```python
# service/routes/copilot.py

@router.post("/copilot/command")
async def process_command(
    request: CoPilotCommandRequest,
    job_id: str,
) -> CoPilotResponse:
    """Process a single Co-Pilot command."""
    ...

@router.post("/copilot/auto-edit")
async def auto_edit(
    job_id: str,
) -> CameraPlan:
    """Generate a complete camera plan via Gemini Auto-Edit."""
    ...

@router.post("/veo/generate")
async def generate_broll(
    request: VeoGenerateRequest,
    job_id: str,
) -> VeoGenerateResponse:
    """Generate a B-roll clip via Veo 3.1."""
    ...
```

### 6.2 WebSocket Endpoint

```python
@router.websocket("/copilot/ws/{job_id}")
async def copilot_ws(websocket: WebSocket, job_id: str):
    """Streaming Co-Pilot interaction.

    Enables:
    - Real-time command processing with streaming responses
    - Voice command results forwarded to engine
    - Multi-client broadcast of edit operations
    """
    await websocket.accept()
    ...
```

---

## 7. Estimated Plan Breakdown

| Plan | Scope | Dependencies |
|------|-------|-------------|
| **12-01** | `copilot/commands.py` — typed command models, `CoPilotResponse`, union type `EditCommand` | Phase 11 models |
| **12-02** | `copilot/prompts.py` — system prompts, auto-edit prompt, output schema definitions | 12-01 |
| **12-03** | `copilot/engine.py` — `CoPilotEngine` with `process_command()` and `auto_edit()` | 12-01, 12-02 |
| **12-04** | `providers/veo.py` — `VeoProvider` with `generate_broll()`, `extend_video()`, reference frame extraction | None |
| **12-05** | `service/routes/copilot.py` — REST endpoints + WebSocket for Co-Pilot interaction | 12-03, 12-04 |
| **12-06** | Config extension — `copilot` + `veo` yaml sections, API key management | 12-03, 12-04 |
| **12-07** | Voice command integration — `useVoiceCommands` hook, platform detection, fallback | 12-05 |
| **12-08** | Integration tests — command parsing, auto-edit generation, Veo mock, regression suite | All above |

---

## 8. Success Criteria

| # | Criterion | Measurement |
|---|-----------|-------------|
| 1 | 5 core command types produce valid EditCommand JSON | Unit tests for each command type |
| 2 | NL → structured command accuracy ≥80% | Test with 20 representative voice commands |
| 3 | Auto-Edit generates valid CameraPlan from transcript | CameraPlan.validate_continuity() returns empty issues |
| 4 | Veo 3.1 generates B-roll clip | Returns a playable .mp4 file |
| 5 | Reference-image style matching produces visually consistent clips | Manual review (subjective) |
| 6 | Voice commands work in Chromium-based browsers | Web Speech API → text → valid command |
| 7 | Co-Pilot WebSocket streams responses in real-time | <2s latency from command to first response token |
| 8 | All existing tests pass | Zero regressions |

---

## 9. Cost & Rate Limit Considerations

| Resource | Limit | Mitigation |
|----------|-------|------------|
| Gemini API (Co-Pilot) | Standard rate limits | Use gemini-2.5-flash for per-command (cheap); gemini-2.5-pro only for auto-edit |
| Veo 3.1 generation | Pay per video, higher at 4K | Default to 720p for previews; upscale only for final render |
| Veo 3.1 rate limits | TBD (preview API) | per-job generation limit (`max_generations_per_job: 5`), queue system |
| Voice recognition | Browser API — free, unlimited | No server cost; all processing in browser |

---

## 10. Open Questions

1. **Veo 3.1 audio in B-roll** — Veo generates native audio (conversations, SFX). For podcast B-roll, we likely want silent video with main podcast audio continuing. Should we strip Veo audio by default or offer a `mixed` option?

2. **Co-Pilot conversation memory** — Should the engine maintain conversation history across page refreshes? Current design is session-only. Persistent history would require DB storage.

3. **Auto-Edit validation** — When Gemini generates a full camera plan, should we auto-apply or always require human review? Current plan: always present for review with "Apply" button.

4. **Veo 3.1 pricing stability** — The API is in paid preview. Pricing may change. Need to surface cost estimates to the user before generation.

---

*This document is a research and planning artifact. No implementation changes should be made based on this document without explicit user approval and per-phase plan creation.*
