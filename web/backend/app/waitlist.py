"""Email capture for the maintenance-mode waitlist (see MAINTENANCE_MODE in
main.py / frontend's NEXT_PUBLIC_MAINTENANCE_MODE). Deliberately its own
tiny module, not folded into auth.py -- a waitlist entry isn't a user
account (no password, no login), and keeping it separate means this table
has nothing to do with the real signup flow if maintenance mode is ever
removed later.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import auth

_EMAIL_RE = auth._EMAIL_RE


def _init_waitlist() -> None:
    with auth._connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS waitlist (
                email TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
            """
        )


_init_waitlist()


def add_to_waitlist(email: str) -> bool:
    """True if this email was newly added, False if it was already on the
    list -- both are a success from the caller's point of view (idempotent
    by design: submitting the same email twice, e.g. a double-click or a
    later revisit, must not error), the return value is only for logging/
    testing, not surfaced to the client."""
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email address")
    # Postgres and sqlite spell "insert, but silently skip a duplicate key"
    # differently -- ON CONFLICT vs INSERT OR IGNORE -- so the two full
    # statements are written out separately rather than assembled from
    # fragments, easier to read correctly than a conditionally-built string.
    if auth._USE_POSTGRES:
        statement = "INSERT INTO waitlist (email, created_at) VALUES (?, ?) ON CONFLICT (email) DO NOTHING"
    else:
        statement = "INSERT OR IGNORE INTO waitlist (email, created_at) VALUES (?, ?)"
    with auth._connect() as conn:
        cur = conn.execute(auth._ph(statement), (email, datetime.now(timezone.utc).isoformat()))
        return (cur.rowcount or 0) > 0
