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

import os
import re
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
    _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5, kwargs={"row_factory": dict_row})
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

PLAN_CREDITS = {"free": 10, "pro": 30}

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


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _row_to_user(row: sqlite3.Row) -> "User":
    user = User(
        id=row["id"],
        email=row["email"],
        plan=row["plan"],
        credits_remaining=row["credits_remaining"],
        credits_reset_month=row["credits_reset_month"],
    )
    # Monthly reset: if the stored reset-month doesn't match the real
    # current month, this user's credits haven't been topped up yet.
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


def create_user(email: str, password: str) -> User:
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
                INSERT INTO users (id, email, password_hash, plan, credits_remaining, credits_reset_month, created_at)
                VALUES (?, ?, ?, 'free', ?, ?, ?)
                """
            ),
            (user_id, email, password_hash, PLAN_CREDITS["free"], this_month, datetime.now(timezone.utc).isoformat()),
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


def consume_credit(user_id: str) -> User:
    """Decrement credits_remaining by 1. Raises ValueError if the user has
    none left (caller -- POST /generate -- turns that into an HTTP 402)."""
    user = get_user_by_id(user_id)
    if user is None:
        raise ValueError("User not found")
    if user.credits_remaining <= 0:
        raise ValueError("No credits remaining this month")

    with _connect() as conn:
        conn.execute(
            _ph("UPDATE users SET credits_remaining = ? WHERE id = ?"),
            (user.credits_remaining - 1, user.id),
        )
    user.credits_remaining -= 1
    return user


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
        "credits_remaining": user.credits_remaining,
        "monthly_credit_allowance": PLAN_CREDITS[user.plan],
        "instructions_included": user.plan == "pro",
    }


router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


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
        user = create_user(req.email, req.password)
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
