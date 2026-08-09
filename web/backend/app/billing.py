"""Stripe integration: Checkout session creation for subscriptions, the
one-off credit top-up, and per-job instructions unlocks, plus the webhook
handler that turns Stripe events into real plan/credit changes.

Kept separate from auth.py (which has the plan/credit model but no
Stripe dependency at all) and main.py (which just wires these functions
into routes) -- mirrors this project's existing separation of concerns
(content_filter.py, rate_limit.py, storage.py).

We never touch card numbers directly -- every flow below uses Stripe's
own hosted Checkout page, which keeps this app entirely out of PCI scope.
No custom card form exists or should be added.
"""
from __future__ import annotations

import os

import stripe

from . import auth

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

# Live-mode Price IDs (Phase 6d), created via scripts/create_stripe_prices.py
# and hardcoded here rather than read from an env var -- per
# web/DEPLOYMENT.md's Phase 6b, which explicitly asks for this rather than
# expecting them pre-set. Stripe test and live modes are completely
# separate environments with their own Price IDs; these have to match
# whichever mode STRIPE_SECRET_KEY (in Railway) is currently set to, or
# Checkout session creation fails outright (a live key can't create a
# session against a test-mode Price, and vice versa).
#
# The original test-mode set (kept here for reference, not used once
# STRIPE_SECRET_KEY is live): builder price_1U1jmTDJhBkIl2qGHfCf8geE, pro
# price_1U1vK9DJhBkIl2qGRu9iF2LQ, topup price_1U1jmUDJhBkIl2qGMAmLAJsR.
PRICE_IDS = {
    "builder": "price_1U1wEpDJhBkIl2qGAPTrPbEn",  # £9/mo, 12 credits
    "pro": "price_1U1wFsDJhBkIl2qGPJArx7aq",  # £20/mo, 30 credits (Master Builder)
    # An earlier live Price (price_1U1wEpDJhBkIl2qG6VJNcmXf) was created at £25 by mistake --
    # scripts/create_stripe_prices.py still had the pre-price-change amount hardcoded, never
    # updated when the test-mode price was fixed via a one-off command instead of editing the
    # actual script. Archived (active=False), not deleted -- same reasoning as the earlier £25
    # test-mode mistake: Stripe won't delete a Price with billing history, and archiving is
    # enough to stop it being offered again. The script itself is now fixed too.
}
TOPUP_PRICE_ID = "price_1U1wEqDJhBkIl2qG1vwOGy6G"  # £6 one-time, +5 credits
TOPUP_CREDITS = 5

# Reverse lookup for the webhook handler: a subscription event carries a
# Price ID, not a plan name.
_PRICE_ID_TO_PLAN = {v: k for k, v in PRICE_IDS.items()}

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _get_or_create_customer(user: auth.User, force_new: bool = False) -> str:
    """Every Checkout Session needs a Stripe Customer -- created once per
    user, on first checkout, and reused after (stored on our own users
    row, not looked up from Stripe on every call).

    force_new bypasses the stored ID -- used by _create_checkout_session
    below to self-heal a stripe_customer_id that's stale for the *current*
    STRIPE_SECRET_KEY's mode. Confirmed as a real production failure, not
    a hypothetical: an account that transacted while STRIPE_SECRET_KEY was
    still test-mode has a customer ID that only exists in test mode's
    entirely separate object space -- Stripe rejects any live-mode call
    referencing it with "No such customer ... a similar object exists in
    test mode". That's a one-time transition case per affected account
    (once it has a live-mode customer, it stays valid), not an ongoing
    cost, so this is handled by retrying on failure rather than verifying
    the stored ID on every single checkout."""
    if user.stripe_customer_id and not force_new:
        return user.stripe_customer_id
    customer = stripe.Customer.create(email=user.email, metadata={"user_id": user.id})
    auth.set_stripe_customer_id(user.id, customer.id)
    return customer.id


def _create_checkout_session(user: auth.User, **session_kwargs) -> str:
    """Shared by all three checkout flows below: resolves the user's Stripe
    Customer and creates the session, retrying once with a freshly created
    Customer if the stored one turns out to be invalid for the current API
    key's mode (see _get_or_create_customer's own docstring)."""
    customer_id = _get_or_create_customer(user)
    try:
        session = stripe.checkout.Session.create(customer=customer_id, **session_kwargs)
    except stripe.InvalidRequestError as exc:
        if "No such customer" not in str(exc):
            raise
        customer_id = _get_or_create_customer(user, force_new=True)
        session = stripe.checkout.Session.create(customer=customer_id, **session_kwargs)
    return session.url


def create_subscription_checkout(user: auth.User, plan: str) -> str:
    """Returns a Checkout URL for a Free -> Builder/Master Builder upgrade,
    or a Builder <-> Master Builder change. The actual plan/credit change
    happens later, driven by the webhook's subscription events below --
    not here -- since the user hasn't actually paid until Stripe confirms
    it."""
    if plan not in PRICE_IDS:
        raise ValueError(f"Unknown plan: {plan!r}")
    return _create_checkout_session(
        user,
        mode="subscription",
        line_items=[{"price": PRICE_IDS[plan], "quantity": 1}],
        success_url=f"{FRONTEND_URL}/pricing?checkout=success",
        cancel_url=f"{FRONTEND_URL}/pricing?checkout=cancelled",
        client_reference_id=user.id,
    )


def create_topup_checkout(user: auth.User) -> str:
    """+5 credits for £6, one-time payment, available regardless of plan.
    Stacks on top of the user's existing credits_remaining -- see
    auth.add_credits -- rather than replacing it."""
    return _create_checkout_session(
        user,
        mode="payment",
        line_items=[{"price": TOPUP_PRICE_ID, "quantity": 1}],
        success_url=f"{FRONTEND_URL}/pricing?checkout=success",
        cancel_url=f"{FRONTEND_URL}/pricing?checkout=cancelled",
        metadata={"type": "topup", "user_id": user.id},
    )


def create_unlock_instructions_checkout(user: auth.User, job_id: str, price_gbp: int) -> str:
    """The one flow with a genuinely dynamic price (£5-15, scaled by part
    count -- see jobs.py::_estimate_instructions_price_gbp), so this uses
    an inline price_data line item instead of one of the fixed Prices
    above -- there's no way to pre-create a Price for an amount that isn't
    known until the model exists."""
    return _create_checkout_session(
        user,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "gbp",
                    "unit_amount": price_gbp * 100,
                    "product_data": {"name": f"BrickForgerAI .ldr file + parts list ({job_id})"},
                },
                "quantity": 1,
            }
        ],
        success_url=f"{FRONTEND_URL}/generate/{job_id}?checkout=success",
        cancel_url=f"{FRONTEND_URL}/generate/{job_id}?checkout=cancelled",
        metadata={"type": "unlock_instructions", "job_id": job_id, "user_id": user.id},
    )


def create_gallery_purchase_checkout(user: auth.User, job_id: str, price_gbp: int) -> str:
    """A non-creator buying access to someone else's published gallery
    build. Same inline price_data shape as create_unlock_instructions_checkout
    (dynamic £5-15 price, no fixed Price object makes sense here either) --
    deliberately a distinct "gallery_purchase" metadata type rather than
    reusing "unlock_instructions", since the webhook needs to route this
    to jobs.record_gallery_purchase (a per-buyer record), not
    _unlock_instructions_for_job (which would incorrectly flip the job's
    own single instructions_unlocked flag, unlocking free downloads for
    every future visitor -- see gallery_purchases's own docstring in
    jobs.py for why that distinction matters)."""
    return _create_checkout_session(
        user,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "gbp",
                    "unit_amount": price_gbp * 100,
                    "product_data": {"name": f"BrickForgerAI gallery build ({job_id})"},
                },
                "quantity": 1,
            }
        ],
        success_url=f"{FRONTEND_URL}/discover/{job_id}?checkout=success",
        cancel_url=f"{FRONTEND_URL}/discover/{job_id}?checkout=cancelled",
        metadata={"type": "gallery_purchase", "job_id": job_id, "user_id": user.id},
    )


def create_billing_portal_session(user: auth.User) -> str:
    """Returns a URL to Stripe's own hosted Billing Portal -- shows the
    customer their next billing date, lets them update their saved card,
    view past invoices, and cancel their subscription, all without this
    app ever touching a card number (same PCI-scope reasoning as
    Checkout, see this module's own docstring). No custom "next billing
    date" or "update card" page should be built to replace this.

    Cancelling through the portal is also how downgrade-to-free actually
    happens -- Stripe's own default behavior keeps the plan active until
    the current period ends (the customer already paid for it), then
    fires customer.subscription.deleted, which handle_webhook_event
    already handles by setting the plan back to 'free'. No separate
    downgrade endpoint or webhook logic is needed on top of what already
    exists for that event.

    Raises ValueError (never a raw stripe.InvalidRequestError) if this
    user has never had a Stripe customer record at all, or if the one on
    file doesn't resolve against the current API key's mode -- same
    stale-test-mode-customer-ID scenario _create_checkout_session
    self-heals by creating a fresh customer, but that fix doesn't apply
    here: the whole point of the portal is showing *existing* billing
    history, and a freshly created empty customer has none to show, so
    surfacing a clear error instead is more honest than silently opening
    a blank portal. Confirmed as a real gap by testing this function
    directly, not just assumed: an unresolvable customer ID previously
    propagated as an unhandled stripe.InvalidRequestError, a raw 500 to
    the caller."""
    if not user.stripe_customer_id:
        raise ValueError("No billing history yet -- nothing to manage")
    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{FRONTEND_URL}/pricing",
        )
    except stripe.InvalidRequestError as exc:
        raise ValueError("Couldn't find your billing account -- contact support") from exc
    return session.url


def verify_and_parse_webhook(payload: bytes, signature_header: str | None) -> stripe.Event:
    """Raises ValueError on a missing/invalid signature -- the caller
    (main.py) turns that into an HTTP 400. Never process a webhook body
    without this: it's the only thing standing between this endpoint and
    anyone on the internet POSTing a fake "payment completed" event."""
    if not _WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")
    try:
        return stripe.Webhook.construct_event(payload, signature_header, _WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise ValueError(str(exc)) from exc


def handle_webhook_event(event: stripe.Event, unlock_instructions_for_job, record_gallery_purchase) -> None:
    """Dispatches a verified event to the right side effect. Idempotency
    is handled by the caller (main.py checks
    auth.mark_stripe_event_processed(event.id) before calling this at
    all) -- every function called from here assumes it's genuinely only
    running once per event.

    unlock_instructions_for_job (job_id) -> None and record_gallery_purchase
    (job_id, buyer_user_id) -> None are both injected rather than imported
    directly, to avoid a circular import: main.py already imports this
    module, and the actual job-mutating logic lives in main.py/jobs.py."""
    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        checkout_type = meta.get("type")
        if obj.get("mode") == "payment" and checkout_type == "topup":
            auth.add_credits(meta["user_id"], TOPUP_CREDITS)
        elif obj.get("mode") == "payment" and checkout_type == "unlock_instructions":
            unlock_instructions_for_job(meta["job_id"])
        elif obj.get("mode") == "payment" and checkout_type == "gallery_purchase":
            record_gallery_purchase(meta["job_id"], meta["user_id"])
        # Subscription-mode sessions are deliberately not handled here --
        # customer.subscription.created below is what actually provisions
        # the plan, since it's the source of truth for what was actually
        # purchased (and also fires for changes made outside our own
        # Checkout flow, e.g. directly in the Stripe dashboard).

    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        customer_id = obj["customer"]
        price_id = obj["items"]["data"][0]["price"]["id"]
        new_plan = _PRICE_ID_TO_PLAN.get(price_id)
        if new_plan is None:
            return
        user = auth.get_user_by_stripe_customer_id(customer_id)
        # Only re-provision on an actual plan change -- calling this on
        # every subscription.updated ping (Stripe fires it for reasons
        # unrelated to price, too) would reset a user's remaining credits
        # mid-cycle even when nothing about their plan changed.
        if user is not None and user.plan != new_plan:
            auth.set_user_plan_and_provision(user.id, new_plan)

    elif event_type == "customer.subscription.deleted":
        customer_id = obj["customer"]
        user = auth.get_user_by_stripe_customer_id(customer_id)
        if user is not None and user.plan != "free":
            auth.set_user_plan_and_provision(user.id, "free")
