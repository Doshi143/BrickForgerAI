"""Per-user and global request throttling for POST /generate, backed by
Redis (the same connection app/jobs.py already sets up for the queue).
Skipped entirely when Redis isn't configured -- there's nowhere to track
counts without it, and this is defence-in-depth against a stolen token or
bot hammering the endpoint, not the real cost gate (auth.consume_credit
already is that, enforced synchronously before a job is ever enqueued).
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone

import redis

from .auth import PLAN_CREDITS
from .jobs import REDIS_CONN

logger = logging.getLogger(__name__)

RATE_LIMIT_DIVISOR = float(os.environ.get("RATE_LIMIT_DIVISOR", "2"))
DAILY_GENERATION_CEILING = int(os.environ.get("DAILY_GENERATION_CEILING", "100"))


def _check_fixed_window(key: str, limit: int, window_s: int) -> bool:
    """Shared by every check below: increments key's fixed-window counter
    and reports whether it's still within limit. Fails open (returns True)
    on any Redis error, not just REDIS_CONN is None -- a transient network
    blip to Redis (confirmed to happen: a real ConnectionError surfaced
    here during testing) previously propagated as an unhandled exception
    all the way to a 500 response, taking down login/signup/generate for
    every user over what this module's own docstring calls
    defence-in-depth, not the real gate."""
    if REDIS_CONN is None:
        return True
    try:
        count = REDIS_CONN.incr(key)
        if count == 1:
            REDIS_CONN.expire(key, window_s)
    except redis.RedisError:
        logger.warning("rate_limit: Redis error on key %s, failing open", key)
        return True
    return count <= limit


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
    hour_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    key = f"ratelimit:user:{user_id}:{hour_bucket}"
    return _check_fixed_window(key, _hourly_limit_for_plan(plan), 3600)


def check_global_daily_ceiling() -> bool:
    """True if today's total generations (across every user) are still
    under the daily ceiling -- the backstop against a runaway bill that
    per-user limits alone wouldn't catch (many distinct accounts each
    staying under their own limit)."""
    day_bucket = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"ratelimit:global:{day_bucket}"
    return _check_fixed_window(key, DAILY_GENERATION_CEILING, 90000)  # a bit over 24h, covers clock drift


def check_auth_rate_limit(client_ip: str, action: str, limit: int, window_s: int) -> bool:
    """Fixed-window per-IP throttle for unauthenticated auth endpoints
    (login/signup), where there's no user_id yet to key on. Deliberately
    doesn't import anything from .auth -- auth.py is this module's own
    caller (login/signup), so importing it back here would be a circular
    import; keying on a plain client_ip string keeps this module a leaf."""
    window_bucket = int(datetime.now(timezone.utc).timestamp() // window_s)
    key = f"ratelimit:auth:{action}:{client_ip}:{window_bucket}"
    return _check_fixed_window(key, limit, window_s)
