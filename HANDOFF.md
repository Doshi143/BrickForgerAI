# BrickForgerAI — Handoff: SNOT Phase C.2

**Purpose:** paste this whole file as your first message in a new conversation
to resume exactly where this session left off. Written 2026-08-09, last
updated 2026-08-10 after Phase C.1 (including region-growing) landed and was
confirmed in Studio. Supersedes the earlier Phase B/C handoff — that one's
deployment content (live app, Railway layout, env vars, security posture) is
still accurate and summarized briefly below, but the active work now is SNOT
Phase C.2, not deployment.

---

## Where things stand right now

**The app is fully live** (`https://brickforgerai.com`), real Stripe payments
in live mode, open signup, Railway (5 services: frontend/backend/worker/
Postgres/Redis). Since the last deployment handoff, four more things shipped:
a **public Gallery** (publish builds from "My Builds", browse/search even
logged out, non-creators always pay regardless of plan — commit `5c5b072`),
**SNOT Phase A** (commits `61b0c80`, `fff54a3`), **SNOT Phase B** (commit
`c743acb`), and **SNOT Phase C.1 with region-growing** (this session,
committed — see below). No other known outstanding bug or half-finished
deployment work.

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
- **Phase C (in progress)** — the actual automatic SNOT placement algorithm.
  **C.1 (anchor detection + flush panels + region-growing) is done, this
  session** — see below, including 4 real bugs found and fixed via Studio
  review. **C.2 (closing slopes, real depth, denser candidate detection) is
  next** — start here.
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

**Explicitly still not done after Phase B:** SNOT children still aren't
part of `Model`'s own collision grid (still written via `RawPlacement`) or
included in real gravity-load propagation; `bridge_unstable`/`prune_unstable`/
`refill_enclosed_holes` don't act on SNOT nodes. (Phase C.1, below, doesn't
change any of this either — still true as of this handoff.)

## Phase C.1 — automatic anchor detection + flush-panel attachment (done, this session)

The full Phase C vision (scan outward faces, decide protrusion depth via
`solid_grid`, pick a closing slope/wedge) was explicitly scoped down before
starting, via a plan the founder approved
(`C:\Users\aarya\.claude\plans\tranquil-dreaming-hamming.md` — read it in
full before touching Phase C.2, it has the reasoning this section only
summarizes) into one verified first slice, the same way Phase A/B were each
scoped down from the full SNOT vision.

**What shipped:**
- `snot.py::rotation_for_outward_face(part, target_face, world_footprint)`
  — given a SNOT part and the world direction its stud should point, tries
  all 4 `Rotation`s, keeps only the ones that preserve `world_footprint`
  (so a swap can't collide with anything else), and returns whichever of
  those also points the part's native `side_stud_face` the right way (or
  `None`). Provably correct for an asymmetric part like 30414 with zero
  special-casing: exactly 2 of the 4 rotations preserve a `[4,1]`
  footprint, and those 2 map the native face to the two faces
  *perpendicular* to the long axis — so the two short ends correctly never
  resolve. Pinned computationally (not just argued) in `tests/test_snot.py`.
- New module `pipeline/snot_placement.py::place_snot_panels(model, solid_grid=None)`
  — scans an already-repaired `Model` for ordinary bricks (`category ==
  "brick"`, `top == "full"`) with a fully-exposed outward side face
  (checked against the same `occupied_cells()` pattern `bridge_unstable`
  already uses), swaps each candidate for the matching real SNOT part
  (87087 or 30414) via `rotation_for_outward_face`, and attaches exactly
  one flush plate outward — gated by `solid_grid` (every cell the panel
  would occupy must be part of the original solid mesh, same "stay inside
  the real shape" reasoning `bridge_unstable` already uses for its own
  pillars) so nothing pokes into open air. `87087` (`top: none`) is only
  swapped in where the candidate's own top is already exposed (same rule
  tile substitution uses); `30414` (`top: full`) never needs that check.
  Returns a `SnotPlacementResult` (`model`, `snot_children`, `swapped`,
  `attached` counts).
- Wired into `examples/structural_report.py` between
  `substitute_staircase_slopes` and `substitute_tiles` (both SNOT and
  staircase-slope detection draw from the same brick-height-block pool, so
  SNOT running second lets slopes get first pick of a genuine step edge) —
  the first real end-to-end use of Phase B's `analyze(model, snot_children)`
  parameter, asserting no regression before/after, same discipline as
  every other substitution pass in that file.
- `tests/test_pipeline_snot_placement.py` (new): the rotation math (moved
  into `tests/test_snot.py` instead, since it's a `snot.py` function, not a
  pipeline one), hand-built swap/attach cases, top-connectivity and
  `solid_grid` gate cases.

**First measurement (turret 9, mushroom 92, bunny 0) was sent to the
founder and shipped a real bug — caught in Studio, not by the test suite.**
Reported back: the turret's panels looked visibly jumbled/misaligned, and
none of the mushroom's 92 panels were visible at all. Root cause, found by
tracing the actual placed geometry rather than re-arguing the code:
`_find_panel`'s original "first exposed face wins, fixed order
+x/-x/+z/-z" rule breaks down for a brick with ALL 4 side faces open — a
free-floating single-stud spike (a crenellation tip, a corner merlon) —
which has no principled "outward" direction at all. The old rule always
picked the fixed `+x` regardless of where the spike actually sat, so
several isolated merlons on the turret all sprouted a panel pointing the
same direction, several pointing straight at each other or into the gaps
between merlons — exactly the jumble reported.

**Fix**: a face only qualifies now if its OPPOSITE face has real backing
material (`any` cell occupied, not `all` — a single thin plate is enough)
— i.e. the brick reads as part of an actual wall, not a floating spike.
`test_fully_isolated_brick_with_no_backing_anywhere_is_not_swapped` pins
this down; the other hand-built tests were redesigned around a genuine
2-brick "wall" (a thin backing plate + the candidate), since the originals
used an isolated single brick as their success case — precisely the
scenario the fix now (correctly) rejects.

**150/150 → 151/151 tests pass after the fix** (+1 net: the new isolated-
spike regression test).

**Re-measured, and it's a large, honest drop, not a bug in the new
numbers:** turret **9 → 6** (the 3 isolated merlon-tip panels correctly
removed; the remaining 6 are 3 coherent opposite-facing pairs, one per
height tier). mushroom **92 → 3** — only 3 of its brick-height blocks
actually have real 2-brick-thick wall backing; the other 89 were isolated
single-stud towers. Bunny stays at **0**, still not root-caused.

**A second, DEEPER geometry bug turned up on re-review in Studio — the
turret still looked wrong.** Root cause: `snot_frame_for_brick`'s in-plane
origin used an unconditional MIN corner, correct only when the child's
local X axis maps to that world axis with coefficient +1 — true for
YAW_0/YAW_270 but not YAW_90/YAW_180 given this codebase's one real
`local_face` ("-z"), and 2 of the turret's 6 panels landed mirrored to the
wrong side of their parent entirely. **This bug predates this session** —
latent in Phase A's own math since it shipped, invisible because Phase A
only ever tested a symmetric child and Phase B's own wide-child test only
ever used a YAW_0 parent. Fixed by reading the sign directly off the
already-composed `frame.matrix` (`matrix[0]`/`matrix[6]`) instead of
assuming it; pinned with `test_wide_child_stays_flush_across_all_four_parent_rotations`
in `tests/test_snot.py`. All 6 turret + 3 mushroom panels re-verified
geometrically flush by direct bounding-box computation before re-sending.

**Region-growing was then implemented in the same session**, at the
founder's explicit, direct request ("I want full stud coverage... not
just partial") rather than deferred to a later phase. Swapped-in parents
sharing the same part id + rotation (identical frame matrix) and
contiguous `SnotFrame` origins now merge into one run, tiled with the
widest available plates instead of one narrow plate per brick — see
`pipeline/snot_placement.py`'s own module docstring.

**This surfaced a THIRD and FOURTH bug**, both found by testing an actual
multi-brick merge rather than trusting the (separately verified) placement
math to compose correctly:
- Merge direction: contiguity is checked in world-ascending order, but
  whether increasing `local_pos` (used to walk from a run's anchor to its
  other members) moves toward increasing or decreasing world coordinate
  depends on the same sign the origin fix above deals with — a naive
  world-ascending tiling order placed a run's second tile on the wrong
  side of the anchor. Fixed by reversing a run's member order when its
  coefficient is negative.
- Missing graph edges: a region-grown tile can rest on studs belonging to
  parents OTHER than the one anchoring its own frame, and the old edge
  computation only ever credited the declared anchor — a merged run's
  trailing tile could end up with ZERO graph edge at all. Fixed by giving
  `SnotChild` an optional `parent_overlaps` field (pre-computed by
  whichever stage builds the child; `None` preserves old single-parent
  behavior exactly) that `structure/graph.py` trusts directly when present.

Pinned with `test_five_adjacent_candidates_merge_into_one_region_grown_run`,
which asserts the merged panel's FULL raw geometry spans the whole row
with no gap/overlap — not just that swaps happened. **156/156 tests pass.**

**Confirmed in Studio**: `examples/output/snot_region_growing_test.ldr` (a
purpose-built 5-brick wall, since the real example models don't happen to
have any physically-adjacent SNOT candidates — see below) — one continuous
merged yellow panel spanning all 5 bricks, confirmed by the founder.

**Net, honest result on the real models: turret/mushroom/bunny counts are
UNCHANGED (6/3/0) after region-growing, with `attached == swapped` in every
case — zero actual merges fired.** Not a bug: none of their current SNOT
candidates happen to be physically adjacent to another candidate facing the
same direction (turret's 6 are 3 isolated opposite-facing pairs at 3
different height tiers; mushroom's 3 are similarly scattered). The
mechanism is implemented and correctly tested; the current models simply
don't have contiguous wall material to exercise it on. Getting a visibly
denser look on a real model needs either a shape with more contiguous SNOT-
eligible wall material, or loosening candidate detection — neither
attempted this session.

**Explicitly, deliberately NOT done this session** (see the plan file for
full reasoning):
- No closing slope/wedge on the panel — still a flat flush plate, not the
  rounded silhouette DESIGN.md's reference image shows. Composing this
  project's existing slope-orientation conventions through a SNOT local
  frame is real new geometry work with the same bug shape this project has
  hit repeatedly this session (2-plate tier shipped backwards historically,
  the origin-sign bug now) — do this as its own verified pass, not rushed.
- No multi-plate depth control past a single outward step — `solid_grid`
  is stud-indexed (20 LDU) but a SNOT plate stack moves outward in plate
  increments (8 LDU); real unit-conversion work, deferred rather than
  hand-waved.
- No collision-checking between two *different* runs' independently
  attached panels (e.g. a concave corner) beyond one partial, sequential
  mitigation: each accepted panel's own cells are added to the shared
  `occupied` set as placement proceeds. Real and effective within one
  pass, not a full symmetric collision system — SNOT children still aren't
  part of `Model`'s own collision grid at all (unchanged from Phase A/B).
- No `4070`/`99207`/`99780`/`44728`/`4733` catalog parts — not needed until
  a bracket/panel shape beyond 87087/30414 is wanted.

## Phase C.2+ — closing slopes, real depth, denser candidate detection (start here next)

1. **Closing slope/wedge selection**, composing this catalog's existing
   slope-orientation work (see `pipeline/slopes.py` and `CLAUDE.md`'s slope
   history) through a SNOT local frame — the major remaining lever for
   visual quality, matching the Niemann-Sculpt reference's rounded look.
2. **Real, sub-stud-granularity depth control** using `solid_grid`, so a
   panel can extend more than one flat plate outward where the mesh
   actually allows it.
3. **Denser candidate detection** — region-growing itself is done, but it
   only helps if there's contiguous material to grow across, and the real
   models currently don't have much (see the honest zero-merges result
   above). Worth investigating whether the backing-check safety rule
   (correct, not to be loosened carelessly — see the isolated-spike bug
   above) is nonetheless leaving genuinely mergeable material on the table,
   or whether this is a real, inherent scarcity in what the legalizer
   produces (matching the already-documented brick-height-material
   scarcity for staircase slopes).
4. Additional verified SNOT parts (`4070`, `99207`, `99780`, `44728`,
   `4733` — DESIGN.md §4.3) once a shape beyond 87087/30414 is actually
   needed for one of the above, each verified against raw `.dat` geometry
   the same way every existing catalog entry was.

## Phase D — web app toggle (last, deliberately)

A build-mode selector (SNOT vs. plates/bricks) near the size selector on
generation, threaded through `GenerateRequest` → `Job`/`process_job` →
`mesh_to_ldr` → `mesh_to_model_full`. Still premature — Phase C.1 exists but
produces a flat-panel result, not the finished look a user-facing toggle
should promise; wait for at least Phase C.2's closing slopes before wiring
this into the web app.

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

## Files touched, Phase B (this session, committed as `c743acb`, pushed)

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

**137/137 tests pass.**

## Files touched, Phase C.1 (this session, including region-growing)

- `core/brickforge/snot.py` — new `rotation_for_outward_face()`; the
  origin-sign fix in `snot_frame_for_brick` (bug #2, predates this
  session but only found/fixed now); new `SnotChild.parent_overlaps` field
- `core/brickforge/__init__.py` — export `rotation_for_outward_face`
- `core/brickforge/structure/graph.py` — SNOT edge computation trusts
  `parent_overlaps` when present (bug #4 fix)
- `core/brickforge/pipeline/snot_placement.py` (new) — `place_snot_panels`,
  `SnotPlacementResult`, region-growing (`_group_into_runs`, `_tile_run`),
  the backing-check fix in `_find_panel` (bug #1), the merge-direction fix
  (bug #3)
- `core/tests/test_snot.py` — `rotation_for_outward_face` tests +
  `test_wide_child_stays_flush_across_all_four_parent_rotations` (pins
  bug #2's fix)
- `core/tests/test_pipeline_snot_placement.py` (new) — hand-built swap/
  attach/gate cases (2-brick "wall" pattern, not an isolated single
  brick) + `test_five_adjacent_candidates_merge_into_one_region_grown_run`
  (pins bugs #3/#4's fixes with a full raw-geometry check)
- `core/examples/structural_report.py` — SNOT placement wired in between
  slope and tile substitution; builds and saves SNOT `RawPlacement`s into
  each `*_refined.ldr`
- `core/examples/output/turret_refined.ldr`, `mushroom_refined.ldr`,
  `bunny_refined.ldr` — final counts turret 6, mushroom 3, bunny 0
  (region-growing fires zero times on all three — see the honest-zero
  writeup above)
- `core/examples/snot_region_growing_test.py` (new) + its `.ldr` output —
  purpose-built 5-brick wall demonstrating the merge; **confirmed correct
  by the founder in Studio**
- `CLAUDE.md` — full writeup of all 4 bugs, the fixes, and the honest
  zero-merges result on real models
- `C:\Users\aarya\.claude\plans\tranquil-dreaming-hamming.md` — the
  approved plan for the original (pre-region-growing) scope of this slice

**156/156 tests pass.**

## Deployment/security posture (unchanged since 2026-08-08, still accurate)

Live Stripe (live mode), `GENERATION_ALLOWLIST` cleared, rate-limited
login/signup, security headers, job_id UUID-validated, `/docs` disabled,
webhook signatures fail-closed, no JWT revocation / Docker runs as root /
no signup email verification (accepted low-severity items, unchanged).
Legal pages current. Full detail in git history if needed — not repeated
here since nothing in this area changed this session.

## Repo state

Phase A (`fff54a3`), Phase B (`c743acb`), and Phase C.1 with region-growing
(`ab862e0`) are all committed and pushed to `master` on GitHub
(`Doshi143/BrickForgerAI`). Studio
confirmations so far: Phase A's `snot_alignment_test.ldr` ✓, Phase B's
`snot_structural_test.ldr` ✓, Phase C.1's `snot_region_growing_test.ldr` ✓
(after 2 rounds of real bugs found and fixed in Studio review). **Not
separately re-confirmed**: the final (bug-#2-fixed) `turret_refined.ldr`/
`mushroom_refined.ldr` — the founder's next reply was about the
region-growing scene, not an explicit re-check of these two specific
files; the geometry is verified computationally (see CLAUDE.md) but a
belt-and-suspenders Studio look wouldn't hurt if picking this up fresh.
**First thing to do in the next session:** start Phase C.2 using the scope
above (closing slopes, real depth, denser candidate detection).
