# BrickForgerAI — Handoff: SNOT Phase C

**Purpose:** paste this whole file as your first message in a new conversation
to resume exactly where this session left off. Written 2026-08-09 (updated
same day after Phase B landed), supersedes the earlier Phase B/C handoff —
that one's deployment content (live app, Railway layout, env vars, security
posture) is still accurate and summarized briefly below, but the active work
now is SNOT Phase C, not deployment.

---

## Where things stand right now

**The app is fully live** (`https://brickforgerai.com`), real Stripe payments
in live mode, open signup, Railway (5 services: frontend/backend/worker/
Postgres/Redis). Since the last deployment handoff, three more things
shipped: a **public Gallery** (publish builds from "My Builds", browse/search
even logged out, non-creators always pay regardless of plan — commit
`5c5b072`), **SNOT Phase A** (commits `61b0c80`, `fff54a3`), and **SNOT Phase
B** (this session — see below, **not yet committed**, working tree has real
changes; commit once you've read this and are ready to continue). No other
known outstanding bug or half-finished deployment work.

## What SNOT is and why it matters here

SNOT ("Studs Not On Top" — sideways brick building) is the product's planned
differentiator (`DESIGN.md` calls it "the moat", staged as Phase 6, deferred
on purpose until the sellable v1 was done). The founder decided to pull this
forward after seeing a competitor (brickbuilder.ai) ship a similar
prompt-to-brick tool, and wants SNOT to be the quality bar that separates
this product from theirs (reference: Niemann-Sculpt-style smooth sculptural
builds using sideways plates + slopes to round out a blocky core).

**Approved plan** (still the roadmap, phasing not renegotiated): saved at
`C:\Users\aarya\.claude\plans\cached-brewing-minsky.md` — read it in full
before starting Phase B, it has the full reasoning, not just the phase list.

- **Phase A (done, prior session)** — coordinate-frame foundations: can a
  SNOT sub-assembly attach to a specific face of an ordinary parent brick,
  with correct position and rotation.
- **Phase B (done, this session)** — teach the structural connectivity graph
  about sideways connections. See below for what shipped.
- **Phase C (not started — do this next)** — the actual automatic SNOT
  placement algorithm.
- **Phase D (not started, last)** — web app build-mode toggle.

## Phase A — what was built, and the bugs found (read before touching `snot.py`)

New module `core/brickforge/snot.py`: `SnotFrame`, `snot_frame_for_brick()`,
`place_in_frame()`. Lets a SNOT child part attach to a face (`+x`/`-x`/`+z`/
`-z`) of an already-placed ordinary `Brick`, reusing the existing, proven
`placement_to_ldraw()` for the child's own local placement, then transforming
by a frame (origin + rotation matrix) into world space. Deliberately a
**separate, composable** module — doesn't touch the existing yaw-only
`Rotation` enum, `Model`, collision detection, or the structural graph.
One verified real catalog part: `87087` ("Brick 1×1 with Stud on 1 Side"),
geometry pulled from the raw `.dat` file, not guessed —
`side_stud_face: "-z"`, `side_stud_offset: [0, 10]` in `catalog/parts_v1.yaml`.

**Three real, non-obvious bugs were found and fixed, all only caught by
rigorously transforming a part's full raw geometry (all 8 corners of its
actual bounding box) and checking the result — not by checking just its
origin point.** If you touch this module again, keep using that standard
(`_raw_geometry_bbox()` in `test_snot.py`) — origin-only checks have now
let bugs through twice.

1. **Convention-mixing** — an intermediate fix that undid/reapplied LDraw's
   Y-flip around the rotation step; necessary but insufficient alone.
2. **Wrong reference vector** — `_LOCAL_TILT_MATRIX` was derived and
   verified against local `+Y`, but this project's own established
   convention (top-anchored parts, see `lattice.py`'s module docstring)
   means the real native "away from stud" direction is local `-Y`. Fixed
   by swapping matrix assignments between opposite-labeled faces.
3. **Double-centering** — `snot_frame_for_brick`'s in-plane origin was
   adding half the parent's face width on top of `placement_to_ldraw`'s
   own automatic centering of the child on that same axis, pushing it a
   full footprint-width off target. Fixed by making the in-plane origin a
   plain corner reference.

After 1–3, the module was believed complete and Studio-verification was
requested. **The founder's screenshot showed the yellow plates floating
visibly too high, not flush** — a fourth bug, caught only because it's a
real render, not because any test caught it:

4. **Vertical-centering bug (fixed in commit `fff54a3`, the very last thing
   done this session)** — `placement_to_ldraw` centers a part within its own
   local grid cell on both horizontal axes, correct for a normal top-down
   grid placement. But for a SNOT child, the tilt redirects **one** of
   those two axes into world-**vertical**. A single stud is a *point* on
   the parent's face, not a cell to center within — so that axis's
   automatic half-footprint centering left every SNOT child floating a
   half-footprint-width (10 LDU for a 1-stud part) away from the real
   attachment point. Fixed in `place_in_frame()` by detecting which local
   axis feeds world Y directly from `frame.matrix`'s own world-Y row
   (`frame.matrix[3:6]`) and subtracting that axis's centering back out.
   Verified by hand computation for both faces in the shipped example
   (worked through the full matrix arithmetic, not just re-run and
   eyeballed), and pinned with a new parametrized test — all 4 faces,
   checking the child's full raw-geometry vertical midpoint against
   `frame.origin_ldu[1]` — the exact check the original test suite was
   missing, which is why bug #4 shipped in the first place.

**125/125 tests pass** (`core/tests/test_snot.py`, 15 tests: the original
11 plus the new vertical-centering regression, parametrized over all 4
faces). `core/examples/snot_alignment_test.py` regenerates
`core/examples/output/snot_alignment_test.ldr` — a 2×2 core of ordinary
bricks with one corner replaced by 87087, and two plates stacked on its
side stud via the new machinery. **This file was re-sent to the founder
after the bug-4 fix but their re-confirmation in Studio has NOT yet come
back as of this handoff — check for that first if you're picking this up
fresh, since Phase A's own completion bar (set in the approved plan) is
"opened in Studio and confirmed flush with no gap," and that bar has now
been missed once already by a bug the test suite didn't catch.**

**One thing still explicitly NOT addressed**, called out in `snot.py`'s own
module docstring as a known open question: each face's tilt matrix is
individually a *correct* rotation, but the remaining one-degree-of-freedom
"spin" around the tilt axis was chosen independently per face, with nothing
yet reconciling how a **non-symmetric** part's other two axes get
distributed relative to each other. 87087 happens to be symmetric enough
that Phase A's test case doesn't expose this. Real bracket parts with
molded asymmetry (see Phase B/C scope below) will need this resolved
against their actual geometry, the same way `local_offset` already handles
asymmetric slopes.

## Phase B — structural graph extension (done, this session)

**Problem it solved:** `structure/graph.py::build_connectivity_graph` only
built edges from `top_stud_world_positions()` / `bottom_stud_world_positions()`.
A SNOT branch hanging off the side of a stable core had no edge type at
all — `analyze()` / `bridge_unstable()` / `prune_unstable()` would have seen
it as a floating island.

**What actually shipped:**
- `snot.py` gained `SnotChild` (a frozen dataclass: `parent_index`, `part`,
  `local_pos`, `local_rotation` — a parallel, explicitly-indexed list kept
  alongside a `Model`, NOT folded into `Model`'s own grid; that decision was
  made deliberately, see below) and `in_plane_axis(face)`.
- `structure/graph.py::build_connectivity_graph(model, snot_children=None)`
  — new optional param. When given a list of `SnotChild`, adds one graph
  node per child (`("snot", i)` tuples — deliberately never plain ints, so
  they can't collide with or be silently misread as brick indices) and two
  edge types, both weighted by shared-stud count the same way the ordinary
  top/bottom edges are: **parent↔child** (child flush against the parent's
  own molded stud(s), weight = how many of the parent's `side_stud_count`
  studs it overlaps) and **child↔child** (two children stacked outward in
  the same frame with overlapping in-plane footprints). Omitting
  `snot_children` (every pre-existing call site) is byte-for-byte the old
  behavior — verified, not just claimed (see test list below).
- **Two existing consumers would have mishandled the new node type and
  needed fixing, found by actually tracing through them, not by
  inspection alone:** `weakpoints.py::find_bricks_outside_main_component`
  filtered its result to `isinstance(i, int)` — this quietly drops the
  `GROUND` string (correct) but would have ALSO silently dropped a
  genuinely-disconnected SNOT island with no int brick in it, turning a
  real disconnection into an empty "all clear" set. Fixed by filtering on
  `i != GROUND` instead. `load.py::propagate_gravity_load` and
  `weakpoints.py::find_ungrounded_bricks` both index `model.bricks[...]`
  by a neighbor node id, which crashes on a `("snot", i)` tuple — both now
  skip non-int neighbors explicitly. Real SNOT load propagation is still
  NOT implemented (a SNOT branch's weight doesn't load its parent, and
  vice versa) — documented as a known gap in `load.py`'s own comment, not
  silently absent.
- `report.py::analyze()` gained the same optional `snot_children` param.
- **The decision the prior handoff flagged as open — does `Model`'s grid
  need to track SNOT children for the graph to see them — was resolved
  as: no, keep them external.** `SnotChild` is a parallel list the caller
  passes explicitly to both `place_in_frame` (LDR output) and
  `build_connectivity_graph` (structural analysis). This matches Phase A's
  own reasoning for keeping SNOT out of `Model`'s collision grid, and
  avoided touching any of `Model`'s already-proven code.
- **A real "longer" SNOT brick was added**, at the founder's explicit
  request that sideways attachment not be stuck at 1×1: `30414` ("Brick
  1 x 4 with Studs on Side"), geometry fetched and verified from the raw
  `.dat` file — 4 `stud2a.dat` placements (same primitive 87087 uses) at
  local X = -30/-10/10/30, Y=10, Z=-10 (same face/from_top convention as
  87087, 4 studs instead of 1); also has real top studs, genuinely
  dual-purpose. Needed one new `Part` field, `side_stud_count` (default 1,
  no existing part affected), plus `side_stud_local_positions()`. **The
  multi-stud generalization needed ZERO changes to Phase A's already-
  verified placement math** — confirmed computationally, not assumed: a
  child at `local_pos.x = k` lands exactly on real stud index `k` for all
  4 positions, and a single wide child spans the parent's entire row flush
  and centered with the *default* `face_offset` (both checked against
  30414's real fetched geometry in `tests/test_snot.py`, not just internal
  consistency).
- **Verification, matching this project's before/after discipline:**
  `tests/test_structure_snot.py` (new, 9 tests) includes
  `test_snot_branch_is_no_longer_misclassified_as_disconnected`, which
  builds a "before" graph by hand (a SNOT node added with no edges, as
  Phase A would have left it) and shows `find_bricks_outside_main_component`
  flags it, then builds the same case through the real
  `build_connectivity_graph(model, snot_children)` and shows it's no longer
  flagged and is in the same component as `GROUND` — the literal
  before/after measurement the plan asked for. Full suite: **137/137
  pass** (125 pre-existing + 4 new in `test_snot.py` for the 30414
  geometry + 9 new in `test_structure_snot.py` for the graph edges + 1
  informational field added to an existing 87087 test).
- `examples/snot_structural_test.py` (new) builds a small real case
  (grounded 30414 + a wide plate spanning all 4 studs + a second wide
  plate stacked outward + a narrow plate at one specific stud index)
  through the real API and runs it through `analyze()` — printed output
  confirms `is_single_piece=True, critical_bricks=set()`. Generates
  `examples/output/snot_structural_test.ldr`. **Not yet sent to / confirmed
  by the founder in Studio** — do that before treating Phase B's geometry
  claims (the 30414 multi-stud placement specifically) as fully closed,
  same two-step discipline as everything else in this project. (Phase A's
  own `snot_alignment_test.ldr` is *also* still unconfirmed as of this
  handoff — see below, that's now two files waiting on Studio review.)

**Explicitly still not done, and not needed for Phase C to start:** SNOT
children still aren't part of `Model`'s own collision grid (still written
via `RawPlacement`) or included in real gravity-load propagation;
`bridge_unstable`/`prune_unstable`/`refill_enclosed_holes` don't act on SNOT
nodes.

## Phase C — automatic placement algorithm (start here)

Scan a stable core's outward-facing faces (from the existing legalize +
repair pipeline output — **the plan is explicit: don't build a second
"stable core" generator, reuse `mesh_to_model_full` → `legalize` →
`bridge_unstable`/`refill_enclosed_holes`/`prune_unstable`'s output
directly**), use the mesh's original solid silhouette (`solid_grid` —
already used by `bridge_unstable` for exactly this "stay inside the real
shape" check) to decide protrusion depth per anchor point, and pick a
closing slope/wedge. Needs additional verified SNOT parts beyond 87087
(DESIGN.md §4.3 names `4070`, `99207`, `99780`, `44728`, `4733` — none
fetched/verified yet) plus more slope/wedge variants for the
surface-finishing pass, each verified against raw `.dat` geometry the same
way every existing catalog entry was (see `CLAUDE.md`'s slope-family
history for how many times "verify, don't assume" caught a real bug there).

## Phase D — web app toggle (last, deliberately)

A build-mode selector (SNOT vs. plates/bricks) near the size selector on
generation, threaded through `GenerateRequest` → `Job`/`process_job` →
`mesh_to_ldr` → `mesh_to_model_full`. Nothing real to build here until
Phases B and C exist — this is a UI stub with no logic behind it otherwise.

## Files touched, Phase A (prior session, committed)

- `core/brickforge/snot.py` (new)
- `core/brickforge/parts.py` — `Part.side_stud_face`, `Part.side_stud_offset`
- `core/brickforge/catalog/parts_v1.yaml` — new `87087` SNOT entry
- `core/brickforge/ldr_writer.py` — `RawPlacement`, `raw_placements` param
- `core/brickforge/__init__.py` — new exports
- `core/tests/test_snot.py` (new, 15 tests)
- `core/tests/test_parts.py` — part count 48→49
- `core/examples/snot_alignment_test.py` (new)
- `core/examples/output/snot_alignment_test.ldr` (generated artifact, sent
  to founder twice — once pre-bug-4-fix, once post-fix; still unconfirmed)

Commits: `61b0c80` (Phase A foundations), `fff54a3` (vertical-centering fix).

## Files touched, Phase B (this session, **NOT yet committed**)

- `core/brickforge/snot.py` — new `SnotChild` dataclass, `in_plane_axis()`
- `core/brickforge/parts.py` — `Part.side_stud_count`,
  `Part.side_stud_local_positions()`
- `core/brickforge/catalog/parts_v1.yaml` — new `30414` SNOT entry
- `core/brickforge/structure/graph.py` — `build_connectivity_graph` gains
  `snot_children` param, `_add_snot_edges`, `_in_plane_span`
- `core/brickforge/structure/weakpoints.py` — `find_bricks_outside_main_component`
  filter fix, `find_ungrounded_bricks` non-int-neighbor guard
- `core/brickforge/structure/load.py` — `propagate_gravity_load`
  non-int-neighbor guard
- `core/brickforge/structure/report.py` — `analyze()` gains
  `snot_children` param
- `core/brickforge/__init__.py` — new exports (`SnotChild`, `in_plane_axis`)
- `core/tests/test_snot.py` — 3 new tests (30414 catalog + geometry
  verification) + 1 new assertion on the existing 87087 test
- `core/tests/test_parts.py` — part count 49→50
- `core/tests/test_structure_snot.py` (new, 9 tests)
- `core/examples/snot_structural_test.py` (new)
- `core/examples/output/snot_structural_test.ldr` (new generated artifact,
  NOT yet sent to / confirmed by the founder)
- `CLAUDE.md` — Phase A (which was missing from this file entirely — the
  prior session's commits never touched it) and Phase B both documented
  now, right before the "See DESIGN.md §9" line

**137/137 tests pass.** Nothing committed yet — review the diff, then
commit with a message covering both the graph extension and the 30414
addition (they landed together this session).

## Deployment/security posture (unchanged since 2026-08-08, still accurate)

Live Stripe (live mode), `GENERATION_ALLOWLIST` cleared, rate-limited
login/signup, security headers, job_id UUID-validated, `/docs` disabled,
webhook signatures fail-closed, no JWT revocation / Docker runs as root /
no signup email verification (accepted low-severity items, unchanged).
Legal pages current. Full detail in git history if needed — not repeated
here since nothing in this area changed this session.

## Repo state

Phase A is committed and pushed to `master` on GitHub (`Doshi143/BrickForgerAI`)
as of commit `fff54a3`. **Phase B (this session) is uncommitted** — working
tree has real, tested changes across the files listed above, plus this
handoff and `web/OPERATIONS.md` (untracked from an earlier session, unrelated
to SNOT). **First thing to do in the next session:**
1. Check whether the founder has confirmed `snot_alignment_test.ldr`
   (Phase A) and/or `snot_structural_test.ldr` (Phase B, new) look flush in
   Studio — neither has a confirmation back yet as of this handoff.
2. Decide whether to commit Phase B's changes before starting Phase C (all
   tests pass, but per this project's practice, only commit when asked —
   confirm with the founder first if that hasn't happened already).
3. Start Phase C using the scope below.
