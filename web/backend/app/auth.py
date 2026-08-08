"""Accounts: signup/login, and the credit balance the pricing plans are
built around (10/month free, 30/month pro -- see PLAN_CREDITS below).

SQLite, not a real database server, for the same reason the job store is
in-memory-plus-JSON: this is a trial app, not a production deployment (see
web/backend/README.md's "known limitations"). Passwords are bcrypt-hashed
(never stored or logged in plain text); sessions are signed JWTs with a
30-day expiry, verified on every request via `get_current_user`, not
stored server-side (so there's no session table to manage, at the cost of
no server-side revocation -- acceptable for a trial).

No real payment processing exists yet (Stripe is explicitly deferred --
see the pricing page). "Pro" plan status here is a plain DB column with no
enforcement of an actual charge behind it; upgrading a user's plan today
is a manual/dev action, not something a user can do by paying. Wiring
real payment processing is exactly the next thing that would flip this
from "trial" to "real."
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "users.db")

# Postgres when DATABASE_URL is set (Railway in production), SQLite
# fallback otherwise -- same local-stays-local-unless-configured pattern
# as storage.py's LocalStorage/R2Storage split, so local dev needs zero
# extra setup and nothing above this module has to know which one is active.
DATABASE_URL = os.environ.get("DATABASE_URL")
_USE_POSTGRES = bool(DATABASE_URL)

if _USE_POSTGRES:
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    # min/max sized for a small always-on service, not a high-concurrency
    # API -- a handful of pooled connections is plenty and avoids paying
    # Postgres's per-connection setup cost on every request.
    #
    # check=ConnectionPool.check_connection -- confirmed as the fix for a
    # real production failure: "psycopg.OperationalError: consuming input
    # failed: SSL error: decryption failed or bad record mac" on the
    # worker's very first DB write of a job (see jobs.py::_record_job_index).
    # The worker sits idle between jobs, sometimes for a long stretch, and
    # Railway's Postgres (or a proxy in front of it) can silently drop an
    # idle TCP connection without a clean close; the pool doesn't know and
    # hands that same now-dead connection back out for the next job, and
    # reusing a connection whose TLS session has gone stale like that
    # produces exactly this "bad record mac" corruption, not a real auth or
    # query error. check_connection is psycopg_pool's own built-in health
    # check (psycopg_pool >= 3.2, matches this project's pinned version): it
    # runs a trivial query before handing out a pooled connection and
    # transparently discards+reconnects if that fails, closing the gap
    # instead of just retrying after the fact.
    _pool = ConnectionPool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
        check=ConnectionPool.check_connection,
    )
    _pool.wait()


def _ph(query: str) -> str:
    """Translate this module's SQLite-style `?` placeholders to psycopg's
    `%s` when Postgres is active. A plain .replace() is safe here -- none
    of the SQL below has a literal "?" character in a string value, only
    ever as a parameter placeholder."""
    return query.replace("?", "%s") if _USE_POSTGRES else query


@contextmanager
def _connect():
    """Same call-site shape either way (`with _connect() as conn:`), so
    every function below is unchanged regardless of which database is
    active -- only this function and _ph() know the difference."""
    if _USE_POSTGRES:
        with _pool.connection() as conn:
            yield conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # sqlite3's own commit-on-success/rollback-on-exception
                yield conn
        finally:
            conn.close()


# Only used to sign session tokens (not for anything else) -- generated
# once and persisted to .env so tokens survive a backend restart; if this
# ever isn't set, every restart would invalidate every logged-in session.
JWT_SECRET = os.environ.get("AUTH_SECRET_KEY")
if not JWT_SECRET:
    raise RuntimeError(
        "AUTH_SECRET_KEY is not set in .env -- generate one (e.g. `python -c "
        "\"import secrets; print(secrets.token_hex(32))\"`) and add it, or every "
        "backend restart will silently log everyone out."
    )

TOKEN_TTL_DAYS = 30

# Same var billing.py reads for Stripe Checkout redirect URLs -- reused
# here to build the reset-password link that goes out in email, so both
# modules point at the same real frontend origin without a second env var.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

RESET_TOKEN_TTL_MINUTES = 60

# "builder" and "pro" (Master Builder) map directly to Stripe subscription
# Prices in billing.py's PRICE_IDS -- the two dicts must stay in sync, but
# live in separate modules deliberately (this one has no Stripe
# dependency, so local dev/tests that never touch billing still work).
PLAN_CREDITS = {"free": 5, "builder": 12, "pro": 30}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                credits_remaining INTEGER NOT NULL,
                credits_reset_month TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Added after the users table already existed in production --
        # plain ADD COLUMN, not part of CREATE TABLE, so existing rows
        # aren't affected (stripe_customer_id stays NULL until a user's
        # first checkout creates one). Swallowing the failure is the
        # simplest thing that's correct on both backends: SQLite has no
        # portable ADD COLUMN IF NOT EXISTS, and Postgres's version isn't
        # available on every server version either -- but "column already
        # exists" is the only realistic failure mode for a fixed, known
        # column add like this, so a bare try/except is safe here, not a
        # hidden-failure risk.
        try:
            conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT")
        except Exception:
            # Explicit rollback, not just swallowing the exception --
            # confirmed as a real production bug (Sentry:
            # InFailedSqlTransaction in init_db, first seen right after
            # this column shipped): Postgres marks the whole transaction
            # aborted after ANY failed statement, so the very next
            # statement below (CREATE TABLE processed_stripe_events, on
            # this same connection/transaction) failed too, on every
            # restart after the first one ever added the column
            # successfully. Same fix as mark_stripe_event_processed's own
            # except block, which got this right from the start.
            conn.rollback()
        try:
            # Purely for the founder's own marketing attribution (e.g.
            # "reddit-sideproject") -- captured client-side from a
            # first-touch ?ref=... query param (ReferralCapture.tsx) and
            # never shown back to any user. Nullable: every signup before
            # this column existed, and any signup with no ?ref= at all,
            # just has NULL here rather than needing a default value.
            conn.execute("ALTER TABLE users ADD COLUMN signup_source TEXT")
        except Exception:
            conn.rollback()
        try:
            # A separate pool from credits_remaining, deliberately -- see
            # add_credits and consume_credit below for why top-up credits
            # need to be trackable independently of plan credits (whether
            # a generation used a paid-for top-up credit determines
            # whether its instructions download is free, regardless of
            # plan; plan credits also get wiped by the monthly reset
            # below in a way top-up credits deliberately never should).
            conn.execute("ALTER TABLE users ADD COLUMN topup_credits_remaining INTEGER NOT NULL DEFAULT 0")
        except Exception:
            conn.rollback()
        # Webhook idempotency: Stripe retries delivery on anything short of
        # a 200, so the same event can arrive more than once. Recording
        # every event ID we've already handled -- checked before any
        # side-effecting work runs -- is what makes a retried "add 5
        # credits" a no-op instead of a double-credit.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_stripe_events (
                event_id TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            )
            """
        )
        # Only the SHA-256 hash of the token is ever stored, the same
        # reasoning as storing a bcrypt hash instead of a plaintext
        # password -- a leaked DB row alone must never be enough to reset
        # someone's password, only the raw token mailed to their inbox is.
        # One row per outstanding request (create_password_reset_token
        # deletes any previous rows for the user first), consumed
        # (deleted) on first successful use so a token can't be replayed.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _row_to_user(row: sqlite3.Row) -> "User":
    user = User(
        id=row["id"],
        email=row["email"],
        plan=row["plan"],
        credits_remaining=row["credits_remaining"],
        credits_reset_month=row["credits_reset_month"],
        stripe_customer_id=row["stripe_customer_id"],
        topup_credits_remaining=row["topup_credits_remaining"],
    )
    # Monthly reset: if the stored reset-month doesn't match the real
    # current month, this user's credits haven't been topped up yet.
    # topup_credits_remaining is deliberately untouched here -- a paid-for
    # top-up credit doesn't expire at month end the way the plan's own
    # monthly allowance does (see add_credits's own docstring).
    this_month = _current_month()
    if user.credits_reset_month != this_month:
        user.credits_remaining = PLAN_CREDITS[user.plan]
        user.credits_reset_month = this_month
        with _connect() as conn:
            conn.execute(
                _ph("UPDATE users SET credits_remaining = ?, credits_reset_month = ? WHERE id = ?"),
                (user.credits_remaining, user.credits_reset_month, user.id),
            )
    return user


@dataclass
class User:
    id: str
    email: str
    plan: str
    credits_remaining: int
    credits_reset_month: str
    stripe_customer_id: str | None = None
    topup_credits_remaining: int = 0


def create_user(email: str, password: str, source: str | None = None) -> User:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email address")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_id = str(uuid.uuid4())
    this_month = _current_month()

    with _connect() as conn:
        existing = conn.execute(_ph("SELECT id FROM users WHERE email = ?"), (email,)).fetchone()
        if existing is not None:
            raise ValueError("An account with that email already exists")
        conn.execute(
            _ph(
                """
                INSERT INTO users (id, email, password_hash, plan, credits_remaining, credits_reset_month, created_at, signup_source)
                VALUES (?, ?, ?, 'free', ?, ?, ?, ?)
                """
            ),
            (
                user_id,
                email,
                password_hash,
                PLAN_CREDITS["free"],
                this_month,
                datetime.now(timezone.utc).isoformat(),
                source,
            ),
        )

    return User(id=user_id, email=email, plan="free", credits_remaining=PLAN_CREDITS["free"], credits_reset_month=this_month)


def authenticate(email: str, password: str) -> User:
    email = email.strip().lower()
    with _connect() as conn:
        row = conn.execute(_ph("SELECT * FROM users WHERE email = ?"), (email,)).fetchone()

    if row is None or not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        raise ValueError("Incorrect email or password")

    return _row_to_user(row)


def get_user_by_id(user_id: str) -> User | None:
    with _connect() as conn:
        row = conn.execute(_ph("SELECT * FROM users WHERE id = ?"), (user_id,)).fetchone()
    return None if row is None else _row_to_user(row)


def consume_credit(user_id: str) -> tuple[User, bool]:
    """Decrements one credit and returns (user, was_topup_credit) -- the
    caller (POST /generate) uses the second value to decide whether this
    generation's instructions download is free, regardless of plan: a
    top-up credit (bought separately, £6 for +5) always requires paying
    for instructions on top, even for a Builder/Master Builder user whose
    *plan* credits normally include it free. Plan credits are drawn down
    first (they're the ones that expire at the monthly reset, so spending
    them before non-expiring top-up credits wastes less); only once
    credits_remaining hits zero does a generation start drawing from
    topup_credits_remaining instead. Raises ValueError if both pools are
    empty (caller turns that into an HTTP 402)."""
    user = get_user_by_id(user_id)
    if user is None:
        raise ValueError("User not found")
    if user.credits_remaining <= 0 and user.topup_credits_remaining <= 0:
        raise ValueError("No credits remaining this month")

    was_topup_credit = user.credits_remaining <= 0
    with _connect() as conn:
        if was_topup_credit:
            conn.execute(
                _ph("UPDATE users SET topup_credits_remaining = ? WHERE id = ?"),
                (user.topup_credits_remaining - 1, user.id),
            )
            user.topup_credits_remaining -= 1
        else:
            conn.execute(
                _ph("UPDATE users SET credits_remaining = ? WHERE id = ?"),
                (user.credits_remaining - 1, user.id),
            )
            user.credits_remaining -= 1
    return user, was_topup_credit


def get_user_by_stripe_customer_id(customer_id: str) -> User | None:
    with _connect() as conn:
        row = conn.execute(_ph("SELECT * FROM users WHERE stripe_customer_id = ?"), (customer_id,)).fetchone()
    return None if row is None else _row_to_user(row)


def set_stripe_customer_id(user_id: str, customer_id: str) -> None:
    with _connect() as conn:
        conn.execute(_ph("UPDATE users SET stripe_customer_id = ? WHERE id = ?"), (customer_id, user_id))


def set_user_plan_and_provision(user_id: str, plan: str) -> User:
    """Sets a user's plan and immediately tops their credits up to that
    plan's full monthly allowance -- called from the Stripe webhook on a
    genuine plan change (upgrade, downgrade, or cancellation-to-free), not
    on every subscription.updated ping (billing.py only calls this when
    the derived plan actually differs from what's stored, so an unrelated
    Stripe-side update can't silently reset a user's remaining credits
    mid-cycle). Idempotent by construction -- setting a specific plan and
    credit amount has the same result no matter how many times a retried
    webhook delivery runs it, unlike consume_credit's relative decrement."""
    if plan not in PLAN_CREDITS:
        raise ValueError(f"Unknown plan: {plan!r}")
    this_month = _current_month()
    with _connect() as conn:
        conn.execute(
            _ph("UPDATE users SET plan = ?, credits_remaining = ?, credits_reset_month = ? WHERE id = ?"),
            (plan, PLAN_CREDITS[plan], this_month, user_id),
        )
    user = get_user_by_id(user_id)
    if user is None:
        raise ValueError("User not found")
    return user


def add_credits(user_id: str, amount: int) -> User:
    """Adds top-up credits on top of the current balance -- goes into
    topup_credits_remaining specifically, not credits_remaining (the
    plan's own monthly allowance), for two reasons: it must survive the
    monthly reset (see _row_to_user above) rather than being wiped along
    with unused plan credits, and consume_credit needs to know a credit
    came from here so it can charge separately for instructions even on
    a plan that normally includes them free (see its own docstring).
    NOT idempotent by itself (unlike set_user_plan_and_provision) -- the
    caller (billing.py's webhook handler) must only call this once per
    Stripe event, via mark_stripe_event_processed below."""
    user = get_user_by_id(user_id)
    if user is None:
        raise ValueError("User not found")
    with _connect() as conn:
        conn.execute(
            _ph("UPDATE users SET topup_credits_remaining = ? WHERE id = ?"),
            (user.topup_credits_remaining + amount, user_id),
        )
    user.topup_credits_remaining += amount
    return user


def mark_stripe_event_processed(event_id: str) -> bool:
    """Returns True the first time this event_id is seen (and records it),
    False on every subsequent call -- Stripe's own recommended idempotency
    pattern, since it retries webhook delivery on anything short of a 200.
    A plain INSERT that fails on the primary-key conflict is simpler and
    more directly correct here than a SELECT-then-INSERT race."""
    with _connect() as conn:
        try:
            conn.execute(
                _ph("INSERT INTO processed_stripe_events (event_id, processed_at) VALUES (?, ?)"),
                (event_id, datetime.now(timezone.utc).isoformat()),
            )
            return True
        except Exception:
            # Explicit rollback, not just "let the caught exception fall
            # through" -- Postgres specifically leaves a transaction
            # aborted after any failed statement, and swallowing the
            # exception here (so _connect()'s own commit-on-clean-exit
            # runs next) would otherwise depend on "committing an aborted
            # transaction is defined to roll back" rather than saying so
            # directly.
            conn.rollback()
            return False


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_password_reset_token(email: str) -> str | None:
    """Returns a fresh raw reset token for this email, or None if no
    account matches -- the caller (the /auth/forgot-password endpoint)
    deliberately returns the same generic response either way, so this
    return value must never leak into an HTTP response, only into the
    email that gets sent when it's not None. Any previous outstanding
    token for this user is deleted first, so at most one reset link is
    ever valid at a time -- requesting a new one implicitly revokes an
    earlier email still sitting unread in an inbox."""
    email = email.strip().lower()
    with _connect() as conn:
        row = conn.execute(_ph("SELECT id FROM users WHERE email = ?"), (email,)).fetchone()
        if row is None:
            return None
        user_id = row["id"]

        token = secrets.token_urlsafe(32)
        token_hash = _hash_reset_token(token)
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)).isoformat()

        conn.execute(_ph("DELETE FROM password_reset_tokens WHERE user_id = ?"), (user_id,))
        conn.execute(
            _ph("INSERT INTO password_reset_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)"),
            (token_hash, user_id, expires_at),
        )
    return token


def reset_password_with_token(token: str, new_password: str) -> None:
    """Raises ValueError (turned into an HTTP 400 by the caller) if the
    token doesn't match, has expired, or the new password is too short.
    The token row is deleted whether or not the rest of the update
    succeeds validation-wise up front, is only actually consumed on a
    genuinely successful password change, matching create_user's own
    length check so both entry points enforce the same minimum."""
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters")

    token_hash = _hash_reset_token(token)
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        row = conn.execute(
            _ph("SELECT user_id, expires_at FROM password_reset_tokens WHERE token_hash = ?"),
            (token_hash,),
        ).fetchone()
        if row is None or row["expires_at"] < now:
            raise ValueError("This reset link is invalid or has expired -- request a new one")

        password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn.execute(
            _ph("UPDATE users SET password_hash = ? WHERE id = ?"),
            (password_hash, row["user_id"]),
        )
        # Consumed -- a used or expired token must never work twice.
        conn.execute(_ph("DELETE FROM password_reset_tokens WHERE token_hash = ?"), (token_hash,))


def _make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "plan": user.plan,
        # Total across both pools -- the frontend just shows one number
        # ("N credits left this month"); which pool a given generation
        # actually draws from (and whether that means paid instructions)
        # is decided in consume_credit, not something the summary display
        # needs to distinguish.
        "credits_remaining": user.credits_remaining + user.topup_credits_remaining,
        "monthly_credit_allowance": PLAN_CREDITS[user.plan],
        "instructions_included": user.plan in ("builder", "pro"),
        # Not the raw Stripe customer ID (that stays server-side) -- just
        # enough for the frontend to decide whether "Manage billing" has
        # anything to show. True for anyone who's ever subscribed or
        # bought a top-up, even if they're back on the free plan now (a
        # cancelled subscriber still has past invoices worth showing).
        "has_billing_account": user.stripe_customer_id is not None,
    }


router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    email: str
    password: str
    # Marketing attribution only (e.g. "reddit-sideproject") -- see
    # ReferralCapture.tsx and create_user's own docstring. Never required,
    # never validated against a known set -- an arbitrary or malformed
    # value here can't do anything beyond being a slightly odd row in a
    # column nothing else reads.
    source: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


def _client_ip(request: Request) -> str:
    """Best-effort caller IP for auth rate limiting below. Behind Railway's
    proxy this only reflects the real client when uvicorn is started with
    --proxy-headers (see Dockerfile/railway.json) -- without it every
    request looks like it comes from the proxy, and this would rate-limit
    all callers as one bucket instead of per-caller."""
    return request.client.host if request.client else "unknown"


@router.post("/signup", response_model=AuthResponse)
def signup(req: SignupRequest, request: Request) -> AuthResponse:
    # Deferred import: rate_limit.py imports from this module (PLAN_CREDITS),
    # so importing it back at module load time here would be circular.
    # By call time both modules are already fully loaded.
    from . import rate_limit

    if not rate_limit.check_auth_rate_limit(_client_ip(request), "signup", limit=5, window_s=3600):
        raise HTTPException(429, "Too many signup attempts -- try again later.")
    try:
        user = create_user(req.email, req.password, source=req.source)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return AuthResponse(token=_make_token(user.id), user=_user_to_dict(user))


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request) -> AuthResponse:
    from . import rate_limit

    # Keyed by IP alone, not IP+email -- keying by email too would let an
    # attacker rotate through many guessed emails from one IP unthrottled,
    # which is exactly the enumeration/brute-force scenario this exists to
    # stop. 10 attempts per 5 minutes is generous for a genuine user who
    # mistyped a password, tight for a credential-stuffing script.
    if not rate_limit.check_auth_rate_limit(_client_ip(request), "login", limit=10, window_s=300):
        raise HTTPException(429, "Too many login attempts -- try again later.")
    try:
        user = authenticate(req.email, req.password)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    return AuthResponse(token=_make_token(user.id), user=_user_to_dict(user))


_GENERIC_FORGOT_PASSWORD_RESPONSE = {
    "message": "If an account exists for that email, we've sent password reset instructions."
}


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request) -> dict:
    # Deferred imports for the same circular-import reason as signup/login
    # above (rate_limit imports PLAN_CREDITS from this module; email_client
    # has no such dependency but is deferred too, for consistency and so a
    # missing/misconfigured RESEND_API_KEY only surfaces when this endpoint
    # is actually hit, not at import time for every process that loads auth.py).
    from . import email_client, rate_limit

    if not rate_limit.check_auth_rate_limit(_client_ip(request), "forgot-password", limit=5, window_s=3600):
        raise HTTPException(429, "Too many requests -- try again later.")

    token = create_password_reset_token(req.email)
    if token is not None:
        reset_url = f"{FRONTEND_URL}/reset-password?token={token}"
        email_client.send_password_reset_email(req.email.strip().lower(), reset_url)

    # Identical response whether or not the email is registered -- telling
    # an unregistered caller "no account with that email" would let anyone
    # enumerate which addresses have accounts on this site.
    return _GENERIC_FORGOT_PASSWORD_RESPONSE


@router.post("/reset-password")
def reset_password_endpoint(req: ResetPasswordRequest, request: Request) -> dict:
    from . import rate_limit

    if not rate_limit.check_auth_rate_limit(_client_ip(request), "reset-password", limit=10, window_s=3600):
        raise HTTPException(429, "Too many attempts -- try again later.")
    try:
        reset_password_with_token(req.token, req.new_password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"message": "Password updated -- you can now sign in."}


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if creds is None:
        raise HTTPException(401, "Sign in required")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired session") from exc

    user = get_user_by_id(payload["sub"])
    if user is None:
        raise HTTPException(401, "Account no longer exists")
    return user


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return _user_to_dict(user)
