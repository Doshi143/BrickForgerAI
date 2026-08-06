"""One-off script: copy local users.db (SQLite) rows into Postgres.

Run once, after DATABASE_URL is set in .env and before relying on Postgres
for real: `python migrate_users_to_postgres.py`. Safe to re-run -- inserts
use ON CONFLICT (id) DO NOTHING, so already-migrated rows are skipped
rather than duplicated or overwritten.

Reads the OLD sqlite file directly (app.auth's own _connect() already
points at Postgres once DATABASE_URL is set, so it can't be used to read
the source data -- only to write the destination).
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app import auth  # noqa: E402


def main() -> None:
    if not auth._USE_POSTGRES:
        raise SystemExit("DATABASE_URL is not set -- nothing to migrate into.")

    if not os.path.isfile(auth.DB_PATH):
        print(f"No local users.db found at {auth.DB_PATH} -- nothing to migrate.")
        return

    auth.init_db()  # make sure the users table exists on the Postgres side

    src = sqlite3.connect(auth.DB_PATH)
    src.row_factory = sqlite3.Row
    rows = src.execute("SELECT * FROM users").fetchall()
    src.close()

    if not rows:
        print("Local users.db has no rows -- nothing to migrate.")
        return

    migrated = 0
    skipped = 0
    with auth._connect() as conn:
        for row in rows:
            result = conn.execute(
                auth._ph(
                    """
                    INSERT INTO users
                        (id, email, password_hash, plan, credits_remaining, credits_reset_month, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                (
                    row["id"],
                    row["email"],
                    row["password_hash"],
                    row["plan"],
                    row["credits_remaining"],
                    row["credits_reset_month"],
                    row["created_at"],
                ),
            )
            if result.rowcount:
                migrated += 1
            else:
                skipped += 1

    print(f"Migrated {migrated} user(s), skipped {skipped} already-present row(s).")


if __name__ == "__main__":
    main()
