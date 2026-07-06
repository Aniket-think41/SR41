"""
Billing & subscriptions via Razorpay (spec §5).

Fully scaffolded but inert until credentials are configured:
  - GET  /api/billing/config       → { enabled, key_id, plans } (UI hides
                                       upgrade buttons when enabled=False)
  - POST /api/billing/checkout     → create an order (402/503 when not enabled)
  - POST /api/billing/webhook      → Razorpay → mark paid + grant the plan
  - GET  /api/billing/subscription → current plans + recent payments

The plan is granted to the target entity (a user's personal space or an org)
only when a verified `paid` webhook arrives, so the same flow that works in
production is exercised end-to-end once keys are added.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import payments
from ..config import get_settings
from ..database import get_db
from ..entitlements import normalize_plan, org_entitlements, plan_catalog, spec_for, user_entitlements
from ..errors import not_found, service_unavailable, unauthorized, validation
from ..models import Organization, Payment, User
from ..permissions import org_by_slug, require_org_admin
from ..schemas import BillingCheckoutIn
from ..security import get_current_user

log = logging.getLogger("app.billing")
router = APIRouter(prefix="/api/billing", tags=["billing"])
settings = get_settings()

PAID_PLANS = ("PRO", "ENTERPRISE")


def _payment_out(p: Payment) -> dict:
    return {
        "id": p.id,
        "target_type": p.target_type,
        "target_id": p.target_id,
        "plan": p.plan,
        "amount": p.amount,
        "currency": p.currency,
        "status": p.status,
        "provider": p.provider,
        "created_at": p.created_at,
    }


@router.get("/config")
def billing_config():
    """What the frontend needs to decide whether to show upgrade UI."""
    return {**payments.public_config(), "plans": plan_catalog()}


@router.post("/checkout")
def checkout(
    body: BillingCheckoutIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = normalize_plan(body.plan)
    if plan not in PAID_PLANS:
        raise validation("plan must be PRO or ENTERPRISE")

    # Resolve the target entity and check the caller may upgrade it.
    if body.target_type == "org":
        if not body.org_slug:
            raise validation("org_slug is required when target_type is 'org'")
        org = org_by_slug(db, body.org_slug)
        require_org_admin(db, org, user)
        target_id, receipt = org.id, f"org:{org.slug}"
    else:
        target_id, receipt = user.id, f"user:{user.username}"

    # Graceful degradation: no Razorpay keys → no checkout (spec §5).
    if not payments.is_enabled():
        raise service_unavailable(
            "Online upgrades aren't available yet. Ask a platform admin to grant your plan in the meantime."
        )

    spec = spec_for(plan)
    pay = Payment(
        user_id=user.id, target_type=body.target_type, target_id=target_id,
        plan=plan, amount=spec.price_usd * 100, currency="USD",
    )
    db.add(pay)
    db.flush()
    order = payments.create_order(  # pragma: no cover - needs live credentials
        amount_cents=pay.amount, receipt=pay.id,
        notes={"payment_id": pay.id, "plan": plan, "target_type": body.target_type, "target_id": target_id},
    )
    pay.provider_order_id = order["id"]
    db.commit()
    return {
        "payment_id": pay.id,
        "order_id": order["id"],
        "amount": pay.amount,
        "currency": "USD",
        "key_id": settings.razorpay_key_id,
    }


def _grant_plan(db: Session, pay: Payment) -> None:
    if pay.target_type == "org":
        org = db.get(Organization, pay.target_id)
        if org:
            org.plan = pay.plan
    else:
        u = db.get(User, pay.target_id)
        if u:
            u.plan = pay.plan


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Razorpay payment webhook. Verifies the signature, marks the Payment paid,
    and grants the plan to the target entity. Inert until the webhook secret is
    configured."""
    if not payments.webhook_configured():
        raise service_unavailable("Payment webhooks are not configured")
    raw = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")
    if not payments.verify_webhook(raw, signature):
        raise unauthorized("Invalid webhook signature")

    event = json.loads(raw or b"{}")
    # Razorpay nests the order id under payload.payment.entity.order_id.
    entity = (
        event.get("payload", {}).get("payment", {}).get("entity", {})
        or event.get("payload", {}).get("order", {}).get("entity", {})
    )
    order_id = entity.get("order_id") or entity.get("id")
    payment_id = entity.get("id")
    event_type = event.get("event", "")

    if not order_id:
        return {"ok": True, "ignored": "no order id"}
    pay = db.query(Payment).filter(Payment.provider_order_id == order_id).first()
    if not pay:
        return {"ok": True, "ignored": "unknown order"}

    if event_type in ("payment.captured", "order.paid"):
        pay.status = "paid"
        pay.provider_payment_id = payment_id
        _grant_plan(db, pay)
        db.commit()
        log.info("Granted %s to %s:%s via payment %s", pay.plan, pay.target_type, pay.target_id, pay.id)
    elif event_type == "payment.failed":
        pay.status = "failed"
        db.commit()
    return {"ok": True}


@router.get("/subscription")
def subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Current plans (personal + owned orgs) and recent payments."""
    owned = db.query(Organization).filter(Organization.owner_id == user.id).all()
    recent = (
        db.query(Payment)
        .filter(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "user": user_entitlements(db, user),
        "orgs": [{"slug": o.slug, "name": o.name, **org_entitlements(db, o)} for o in owned],
        "payments": [_payment_out(p) for p in recent],
    }
