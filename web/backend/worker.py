"""RQ worker entrypoint -- runs the brickify pipeline out-of-process from
the API server, so a slow job (image gen + mesh gen + brickify, easily
minutes) never blocks the API from responding to other requests.

Run from web/backend (same working directory as the uvicorn command):
    python worker.py

Requires REDIS_URL to be set in .env -- there is no local fallback here on
purpose: if you don't have Redis configured, main.py's generate() falls
back to running the pipeline in-process via BackgroundTasks instead, and
this worker has nothing to do.
"""
from __future__ import annotations

import os

import sentry_sdk
from rq import Worker
from rq.timeouts import TimerDeathPenalty
from rq.worker import SimpleWorker

from app.jobs import QUEUE, REDIS_CONN

# Separate from the API's own sentry_sdk.init() call in main.py -- these
# are two different OS processes, each needs its own initialization. A
# pipeline exception here (image gen, mesh gen, brickify all failing in
# ways specific to a real generation, not just an HTTP-layer bug) is
# exactly the kind of thing worth seeing in Sentry that the API process
# alone would never observe, since it never runs the pipeline itself.
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.1)

# RQ's default Worker isolates each job by os.fork()-ing a child process --
# fork() doesn't exist on Windows at all (confirmed directly: it crashed
# with "AttributeError: module 'os' has no attribute 'fork'" the instant it
# tried to run a real job, not on startup, since listening for jobs doesn't
# touch fork() but executing one does). SimpleWorker runs the job in the
# worker's own process instead -- the standard, RQ-documented workaround
# for platforms without fork() -- at the cost of losing per-job process
# isolation (a job that corrupts interpreter state could affect the next
# one). Acceptable here: this pipeline doesn't do anything that leaves
# process-global state behind between jobs.
#
# Separately, RQ's job_timeout enforcement (UnixSignalDeathPenalty, on both
# Worker and even SimpleWorker) uses signal.SIGALRM -- also confirmed
# missing on Windows the same way, a second real crash, not a hypothetical.
# TimerDeathPenalty is RQ's own thread-based alternative for exactly this.
if os.name == "nt":

    class _WindowsSimpleWorker(SimpleWorker):
        death_penalty_class = TimerDeathPenalty

    WorkerClass = _WindowsSimpleWorker
else:
    WorkerClass = Worker


def main() -> None:
    if QUEUE is None:
        raise SystemExit(
            "REDIS_URL is not set -- there is no queue for this worker to listen on. "
            "Set REDIS_URL in .env, or if you don't need a separate worker right now, "
            "the API already falls back to running jobs in-process without one."
        )
    worker = WorkerClass([QUEUE], connection=REDIS_CONN)
    worker.work()


if __name__ == "__main__":
    main()
