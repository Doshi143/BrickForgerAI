# Build context MUST be the repository root, not web/backend -- this
# service needs both core/ (installed editable, matching the exact
# `pip install -e ../../core` step every README in this repo already
# documents for local dev) and web/backend/ copied in. In Railway's
# dashboard, set this service's Root Directory to "." (the repo root),
# not "web/backend" -- pointing it at web/backend directly would make
# core/ invisible to this build entirely, and the editable install below
# would fail.
FROM python:3.11-slim

WORKDIR /app

# rtree, manifold3d, and embreex (core/brickforge's own dependencies)
# ship precompiled wheels for common Linux platforms, so this is normally
# unnecessary -- but cheap to include as a fallback for a source build on
# an unsupported architecture, and expensive to discover missing partway
# through a real deploy.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# core/ copied and installed before web/backend/'s own requirements, so
# Docker's layer cache only invalidates this (slower) step when core/
# actually changes, not on every backend-only edit.
COPY core/ /app/core/
RUN pip install --no-cache-dir -e /app/core

COPY web/backend/requirements.txt /app/web/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/web/backend/requirements.txt

# Chromium for the worker's build-instructions PDF renderer
# (app/pipeline/instructions_pdf.py) -- --with-deps pulls the system
# libraries headless Chromium needs (libnss3, libatk, etc.) that a
# python:3.11-slim base doesn't ship. Only the worker process actually
# launches it (see instructions_pdf.py's own docstring), but this
# Dockerfile builds one shared image for both API and worker services
# (see the CMD comment below) rather than maintaining two, so the API
# image carries this too -- a real, deliberate size/build-time tradeoff,
# not an oversight.
RUN python -m playwright install --with-deps chromium

COPY web/backend/ /app/web/backend/
WORKDIR /app/web/backend

# Railway assigns a dynamic $PORT per service rather than always 8000 --
# explicit `sh -c "..."` rather than relying on Docker's own shell-form
# CMD wrapping, confirmed necessary the hard way: Railway's per-service
# "Custom Start Command" (which railway.json's deploy.startCommand feeds)
# execs the given string as a direct process, not through a shell, so
# ${PORT:-8000} was never expanded and uvicorn received the literal
# string "${PORT:-8000}" as --port -- a real deploy failure, not a
# hypothetical. Being explicit here means this CMD is correct standalone
# too, not just when Railway's own startCommand override happens to save it.
#
# --proxy-headers --forwarded-allow-ips='*' trusts X-Forwarded-For from
# Railway's edge proxy so request.client.host (used for per-IP auth rate
# limiting, see app/auth.py::_client_ip) reflects the real caller instead
# of Railway's internal proxy IP for every request. '*' is safe here
# specifically because Railway's proxy is the only thing that can reach
# this container directly (no public ingress bypasses it).
#
# This is the API's default command. The worker service uses the exact
# same image (same dependencies, same code) but overrides this with
# "python worker.py" via Railway's own per-service Custom Start Command
# setting -- see DEPLOYMENT.md's Phase 5 manual steps. There is no
# separate Dockerfile.worker; building two images for one dependency set
# would just double build time for no benefit.
CMD ["/bin/sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
