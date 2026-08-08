"""One-off script: populates jobs.py's job_index table (added to fix "My
Builds" losing jobs after every backend redeploy -- see that table's own
docstring in app/jobs.py) from every meta.json already sitting in R2.

Only needed once, run against whichever environment's R2 bucket and
database actually hold real job history -- typically production, since
that's where the redeploys that caused this were actually happening.
Safe to run more than once: every write is the same upsert
_record_job_index already uses for every normal job update, so re-running
this just re-confirms the same rows rather than duplicating anything.

Usage (from web/backend, with the target environment's real
R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET and
DATABASE_URL set -- e.g. run via Railway's own Console on the backend or
worker service, where those are already the production values):
    python scripts/backfill_job_index.py
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app import jobs  # noqa: E402  (import after load_dotenv, matching app/jobs.py's own pattern)
from app.storage import R2Storage  # noqa: E402


def main() -> None:
    if not isinstance(jobs.STORAGE, R2Storage):
        raise SystemExit(
            "This environment isn't using R2Storage (no R2_* env vars configured) -- "
            "there's nothing to backfill from local disk, since local disk is exactly "
            "what this script exists to stop depending on."
        )

    client = jobs.STORAGE.client
    bucket = jobs.STORAGE.bucket

    recorded = 0
    skipped = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith("/meta.json"):
                continue
            job_id = key[: -len("/meta.json")]

            raw = jobs.STORAGE.get_bytes(job_id, "meta.json")
            if raw is None:
                skipped += 1
                continue
            data = json.loads(raw)

            user_id = data.get("user_id")
            status = data.get("status")
            created_at = data.get("created_at")
            if not (user_id and status and created_at):
                print(f"skipping {job_id}: missing user_id/status/created_at in stored meta.json")
                skipped += 1
                continue

            jobs._record_job_index(job_id, user_id, status, created_at)
            recorded += 1

    print(f"\nDone. Recorded {recorded} job(s), skipped {skipped}.")


if __name__ == "__main__":
    main()
