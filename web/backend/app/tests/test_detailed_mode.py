"""Detailed mode, backend side: request validation, the 2-credit charge and
its refunds, instructions unlocking, the feature flag, and the job's
failure/success paths.  Plain script style like the other tests here.

Never touches production: DATABASE_URL / REDIS_URL / SENTRY_DSN are blanked
before the app is imported (web/backend/.env points at the live Railway
services), the database is a throwaway SQLite file, job files go to a temp
dir, and the designer itself is stubbed -- no Claude or OpenAI calls.

Run: python app/tests/test_detailed_mode.py
"""
from __future__ import annotations

import os
import sys
import tempfile

for var in ("DATABASE_URL", "REDIS_URL", "SENTRY_DSN", "R2_ACCOUNT_ID"):
    os.environ[var] = ""                        # load_dotenv never overrides a variable that is already set
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402  -- first: main loads .env before auth reads it
from app import auth, jobs  # noqa: E402
from app.pipeline import designer_bridge  # noqa: E402
from app.storage import LocalStorage  # noqa: E402
from brickforge_designer.pipeline import DesignerError  # noqa: E402

TMP = tempfile.mkdtemp(prefix="bf_detailed_test_")
auth.DB_PATH = os.path.join(TMP, "users.db")
auth.init_db()
jobs._init_job_index()
jobs.JOBS_DIR = os.path.join(TMP, "jobs")
jobs.STORAGE = LocalStorage(jobs.JOBS_DIR)            # same layout as local dev: storage root == jobs dir
main.STORAGE = jobs.STORAGE
main.JOBS_DIR = jobs.JOBS_DIR


class _NoImages:
    """Stands in for OpenAI in every test (the real client would spend money):
    fails like an outage, which a Detailed job must survive by designing
    without the picture.  One test swaps in a working fake."""

    def generate(self, prompt, out_path, quality=None):
        raise RuntimeError("image service unavailable (test stub)")


jobs.get_image_client = lambda: _NoImages()
client = TestClient(main.app)
_n = [0]


def new_user(monthly=0, dev=0, topup=0, plan="free"):
    _n[0] += 1
    u = auth.create_user(f"t{_n[0]}@example.com", "correct horse battery")
    with auth._connect() as conn:
        conn.execute(auth._ph("UPDATE users SET credits_remaining = ?, dev_credits_remaining = ?, "
                              "topup_credits_remaining = ?, plan = ?, credits_reset_month = ? WHERE id = ?"),
                     (monthly, dev, topup, plan, auth._current_month(), u.id))
    return auth.get_user_by_id(u.id)


def pools(uid):
    u = auth.get_user_by_id(uid)
    return u.credits_remaining, u.dev_credits_remaining, u.topup_credits_remaining


def token(u):
    return {"Authorization": f"Bearer {auth._make_token(u.id)}"}


def set_flag(on, allow=""):
    os.environ["DETAILED_MODE_ENABLED"] = "true" if on else "false"
    os.environ["DETAILED_MODE_ALLOWLIST"] = allow


# ---------------------------------------------------------------- credits
def test_two_credits_come_from_the_same_pools_in_the_same_order_and_refund_back():
    u = new_user(monthly=1, topup=3)
    u2, source = auth.consume_credit(u.id, 2)
    assert source == "monthly,topup", source
    assert pools(u.id) == (0, 0, 2)
    auth.refund_credit(u.id, source)
    assert pools(u.id) == (1, 0, 3)


def test_two_credits_are_all_or_nothing():
    u = new_user(monthly=1)
    try:
        auth.consume_credit(u.id, 2)
        raise AssertionError("should have refused")
    except ValueError as e:
        assert "2 credits" in str(e)
    assert pools(u.id) == (1, 0, 0)


def test_single_credit_behaviour_is_unchanged():
    u = new_user(monthly=1, dev=1)
    _, source = auth.consume_credit(u.id)
    assert source == "monthly" and pools(u.id) == (0, 1, 0)
    auth.refund_credit(u.id, source)
    assert pools(u.id) == (1, 1, 0)


# ---------------------------------------------------------------- validation + unlocking
def test_request_validation_per_mode():
    ok = [main.GenerateRequest(prompt="x", target_size_studs=30),
          main.GenerateRequest(prompt="x", mode="detailed", target_size_studs=24, finish="studs", sideways="off")]
    bad = [main.GenerateRequest(prompt="x", mode="detailed", target_size_studs=40),
           main.GenerateRequest(prompt="x", mode="detailed", target_size_studs=24, finish="shiny"),
           main.GenerateRequest(prompt="x", mode="detailed", target_size_studs=24, sideways="lots"),
           main.GenerateRequest(prompt="x", mode="banana"),
           main.GenerateRequest(prompt="x", target_size_studs=500)]
    for r in ok:
        main._validate_generate_request(r)
    for r in bad:
        try:
            main._validate_generate_request(r)
            raise AssertionError(f"accepted {r}")
        except HTTPException as e:
            assert e.status_code == 400


def test_instructions_unlocking_for_two_credit_jobs():
    free = new_user(plan="free")
    paid = new_user(plan="builder")
    assert not main._instructions_unlocked(free, "monthly,monthly")
    assert main._instructions_unlocked(paid, "monthly,monthly")
    assert not main._instructions_unlocked(paid, "monthly,topup")      # a topup credit never unlocks
    assert main._instructions_unlocked(free, "dev,dev")
    assert main._instructions_unlocked(paid, "monthly")                # single-credit cases unchanged
    assert not main._instructions_unlocked(paid, "topup")


# ---------------------------------------------------------------- flag + endpoints
def test_features_endpoint_and_flag():
    u = new_user(monthly=5)
    set_flag(False)
    assert client.get("/features").json()["detailed_mode"] is False
    set_flag(True)
    assert client.get("/features").json()["detailed_mode"] is True
    set_flag(True, allow="someone@else.com")
    assert client.get("/features").json()["detailed_mode"] is False            # signed out: allowlisted -> hidden
    assert client.get("/features", headers=token(u)).json()["detailed_mode"] is False
    set_flag(True, allow=u.email.upper())
    assert client.get("/features", headers=token(u)).json()["detailed_mode"] is True
    body = client.get("/features").json()
    assert body["credit_cost"] == {"voxel": 1, "detailed": 2}


def test_detailed_generate_is_refused_when_the_flag_is_off_and_costs_nothing():
    u = new_user(monthly=5)
    set_flag(False)
    r = client.post("/generate", json={"prompt": "a fox", "mode": "detailed", "target_size_studs": 24},
                    headers=token(u))
    assert r.status_code == 403, r.text
    assert pools(u.id) == (5, 0, 0)


def test_detailed_generate_charges_two_and_a_failed_design_refunds_both():
    u = new_user(monthly=1, topup=2)
    set_flag(True)

    def failing(*a, **k):
        err = DesignerError("checks failed", "We couldn't design a model for this prompt that holds together.")
        err.usage = {"totals": {"cost_usd": 0.12, "calls": 3}, "rounds": 2}
        err.spec, err.problems = "model fox\n", ["LOOSE main: 4 part(s) from line 3", "TOO BIG: 2600 parts"]
        raise err
    real = designer_bridge.design_to_ldr
    designer_bridge.design_to_ldr = failing
    try:
        r = client.post("/generate", json={"prompt": "a fox", "mode": "detailed", "target_size_studs": 24,
                                           "finish": "studs", "sideways": "off"}, headers=token(u))
    finally:
        designer_bridge.design_to_ldr = real
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    meta = jobs.load_job_meta(job_id)
    assert meta["status"] == "failed" and meta["mode"] == "detailed"
    assert "2 credits" in meta["error"] and "refunded" in meta["error"]
    assert "Traceback" not in meta["error"]
    assert meta["cost_usd"] == 0.12                      # spend is still recorded on failure
    assert pools(u.id) == (1, 0, 2), pools(u.id)         # both credits back where they came from
    # the failed spec and checker report are kept for a free local rebuild
    assert jobs.STORAGE.get_bytes(job_id, "design.bfd") == b"model fox\n"
    assert b"TOO BIG" in jobs.STORAGE.get_bytes(job_id, "design_problems.txt")
    public = client.get(f"/generate/{job_id}", headers=token(u)).json()
    assert "cost_usd" not in public and "design_usage" not in public and "credit_source" not in public


def test_detailed_job_success_path_records_stats_and_cost():
    u = new_user(monthly=3)
    set_flag(True)

    def ok(prompt, ldr_out_path, **k):
        with open(ldr_out_path, "w") as f:
            f.write("0 test\n")
        return {"part_count": 120, "slope_count": 4, "tile_count": 9, "color_count": 5, "color_source": "designer",
                "was_repaired": None, "still_critical_count": None, "is_single_piece": True, "piece_count": 2,
                "symmetrized": False, "spec": "model t\n", "pdf_generated": False,
                "design_usage": {"totals": {"cost_usd": 0.07, "calls": 1}, "rounds": 0}}
    real = designer_bridge.design_to_ldr
    designer_bridge.design_to_ldr = ok
    try:
        r = client.post("/generate", json={"prompt": "a pickup truck", "mode": "detailed", "target_size_studs": 20},
                        headers=token(u))
    finally:
        designer_bridge.design_to_ldr = real
    meta = jobs.load_job_meta(r.json()["job_id"])
    assert meta["status"] == "done", meta.get("error")
    assert (meta["part_count"], meta["piece_count"], meta["color_source"]) == (120, 2, "designer")
    assert meta["was_repaired"] is None and meta["still_critical_count"] is None
    assert meta["cost_usd"] == 0.07 and meta["finish"] == "tiled" and meta["sideways"] == "auto"
    assert pools(u.id) == (1, 0, 0)                      # 2 credits spent, none refunded
    with auth._connect() as conn:
        row = conn.execute(auth._ph("SELECT mode, cost_usd FROM job_index WHERE job_id = ?"),
                           (r.json()["job_id"],)).fetchone()
    assert (row["mode"], row["cost_usd"]) == ("detailed", 0.07)


def test_design_image_is_never_the_thumbnail_but_a_build_render_is():
    u = new_user(monthly=2)
    set_flag(True)
    seen = {}

    class FakeImages:
        def generate(self, prompt, out_path, quality=None):
            seen["quality"] = quality
            with open(out_path, "wb") as f:
                f.write(b"\x89PNG design picture")
            return out_path

    def ok(prompt, ldr_out_path, reference_image_path=None, **k):
        seen["ref"] = reference_image_path
        with open(ldr_out_path, "w") as f:
            f.write("0 test\n")
        return {"part_count": 50, "slope_count": 0, "tile_count": 0, "color_count": 2, "color_source": "designer",
                "was_repaired": None, "still_critical_count": None, "is_single_piece": True, "piece_count": 1,
                "symmetrized": False, "spec": "model t\n", "pdf_generated": False,
                "design_usage": {"totals": {"cost_usd": 0.1, "calls": 1}, "rounds": 0}}
    real_d, real_i = designer_bridge.design_to_ldr, jobs.get_image_client
    designer_bridge.design_to_ldr, jobs.get_image_client = ok, lambda: FakeImages()
    try:
        r = client.post("/generate", json={"prompt": "a green dragon", "mode": "detailed", "target_size_studs": 24},
                        headers=token(u))
    finally:
        designer_bridge.design_to_ldr, jobs.get_image_client = real_d, real_i
    job_id = r.json()["job_id"]
    meta = jobs.load_job_meta(job_id)
    assert seen["quality"] == "medium" and seen["ref"].endswith("design_reference.png")
    assert meta["cost_usd"] == round(0.1 + designer_bridge.REFERENCE_IMAGE_COST_USD, 4)
    assert not jobs.STORAGE.exists(job_id, "reference.png")
    assert meta["thumbnail_url"] is None                               # nothing to show until a render exists
    assert client.get(f"/generate/{job_id}/thumbnail").status_code == 404
    render = os.path.join(TMP, "render.png")
    with open(render, "wb") as f:
        f.write(b"\x89PNG build render")
    jobs.STORAGE.put(job_id, "render.png", render)
    assert jobs.load_job_meta(job_id)["thumbnail_url"] == f"/generate/{job_id}/thumbnail"
    assert client.get(f"/generate/{job_id}/thumbnail").content == b"\x89PNG build render"


def test_my_builds_lists_finished_detailed_jobs_but_not_failed_ones():
    """My Builds (GET /generate) shows every finished job of the caller, whatever
    its mode; failed jobs (any mode) are never listed."""
    u = new_user(monthly=4)
    set_flag(True, allow=u.email)

    def ok(prompt, ldr_out_path, **k):
        with open(ldr_out_path, "w") as f:
            f.write("0 test\n")
        return {"part_count": 80, "slope_count": 0, "tile_count": 3, "color_count": 3, "color_source": "designer",
                "was_repaired": None, "still_critical_count": None, "is_single_piece": True, "piece_count": 1,
                "symmetrized": False, "spec": "model t\n", "pdf_generated": False,
                "design_usage": {"totals": {"cost_usd": 0.1, "calls": 1}, "rounds": 0}}

    def failing(*a, **k):
        raise DesignerError("checks failed", "We couldn't design a model for this prompt that holds together.")

    real = designer_bridge.design_to_ldr
    ids = {}
    try:
        for name, fn in (("done", ok), ("failed", failing)):
            designer_bridge.design_to_ldr = fn
            r = client.post("/generate", json={"prompt": f"a {name} castle", "mode": "detailed",
                                               "target_size_studs": 24}, headers=token(u))
            ids[name] = r.json()["job_id"]
    finally:
        designer_bridge.design_to_ldr = real
    listed = client.get("/generate", headers=token(u)).json()
    assert [j["job_id"] for j in listed] == [ids["done"]], listed
    assert listed[0]["mode"] == "detailed" and "cost_usd" not in listed[0]


def test_a_finished_job_whose_index_write_was_dropped_is_reindexed_from_storage():
    """Production, 2026-09-25: the worker's job_index writes hit PoolTimeout and
    were dropped, so finished jobs never showed in My Builds.  The startup
    reindex re-adds them from meta.json -- but not for deleted accounts."""
    u, gone = new_user(), new_user()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()   # My Builds shows this month's jobs
    for jid, owner in (("lost-job-1", u.id), ("lost-job-2", gone.id)):
        jobs._write_job_meta_dict(jid, {"job_id": jid, "user_id": owner, "status": "done", "created_at": now,
                                        "prompt": "a swan", "mode": "detailed", "cost_usd": 0.12})
    with auth._connect() as conn:
        conn.execute(auth._ph("DELETE FROM job_index WHERE job_id IN (?, ?)"), ("lost-job-1", "lost-job-2"))
        conn.execute(auth._ph("DELETE FROM users WHERE id = ?"), (gone.id,))
    assert [j["job_id"] for j in client.get("/generate", headers=token(u)).json()] == []
    jobs._backfill_missing_index()
    listed = client.get("/generate", headers=token(u)).json()
    assert [j["job_id"] for j in listed] == ["lost-job-1"], listed
    with auth._connect() as conn:
        rows = conn.execute(auth._ph("SELECT job_id FROM job_index WHERE job_id = ?"), ("lost-job-2",)).fetchall()
    assert rows == []


def test_a_column_added_before_an_existing_one_survives_the_migration():
    """Production, 2026-09-26: job_index's mode/cost_usd were added and then
    undone, on every startup, by the rollback after the next (already
    present) column's ALTER failed -- so every job_index write failed and no
    new build reached My Builds.  Reproduced here the way Postgres runs it:
    all the migrations inside one open transaction."""
    import sqlite3
    conn = sqlite3.connect(os.path.join(TMP, "migrate.db"), isolation_level=None)
    conn.execute("CREATE TABLE t (a TEXT, old TEXT)")
    conn.execute("BEGIN")
    auth._add_column_if_missing(conn, "ALTER TABLE t ADD COLUMN new TEXT", "new")
    auth._add_column_if_missing(conn, "ALTER TABLE t ADD COLUMN old TEXT", "old")
    conn.execute("COMMIT")
    assert [r[1] for r in conn.execute("PRAGMA table_info(t)")] == ["a", "old", "new"]


def test_the_final_status_write_retries_harder_than_intermediate_ones():
    real_connect, real_sleep = auth._connect, jobs.time.sleep
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) <= 4:
            raise RuntimeError("PoolTimeout (test)")
        return real_connect(*a, **k)

    auth._connect, jobs.time.sleep = flaky, lambda s: None
    try:
        jobs._record_job_index("retry-job", "u-x", "designing", "2026-09-25T20:00:00+00:00", "p", "detailed", None)
        assert len(calls) == 2                      # intermediate: one retry, then give up
        calls.clear()
        jobs._record_job_index("retry-job", "u-x", "done", "2026-09-25T20:00:00+00:00", "p", "detailed", None)
        assert len(calls) == 5                      # final: kept trying and got through
    finally:
        auth._connect, jobs.time.sleep = real_connect, real_sleep
    with auth._connect() as conn:
        row = conn.execute(auth._ph("SELECT status FROM job_index WHERE job_id = ?"), ("retry-job",)).fetchone()
    assert row["status"] == "done"


def test_voxel_generate_still_costs_one_credit():
    u = new_user(monthly=2)
    real = main.process_job
    main.process_job = lambda **k: None                 # don't run the real voxel pipeline
    try:
        r = client.post("/generate", json={"prompt": "a vase", "target_size_studs": 22}, headers=token(u))
    finally:
        main.process_job = real
    assert r.status_code == 200, r.text
    assert pools(u.id) == (1, 0, 0)
    assert jobs.load_job_meta(r.json()["job_id"])["mode"] == "voxel"


if __name__ == "__main__":
    tests = [(k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS: {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            print(f"FAIL: {name}: {exc!r}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed.")
    sys.exit(1 if failed else 0)
