# Security & Compliance Plan

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only
**Reference:** `00-SAAS-MASTER-PLAN.md`

---

## 1. Compliance Requirements

### 1.1 GDPR (Required — EU Users)

| Requirement | Implementation | Priority |
|-------------|----------------|----------|
| **Legal basis for processing** | Contractual necessity (Terms of Service) + Consent for analytics | Week 7 |
| **Privacy policy** | Generated via Termly/Iubenda, customized for audio/video processing | Week 7 |
| **Data Processing Agreement (DPA)** | Template DPA available at `/legal/dpa` for enterprise customers | Week 8 |
| **Right to access** | API endpoint: `GET /user/data-export` → JSON dump of all user data | Week 6 |
| **Right to deletion** | API endpoint: `DELETE /user/account` → cascade delete all data + S3 assets | Week 6 |
| **Right to portability** | Data export includes jobs, transcripts, scripts, branding in standard formats | Week 6 |
| **Data minimization** | Only collect email, name; no unnecessary PII | Week 1 |
| **Breach notification** | Sentry alerts + documented incident response (notify within 72 hours) | Week 8 |
| **Cookie consent** | CookieYes banner for analytics cookies (PostHog) | Week 7 |
| **Sub-processor disclosure** | List all third-party processors: Supabase, Stripe, Sentry, PostHog, Gemini, Veo | Week 7 |

### 1.2 CCPA (Required — California Users)

| Requirement | Implementation |
|-------------|----------------|
| **"Do Not Sell" link** | Footer link → opt-out of analytics tracking |
| **Disclosure of data collected** | Privacy policy section on collected categories |
| **Right to delete** | Same as GDPR deletion endpoint |
| **Opt-out of sale** | Not selling data; document this clearly |

### 1.3 SOC 2 (Deferred)

SOC 2 Type II is NOT required for indie podcasters and small agencies. Defer until:
- Enterprise customers request it (> $500/mo contracts)
- Estimated cost: $20K–$50K for audit
- Trigger: $25K+ MRR with enterprise pipeline

---

## 2. Data Isolation Architecture

### 2.1 Database Level (PostgreSQL + Supabase RLS)

```
                    ┌────────────────────────────┐
                    │     PostgreSQL (Supabase)    │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │   Row Level Security    │  │
                    │  │                          │  │
                    │  │  User A sees →  A's jobs │  │
                    │  │  User B sees →  B's jobs │  │
                    │  │  Team X sees → X's jobs  │  │
                    │  │                          │  │
                    │  │  POLICY: auth.uid() =    │  │
                    │  │    user_id OR             │  │
                    │  │    team_id matches        │  │
                    │  └────────────────────────┘  │
                    └────────────────────────────┘
```

**Enforcement:** Every table with user data has RLS enabled. Even if application code has a bug, the database itself prevents cross-user reads.

### 2.2 Object Storage Level (S3/R2)

```
Bucket: podcast-studio-assets
├── users/{user_id}/          ← User-scoped prefix
│   ├── jobs/{job_id}/
│   │   ├── raw/
│   │   ├── intermediate/
│   │   └── output/
│   └── branding/
└── (no cross-user access)
```

**Enforcement:**
- Pre-signed URLs scoped to user prefix
- Backend validates `user_id` matches JWT before generating pre-signed URL
- No public bucket access
- Lifecycle policy: delete intermediate files after 30 days

### 2.3 Redis Level

```
Key pattern: {scope}:{user_id}:{resource}:{period}
Example:     usage:abc123:episodes:2026-02
             rate:abc123:requests
             session:abc123:token
```

**Enforcement:** All Redis keys include `user_id`. No global keys for user-specific data.

---

## 3. Authentication Security

### 3.1 JWT Security

| Control | Implementation |
|---------|----------------|
| **Algorithm** | HS256 with Supabase JWT secret (256-bit) |
| **Token expiry** | Access token: 1 hour; Refresh token: 7 days |
| **Token rotation** | Refresh tokens rotated on use (Supabase default) |
| **Token storage (web)** | `httpOnly` cookie (not localStorage) |
| **Token storage (desktop)** | Tauri secure storage (OS keychain) |
| **Invalid token response** | 401 with generic message (no leak of why) |

### 3.2 Password Security

| Control | Implementation |
|---------|----------------|
| **Hashing** | bcrypt via Supabase Auth (automatic) |
| **Minimum length** | 8 characters (Supabase default) |
| **Breach detection** | HaveIBeenPwned check via Supabase (if enabled) |
| **Rate limiting on login** | 5 attempts/minute per IP (slowapi) |
| **Account lockout** | 10 failed attempts → 15-minute lockout |

### 3.3 API Key Security (Team Tier)

| Control | Implementation |
|---------|----------------|
| **Key generation** | 32-byte random (secrets.token_urlsafe(32)) |
| **Key storage** | SHA-256 hash in DB; plaintext shown once on creation |
| **Key scoping** | Per-team, with defined permissions |
| **Key rotation** | User can regenerate from settings |
| **Rate limiting** | Same per-tier limits as JWT-authenticated requests |

---

## 4. API Security

### 4.1 Input Validation

```python
# All endpoints use Pydantic models for input validation
# Example: Job creation

class CreateJobRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    platforms: list[str] = Field(default_factory=list)

    @validator("platforms")
    def validate_platforms(cls, v):
        allowed = {"youtube", "spotify", "tiktok", "instagram", ...}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Unknown platforms: {invalid}")
        return v
```

### 4.2 Security Headers

```python
# service/app.py — security middleware

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response
```

### 4.3 CORS Configuration

```python
# Already exists in service/app.py — tighten for production

ALLOWED_ORIGINS = [
    "https://app.podcaststudio.com",      # Production web
    "tauri://localhost",                    # Tauri desktop
    "http://localhost:8501",               # Streamlit dev
    "http://localhost:8787",               # FastAPI dev
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)
```

### 4.4 Rate Limiting

```python
# Three layers of rate limiting:

# Layer 1: Global (all requests)
# 1000 req/min per IP — blocks DDoS
@app.middleware("http")
async def global_rate_limit(request, call_next):
    ...

# Layer 2: Per-user (authenticated requests)
# Tier-based: Free=5/min, Pro=100/min, Team=500/min
@router.post("/jobs/{id}/run")
@limiter.limit(lambda request: TIER_RATE_LIMITS[request.state.user.tier])
async def run_job(...):
    ...

# Layer 3: Per-resource (expensive operations)
# AI calls: Free=5/day, Pro=unlimited
@router.post("/copilot/command")
@limiter.limit("5/day", key_func=get_user_identifier)
async def copilot_command(...):  # Overridden for Pro+ via tier check
    ...
```

---

## 5. Data Encryption

### 5.1 Encryption at Rest

| Data | Encryption | Provider |
|------|-----------|----------|
| Database (PostgreSQL) | AES-256 | Supabase (automatic) |
| Object Storage (S3/R2) | AES-256 | AWS S3/Cloudflare R2 (automatic) |
| Redis cache | TLS in transit | Upstash (automatic) |
| User API keys | AES-256 (application-level) | Custom encrypt/decrypt |
| BYOK API keys | AES-256-GCM per-user | Supabase Vault or app-level |

### 5.2 Encryption in Transit

| Path | Protocol | Certificate |
|------|----------|------------|
| Client → API | HTTPS/TLS 1.3 | Render auto-SSL (Let's Encrypt) |
| API → Database | TLS | Supabase (automatic) |
| API → Redis | TLS | Upstash (automatic) |
| API → Stripe | HTTPS/TLS 1.3 | Stripe (automatic) |
| WebSocket | WSS (TLS) | Render auto-SSL |

### 5.3 BYOK API Key Encryption

```python
# auth/encryption.py

from cryptography.fernet import Fernet

class APIKeyEncryptor:
    """Encrypt/decrypt user-provided API keys (BYOK)."""

    def __init__(self, master_key: str) -> None:
        self._fernet = Fernet(master_key.encode())

    def encrypt(self, plaintext_key: str) -> str:
        return self._fernet.encrypt(plaintext_key.encode()).decode()

    def decrypt(self, encrypted_key: str) -> str:
        return self._fernet.decrypt(encrypted_key.encode()).decode()

# Usage:
# encryptor = APIKeyEncryptor(os.environ["ENCRYPTION_MASTER_KEY"])
# stored = encryptor.encrypt(user_gemini_key)  # Store in DB
# key = encryptor.decrypt(stored)              # Use for API call
```

---

## 6. File Upload Security

### 6.1 Upload Validation

```python
ALLOWED_VIDEO_TYPES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_AUDIO_TYPES = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
ALLOWED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB per file
MAX_FILES_PER_JOB = 10

async def validate_upload(file: UploadFile) -> None:
    # 1. Check file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_TYPES | ALLOWED_AUDIO_TYPES | ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, f"Unsupported file type: {ext}")

    # 2. Check file size (Content-Length header)
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(413, f"File exceeds {MAX_FILE_SIZE // (1024**3)}GB limit")

    # 3. Validate magic bytes (first 8 bytes) match claimed type
    header = await file.read(8)
    await file.seek(0)
    if not validate_magic_bytes(header, ext):
        raise HTTPException(415, "File content does not match extension")
```

### 6.2 Malware Scanning

- **Phase 1:** Magic byte validation only (sufficient for media files)
- **Phase 2 ($10K+ MRR):** ClamAV scan on upload (Docker sidecar)
- **Phase 3:** Third-party scanning API (VirusTotal) for Team tier

---

## 7. Incident Response

### 7.1 Response Procedure

```
1. DETECT   → Sentry alert / user report / monitoring anomaly
2. ASSESS   → Severity classification (Critical/High/Medium/Low)
3. CONTAIN  → Isolate affected systems, revoke compromised tokens
4. NOTIFY   → If personal data breach:
              → Notify affected users within 24 hours
              → Notify GDPR authority within 72 hours
5. REMEDIATE → Fix vulnerability, deploy patch
6. POSTMORTEM → Document root cause, preventive measures
```

### 7.2 Severity Classification

| Severity | Example | Response Time | Notification |
|----------|---------|--------------|-------------|
| **Critical** | Data breach, auth bypass | < 1 hour | All users + authority |
| **High** | Payment data exposure | < 4 hours | Affected users |
| **Medium** | Service outage > 30 min | < 24 hours | Status page |
| **Low** | Minor bug, UI issue | < 72 hours | Changelog |

---

## 8. Compliance Checklist

### Pre-Launch (Week 8)

- [ ] Privacy policy published at `/privacy`
- [ ] Terms of service published at `/terms`
- [ ] Cookie consent banner active (PostHog)
- [ ] "Do Not Sell" link in footer (CCPA)
- [ ] Data deletion endpoint functional (`DELETE /user/account`)
- [ ] Data export endpoint functional (`GET /user/data-export`)
- [ ] Sub-processor list documented
- [ ] DPA template available for download
- [ ] Security headers on all responses
- [ ] CORS locked to production origins
- [ ] Rate limiting active on all endpoints
- [ ] RLS policies tested (cross-user access denied)
- [ ] File upload validation active
- [ ] HTTPS enforced (HSTS header)
- [ ] Stripe PCI compliance (Stripe handles card data — no PCI scope on our end)

### Post-Launch (Quarterly Review)

- [ ] Dependency audit (`pip-audit`, already in CI)
- [ ] RLS policy review (any new tables?)
- [ ] Rate limit tuning (check abuse patterns)
- [ ] Sentry error review (any unhandled auth errors?)
- [ ] GDPR deletion requests processed (if any)
- [ ] Privacy policy updated for new features/processors

---

*This document covers requirements for indie/SMB podcast users. Enterprise compliance (SOC 2, HIPAA) is explicitly deferred until enterprise revenue justifies the audit cost.*
