"""Staircase-to-slope substitution (DESIGN.md pipeline step: surface
refinement). Detects blocks that sit at a genuine step-down edge in one of
the 4 cardinal directions and replaces them in place with the
correspondingly-sized, correspondingly-rotated upright slope -- at whatever
height tiers the catalog provides.

Three tiers exist:

- **3-plate (brick height), swap**: a **1-to-1 swap** of a single already-placed
  `brick`-category part for the matching slope. Originally measured to fire
  on zero real models (see CLAUDE.md Phase 3): the legalizer's output used
  to be almost entirely individual plates, so brick-height blocks were
  rare. The Stage B seam-penalty loosening (see legalize.py's
  SEAM_CANDIDATE_PENALTY_WEIGHT) produces far more consolidated bricks,
  which is exactly the material this tier needs -- see CLAUDE.md for the
  re-measured counts. Two independent slope families now compete for this
  tier (45-degree, run=2 studs, and 33-degree, run=3 studs -- see below);
  "prefer whichever fits" falls out of the generalized lookup key, not an
  explicit tie-break.
- **3-plate (brick height), stack**: the same riser and the same
  `_find_step_edge_rotation` geometry as the swap tier above, but applied
  to three vertically-stacked, identically-footprinted PLATES that
  legalize.py's Stage B deliberately left unconsolidated because their
  own top was genuinely exposed (see that module's own Stage B comment).
  Added because the swap tier alone was starved by construction: Stage B
  used to consolidate every eligible run into a brick unconditionally,
  which is exactly the material a *tile* substitution can never use (no
  tile exists for brick-height parts) -- so a top-exposed run that wasn't
  a genuine step-down edge was permanently locked out of ever becoming a
  smooth tiled surface either. This tier is what lets a genuinely
  step-down-shaped run become a slope even though the legalizer never
  independently decided to consolidate it into a brick on its own.
- **2-plate ("2/3 brick"), merge -- the real "detail" tier**: no standard
  rectangular slope is exactly 1 plate tall (searched, came up empty, did
  not invent a part -- see catalog/parts_v1.yaml's header on this family).
  2 plates is the shallowest real size, and this project's plate-heavy
  legalizer output is full of *pairs* of vertically-stacked, identically
  footprinted plates that never got consolidated into a brick (Stage B
  only merges stacks of exactly 3, and even a genuine 3-stack now goes to
  the tier above first if it qualifies -- see the ordering note below).
  So this tier is a **merge of two placed parts into one**, not a swap --
  see the module-level safety note below, since that's a materially
  different operation from tile substitution and the swap tier.

The swap tier can never collide with either plate-based tier (a
brick-category object is never also a candidate plate stack/pair, and
vice versa, since a catalog `Part`'s `height_plates` is always exactly 3
for `category: brick` and exactly 1 for `category: plate`), so it's
always tried independently. The two PLATE-based tiers, unlike the old
two-tier design, genuinely can compete for the same three stacked
plates -- a bottom pair of a real 3-stack is also a valid 2-plate
candidate on its own. `substitute_staircase_slopes` resolves this with an
explicit ordering, not a lookup-key trick: the 3-stack tier runs first
and marks every plate it consumes, and the 2-plate tier then skips
anything already claimed -- so "prefer a larger slope where one is
possible" still holds, it just needs an actual tie-break now that two
tiers share the same kind of source material.

Orientation was verified empirically, not derived from the naming
convention alone (same discipline as the footprint-axis and origin-anchor
findings elsewhere in this catalog): at YAW_0, the **45-degree 3-plate**
family's tall/vertical face is on the -Z side of its own footprint and it
descends toward +Z -- confirmed via examples/output/slope_orientation_test.ldr
(a 2x2 brick placed immediately adjacent, in +Z, to a 2x2 slope), opened in
Studio and visually confirmed flush at the boundary with no step or gap.
Rotating that relationship through each yaw (via the same Rotation matrix
already used by rotate_offset) gives the base map below.

    downhill +Z -> YAW_0   (tall/uphill face -Z)
    downhill +X -> YAW_90  (tall/uphill face -X)
    downhill -Z -> YAW_180 (tall/uphill face +Z)
    downhill -X -> YAW_270 (tall/uphill face +X)

**Two other families face the OPPOSITE way at YAW_0 -- each verified
independently from raw geometry, never assumed to match the 45-degree
family just because all three are "slopes" (a real bug the 2-plate tier's
first version shipped with, caught by the user seeing it placed backwards
in Studio).** The 2-plate family's 7825 (`s/7825s01.dat`) runs from
(Z=-10, Y=-4) -- close to this bottom-anchored family's own ground level,
the THIN/downhill edge -- to (Z=+6, Y=-13.6) -- near full height, the
TALL/uphill edge: tall face at +Z, descending toward -Z (85984 and 7835
show the identical pairing). The 33-degree 3-plate family
(4286/3298/4161/3297) shows the same mirrored pattern despite being
brick-height like the 45-degree family, not 2-plate-height like the
family it happens to share a facing convention with: 4286's sloped-face
quad runs from (Z=-10, Y=0) -- the TALL/uphill edge, full height -- to
(Z=-50, Y=20) -- near the THIN/downhill edge; tall face at the less-
negative Z end (mapped to +Z after recentering, see catalog/parts_v1.yaml),
downhill toward more-negative Z, same mirror-image shape as the 2-plate
family and the opposite of the 45-degree family's own -Z-tall convention.
3298/4161/3297 show the identical Z/Y pairing at their respective widths.
Rather than maintain a second (or third) direction-to-rotation table,
every part whose real orientation is flipped is listed explicitly in
`_FLIPPED_PART_IDS`, and `_find_step_edge_rotation` applies
`_OPPOSITE_ROTATION` only for those -- one source of truth for "which
direction is which rotation" (the base table), with per-part flips layered
on top rather than guessed from any shared property (height tier, run
length, etc.) of the parts involved.

**Inverted slopes (the underside/overhang case) are now handled too --
one tier only, mirroring the upright 3-plate swap tier exactly.** A
brick-category candidate whose own BOTTOM is exposed to open air (the
overhang case: nothing directly beneath it) gets checked for a genuine
step-up edge underneath, using `column_bottom` (the shallowest/lowest y
any brick reaches in a column -- the mirror image of `column_top`) and
comparing with `<=`/`>` instead of `>=`/`<`, the same shape of test just
flipped top-for-bottom and max-for-min. Reuses the exact same
`_DOWNHILL_ROTATION` table and per-part `_FLIPPED_PART_IDS` mechanism --
"downhill"/"uphill" mean the same cardinal-direction relationship
whether the tested face is a top or a bottom, so no second rotation
table was needed, only a mirrored geometric test
(`_find_step_edge_rotation_underside`).

Verified from raw geometry, not assumed to share the upright family's
own orientation: 3665/3660's real sloped-face quads put their
TALL/thick end at the LESS-negative-Z side of their own footprint and
their THIN end at the MORE-negative-Z side -- the mirror image of the
upright 45-degree family's own -Z-tall/+Z-thin convention (see the
existing docstring section above). So 3665, 3660, and their two new
cutout/double-convex variants (2310, 3676 -- same shape family, same
measured Z split) are all listed in `_FLIPPED_PART_IDS` alongside the
already-flipped upright families, rather than assumed to follow the
un-flipped 45-degree base convention just because they're "the same 45
degrees".

**Only the 3-plate (brick-height) inverted swap tier is implemented.**
Deliberately not attempted this pass, to avoid shipping unverified
geometry: `24201` (the 2-plate curved inverted slope) is in the catalog
but not wired into detection here -- its footprint/height/local_offset
were confirmed from raw geometry, but which cardinal direction is its
own "thick" vs "thin" end was not independently verified the way
3665/3660 were, and this catalog has been burned before by assuming
orientation carries across families without checking (see the existing
docstring section above on the 2-plate and 33-degree families). Also
not attempted: plate-stack/plate-merge tiers for the inverted case
(the analogues of `_find_3plate_stack_slope`/`_find_2plate_merge`) --
real future scope, not silently dropped, just genuinely more surface
area than this pass covers.

Safety, inverted tier: actually a STRICTLY safer substitution than any
upright tier. A plain brick candidate always has `top: full` in this
catalog, and every inverted slope here also has `top: full` -- so the
substitution changes NOTHING about top connectivity, ever. The only
thing that changes is bottom connectivity (full -> none), and that's
only attempted where the candidate's bottom is already exposed to open
air (nothing there to disconnect from in the first place) -- the exact
same "only removes connectivity nothing was using" argument the upright
tiers rely on, just for the one face that changes instead of two.

Safety, 3-plate (swap) tier: exactly the same precondition as tile
substitution (surface_refine.py) -- every brick part in this catalog has
bottom: full, same as every slope, so a substitution never changes
downward connectivity; it only ever removes TOP connectivity, and only
where a candidate's top is already fully exposed (nothing resting on it).

Safety, 2-plate (merge) tier and 3-plate (stack) tier: a merge/stack
deletes TWO or THREE placed parts (a lower plate plus one or two more
directly above it, all sharing the identical footprint) and replaces all
of them with ONE slope at the lowest plate's position. Both reduce to the
same "only ever removes unused TOP connectivity" argument the swap tier
uses, just restated for a chain: the lowest plate's own downward
connectivity (position, footprint, bottom: full) is unchanged, so
whatever supported it still does; the topmost plate's top must be fully
exposed (identical precondition to the swap case) before a merge/stack is
attempted; and every internal stud edge between the chained plates is not
left dangling -- both endpoints of each one are deleted together, so
nothing external ever depended on any of them surviving. Net effect on
the connectivity graph has the same shape as the swap case regardless of
chain length: one node's downward connectivity preserved, its upward
connectivity removed only where nothing used it. Confirmed with a
before/after analyze() test for all three tiers, not just argued (see
tests/test_pipeline_slopes.py).

A candidate is only converted if the surface genuinely steps down: the
column(s) immediately beyond its downhill face must be strictly lower (or
empty), and the column(s) behind its uphill face must be at least as
tall. This rules out carving a wedge out of a flat roof or an isolated
peak with no real "step" to smooth. If a candidate matches more than one
direction (e.g. a peak surrounded by lower terrain on all sides), the
first match wins -- an arbitrary but geometrically valid tie-break, since
only one slope can ever replace a single candidate.
"""

from __future__ import annotations

from ..lattice import Rotation
from ..model import Brick, Model
from ..parts import PartCatalog

# (dx, dz) downhill direction -> rotation whose tall/uphill face points at -direction.
# Derived from the 3-plate family's empirically-verified (Studio-confirmed)
# orientation: at YAW_0, tall/uphill face at -Z, descending toward +Z.
_DOWNHILL_ROTATION: dict[tuple[int, int], Rotation] = {
    (0, 1): Rotation.YAW_0,
    (1, 0): Rotation.YAW_90,
    (0, -1): Rotation.YAW_180,
    (-1, 0): Rotation.YAW_270,
}

# Rotates a base-table rotation by 180 -- YAW_0<->YAW_180, YAW_90<->YAW_270 --
# to correct for a family whose rest orientation is the mirror image of the
# 45-degree family's (see module docstring for which families and why).
_OPPOSITE_ROTATION: dict[Rotation, Rotation] = {
    Rotation.YAW_0: Rotation.YAW_180,
    Rotation.YAW_90: Rotation.YAW_270,
    Rotation.YAW_180: Rotation.YAW_0,
    Rotation.YAW_270: Rotation.YAW_90,
}

# Part ids whose real-world rest orientation is the mirror image of the
# 45-degree family's -Z-tall/+Z-downhill convention -- see module docstring
# for the raw-geometry evidence per family. Listed explicitly per PART, not
# derived from height tier or run length: those are incidental properties
# that happen to correlate with orientation for the families measured so
# far, not a rule this catalog has verified holds in general.
_FLIPPED_PART_IDS: frozenset[str] = frozenset(
    {
        "54200", "85984", "7825", "7835",  # 2-plate ("cheese") family
        "4286", "3298", "4161", "3297",  # 33-degree 3-plate family
        "3665", "3660", "2310", "3676",  # inverted 45-degree 3-plate family
        "11477",  # curved 2-plate slope -- shipped backwards, confirmed visually in
        # Studio (slope11477_orientation_test.ldr): the default (unflipped)
        # orientation put the thin edge against the uphill support instead of
        # the tall/rounded face. Same fix as the 2-plate flat family above,
        # which had the identical bug the first time it shipped.
    }
)

# Cosmetic variants that share an exact (height, perp, run) key with a
# plain part -- see _build_inverted_slope_map's own docstring for why
# these must never win an automatic substitution over the plain part
# they're a decorated version of. "28192" added alongside the original two
# once it created the identical problem on the UPRIGHT side: it's a "with
# Cutout and without Stud" print variant of 3040 (same footprint, height,
# and local_offset -- verified independently, see parts_v1.yaml's own
# comment), so it collides on the exact same (height, perp, run) key.
_DECORATIVE_SLOPE_VARIANTS: frozenset[str] = frozenset({"2310", "3676", "28192"})


def _build_slope_map(catalog: PartCatalog) -> dict[tuple[int, int, int], tuple[str, bool]]:
    """(height_plates, perpendicular-to-incline width in studs, incline run
    length in studs) -> (upright slope part id, whether this part's rest
    orientation is flipped relative to the base _DOWNHILL_ROTATION table).

    Keyed by all three of (height, perp, run) rather than just
    (height, perp): two families can share a height tier AND a
    perpendicular width while running a different number of studs along
    the incline -- exactly what happens here, since the 45-degree (run=2)
    and 33-degree (run=3) families are both brick-height and both span
    widths 1-4 studs. A 2-key lookup would let one family silently shadow
    the other for every shared (height, perp) pair; the 3-key lookup
    can't collide FAMILIES, since (height, perp, run) uniquely identifies
    which family applies -- but it can still collide within a single
    family, the same way _build_inverted_slope_map's own key can: 28192 is
    a decorative print variant of 3040 sharing its exact key. Same fix,
    same reasoning -- see _DECORATIVE_SLOPE_VARIANTS and
    _build_inverted_slope_map's own docstring for why a decorative variant
    must never silently win an automatic substitution over the plain part
    it's a decorated version of."""
    result: dict[tuple[int, int, int], tuple[str, bool]] = {}
    for p in catalog:
        if not (p.category == "slope" and p.top == "none"):
            continue
        key = (p.height_plates, p.footprint[0], p.footprint[1])
        if key in result and p.id in _DECORATIVE_SLOPE_VARIANTS:
            continue  # a plain part already claimed this key -- keep it
        result[key] = (p.id, p.id in _FLIPPED_PART_IDS)
    return result


def _find_step_edge_rotation(
    x0: int,
    z0: int,
    w: int,
    d: int,
    top_y: int,
    riser: int,
    column_top: dict[tuple[int, int], int],
    slope_by_tier: dict[tuple[int, int, int], tuple[str, bool]],
) -> tuple[str, Rotation] | None:
    """Shared by both tiers: does this (x0, z0, w, d) candidate, whose top
    surface sits at internal-grid height `top_y`, have a genuine step-down
    edge in one of the 4 cardinal directions, at a slope of height `riser`
    that actually exists in the catalog for the relevant perpendicular
    width and run length? The returned rotation already accounts for
    whichever family's rest orientation applies (see _FLIPPED_PART_IDS)."""
    for (dxd, dzd), rotation in _DOWNHILL_ROTATION.items():
        along_d = w if dxd != 0 else d
        perp = d if dxd != 0 else w
        entry = slope_by_tier.get((riser, perp, along_d))
        if entry is None:
            continue
        slope_id, is_flipped = entry

        if dxd != 0:
            downhill_x = x0 + along_d if dxd > 0 else x0 - 1
            uphill_x = x0 - 1 if dxd > 0 else x0 + along_d
            downhill_cols = [(downhill_x, z0 + dz) for dz in range(perp)]
            uphill_cols = [(uphill_x, z0 + dz) for dz in range(perp)]
        else:
            downhill_z = z0 + along_d if dzd > 0 else z0 - 1
            uphill_z = z0 - 1 if dzd > 0 else z0 + along_d
            downhill_cols = [(x0 + dx, downhill_z) for dx in range(perp)]
            uphill_cols = [(x0 + dx, uphill_z) for dx in range(perp)]

        is_downhill = all(column_top.get(c, -1) < top_y for c in downhill_cols)
        is_uphill = all(column_top.get(c, -1) >= top_y for c in uphill_cols)
        if is_downhill and is_uphill:
            return slope_id, (_OPPOSITE_ROTATION[rotation] if is_flipped else rotation)

    return None


def _find_single_part_slope(
    brick: Brick,
    column_top: dict[tuple[int, int], int],
    occupied_at_y: dict[tuple[int, int, int], int],
    slope_by_tier: dict[tuple[int, int, int], tuple[str, bool]],
) -> tuple[str, Rotation] | None:
    """3-plate tier: brick.part.category == "brick" is, in this catalog,
    always exactly 3 plates tall and always a single placed part (Stage B
    only ever consolidates exactly 3 identical plates into a brick), so
    this is a straight 1-to-1 swap candidate."""
    if brick.part.category != "brick":
        return None

    w, d = brick.footprint
    x0, y0, z0 = brick.pos.x, brick.pos.y, brick.pos.z
    riser = brick.part.height_plates
    top_y = y0 + riser

    top_exposed = all(
        (x0 + dx, top_y, z0 + dz) not in occupied_at_y for dx in range(w) for dz in range(d)
    )
    if not top_exposed:
        return None

    return _find_step_edge_rotation(x0, z0, w, d, top_y, riser, column_top, slope_by_tier)


def _build_inverted_slope_map(catalog: PartCatalog) -> dict[tuple[int, int, int], tuple[str, bool]]:
    """Mirror of _build_slope_map for the underside/overhang case:
    top == "full" and bottom == "none" (an inverted slope) instead of
    top == "none" (an upright one). Keyed identically, and reuses the
    same _FLIPPED_PART_IDS registry -- see module docstring.

    Has a real (height, perp, run) collision, same as the upright map now
    does too (see _build_slope_map's own docstring): 3660 and its two
    cosmetic variants (2310's footprint is actually [1,2], distinct, but
    3676 shares 3660's exact [2,2] footprint and height) can share a key.
    A plain dict comprehension would let whichever part iterates last
    silently shadow the other -- exactly the failure shape
    _build_slope_map's own 3-key design was built to prevent for the
    45/33-degree families, just one level down (same key, different part,
    rather than a colliding key at all). Since there's no principled
    reason to prefer a decorative cutout/convex variant over the plain
    part for an *automatic* substitution, this explicitly prefers
    whichever candidate is NOT in `_DECORATIVE_SLOPE_VARIANTS`, rather
    than leaving the choice to incidental catalog ordering."""
    result: dict[tuple[int, int, int], tuple[str, bool]] = {}
    for p in catalog:
        if not (p.category == "slope" and p.top == "full" and p.bottom == "none"):
            continue
        key = (p.height_plates, p.footprint[0], p.footprint[1])
        if key in result and p.id in _DECORATIVE_SLOPE_VARIANTS:
            continue  # a plain part already claimed this key -- keep it
        result[key] = (p.id, p.id in _FLIPPED_PART_IDS)
    return result


def _find_step_edge_rotation_underside(
    x0: int,
    z0: int,
    w: int,
    d: int,
    bottom_y: int,
    riser: int,
    column_bottom: dict[tuple[int, int], int],
    slope_by_tier: dict[tuple[int, int, int], tuple[str, bool]],
) -> tuple[str, Rotation] | None:
    """Mirror of _find_step_edge_rotation for a candidate's BOTTOM face:
    does this (x0, z0, w, d) candidate, whose own base sits at
    internal-grid height `bottom_y`, have a genuine step-up edge
    underneath it in one of the 4 cardinal directions? `column_bottom`
    tracks the shallowest (lowest-reaching) y any brick occupies per
    column -- the mirror image of `column_top` -- and the comparisons
    are flipped accordingly: "downhill" (open/unsupported) means nothing
    there reaches as deep as this candidate's own base; "uphill"
    (support) means material there reaches at least as deep. Same
    `_DOWNHILL_ROTATION`/`_FLIPPED_PART_IDS` mechanism as the upright
    case -- "downhill"/"uphill" describe the same cardinal relationship
    regardless of which face is being tested."""
    for (dxd, dzd), rotation in _DOWNHILL_ROTATION.items():
        along_d = w if dxd != 0 else d
        perp = d if dxd != 0 else w
        entry = slope_by_tier.get((riser, perp, along_d))
        if entry is None:
            continue
        slope_id, is_flipped = entry

        if dxd != 0:
            downhill_x = x0 + along_d if dxd > 0 else x0 - 1
            uphill_x = x0 - 1 if dxd > 0 else x0 + along_d
            downhill_cols = [(downhill_x, z0 + dz) for dz in range(perp)]
            uphill_cols = [(uphill_x, z0 + dz) for dz in range(perp)]
        else:
            downhill_z = z0 + along_d if dzd > 0 else z0 - 1
            uphill_z = z0 - 1 if dzd > 0 else z0 + along_d
            downhill_cols = [(x0 + dx, downhill_z) for dx in range(perp)]
            uphill_cols = [(x0 + dx, uphill_z) for dx in range(perp)]

        is_downhill = all(column_bottom.get(c, float("inf")) > bottom_y for c in downhill_cols)
        is_uphill = all(column_bottom.get(c, float("inf")) <= bottom_y for c in uphill_cols)
        if is_downhill and is_uphill:
            return slope_id, (_OPPOSITE_ROTATION[rotation] if is_flipped else rotation)

    return None


def _find_single_part_slope_inverted(
    brick: Brick,
    column_bottom: dict[tuple[int, int], int],
    occupied_at_y: dict[tuple[int, int, int], int],
    inverted_slope_by_tier: dict[tuple[int, int, int], tuple[str, bool]],
) -> tuple[str, Rotation] | None:
    """Underside tier: mirror of _find_single_part_slope, checking the
    candidate's own bottom face (nothing directly beneath it) instead of
    its top.

    y0 <= 0 is excluded up front -- a real bug, caught by this module's
    own existing test suite, not just reasoned about in the abstract: the
    upright case's "nothing above" is unambiguous (there's no ceiling,
    so open air above is always real), but "nothing below" at y0 == 0 is
    just the model's own ground/baseplate boundary, not an overhang --
    every model in this pipeline is built bottom-up from y=0 (see
    DESIGN.md's own build-order note), so a ground-level brick sitting
    directly next to another ground-level brick always has an
    'exposed' bottom by this test's own logic, even though that's
    completely normal flat terrain, not a step-up edge underneath
    anything. Confirmed by a real test failure: a brick at y=0 next to
    another y=0 brick of the same height was wrongly swapped for an
    inverted slope before this guard existed."""
    if brick.part.category != "brick" or brick.pos.y <= 0:
        return None

    w, d = brick.footprint
    x0, y0, z0 = brick.pos.x, brick.pos.y, brick.pos.z
    riser = brick.part.height_plates

    bottom_exposed = all(
        (x0 + dx, y0 - 1, z0 + dz) not in occupied_at_y for dx in range(w) for dz in range(d)
    )
    if not bottom_exposed:
        return None

    return _find_step_edge_rotation_underside(x0, z0, w, d, y0, riser, column_bottom, inverted_slope_by_tier)


def _find_3plate_stack_slope(
    lower: Brick,
    bricks: list[Brick],
    column_top: dict[tuple[int, int], int],
    occupied_at_y: dict[tuple[int, int, int], int],
    slope_by_tier: dict[tuple[int, int, int], tuple[str, bool]],
) -> tuple[str, Rotation, int, int] | None:
    """3-plate STACK tier: three vertically-stacked, identically-footprinted
    plates that legalize.py's Stage B deliberately left unconsolidated
    (see its own Stage B comment) because the stack's own top was
    genuinely exposed -- exactly the material this tier needs, and
    exactly why that change was made there rather than here. Tried BEFORE
    the 2-plate merge tier below, so "prefer a larger slope where
    possible" holds for real instead of only for footprints that happened
    to already exist as a consolidated brick.

    Reuses `_find_step_edge_rotation` unchanged, at riser=3 -- the exact
    same geometry and orientation logic the brick-swap tier already uses,
    just fed a stack of plates instead of an already-formed brick. No new
    coordinate math, which is deliberate: every real bug this module has
    shipped came from new geometric transforms, not from swapping which
    source material feeds an already-verified one.

    Returns (slope_id, rotation, middle_index, upper_index) so the caller
    can delete all three source plates and place one slope at the lower
    plate's position."""
    w, d = lower.footprint
    x0, y0, z0 = lower.pos.x, lower.pos.y, lower.pos.z
    riser = 3

    middle_y = y0 + 1
    middle_cells = [(x0 + dx, middle_y, z0 + dz) for dx in range(w) for dz in range(d)]
    middle_indices = {occupied_at_y.get(c) for c in middle_cells}
    if len(middle_indices) != 1 or None in middle_indices:
        return None
    middle_index = middle_indices.pop()
    middle = bricks[middle_index]
    if middle.part.category != "plate" or middle.footprint != (w, d):
        return None

    upper_y = y0 + 2
    upper_cells = [(x0 + dx, upper_y, z0 + dz) for dx in range(w) for dz in range(d)]
    upper_indices = {occupied_at_y.get(c) for c in upper_cells}
    if len(upper_indices) != 1 or None in upper_indices:
        return None
    upper_index = upper_indices.pop()
    upper = bricks[upper_index]
    if upper.part.category != "plate" or upper.footprint != (w, d):
        return None

    top_y = y0 + riser
    top_exposed = all(
        (x0 + dx, top_y, z0 + dz) not in occupied_at_y for dx in range(w) for dz in range(d)
    )
    if not top_exposed:
        return None

    result = _find_step_edge_rotation(x0, z0, w, d, top_y, riser, column_top, slope_by_tier)
    if result is None:
        return None
    slope_id, rotation = result
    return slope_id, rotation, middle_index, upper_index


def _find_2plate_merge(
    lower_index: int,
    lower: Brick,
    bricks: list[Brick],
    column_top: dict[tuple[int, int], int],
    occupied_at_y: dict[tuple[int, int, int], int],
    slope_by_tier: dict[tuple[int, int, int], tuple[str, bool]],
) -> tuple[str, Rotation, int] | None:
    """2-plate tier: find a plate directly above `lower` with the identical
    footprint (every cell it covers belongs to that same single other
    plate -- not, e.g., two smaller tiles), then apply the same step-edge
    test as the swap case, parameterized by riser=2. Returns
    (slope_id, rotation, upper_index) so the caller can delete both source
    plates and place one slope in their place."""
    w, d = lower.footprint
    x0, y0, z0 = lower.pos.x, lower.pos.y, lower.pos.z
    riser = 2

    upper_y = y0 + 1
    upper_cells = [(x0 + dx, upper_y, z0 + dz) for dx in range(w) for dz in range(d)]
    upper_indices = {occupied_at_y.get(c) for c in upper_cells}
    if len(upper_indices) != 1 or None in upper_indices:
        return None
    upper_index = upper_indices.pop()
    upper = bricks[upper_index]
    if upper.part.category != "plate" or upper.footprint != (w, d):
        return None

    top_y = y0 + riser
    top_exposed = all(
        (x0 + dx, top_y, z0 + dz) not in occupied_at_y for dx in range(w) for dz in range(d)
    )
    if not top_exposed:
        return None

    result = _find_step_edge_rotation(x0, z0, w, d, top_y, riser, column_top, slope_by_tier)
    if result is None:
        return None
    slope_id, rotation = result
    # No manual flip here: _find_step_edge_rotation already applies
    # _OPPOSITE_ROTATION for this family, since 2-plate part ids are listed
    # in _FLIPPED_PART_IDS -- flipping again here would cancel it back out.
    return slope_id, rotation, upper_index


def substitute_staircase_slopes(model: Model) -> Model:
    """Return a copy of `model` with blocks at a genuine step-down edge
    replaced by the matching upright slope, at both the 3-plate (swap) and
    2-plate (merge) tiers the catalog provides, plus blocks at a genuine
    step-up edge UNDERNEATH them replaced by the matching inverted slope
    (see module docstring's own section on that tier)."""
    slope_by_tier = _build_slope_map(model.catalog)
    inverted_slope_by_tier = _build_inverted_slope_map(model.catalog)
    if not slope_by_tier and not inverted_slope_by_tier:
        return model

    column_top: dict[tuple[int, int], int] = {}
    column_bottom: dict[tuple[int, int], int] = {}
    occupied_at_y: dict[tuple[int, int, int], int] = {}
    for i, brick in enumerate(model.bricks):
        base = brick.pos.y
        top = base + brick.part.height_plates
        w, d = brick.footprint
        for dx in range(w):
            for dz in range(d):
                col = (brick.pos.x + dx, brick.pos.z + dz)
                column_top[col] = max(column_top.get(col, top), top)
                column_bottom[col] = min(column_bottom.get(col, base), base)
        for cell in brick.occupied_cells():
            occupied_at_y[cell] = i

    swap_choice: dict[int, tuple[str, Rotation]] = {}
    for i, brick in enumerate(model.bricks):
        placement = _find_single_part_slope(brick, column_top, occupied_at_y, slope_by_tier)
        if placement is not None:
            swap_choice[i] = placement

    # Underside (inverted) tier: only tried for a brick that didn't
    # already match the upright swap tier above -- a candidate whose top
    # AND bottom are both exposed with matching step patterns is rare,
    # and preferring the (older, more-tested) upright match is an
    # arbitrary but harmless tie-break, not a case this project has ever
    # actually observed.
    inverted_choice: dict[int, tuple[str, Rotation]] = {}
    if inverted_slope_by_tier:
        for i, brick in enumerate(model.bricks):
            if i in swap_choice:
                continue
            placement = _find_single_part_slope_inverted(brick, column_bottom, occupied_at_y, inverted_slope_by_tier)
            if placement is not None:
                inverted_choice[i] = placement

    # 3-plate STACK tier: three unconsolidated identical plates -> one
    # slope (see _find_3plate_stack_slope's own docstring for why this
    # material exists at all). Tried before the 2-plate merge tier below
    # so a genuine 3-tall match always wins over a shorter one at the
    # same anchor, the same "prefer larger" principle the module docstring
    # already states for the swap/merge tiers.
    stack_choice: dict[int, tuple[str, Rotation]] = {}
    stacked_away: set[int] = set()  # middle+upper plate indices consumed by a 3-stack
    for i, brick in enumerate(model.bricks):
        if brick.part.category != "plate" or i in stacked_away:
            continue
        result = _find_3plate_stack_slope(brick, model.bricks, column_top, occupied_at_y, slope_by_tier)
        if result is not None:
            slope_id, rotation, middle_index, upper_index = result
            stack_choice[i] = (slope_id, rotation)
            stacked_away.add(middle_index)
            stacked_away.add(upper_index)

    merge_choice: dict[int, tuple[str, Rotation]] = {}  # anchor (lower) index -> (slope_id, rotation)
    merged_away: set[int] = set()  # upper-plate indices consumed by a merge
    for i, brick in enumerate(model.bricks):
        if brick.part.category != "plate" or i in merged_away or i in stack_choice or i in stacked_away:
            continue
        result = _find_2plate_merge(i, brick, model.bricks, column_top, occupied_at_y, slope_by_tier)
        if result is not None:
            slope_id, rotation, upper_index = result
            merge_choice[i] = (slope_id, rotation)
            merged_away.add(upper_index)

    refined = Model(catalog=model.catalog)
    for i, brick in enumerate(model.bricks):
        if i in merged_away or i in stacked_away:
            continue
        if i in stack_choice:
            slope_id, rotation = stack_choice[i]
        elif i in merge_choice:
            slope_id, rotation = merge_choice[i]
        elif i in swap_choice:
            slope_id, rotation = swap_choice[i]
        elif i in inverted_choice:
            slope_id, rotation = inverted_choice[i]
        else:
            refined.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)
            continue
        refined.place(slope_id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=rotation)

    return refined
