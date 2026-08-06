"""Per-user and global request throttling for POST /generate, backed by
Redis (the same connection app/jobs.py already sets up for the queue).
Skipped entirely when Redis isn't configured -- there's nowhere to track
counts without it, and this is defence-in-depth against a stolen token or
bot hammering the endpoint, not the real cost gate (auth.consume_credit
already is that, enforced synchronously before a job is ever enqueued).
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone

from .auth import PLAN_CREDITS
from .jobs import REDIS_CONN

RATE_LIMIT_DIVISOR = float(os.environ.get("RATE_LIMIT_DIVISOR", "2"))
DAILY_GENERATION_CEILING = int(os.environ.get("DAILY_GENERATION_CEILING", "100"))


def _hourly_limit_for_plan(plan: str) -> int:
    """Scaled to the plan's own monthly allowance rather than one flat
    number for every tier -- a flat cap is either pointless (Free's whole
    monthly allowance is already smaller than any per-hour number could
    constrain) or throttles paying users below what they bought (a higher
    tier's larger allowance implies wanting to burn several in one
    sitting). Only the divisor is configurable by env var, not per-plan
    numbers -- see DEPLOYMENT.md Phase 4 for the full reasoning, including
    why this needed fixing once before (an earlier version hardcoded a
    flat 5/hour for every plan)."""
    allowance = PLAN_CREDITS.get(plan, PLAN_CREDITS["free"])
    return max(3, math.ceil(allowance / RATE_LIMIT_DIVISOR))


def check_per_user_rate_limit(user_id: str, plan: str) -> bool:
    """True if this request may proceed. Increments the user's current
    hour bucket regardless of the outcome -- a rejected attempt still
    counts against the window, or repeated retries would be a free way
    around the limit."""
    if REDIS_CONN is None:
        return True

    hour_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    key = f"ratelimit:user:{user_id}:{hour_bucket}"
    count = REDIS_CONN.incr(key)
    if count == 1:
        REDIS_CONN.expire(key, 3600)
    return count <= _hourly_limit_for_plan(plan)


def check_global_daily_ceiling() -> bool:
    """True if today's total generations (across every user) are still
    under the daily ceiling -- the backstop against a runaway bill that
    per-user limits alone wouldn't catch (many distinct accounts each
    staying under their own limit)."""
    if REDIS_CONN is None:
        return True

    day_bucket = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"ratelimit:global:{day_bucket}"
    count = REDIS_CONN.incr(key)
    if count == 1:
        REDIS_CONN.expire(key, 90000)  # a bit over 24h, covers clock drift
    return count <= DAILY_GENERATION_CEILING
