# Future MCP Tools: Platform Distribution & Upload

## Objective
Research and define the technical architecture for the `upload_to_platform` MCP server tool.
Currently, our `podcast-pipeline` handles encoding perfectly, but stops at exporting video files to disk. The goal is to build an automated distribution layer that publishes rendered files directly to social and podcasting platforms, utilizing 100% of the platform's features (custom thumbnails, tags, scheduling, descriptions).

## The Research Constraints
Because platform API availability is highly fragmented, this future MCP tool MUST support a hybrid architecture:
1. **Official OAuth APIs** — For platforms that support them.
2. **Headless Browser Automation (Playwright)** — For restrictive or locked-down platforms.

---

## Task for the Research Agent

Please investigate the following distribution targets and provide a technical architecture brief for each. For each platform, you must answer:
- Does it have a public upload API, or must we construct a Playwright UI bot?
- What are the authentication requirements (OAuth2, Cookies, API Keys)?
- What is the upload file size/duration limit?
- How do we attach custom thumbnail images (if supported)?

### Priority Target 1: YouTube
- **Assumption:** Supported via Google's `YouTube Data API v3`.
- **Requirements:** Detail the OAuth2 consent flow and the POST requests required to upload a 4K HEVC `.mp4`, attach a custom `.jpg` thumbnail, set the Privacy Status to "Scheduled", and inject the Title/Description/Tags.

### Priority Target 2: Spotify for Podcasters (Video)
- **Assumption:** Currently lacks a public API for direct Video MP4 upload (historically relies on RSS for audio, but video uploads require their dashboard).
- **Requirements:** If no Video Upload API exists, draft a Playwright architecture using the `playwright` Python library (or the existing Playwright MCP server). Outline the steps for injecting a session cookie, navigating to the dashboard, and programmatically attaching the file to the DOM drop-zone.

### Priority Target 3: Instagram (Reels)
- **Assumption:** Supported via the `Instagram Graph API` (for Instagram Professional accounts linked to Facebook Pages).
- **Requirements:** Detail the exact Graph API endpoints needed to upload a 9:16 vertical video from a local URL/path, set the cover image (thumbnail), and apply the caption.

### Priority Target 4: TikTok
- **Assumption:** The official `TikTok Content Posting API` is notoriously difficult to get production approval for without an enterprise partnership.
- **Requirements:** Cross-reference official API documentation versus the community standard of using a Playwright headless script. Propose the most resilient method for uploading `.mp4` files and injecting hashtags.

### Priority Target 5: X (Twitter)
- **Assumption:** Supported via the `X API v2`.
- **Requirements:** Detail the "Chunked Media Upload" flow. Videos over 15MB must be uploaded in chunks (`INIT`, `APPEND`, `FINALIZE`). Provide the architectural steps to encode the video, run the chunked upload, wait for Twitter's async backend processing (`STATUS`), and finally attach the `media_id` to a new Tweet.

---

## Output Expectations
Do not write code for this phase. Output a structured document detailing the endpoint URLs, the exact authentication scopes required, and the recommended Python libraries (`google-api-python-client`, `playwright`, `tweepy`, etc.) to execute this distribution layer.
