# Monetization Engine — Payments, Billing, Tier Enforcement & Feature Gates

**Author:** Opus (Antigravity)
**Date:** 2026-02-26
**Status:** DRAFT — Planning Only
**Reference:** `00-SAAS-MASTER-PLAN.md`, `02-TECH-STACK-COMPARISON.md`

---

## 1. Subscription Tiers — Full Specification

### 1.1 Tier Definitions

```python
# auth/models.py

from enum import IntEnum

class UserTier(IntEnum):
    """User subscription tiers, ordered by access level."""
    FREE = 0
    STARTER = 1
    PRO = 2
    TEAM = 3

TIER_CONFIG = {
    UserTier.FREE: {
        "display_name": "Free",
        "price_monthly": 0,
        "price_annual": 0,
        "stripe_price_monthly": None,
        "stripe_price_annual": None,
        "limits": {
            "episodes_per_month": 3,
            "ai_calls_per_month": 10,
            "veo_generations_per_month": 0,
            "max_cameras": 1,
            "max_export_platforms": 0,  # Render only, no publish
            "max_team_seats": 1,
            "max_upload_gb": 5,
            "render_quality": "draft",  # 720p, watermarked
        },
    },
    UserTier.STARTER: {
        "display_name": "Starter",
        "price_monthly": 19,
        "price_annual": 190,  # ~$15.83/mo
        "stripe_price_monthly": "price_starter_monthly",
        "stripe_price_annual": "price_starter_annual",
        "limits": {
            "episodes_per_month": 5,
            "ai_calls_per_month": 50,
            "veo_generations_per_month": 2,
            "max_cameras": 2,
            "max_export_platforms": 1,  # YouTube only
            "max_team_seats": 1,
            "max_upload_gb": 25,
            "render_quality": "standard",  # 1080p, no watermark
        },
    },
    UserTier.PRO: {
        "display_name": "Pro",
        "price_monthly": 69,
        "price_annual": 588,  # $49/mo
        "stripe_price_monthly": "price_pro_monthly",
        "stripe_price_annual": "price_pro_annual",
        "limits": {
            "episodes_per_month": 999,  # "Unlimited"
            "ai_calls_per_month": 999,
            "veo_generations_per_month": 20,
            "max_cameras": 4,
            "max_export_platforms": 999,  # All platforms
            "max_team_seats": 1,
            "max_upload_gb": 100,
            "render_quality": "ultra",  # 4K, HEVC 10-bit
        },
    },
    UserTier.TEAM: {
        "display_name": "Team / Agency",
        "price_monthly": 129,
        "price_annual": 1068,  # $89/mo
        "stripe_price_monthly": "price_team_monthly",
        "stripe_price_annual": "price_team_annual",
        "limits": {
            "episodes_per_month": 999,
            "ai_calls_per_month": 999,
            "veo_generations_per_month": 50,
            "max_cameras": 4,
            "max_export_platforms": 999,
            "max_team_seats": 5,  # Additional seats: $29/mo each
            "max_upload_gb": 500,
            "render_quality": "ultra",
        },
    },
}
```

### 1.2 Feature Access Matrix

```python
# gates/tier_gate.py

FEATURE_TIER_MAP: dict[str, UserTier] = {
    # Core pipeline (all tiers)
    "create_job": UserTier.FREE,
    "transcribe": UserTier.FREE,
    "basic_edit": UserTier.FREE,
    "filler_detection": UserTier.FREE,
    "view_transcript": UserTier.FREE,

    # Starter+ features
    "multi_cam_2": UserTier.STARTER,
    "broll_upload": UserTier.STARTER,
    "render_no_watermark": UserTier.STARTER,
    "publish_youtube": UserTier.STARTER,
    "saved_branding_kits": UserTier.STARTER,

    # Pro features
    "multi_cam_4": UserTier.PRO,
    "copilot_chat": UserTier.PRO,
    "copilot_auto_edit": UserTier.PRO,
    "copilot_voice": UserTier.PRO,
    "veo_generate_broll": UserTier.PRO,
    "veo_extend_video": UserTier.PRO,
    "publish_all_platforms": UserTier.PRO,
    "smart_crop_subject": UserTier.PRO,
    "ultra_quality_render": UserTier.PRO,
    "priority_render_queue": UserTier.PRO,

    # Team features
    "api_access": UserTier.TEAM,
    "white_label": UserTier.TEAM,
    "team_seats": UserTier.TEAM,
    "team_workspace": UserTier.TEAM,
    "priority_support": UserTier.TEAM,
    "custom_branding_removal": UserTier.TEAM,
}
```

---

## 2. Stripe Integration — Complete Flow

### 2.1 Subscription Lifecycle

```
User clicks "Subscribe to Pro" in UI
    │
    ▼
POST /billing/create-checkout
    │
    ├── 1. Create Stripe Customer (if not exists)
    │       └── stripe.Customer.create(email=user.email)
    │
    ├── 2. Create Checkout Session
    │       └── stripe.checkout.Session.create(
    │             customer=customer_id,
    │             price=price_pro_monthly,
    │             trial_period_days=14,
    │             success_url="/billing/success",
    │             cancel_url="/billing/cancel",
    │           )
    │
    └── 3. Return checkout_url → redirect user

    ▼
User completes payment on Stripe Checkout page
    │
    ▼
Stripe fires webhook: checkout.session.completed
    │
    ├── 4. Extract subscription_id, customer_id
    ├── 5. Update user profile in Supabase:
    │       profiles.update({
    │           tier: "pro",
    │           stripe_customer_id: customer_id,
    │           stripe_subscription_id: subscription_id,
    │       })
    ├── 6. Update JWT claims (tier: "pro")
    │       └── Supabase app_metadata update → next JWT issued has new tier
    ├── 7. Track event in PostHog: "subscription_created"
    │
    └── User redirected to /billing/success → "Welcome to Pro! 🎉"
```

### 2.2 Webhook Handler

```python
# billing/webhooks.py

import stripe
from fastapi import Request, HTTPException

async def handle_stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "invoice.payment_failed": _handle_payment_failed,
        "customer.subscription.trial_will_end": _handle_trial_ending,
    }

    handler = handlers.get(event["type"])
    if handler:
        await handler(event["data"]["object"])

    return {"received": True}

async def _handle_checkout_completed(session: dict) -> None:
    """New subscription created via checkout."""
    customer_id = session["customer"]
    subscription_id = session["subscription"]

    # Look up the subscription to get the price/tier
    sub = stripe.Subscription.retrieve(subscription_id)
    tier = _price_to_tier(sub["items"]["data"][0]["price"]["id"])

    # Update user in Supabase
    user_id = session["client_reference_id"]  # Set during checkout creation
    await update_user_tier(user_id, tier, customer_id, subscription_id)

    # Track analytics
    posthog.capture(user_id, "subscription_created", {
        "tier": tier,
        "price": sub["items"]["data"][0]["price"]["unit_amount"] / 100,
        "annual": sub["items"]["data"][0]["price"]["recurring"]["interval"] == "year",
    })

async def _handle_subscription_updated(subscription: dict) -> None:
    """Tier change (upgrade/downgrade)."""
    customer_id = subscription["customer"]
    new_tier = _price_to_tier(subscription["items"]["data"][0]["price"]["id"])
    user_id = await get_user_id_by_customer(customer_id)
    await update_user_tier(user_id, new_tier)

async def _handle_subscription_deleted(subscription: dict) -> None:
    """Subscription cancelled — downgrade to free."""
    customer_id = subscription["customer"]
    user_id = await get_user_id_by_customer(customer_id)
    await update_user_tier(user_id, "free")

async def _handle_payment_failed(invoice: dict) -> None:
    """Payment failed — send dunning email, don't immediately downgrade."""
    customer_id = invoice["customer"]
    # Stripe handles retries (3 attempts over 7 days by default)
    # Only downgrade after all retries fail (subscription.deleted event)
    logger.warning("payment_failed", customer_id=customer_id)

async def _handle_trial_ending(subscription: dict) -> None:
    """Trial ending in 3 days — send reminder email."""
    customer_id = subscription["customer"]
    user_id = await get_user_id_by_customer(customer_id)
    # Send email via transactional email service
    await send_trial_ending_email(user_id)
```

### 2.3 Metered Billing (AI Overages)

```python
# billing/usage.py

class MeterEventReporter:
    """Report metered usage to Stripe for overage billing."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._session = None
        self._session_expires: datetime | None = None

    async def report_ai_usage(
        self,
        customer_id: str,
        event_type: str,  # "ai_generation", "veo_generation"
        units: int = 1,
    ) -> None:
        """Report a single AI usage event for metered billing.

        This is called AFTER the user has exceeded their tier's
        included limit. Pre-limit usage is free/included.
        """
        await self._ensure_session()
        client = stripe.StripeClient(self._session["authentication_token"])
        client.v2.billing.meter_event_stream.create(
            params={
                "events": [{
                    "event_name": event_type,
                    "payload": {
                        "stripe_customer_id": customer_id,
                        "value": str(units),
                    },
                }]
            }
        )

    async def _ensure_session(self) -> None:
        if (
            self._session is None
            or self._session_expires <= datetime.now(timezone.utc)
        ):
            client = stripe.StripeClient(self._api_key)
            self._session = client.v2.billing.meter_event_session.create()
            self._session_expires = datetime.fromisoformat(
                self._session["expires_at"]
            )
```

### 2.4 Overage Pricing

```
Stripe Meter: "ai_generations"
  - Applies AFTER tier limits exhausted
  - Free/Starter: triggers metered billing immediately after limit
  - Pro/Team:     triggers after high included limit (999 effectively unlimited)

Overage Rates:
  - AI analysis call (Gemini):      $0.02/call
  - Veo 3.1 generation (720p):     $0.10/generation
  - Veo 3.1 generation (4K):       $0.50/generation
  - Additional render (per-platform): $0.05/render
```

---

## 3. Customer Self-Service Portal

### 3.1 Stripe Customer Portal

```python
# service/routes/billing.py

@router.post("/billing/portal")
async def create_portal_session(
    user: UserProfile = Depends(get_current_user),
) -> dict:
    """Redirect user to Stripe Customer Portal for self-service."""
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{APP_URL}/dashboard",
    )
    return {"url": session.url}
```

**Portal Features (Stripe-managed, zero code):**
- View/download invoices
- Update payment method
- Upgrade/downgrade subscription
- Cancel or pause subscription
- View upcoming invoice with overages

### 3.2 In-App Billing Endpoints

```python
# service/routes/billing.py

@router.get("/billing/status")
async def billing_status(
    user: UserProfile = Depends(get_current_user),
) -> BillingStatusResponse:
    """Current subscription status and usage."""
    return BillingStatusResponse(
        tier=user.tier.name,
        subscription_active=user.stripe_subscription_id is not None,
        current_period_end=get_period_end(user),
        usage=await get_current_usage(user.user_id),
        limits=TIER_CONFIG[user.tier]["limits"],
    )

@router.post("/billing/checkout")
async def create_checkout(
    request: CheckoutRequest,
    user: UserProfile = Depends(get_current_user),
) -> dict:
    """Create Stripe Checkout session for subscription."""
    stripe_price = TIER_CONFIG[UserTier[request.tier.upper()]]["stripe_price_monthly"]
    if request.annual:
        stripe_price = TIER_CONFIG[UserTier[request.tier.upper()]]["stripe_price_annual"]

    session = stripe.checkout.Session.create(
        customer=user.stripe_customer_id,
        client_reference_id=user.user_id,
        line_items=[{"price": stripe_price, "quantity": 1}],
        mode="subscription",
        allow_promotion_codes=True,
        subscription_data={"trial_period_days": 14},
        success_url=f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{APP_URL}/billing/cancel",
    )
    return {"checkout_url": session.url}
```

---

## 4. Feature Gate Implementation

### 4.1 FastAPI Dependency Pattern

```python
# gates/tier_gate.py

from functools import wraps
from fastapi import Depends, HTTPException

class FeatureGate:
    """Check if a user's tier allows access to a feature."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._usage = UsageTracker(redis_client)

    async def check(
        self,
        user: UserProfile,
        feature: str,
        consume_unit: str | None = None,  # e.g., "episodes", "ai_calls"
    ) -> GateResult:
        # Step 1: Check tier allows feature
        required_tier = FEATURE_TIER_MAP.get(feature, UserTier.FREE)
        if user.tier < required_tier:
            return GateResult(
                allowed=False,
                reason=f"'{feature}' requires {required_tier.name} tier",
                upgrade_prompt=True,
                upgrade_tier=required_tier.name,
            )

        # Step 2: Check usage quota (if consumable)
        if consume_unit:
            usage = await self._usage.check_and_increment(
                user.user_id,
                user.tier.name.lower(),
                consume_unit,
            )
            if not usage.allowed:
                return GateResult(
                    allowed=False,
                    reason=f"Monthly {consume_unit} limit reached "
                           f"({usage.current}/{usage.limit})",
                    overage=True,
                    overage_rate=OVERAGE_RATES.get(consume_unit, 0),
                )

        return GateResult(allowed=True)


# FastAPI dependency factory
def require_feature(feature: str, consume: str | None = None):
    """Dependency that checks feature access and usage limits."""
    async def _dependency(
        user: UserProfile = Depends(get_current_user),
        gate: FeatureGate = Depends(get_feature_gate),
    ) -> UserProfile:
        result = await gate.check(user, feature, consume)
        if not result.allowed:
            detail = {"error": result.reason}
            if result.upgrade_prompt:
                detail["upgrade_url"] = "/billing/checkout"
                detail["required_tier"] = result.upgrade_tier
            if result.overage:
                detail["overage_rate"] = result.overage_rate
                detail["overage_consent_url"] = "/billing/overage-consent"
            raise HTTPException(status_code=403, detail=detail)
        return user
    return _dependency
```

### 4.2 Usage in Routes

```python
# Existing routes — add feature gates with MINIMAL changes

# Before (no gate):
@router.post("/copilot/command")
async def copilot_command(request: CoPilotCommandRequest):
    ...

# After (with gate — 1 line change):
@router.post("/copilot/command")
async def copilot_command(
    request: CoPilotCommandRequest,
    user: UserProfile = Depends(require_feature("copilot_chat", consume="ai_calls")),
):
    ...

# Veo generation (gated + usage-tracked):
@router.post("/veo/generate")
async def generate_broll(
    request: VeoGenerateRequest,
    user: UserProfile = Depends(require_feature("veo_generate_broll", consume="veo_gens")),
):
    ...

# Job creation (episode counter):
@router.post("/jobs")
async def create_job(
    request: CreateJobRequest,
    user: UserProfile = Depends(require_feature("create_job", consume="episodes")),
):
    ...
```

### 4.3 Free Tier Watermark

```python
# stages/render.py — minimal change

async def _apply_watermark_if_needed(
    output_path: Path,
    user_tier: UserTier,
) -> Path:
    """Add watermark overlay for free-tier renders."""
    if user_tier > UserTier.FREE:
        return output_path  # No watermark for paid users

    # FFmpeg drawtext filter for watermark
    watermarked = output_path.with_stem(f"{output_path.stem}_wm")
    await run_ffmpeg([
        "-i", str(output_path),
        "-vf", (
            "drawtext=text='Made with AI Podcast Studio':"
            "fontsize=24:fontcolor=white@0.3:"
            "x=(w-tw)/2:y=h-th-20"
        ),
        "-c:a", "copy",
        str(watermarked),
    ])
    return watermarked
```

---

## 5. Trial System

### 5.1 Trial Flow

```
New user signs up
    │
    ├── Account created (tier: FREE)
    │
    ├── "Start 14-day Pro Trial" button
    │     │
    │     └── POST /billing/start-trial
    │           │
    │           ├── Create Stripe Checkout with trial_period_days=14
    │           ├── Requires payment method (no charge until trial ends)
    │           ├── Set tier to PRO in Supabase
    │           └── Track "trial_started" in PostHog
    │
    ├── During trial:
    │     ├── Full Pro access
    │     ├── Day 11: "Trial ending in 3 days" email
    │     ├── Day 14: Stripe charges first invoice
    │     └── If payment fails → downgrade to Free
    │
    └── After trial:
          ├── Successful charge → continue as Pro
          └── Cancelled → downgrade to Free
```

### 5.2 Trial Configuration

```python
TRIAL_CONFIG = {
    "days": 14,
    "tier": UserTier.PRO,        # Trial gives Pro access
    "require_card": True,         # Must add card to start trial
    "one_per_user": True,         # Only one trial ever
    "reminder_days_before": 3,    # Email 3 days before trial ends
}
```

---

## 6. Upgrade/Downgrade Handling

### 6.1 Upgrade (Immediate)

```python
async def upgrade_subscription(
    user: UserProfile,
    new_tier: UserTier,
) -> None:
    """Upgrade subscription — prorated charge for remaining period."""
    new_price = TIER_CONFIG[new_tier]["stripe_price_monthly"]

    stripe.Subscription.modify(
        user.stripe_subscription_id,
        items=[{
            "id": get_subscription_item_id(user),
            "price": new_price,
        }],
        proration_behavior="create_prorations",  # Charge difference immediately
    )

    await update_user_tier(user.user_id, new_tier.name.lower())
```

### 6.2 Downgrade (End of Period)

```python
async def downgrade_subscription(
    user: UserProfile,
    new_tier: UserTier,
) -> None:
    """Downgrade — takes effect at end of current billing period."""
    new_price = TIER_CONFIG[new_tier]["stripe_price_monthly"]

    # Schedule change for end of period (no immediate proration)
    stripe.Subscription.modify(
        user.stripe_subscription_id,
        items=[{
            "id": get_subscription_item_id(user),
            "price": new_price,
        }],
        proration_behavior="none",
        cancel_at_period_end=False,
    )

    # Don't change tier yet — wait for webhook at period end
    logger.info("downgrade_scheduled", user_id=user.user_id, new_tier=new_tier.name)
```

### 6.3 Pause Subscription

```python
async def pause_subscription(
    user: UserProfile,
    resume_date: datetime | None = None,
) -> None:
    """Pause subscription for up to 3 months."""
    max_pause = timedelta(days=90)

    stripe.Subscription.modify(
        user.stripe_subscription_id,
        pause_collection={
            "behavior": "void",  # Don't invoice during pause
            "resumes_at": int((resume_date or datetime.now() + max_pause).timestamp()),
        },
    )

    # Downgrade to Free during pause
    await update_user_tier(user.user_id, "free")
    posthog.capture(user.user_id, "subscription_paused", {"tier": user.tier.name})
```

---

## 7. Billing UI Components

### 7.1 Pricing Page (Streamlit)

```python
# ui/billing_page.py

def render_pricing():
    st.title("Choose Your Plan")

    cols = st.columns(4)

    for i, (tier, config) in enumerate(TIER_CONFIG.items()):
        with cols[i]:
            st.subheader(config["display_name"])
            if config["price_monthly"] == 0:
                st.metric("Price", "Free")
            else:
                st.metric("Price", f"${config['price_monthly']}/mo")
                annual_monthly = config['price_annual'] / 12
                st.caption(f"or ${annual_monthly:.0f}/mo billed annually")

            # Feature list
            limits = config["limits"]
            st.write(f"📹 {limits['episodes_per_month']} episodes/month")
            st.write(f"🎥 {limits['max_cameras']} camera{'s' if limits['max_cameras'] > 1 else ''}")
            st.write(f"🤖 {limits['ai_calls_per_month']} AI calls/month")
            st.write(f"✨ {limits['veo_generations_per_month']} Veo generations/month")

            if config["stripe_price_monthly"]:
                if st.button(f"Subscribe to {config['display_name']}", key=f"sub_{tier.name}"):
                    checkout_url = create_checkout(tier)
                    st.markdown(f"[Complete subscription]({checkout_url})")
```

### 7.2 Usage Dashboard

```python
# ui/usage_dashboard.py

def render_usage(user: UserProfile):
    st.subheader("📊 Usage This Month")

    usage = get_current_usage(user.user_id)
    limits = TIER_CONFIG[user.tier]["limits"]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Episodes",
            f"{usage.episodes}/{limits['episodes_per_month']}",
            delta=f"{limits['episodes_per_month'] - usage.episodes} remaining",
        )

    with col2:
        st.metric(
            "AI Calls",
            f"{usage.ai_calls}/{limits['ai_calls_per_month']}",
        )

    with col3:
        st.metric(
            "Veo Generations",
            f"{usage.veo_gens}/{limits['veo_generations_per_month']}",
        )

    # Progress bars
    for name, used, limit in [
        ("Episodes", usage.episodes, limits["episodes_per_month"]),
        ("AI Calls", usage.ai_calls, limits["ai_calls_per_month"]),
    ]:
        pct = min(used / max(limit, 1), 1.0)
        st.progress(pct, text=f"{name}: {used}/{limit}")

    # Upgrade prompt if near limits
    if usage.episodes >= limits["episodes_per_month"] * 0.8:
        st.warning("⚠️ You're running low on episodes this month. [Upgrade →](/billing)")
```

---

## 8. Coupon System

### 8.1 Pre-Configured Coupons

| Coupon Code | Discount | Duration | Use Case |
|-------------|----------|----------|----------|
| `LAUNCH20` | 20% off | 3 months | Launch promotion |
| `BETA50` | 50% off | Lifetime | Beta testers |
| `ANNUAL15` | 15% off | Annual (built into pricing) | Annual billing |
| `WINBACK` | 30% off | 1 month | Churned user recovery |
| `AFFILIATE_REFER` | 10% off | 1 month | Affiliate referral bonus |

### 8.2 Stripe Coupon Setup

```python
# Run once to create coupons in Stripe

stripe.Coupon.create(
    id="LAUNCH20",
    percent_off=20,
    duration="repeating",
    duration_in_months=3,
)

stripe.Coupon.create(
    id="BETA50",
    percent_off=50,
    duration="forever",
)

stripe.Coupon.create(
    id="WINBACK",
    percent_off=30,
    duration="once",
)
```

---

## 9. Revenue Tracking

### 9.1 PostHog Revenue Events

```python
# Track these events for revenue analytics:

# When subscription is created:
posthog.capture(user_id, "$page_view", properties={"$current_url": "/billing/success"})
posthog.capture(user_id, "subscription_created", {
    "tier": "pro",
    "revenue": 69.00,
    "currency": "USD",
    "annual": False,
    "trial": True,
    "coupon": "LAUNCH20" or None,
})

# When subscription upgrades:
posthog.capture(user_id, "subscription_upgraded", {
    "from_tier": "starter",
    "to_tier": "pro",
    "revenue_increase": 50.00,
})

# When subscription cancels:
posthog.capture(user_id, "subscription_cancelled", {
    "tier": "pro",
    "revenue_lost": 69.00,
    "reason": "too_expensive",  # from cancellation survey
    "months_active": 4,
})
```

### 9.2 Key Revenue Metrics Dashboard

| Metric | Formula | Target |
|--------|---------|--------|
| **MRR** | Sum of all active subscription monthly values | $10K by Month 12 |
| **Net MRR Growth** | MRR gained − MRR lost (from churn) | > 15%/mo |
| **ARPU** | Total MRR ÷ Paid users | > $55 |
| **Annual Run Rate (ARR)** | MRR × 12 | $120K by Month 12 |
| **Expansion Revenue** | Revenue from upgrades + overages | > 10% of MRR |
| **Contraction Revenue** | Revenue lost from downgrades | < 5% of MRR |

---

## 10. Integration Test Scenarios

```python
# tests/test_billing_integration.py

class TestSubscriptionLifecycle:
    """End-to-end billing tests using Stripe test mode."""

    async def test_free_user_cannot_access_pro_features(self, client):
        resp = await client.post("/copilot/command", headers=free_user_headers)
        assert resp.status_code == 403
        assert "requires PRO tier" in resp.json()["detail"]["error"]

    async def test_subscribe_upgrades_tier(self, client, stripe_mock):
        # Simulate checkout completed webhook
        await client.post("/billing/webhook", content=checkout_event)
        user = await get_user(user_id)
        assert user.tier == UserTier.PRO

    async def test_usage_counter_blocks_at_limit(self, client, redis_client):
        # Set counter to limit
        await redis_client.set(f"usage:{user_id}:episodes:2026-02", "3")
        resp = await client.post("/jobs", headers=free_user_headers)
        assert resp.status_code == 403
        assert "limit reached" in resp.json()["detail"]["error"]

    async def test_metered_overage_reported(self, client, stripe_mock):
        # Pro user exceeds Veo limit
        await redis_client.set(f"usage:{user_id}:veo_gens:2026-02", "20")
        resp = await client.post("/veo/generate", headers=pro_user_headers)
        # Should succeed but report overage to Stripe
        assert resp.status_code == 200
        stripe_mock.assert_meter_event_sent("veo_generation", 1)

    async def test_cancelled_user_downgraded(self, client, stripe_mock):
        # Simulate subscription deleted webhook
        await client.post("/billing/webhook", content=cancel_event)
        user = await get_user(user_id)
        assert user.tier == UserTier.FREE
```

---

*This document is the single source of truth for monetization implementation. Every billing interaction, feature gate, and usage limit is defined here. No ad-hoc billing logic elsewhere in the codebase.*
