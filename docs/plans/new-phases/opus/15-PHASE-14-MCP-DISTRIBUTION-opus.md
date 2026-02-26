# Phase 14: Automated Publishing & MCP Distribution — Detailed EPC

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Research & Planning Only
**Supersedes:** `15-PHASE-14-MCP-DISTRIBUTION.md` (skeleton)
**Depends on:** Phase 11 (render extensions for multi-cam/B-roll output)
**Reference:** `11-AI-PODCAST-STUDIO-ARCHITECTURE-opus.md` (EPC-5), `docs/plans/11-research.md` (verified code)

---

## 1. Goal

Implement automated one-click publishing to all major platforms:

1. **YouTube** — OAuth2 + resumable upload via YouTube Data API v3
2. **Spotify** — RSS feed generation via `feedgen` (no upload API exists)
3. **TikTok** — Content Posting API with file upload
4. **Instagram** — Playwright browser automation (no public upload API for Reels)
5. **Smart content generation** — AI-generated titles, descriptions, and thumbnails per platform
6. **Branding kit auto-application** — saved kits automatically applied per platform during render

---

## 2. Current State Analysis

### 2.1 Already Researched (HIGH Confidence)

The `docs/plans/11-research.md` file contains **800+ lines of verified research** including:

- ✅ YouTube OAuth2 flow + resumable upload (code examples, quota limits)
- ✅ Spotify RSS feed generation via `feedgen` (no upload API — confirmed)
- ✅ TikTok Content Posting API flow (init → chunk upload → status poll)
- ✅ Playwright fallback architecture for Instagram
- ✅ `smart_crop_subject` YuNet face detection + sendcmd approach
- ✅ `overlay_video` FFmpeg filter_complex patterns

### 2.2 What Already Exists

| Component | Location | Relevance |
|-----------|----------|-----------|
| Platform specs | `config.yaml` platforms section | 13 platform export profiles (YouTube, Spotify, TikTok, Instagram, etc.) |
| Render stage | `stages/render.py` | Per-platform rendering with quality controls, branding, captions |
| Branding profiles | `models/branding.py` | Per-platform overrides, logo, colors, fonts, sound kits |
| Marketing copy | `stages/render.py` | AI-generated titles/descriptions per platform (Gemini/Claude) |
| Thumbnail generation | `utils/thumbnails.py` | Gemini Vision AI thumbnail generation |
| MCP tools | `mcp/ffmpeg_server.py` | 14 existing FFmpeg tools + registration pattern |

### 2.3 What Doesn't Exist Yet

| Component | Purpose |
|-----------|---------|
| `uploaders/base.py` | `PlatformUploader` protocol |
| `uploaders/youtube.py` | YouTube Data API v3 uploader |
| `uploaders/spotify_rss.py` | RSS feed generator + hosting push |
| `uploaders/tiktok.py` | TikTok Content Posting API uploader |
| `uploaders/playwright_base.py` | Browser automation base for Instagram |
| `service/routes/publish.py` | REST endpoints for publish operations |
| MCP tool: `upload_to_platform` | Unified publishing MCP tool |
| MCP tool: `smart_crop_subject` | Dynamic face-tracking crop for vertical exports |

---

## 3. Architecture

### 3.1 Uploader Protocol

```python
# uploaders/base.py

class UploadResult(BaseModel):
    """Result of a platform upload attempt."""
    platform: str
    success: bool
    url: str | None = None        # public URL if available
    platform_id: str | None = None # platform-specific ID (video ID, etc.)
    error: str | None = None
    metadata: dict[str, Any] = {}  # platform-specific response data

class PlatformUploader(Protocol):
    """Protocol for platform-specific uploaders."""

    platform_name: str

    async def upload(
        self,
        file_path: Path,
        title: str,
        description: str,
        *,
        thumbnail_path: Path | None = None,
        tags: list[str] | None = None,
        privacy: str = "private",
        **kwargs: Any,
    ) -> UploadResult:
        """Upload a file to the platform."""
        ...

    async def check_credentials(self) -> bool:
        """Verify that credentials are valid and not expired."""
        ...
```

### 3.2 YouTube Uploader

```python
# uploaders/youtube.py
# Implementation follows verified pattern from docs/plans/11-research.md

class YouTubeUploader:
    """YouTube Data API v3 resumable upload.

    Quota: videos.insert costs 1,600 units.
    Default daily quota: 10,000 units (= 6 uploads/day).
    Apply for quota increase in Google Cloud Console for production.
    """

    platform_name = "youtube"

    def __init__(
        self,
        client_secrets_path: Path,
        token_path: Path = Path("~/.cache/podcast-pipeline/youtube_token.json"),
    ) -> None:
        self._secrets_path = client_secrets_path
        self._token_path = token_path.expanduser()

    async def upload(
        self,
        file_path: Path,
        title: str,
        description: str,
        *,
        thumbnail_path: Path | None = None,
        tags: list[str] | None = None,
        privacy: str = "private",
        category_id: str = "22",  # People & Blogs
        **kwargs: Any,
    ) -> UploadResult:
        """Upload video with resumable upload + optional thumbnail."""
        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": category_id,
                "tags": tags or [],
            },
            "status": {"privacyStatus": privacy},
        }

        media = MediaFileUpload(str(file_path), chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            _, response = request.next_chunk()

        video_id = response["id"]

        # Upload thumbnail if provided
        if thumbnail_path and thumbnail_path.exists():
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail_path)),
                ).execute()
            except Exception as e:
                logger.warning("thumbnail_upload_failed", video_id=video_id, error=str(e))

        return UploadResult(
            platform="youtube",
            success=True,
            url=f"https://www.youtube.com/watch?v={video_id}",
            platform_id=video_id,
            metadata={"privacy": privacy, "category_id": category_id},
        )
```

### 3.3 Spotify RSS Uploader

```python
# uploaders/spotify_rss.py

class SpotifyRSSUploader:
    """Spotify integration via RSS feed generation.

    Spotify has NO upload API. The integration path is:
    1. Host the audio file on web-accessible storage
    2. Generate/update podcast RSS feed XML
    3. Push RSS to hosting location
    4. Spotify polls automatically (typically within 1 hour)
    """

    platform_name = "spotify"

    def __init__(
        self,
        feed_path: Path,
        podcast_title: str,
        podcast_link: str,
        storage_upload_fn: Callable | None = None,  # custom upload handler
    ) -> None:
        self._feed_path = feed_path
        self._podcast_title = podcast_title
        self._podcast_link = podcast_link
        self._storage_upload = storage_upload_fn

    async def upload(
        self,
        file_path: Path,
        title: str,
        description: str,
        *,
        audio_url: str | None = None,  # pre-hosted URL
        episode_number: int | None = None,
        **kwargs: Any,
    ) -> UploadResult:
        """Add episode to RSS feed. Spotify ingests automatically."""
        # If no pre-hosted URL, upload to configured storage
        if audio_url is None and self._storage_upload:
            audio_url = await self._storage_upload(file_path)
        if audio_url is None:
            return UploadResult(
                platform="spotify",
                success=False,
                error="No audio_url provided and no storage upload configured",
            )

        # Generate RSS feed entry
        fg = FeedGenerator()
        fg.load_extension("podcast")
        fg.id(self._podcast_link)
        fg.title(self._podcast_title)
        fg.link(href=self._podcast_link, rel="alternate")

        fe = fg.add_entry()
        fe.id(audio_url)
        fe.title(title)
        fe.description(description)
        fe.published(datetime.now(tz=timezone.utc))
        fe.enclosure(audio_url, str(file_path.stat().st_size), "audio/mpeg")

        if episode_number:
            fe.podcast.itunes_episode(str(episode_number))

        fg.rss_file(str(self._feed_path), pretty=True)

        return UploadResult(
            platform="spotify",
            success=True,
            url=audio_url,
            metadata={"feed_path": str(self._feed_path), "delivery": "rss"},
        )
```

### 3.4 TikTok Uploader

```python
# uploaders/tiktok.py

class TikTokUploader:
    """TikTok Content Posting API uploader.

    WARNING: Until TikTok app audit is complete, all uploads are
    forced to SELF_ONLY privacy regardless of requested level.
    Rate limit: 6 requests/min, 5 uploads/24h (unaudited).
    """

    platform_name = "tiktok"
    API_BASE = "https://open.tiktokapis.com/v2"

    def __init__(self, access_token: str) -> None:
        self._token = access_token

    async def upload(
        self,
        file_path: Path,
        title: str,
        description: str,
        *,
        privacy: str = "SELF_ONLY",
        **kwargs: Any,
    ) -> UploadResult:
        """Upload via Content Posting API init → chunk upload → poll."""
        # Implementation follows verified pattern from 11-research.md
        # Step 1: Init upload session
        # Step 2: Upload file chunks via PUT
        # Step 3: Poll for PUBLISH_COMPLETE status
        ...
```

### 3.5 Playwright Fallback

```python
# uploaders/playwright_base.py

class PlaywrightUploader:
    """Browser automation base for platforms without upload APIs.

    Uses Playwright with persistent browser state (cookies) to
    automate file upload through the platform's web interface.
    """

    def __init__(
        self,
        state_path: Path = Path("~/.cache/podcast-pipeline/browser_state.json"),
    ) -> None:
        self._state_path = state_path.expanduser()

    async def _get_browser_context(self) -> BrowserContext:
        """Get browser context with persisted auth state."""
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=True)

        if self._state_path.exists():
            return await browser.new_context(
                storage_state=str(self._state_path)
            )
        return await browser.new_context()

    async def save_state(self, context: BrowserContext) -> None:
        """Save browser cookies/localStorage for next session."""
        await context.storage_state(path=str(self._state_path))
```

---

## 4. Smart Crop Subject (MCP Tool)

### 4.1 Purpose

Convert 16:9 landscape podcast footage to 9:16 vertical (TikTok/Reels/Shorts) with dynamic speaker-tracking crop. This is critical for the automated publishing pipeline — without it, vertical exports use static center-crop which often frames empty space.

### 4.2 Architecture

Two-pass approach (from `11-research.md`, verified):

**Pass 1 (OpenCV analysis):** YuNet face detection + TrackerMIL + EMA smoothing → sendcmd file
**Pass 2 (FFmpeg render):** `crop@cam` + `sendcmd=f={file}` → final crop

Full implementation specification is documented in `11-research.md` lines 307–438 with verified code examples.

### 4.3 Integration Point

The `smart_crop_subject` tool runs BEFORE platform-specific rendering when target aspect ratio is 9:16:

```
render_platform("tiktok")
  → detect aspect_ratio = "9:16"
  → if smart_crop_enabled:
      → run smart_crop_subject(input_video, sendcmd_file)
      → use sendcmd_file in render filter_complex
    else:
      → static center crop (existing behavior)
```

---

## 5. Publishing Pipeline Integration

### 5.1 Render → Publish Flow

```
render_stage.run() → per-platform exports
        │
        ▼
┌──────────────────────────────┐
│  PUBLISH STAGE (new)          │
│                               │
│  For each rendered platform:  │
│  1. Load marketing copy       │
│  2. Select uploader           │
│  3. Upload with metadata      │
│  4. Record result             │
└──────────┬───────────────────┘
           │
           ▼
  publish_results.json
  {
    "youtube": {"success": true, "url": "...", "video_id": "..."},
    "spotify": {"success": true, "url": "...", "delivery": "rss"},
    "tiktok":  {"success": false, "error": "SELF_ONLY restriction"}
  }
```

### 5.2 Credential Management

```yaml
# config.yaml additions

publishing:
  enabled: false
  auto_publish: false               # require manual confirmation before upload
  default_privacy: private          # private | unlisted | public

  youtube:
    enabled: false
    client_secrets: ~/.config/podcast-pipeline/youtube_secrets.json
    token_path: ~/.cache/podcast-pipeline/youtube_token.json
    default_privacy: private
    default_category: "22"           # People & Blogs

  spotify:
    enabled: false
    feed_path: ./podcast_feed.xml
    podcast_title: ""
    podcast_link: ""
    storage_type: local              # local | s3 | gcs

  tiktok:
    enabled: false
    # Access token stored in environment: TIKTOK_ACCESS_TOKEN

  instagram:
    enabled: false
    browser_state: ~/.cache/podcast-pipeline/ig_browser_state.json
    headless: true
```

---

## 6. Smart Content Generation

### 6.1 AI-Generated Platform Metadata

The existing marketing copy pipeline (Phases 6.1) already generates per-platform titles and descriptions. Phase 14 extends this with:

- **Hashtag generation** — platform-specific hashtags from transcript topics
- **Thumbnail text overlay** — AI-suggested text for thumbnail captions
- **Scheduled posting** — AI-recommended posting times based on audience analytics
- **Cross-platform linking** — auto-insert links to other platform versions in descriptions

### 6.2 Auto-Applied Branding Kits

The existing `BrandingProfile.resolved_for_platform()` returns a flat profile per platform. Phase 14 adds:

```python
# Extension to models/branding.py

class AutoPublishProfile(BaseModel):
    """Publishing-specific branding settings per platform."""
    platform: str
    branding_profile: str            # name of BrandingProfile to use
    default_privacy: str = "private"
    auto_thumbnail: bool = True      # generate and upload thumbnail
    auto_captions: bool = True       # burn captions for this platform
    smart_crop: bool = True          # use smart_crop_subject for vertical
    hashtags: list[str] = []         # default hashtags
    end_screen_template: str | None = None  # YouTube end screen
```

---

## 7. MCP Tool Expansion Summary

### 7.1 New Tools for Phase 14

| Tool | File | Inputs | Outputs |
|------|------|--------|---------|
| `upload_to_platform` | `uploaders/` | platform, file_path, title, description, privacy | UploadResult (url, platform_id, success) |
| `smart_crop_subject` | `ffmpeg_toolkit.py` | input_path, output_path, target_aspect | cropped video with dynamic tracking |

### 7.2 MCP Server Registration

```python
# mcp/ffmpeg_server.py additions

@mcp.tool()
def upload_to_platform(
    platform: str,          # youtube | spotify | tiktok | instagram
    file_path: str,
    title: str,
    description: str,
    privacy: str = "private",
    thumbnail_path: str | None = None,
) -> dict:
    """Upload rendered content to a social media platform."""
    ...

@mcp.tool()
def smart_crop_subject(
    input_path: str,
    output_path: str,
    crop_aspect: str = "9:16",   # target aspect ratio
    detection_interval: int = 5,  # re-detect every N frames
    smoothing_alpha: float = 0.15,
) -> dict:
    """Dynamically crop video to track the active speaker's face."""
    ...
```

---

## 8. Estimated Plan Breakdown

| Plan | Scope | Dependencies |
|------|-------|-------------|
| **14-01** | `uploaders/base.py` — PlatformUploader protocol, UploadResult model | None |
| **14-02** | `uploaders/youtube.py` — YouTube OAuth2 + resumable upload | 14-01 |
| **14-03** | `uploaders/spotify_rss.py` — RSS feed generation via feedgen | 14-01 |
| **14-04** | `uploaders/tiktok.py` — Content Posting API chunk upload | 14-01 |
| **14-05** | `uploaders/playwright_base.py` — browser automation for Instagram | 14-01 |
| **14-06** | `smart_crop_subject` — YuNet + sendcmd two-pass dynamic crop | None |
| **14-07** | Config extension — `publishing` yaml section, credential management | 14-01 |
| **14-08** | `service/routes/publish.py` — REST endpoints + publish stage | 14-02 to 14-05 |
| **14-09** | MCP registration — `upload_to_platform` + `smart_crop_subject` tools | 14-06, 14-08 |
| **14-10** | Integration tests — mock uploads, RSS validation, crop accuracy, regression suite | All above |

---

## 9. Success Criteria

| # | Criterion |
|---|-----------|
| 1 | YouTube upload succeeds with resumable upload + thumbnail |
| 2 | Spotify RSS feed generates valid XML accepted by feed validators |
| 3 | TikTok upload completes (SELF_ONLY until audit) |
| 4 | Playwright uploads to Instagram (headless Chromium) |
| 5 | Smart crop tracks speaker face across 60min video |
| 6 | Vertical (9:16) exports use smart crop instead of static center-crop |
| 7 | Publishing results persisted in `publish_results.json` |
| 8 | All existing tests pass (zero regressions) |

---

## 10. New Dependencies

```bash
# Publishing extras (new optional group in pyproject.toml)
[project.optional-dependencies]
publish = [
    "google-api-python-client>=2.0",
    "google-auth-oauthlib>=1.0",
    "feedgen>=0.9.0",
    "playwright>=1.49",
]

# Post-install for Playwright
uv run playwright install chromium
```

---

## 11. Risk & Limitation Summary

| Risk | Impact | Mitigation |
|------|--------|------------|
| YouTube quota (6/day free) | Cannot publish multiple episodes daily | Apply for quota increase; add pre-upload quota check |
| TikTok SELF_ONLY | Videos invisible to public | Start audit immediately; Playwright fallback |
| Spotify no video RSS | Video episodes require YouTube cross-linking | Audio-only RSS for Spotify; video via YouTube |
| Instagram bot detection | Playwright may be detected and blocked | playwright-stealth plugin; rate limiting; manual fallback |
| Smart crop model download | First-run downloads 1.8MB ONNX model | Auto-download to `~/.cache/podcast-pipeline/models/`; log clearly |

---

*This document is a research and planning artifact. No implementation changes should be made based on this document without explicit user approval and per-phase plan creation.*
