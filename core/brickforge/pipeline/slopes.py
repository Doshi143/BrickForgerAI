"""Staircase-to-slope substitution (DESIGN.md pipeline step: surface
refinement). Detects blocks that sit at a genuine step-down edge in one of
the 4 cardinal directions and replaces them in place with the
correspondingly-sized, correspondingly-rotated upright slope -- at whatever
height tiers the catalog provides.

Two tiers exist:

- **3-plate (brick height)**: a **1-to-1 swap** of a single already-placed
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
- **2-plate ("2/3 brick") -- the real "detail" tier**: no standard
  rectangular slope is exactly 1 plate tall (searched, came up empty, did
  not invent a part -- see catalog/parts_v1.yaml's header on this family).
  2 plates is the shallowest real size, and this project's plate-heavy
  legalizer output is full of *pairs* of vertically-stacked, identically
  footprinted plates that never got consolidated into a brick (Stage B
  only merges stacks of exactly 3). So this tier is a **merge of two
  placed parts into one**, not a swap -- see the module-level safety note
  below, since that's a materially different operation from tile
  substitution and the 3-plate tier.

Because a catalog `Part`'s `height_plates` is always exactly 3 for
`category: brick` and exactly 1 for `category: plate` in this catalog, the
two tiers can never compete for the same source brick: a brick-category
object is never also a candidate plate-pair member, and vice versa. So
"prefer a larger slope where one is possible" falls out for free from
running both passes independently -- there is no location where both tiers
could apply to the same source material, so no explicit tie-break is
needed between them.

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

Only upright slopes (top: none) are handled -- inverted slopes (the
underside/overhang case) are a different detection pattern and are not
attempted here.

Safety, 3-plate (swap) tier: exactly the same precondition as tile
substitution (surface_refine.py) -- every brick part in this catalog has
bottom: full, same as every slope, so a substitution never changes
downward connectivity; it only ever removes TOP connectivity, and only
where a candidate's top is already fully exposed (nothing resting on it).

Safety, 2-plate (merge) tier: a merge deletes TWO placed parts (a lower
and an upper plate, identical footprint, one directly on the other) and
replaces both with ONE slope at the lower plate's position. This still
reduces to the same "only ever removes unused TOP connectivity" argument,
just restated for a pair: the lower plate's own downward connectivity
(position, footprint, bottom: full) is unchanged, so whatever supported it
still does; the upper plate's top must be fully exposed (identical
precondition to the swap case) before a merge is attempted; and the
internal stud edge between the two plates being merged is not left
dangling -- both of its endpoints are deleted together, so nothing
external ever depended on it surviving. Net effect on the connectivity
graph has the same shape as the swap case: one node's downward
connectivity preserved, its upward connectivity removed only where
nothing used it. Confirmed with a before/after analyze() test for both
tiers, not just argued (see tests/test_pipeline_slopes.py).

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
    }
)


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
    can't collide, since (height, perp, run) uniquely identifies which
    family (and therefore which part) applies."""
    return {
        (p.height_plates, p.footprint[0], p.footprint[1]): (p.id, p.id in _FLIPPED_PART_IDS)
        for p in catalog
        if p.category == "slope" and p.top == "none"
    }


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
    2-plate (merge) tiers the catalog provides."""
    slope_by_tier = _build_slope_map(model.catalog)
    if not slope_by_tier:
        return model

    column_top: dict[tuple[int, int], int] = {}
    occupied_at_y: dict[tuple[int, int, int], int] = {}
    for i, brick in enumerate(model.bricks):
        top = brick.pos.y + brick.part.height_plates
        w, d = brick.footprint
        for dx in range(w):
            for dz in range(d):
                col = (brick.pos.x + dx, brick.pos.z + dz)
                column_top[col] = max(column_top.get(col, top), top)
        for cell in brick.occupied_cells():
            occupied_at_y[cell] = i

    swap_choice: dict[int, tuple[str, Rotation]] = {}
    for i, brick in enumerate(model.bricks):
        placement = _find_single_part_slope(brick, column_top, occupied_at_y, slope_by_tier)
        if placement is not None:
            swap_choice[i] = placement

    merge_choice: dict[int, tuple[str, Rotation]] = {}  # anchor (lower) index -> (slope_id, rotation)
    merged_away: set[int] = set()  # upper-plate indices consumed by a merge
    for i, brick in enumerate(model.bricks):
        if brick.part.category != "plate" or i in merged_away:
            continue
        result = _find_2plate_merge(i, brick, model.bricks, column_top, occupied_at_y, slope_by_tier)
        if result is not None:
            slope_id, rotation, upper_index = result
            merge_choice[i] = (slope_id, rotation)
            merged_away.add(upper_index)

    refined = Model(catalog=model.catalog)
    for i, brick in enumerate(model.bricks):
        if i in merged_away:
            continue
        if i in merge_choice:
            slope_id, rotation = merge_choice[i]
        elif i in swap_choice:
            slope_id, rotation = swap_choice[i]
        else:
            refined.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)
            continue
        refined.place(slope_id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=rotation)

    return refined
