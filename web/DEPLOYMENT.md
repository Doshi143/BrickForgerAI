# Deploying BrickForgerAI

A runbook for taking the trial app in `web/` from "runs on Aaryan's PC" to
"runs on the internet without Aaryan's PC being on."

Two kinds of step appear below:

- **🤖 Prompt** — paste into Claude Code. Each is self-contained.
- **✋ Manual** — only you can do it (accounts, cards, DNS, secrets).

Work top to bottom. Every phase leaves the app in a working state, so you can
stop at any phase boundary and come back.

---

## Platform decision: Railway, not Vercel + Render

**Use one platform for everything.** For this app's shape — 3 small services,
low traffic, bursty CPU — usage-based billing beats per-service billing by a
lot.

| Setup | Monthly, low traffic |
|---|---|
| **Railway (everything)** | **~$10–20** |
| Render (everything) | ~$46 — $25 workspace fee + ~$7/service since the Apr 2026 restructure |
| Vercel Pro + Render | ~$59 |

Railway's Hobby plan is $5/month minimum including $5 of usage credit, then
pay-as-you-go across CPU, RAM, egress, and volume. Three mostly-idle services
plus Postgres and Redis land well under the per-service model. It also gives you
one dashboard, one bill, and private networking between services (no egress
charges for backend↔database traffic).

**What you give up by not using Vercel:** its CDN, edge network, and automatic
image optimization for the Next.js frontend. For a content-heavy marketing site
that would matter. For this app — mostly authenticated, dynamic, dominated by a
client-side three.js viewer — the loss is small and not worth $40/month at
launch. Revisit if the landing page ever becomes a real traffic driver.

> ⚠️ **Railway has no hard spending cap.** A runaway job or a traffic spike bills
> you. Set a usage alert during setup (Phase 0) and treat it as mandatory, not
> optional. Your per-generation API costs (OpenAI, fal) are capped separately at
> those providers.

### Target architecture

```
Railway project "brickforgerai"
├── frontend    Next.js          (web/frontend)
├── backend     FastAPI          (web/backend)     ← API only, fast responses
├── worker      RQ worker        (web/backend)     ← the slow pipeline
├── Postgres                                       ← users, credits, jobs
└── Redis                                          ← the job queue
        │
        └── Cloudflare R2 (external)               ← .ldr, renders, meshes
```

External services: OpenAI (`gpt-image-1`), fal.ai (`fal-ai/trellis-2`),
Cloudflare R2, Stripe, Resend, Sentry.

---

## Phase 0 — Accounts and keys ✋

Do all of this before running any prompt. Roughly an afternoon.

- [ ] **Buy a domain.** Cloudflare Registrar or Namecheap, ~£10/yr.
      **No "lego" in the name** — it is a registered trademark and they enforce
      it. `brickforger.ai`, `brickforgerai.com`, etc. are all fine.
- [ ] **Railway** — sign up at railway.app, add a card, select Hobby ($5/mo).
- [ ] **Railway usage alert** — Project → Settings → Usage → set an alert at
      $25. Do not skip this.
- [ ] **fal.ai** — sign up, top up $10, create an API key.
      Copy it now; it is shown once. → `FAL_KEY`
- [ ] **OpenAI** — confirm your key works, then **set a hard monthly spend
      limit** (Settings → Limits). $20 to start. → `OPENAI_API_KEY`
- [ ] **Cloudflare R2** — create a bucket named `brickforge-jobs`. Create an
      R2 API token with Object Read & Write.
      → `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
- [ ] **Sentry** — free tier, create a project, copy the DSN. → `SENTRY_DSN`
- [ ] **Generate a fresh auth secret** for production. Do **not** reuse the one
      in your local `.env`:
      ```
      python -c "import secrets; print(secrets.token_hex(32))"
      ```
      → `AUTH_SECRET_KEY`

Defer until Phase 6: Stripe, Resend.

**Keep every value in a password manager, not a text file.** You will paste them
into Railway's dashboard in Phase 5 — never commit them, and never paste them
into a chat.

---

## Phase 1 — Get the mesh step off your PC 🤖

**This is the unblocking step.** Nothing else can go live while a core stage
needs your desktop switched on. Everything after this is ordinary migration
work; this is the one that changes what's possible.

```
Add a fal.ai provider to web/backend/app/clients/mesh_gen.py so the mesh
stage can run without my local ComfyUI.

Context you should verify rather than trust from me:
- mesh_gen.py already has a MeshGenClient ABC, a MeshyClient, a
  TrellisComfyUIClient, and a get_mesh_client() factory switching on the
  MESH_GEN_PROVIDER env var. Follow that existing pattern exactly; do not
  restructure it.
- My local ComfyUI workflow runs TRELLIS 2 with a Trellis2MeshTexturing
  node, so meshes arrive genuinely textured. The correct hosted equivalent
  is fal-ai/trellis-2, NOT fal-ai/trellis (the original, which is
  shape-only and would silently reactivate reference_color.py).

Add a FalTrellis2Client that:
- submits the image to fal-ai/trellis-2 and polls until the job completes
- downloads the resulting .glb to out_path
- mirrors MeshyClient's timeout/poll/error-handling conventions
- reads FAL_KEY from the environment
- registers in get_mesh_client() as provider "fal_trellis2", leaving
  "trellis_local" and "meshy" working unchanged

Use fal's HTTP queue API with the `requests` library already in
requirements.txt. Do not add the fal Python SDK unless there's a concrete
reason, and say so if there is.

Then verify, don't assume: run a real generation through it with a
reference image from an existing job in web/backend/jobs/, and measure the
returned mesh's unique vertex colour count the same way we measured the
local TRELLIS 2 output (~48k-70k unique colours on ~380k vertices). If it
comes back flat, the wrong model is wired up — say so plainly rather than
letting reference_color.py paper over it.
```

Then, once it works:

```
Make fal_trellis2 the default MESH_GEN_PROVIDER, keeping trellis_local
available as an explicit opt-in for local development. Update
web/backend/README.md and the relevant section of CLAUDE.md to describe
the new default, including the "match TRELLIS 2, not TRELLIS" reasoning
already documented in CLAUDE.md.
```

✋ **After this:** turn ComfyUI off and run a full generation from the frontend.
If it works, your PC is no longer load-bearing.

---

## Phase 2 — Make data survive a deploy 🤖

Right now users live in a SQLite file and job outputs live in a local folder.
On any hosting platform, **both are destroyed on every deploy.** Users would
silently vanish.

```
Migrate web/backend/app/auth.py from SQLite to Postgres.

Requirements:
- Read the connection string from DATABASE_URL. Keep SQLite working as a
  fallback when DATABASE_URL is unset, so local development is unchanged.
- Preserve the existing schema and behaviour exactly: bcrypt password
  hashing, JWT sessions via AUTH_SECRET_KEY, PLAN_CREDITS, and the monthly
  credit auto-reset that compares credits_reset_month against the current
  month.
- Add connection pooling appropriate for a small always-on service.
- Write a small migration script that copies an existing users.db into
  Postgres, so my local test accounts carry over.

Use psycopg (v3) and add it to requirements.txt. Do not introduce an ORM —
the existing code is plain SQL and should stay that way.

Verify by running the existing auth flows against a local Postgres
container: signup, signin, credit consumption, and the monthly reset path.
```

```
Move job artifact storage from the local jobs/ folder to S3-compatible
object storage (Cloudflare R2).

Files currently written per job: model.ldr, model.glb, reference.png,
render.png, meta.json.

Requirements:
- New module web/backend/app/storage.py with a small interface (put, get,
  exists, signed_url). Two implementations: LocalStorage (current
  behaviour, the default when R2 env vars are absent) and R2Storage.
- Read R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
- Update main.py's endpoints to go through this interface. Pay attention
  to the download gating: GET /generate/{id}/preview is deliberately
  unrestricted while GET /generate/{id}/download 402s unless
  instructions_unlocked. That distinction is a deliberate fix, documented
  in CLAUDE.md — do not collapse the two endpoints.
- Serve downloads via short-lived signed URLs rather than proxying bytes
  through the API.

Use boto3 pointed at R2's S3-compatible endpoint. Verify by round-tripping
a real job's files through R2 and confirming both the preview and the
gated download still behave correctly.
```

---

## Phase 3 — Split the slow work out 🤖

Today the pipeline runs via `BackgroundTasks` inside the web process. One
generation pegs the CPU for 1–5 minutes and makes the whole site sluggish; worse,
a pegged process can fail health checks and get restarted mid-job.

```
Split the brickify pipeline out of the web process into a separate worker,
using Redis as the queue.

Requirements:
- Use RQ (simpler than Celery and sufficient here). Read REDIS_URL from
  the environment.
- POST /generate should enqueue a job and return immediately. The polling
  endpoint GET /generate/{id} must keep reporting the same incremental
  phase names it does today — that responsiveness is the point of the
  current design and must not regress.
- New entrypoint web/backend/worker.py that runs the RQ worker.
- Keep the existing meta.json-style persistence so job state survives a
  restart of either process, and keep the fallback that reads job state
  from storage when the in-memory dict misses.
- app/pipeline/brickforge_bridge.py must stay a thin adapter. Queue
  plumbing does not belong in it.

Verify by running API and worker as separate processes, submitting two
generations concurrently, and confirming the API stays responsive
throughout and both jobs complete.
```

---

## Phase 4 — Production hardening 🤖

```
Add production safety guards to the backend. Right now anyone can hammer
POST /generate and run up my OpenAI and fal bills.

Add:
- Per-user rate limiting on POST /generate (default 5/hour, configurable
  by env var). Credits are already enforced server-side via
  auth.consume_credit — this is defence in depth for the unauthenticated
  and abuse cases, not a replacement.
- A global daily generation ceiling, configurable by env var, that returns
  503 with a clear message when exceeded. This is my backstop against a
  runaway bill.
- Sentry error reporting, initialised from SENTRY_DSN, in both the API and
  the worker. It must be a no-op when the DSN is unset.
- A /health endpoint that actually checks Postgres and Redis
  connectivity rather than just returning 200.
- CORS locked to an ALLOWED_ORIGINS env var instead of anything permissive.

Do not add an API gateway, a WAF, or any other infrastructure. These are
small application-level guards.
```

---

## Phase 5 — Deploy 🤖 then ✋

```
Prepare this repo for deployment to Railway as four services in one
project: frontend (Next.js, web/frontend), backend (FastAPI, web/backend),
worker (RQ, web/backend), plus managed Postgres and Redis.

Produce:
- A railway.json or per-service config with correct build and start
  commands for each service.
- A Dockerfile for the backend and worker if that's cleaner than
  Railway's Python buildpack, given this project needs `pip install -e
  ../../core` for `import brickforge` to resolve. Explain which you chose
  and why — that editable local install across directories is the awkward
  part and I want to know how it's handled.
- A documented list of every environment variable each service needs,
  written to web/DEPLOYMENT_ENV.md. Names and purposes only — never
  actual secret values.
- Confirmation that the frontend reads the backend URL from an env var
  rather than a hardcoded localhost:8001.

Do not commit any secrets. Do not run any deployment commands — I will
click through Railway's dashboard myself.
```

✋ **Then, in Railway's dashboard:**

1. New Project → Deploy from GitHub repo → select this repo.
2. Add service **backend** → root directory `web/backend` → start command from
   the generated config.
3. Add service **worker** → same repo, root `web/backend` → start command
   `python worker.py`.
4. Add service **frontend** → root directory `web/frontend`.
5. Add **Postgres** (Railway → New → Database → Postgres).
6. Add **Redis** (Railway → New → Database → Redis).
7. For each service, **Variables** tab → paste the values from Phase 0.
   Use Railway's reference syntax (`${{Postgres.DATABASE_URL}}`,
   `${{Redis.REDIS_URL}}`) rather than pasting connection strings by hand —
   they update automatically if a database is recreated.
8. **Networking** → generate a public domain for `frontend` and `backend`.
9. Set the frontend's backend-URL variable to the backend's public domain.
10. Set the backend's `ALLOWED_ORIGINS` to the frontend's public domain.
11. **Custom domain:** point your domain at the frontend service and
    `api.yourdomain.com` at the backend. Railway shows the exact DNS records;
    add them at your registrar.
12. Run one full generation end to end on the live site.

---

## Phase 6 — Launch paid, day one

No free soft-launch period — paid from the first user. That's a real trade-off,
worth naming plainly: skipping it means your first bug reports come from
paying customers instead of free testers, and any generation-pipeline issue
that would've surfaced in a week of free use now surfaces as a refund request
instead. Mitigate it by doing 6d (a fast smoke test, still on today's plan)
right before flipping Stripe live — a few hours, not a week, but not skipped
either.

The ordering below is fixed regardless of launch speed: **content filter and
legal pages must exist before Stripe goes live**, not after. Charging money
for output before either exists is the actual risk, more so than skipping a
free trial period.

### 6a. Content filter 🤖 — required before accepting a single payment

```
Add a content filter to the prompt input, before any image generation
happens.

The problem: users will prompt for copyrighted characters (Pikachu, Baby
Yoda, etc.). Selling build instructions for those is a genuine legal
exposure. The TRELLIS MIT licence covers the model, not the subject.

Requirements:
- Reject clearly-infringing prompts server-side, before spending money on
  gpt-image-1, with a clear user-facing message.
- Prefer OpenAI's moderation endpoint plus a maintained blocklist of
  well-known franchises over trying to write clever regexes.
- Log rejections so I can see false positives and tune it.

Keep it conservative — a false rejection is annoying, a false acceptance
is a takedown notice.
```

### 6b. Payments 🤖

```
Add Stripe Checkout for credit packs.

Context: web/backend/app/auth.py already has the full credit system
(PLAN_CREDITS, consume_credit, monthly reset) and a working
POST /generate/{id}/unlock-instructions endpoint with no charge behind it.
The module docstring says wiring real payment is the intended next step.
That's this task.

Requirements:
- Stripe Checkout (the hosted page). We must never touch card numbers —
  that keeps us out of PCI scope. Do not build a card form.
- Credit packs, not subscriptions, for now.
- A webhook endpoint that adds credits on checkout.session.completed, with
  signature verification and idempotency (Stripe retries; double-crediting
  is a real bug, not a hypothetical).
- Wire the existing unlock-instructions flow to a real charge.
- Test against Stripe's test mode and test webhook signatures.
```

### 6c. Legal pages — required before flipping Stripe out of test mode ✋

- [ ] Write real Terms and Privacy content — the pages exist at
      `web/frontend/app/terms` and `app/privacy` but need actual text.
- [ ] Add the trademark disclaimer to the footer: *"Not affiliated with,
      endorsed, or sponsored by the LEGO Group. LEGO® is a trademark of the
      LEGO Group."*
- [ ] Add the LDraw CCAL 2.0 attribution notice.
- [ ] Set up Resend for receipts and password resets.

### 6d. Smoke test, same day — not a substitute for 6a–6c, a check that they work ✋

Do this right before switching Stripe to live mode, with everything from 6a–6c
already in place:

- [ ] Turn Sentry on and confirm you receive a test error.
- [ ] Run 3–5 full generations yourself on the production URL, in Stripe test
      mode, including at least one prompt the content filter should reject.
      Confirm the rejection actually happens.
- [ ] Complete one real Stripe test-mode checkout end to end and confirm
      credits land on the account.
- [ ] Only once all of that is clean: switch Stripe out of test mode. You are
      now live and charging real money.

---

## Running costs

**Fixed, per month:**

| | |
|---|---|
| Railway (4 services + Postgres + Redis, low traffic) | ~$10–20 |
| Cloudflare R2 | $0 (10 GB free, and R2 charges nothing for egress) |
| Sentry, Resend | $0 (free tiers) |
| Domain | ~$1 |
| **Total** | **~$15–25** |

**Per generation:**

| | |
|---|---|
| Image — gpt-image-1 | $0.04–0.19 |
| Mesh — fal-ai/trellis-2 @ 512p | ~$0.25 |
| Brickify — CPU | $0.01–0.05 |
| **Total** | **~$0.30–0.50** |

Stripe takes 2.9% + 30¢ per sale.

**At £10 per model you're profitable at about 4 sales a month.** That is the
number worth holding on to — the infrastructure is not what makes or breaks
this.

---

## Three things that can actually sink you

1. **Trademark.** Never put "LEGO" in the name, domain, logo, or paid ads.
   Nominative use in body copy is fine *with* the disclaimer.
2. **Copyrighted subjects.** Phase 6a (the content filter) is not optional before you charge.
3. **Physical kits.** Don't. It turns a software business into a warehouse and
   would consume all your time. v1 is digital: a file, a parts list, a PDF.

---

## Deferred on purpose

Not needed at launch; revisit when there's evidence they're needed:

- Vercel for the frontend — only if the landing page becomes a real traffic
  driver and the CDN starts to matter.
- Self-hosted TRELLIS on a rented GPU — only if volume makes the ~$0.25/mesh
  actually significant. Ops burden will cost you more than margin at this scale.
- A Rust port of the legalizer — see CLAUDE.md; only when it measurably
  bottlenecks.
- Physical fulfilment. See above.
