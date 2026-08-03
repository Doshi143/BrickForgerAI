"""LDU lattice constants and coordinate conversion.

Source of truth for the constants below: the LDraw.org File Format
Specification (https://www.ldraw.org/article/218.html), section on units
and the coordinate system:

    - LDraw uses a right-handed coordinate system where -Y is "up".
    - 1 LDU (LDraw Unit) is approximately 0.4 mm.
    - Standard brick footprint pitch (stud-to-stud spacing) is 20 LDU.
    - Standard plate height is 8 LDU; a brick is 3 plates tall (24 LDU).
    - Standard stud diameter is 12 LDU.

Internal convention (deliberately different from LDraw's, to keep the
brickify pipeline's math simple): the model grid is integer, **Y-up**,
and anisotropic —

    x, z : stud units      (1 unit = 20 LDU)
    y    : plate units     (1 unit = 8 LDU)

Conversion to LDraw's -Y-up LDU space happens only at LDR serialization
time (see ldr_writer.py). Nothing upstream of that should know LDraw's Y
is flipped.

Part origin convention: verified directly against official part files
(not merely long-standing convention) by fetching parts/3005.dat (Brick
1 x 1) and parts/3024.dat (Plate 1 x 1) from the LDraw parts library and
inspecting their raw geometry. Both place all Y coordinates in
[0, height_ldu] -- i.e. **local Y = 0 is the TOP of the part** (where
the stud sits) and the part extends *downward* to local Y = +height_ldu
at the bottom (consistent with -Y being "up"). This is the opposite of
what a naive reading of "-Y is up" might suggest (that the origin, at
Y=0, sits at the bottom with the part extending upward into negative Y)
-- an earlier version of this module assumed exactly that and placed
every part shifted by its own height relative to where it should have
been, which is invisible for a stack of uniform-height parts (the
per-part shift is constant, so courses stay contiguous) but produces
overlapping/floating parts wherever parts of different heights meet
(e.g. a 1-plate-tall roof under 3-plate-tall merlons). Horizontal
centering (origin at the mid-point of X and Z) was independently
confirmed from the same files and is unaffected.

**Not every part follows the top-anchored convention -- verified, not
assumed, a second time.** Fetching the raw geometry for the 2-plate-tall
("2/3 brick") slope family (54200, 5404, 85984, 7825, 7835) shows every Y
coordinate in [-height_ldu, 0], the mirror image of the top-anchored
bricks/plates/tiles/3-plate-slopes above -- i.e. **local Y = 0 is the
BOTTOM of these parts**, extending *upward* (more negative Y) to the
sloped top. This isn't a guess from the sign pattern alone: 61409's
official `!HISTORY` says outright "Updated origin to bottom center"
(2009-03-30). `Part.y_anchor` ("top" | "bottom", default "top" so every
existing part is unaffected) records which convention a given part
actually uses; `placement_to_ldraw` branches on it. Getting this wrong
for a bottom-anchored part would silently place it one full part-height
too high (invisible for a lone part resting on a flat floor, wrong the
moment it sits against a neighbor of a different height) -- the same
failure shape as the top/bottom mixup this module already documents
above, so it gets the same fix pattern: a typed field, not an assumption.

`placement_to_ldraw` below relies on each part's own (verified, not
assumed) `y_anchor` to compute where its origin must land in world LDU
space, given the grid cell of its footprint's bottom-front-left corner
and the part's height.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

STUD_LDU = 20
PLATE_HEIGHT_LDU = 8
BRICK_HEIGHT_LDU = 24
STUD_DIAMETER_LDU = 12
LDU_MM = 0.4

PLATES_PER_BRICK = BRICK_HEIGHT_LDU // PLATE_HEIGHT_LDU  # 3
SNOT_PLATE_RUN = 5  # 5 plates (40 LDU) == 2 studs (40 LDU); the SNOT anchor identity


class Rotation(Enum):
    """Yaw rotation about the vertical axis, in 90-degree steps.

    Matrices are the standard LDraw a-b-c/d-e-f/g-h-i rotation-about-Y
    matrices used by MLCad/LeoCAD-family tools for axis-aligned yaw:

        u' = a*u + b*v + c*w
        v' = d*u + e*v + f*w
        w' = g*u + h*v + i*w

    with (u, v, w) the part's local frame. These are rotation matrices
    about the vertical axis, so they are identical whether that axis is
    called +Y (internal convention) or -Y (LDraw convention) — a
    rotation about an axis doesn't depend on which way along that axis
    is labeled "up".
    """

    YAW_0 = (0, (1, 0, 0, 0, 1, 0, 0, 0, 1))
    YAW_90 = (90, (0, 0, 1, 0, 1, 0, -1, 0, 0))
    YAW_180 = (180, (-1, 0, 0, 0, 1, 0, 0, 0, -1))
    YAW_270 = (270, (0, 0, -1, 0, 1, 0, 1, 0, 0))

    def __init__(self, degrees: int, matrix: tuple[int, ...]):
        self.degrees = degrees
        self.matrix = matrix

    @property
    def swaps_footprint(self) -> bool:
        """True if this rotation swaps the X/Z (width/depth) footprint extents."""
        return self.degrees in (90, 270)

    def rotate_footprint(self, width_studs: int, depth_studs: int) -> tuple[int, int]:
        """Return (width, depth) in studs after applying this yaw rotation."""
        if self.swaps_footprint:
            return depth_studs, width_studs
        return width_studs, depth_studs

    def rotate_offset(self, dx: int, dz: int) -> tuple[int, int]:
        """Rotate a local (dx, dz) LDU offset by this yaw -- for parts whose
        origin isn't at the horizontal center of their own footprint (see
        Part.local_offset). Derived directly from this Rotation's own
        a-b-c/g-h-i matrix applied to a local (u, 0, w) vector, not a
        separate ad-hoc rule: YAW_0 -> (dx, dz); YAW_90 -> (dz, -dx);
        YAW_180 -> (-dx, -dz); YAW_270 -> (-dz, dx)."""
        a, _, c, _, _, _, g, _, i = self.matrix
        return a * dx + c * dz, g * dx + i * dz


@dataclass(frozen=True)
class GridPos:
    """A grid-cell anchor: the bottom-front-left corner of a part's footprint,
    in internal Y-up (x, z in studs; y in plates) coordinates."""

    x: int
    y: int
    z: int


def placement_to_ldraw(
    pos: GridPos,
    width_studs: int,
    depth_studs: int,
    height_plates: int,
    rotation: Rotation = Rotation.YAW_0,
    local_offset: tuple[int, int] = (0, 0),
    y_anchor: str = "top",
) -> tuple[int, int, int]:
    """Compute the LDU coordinates (LDraw space) of a part's local origin,
    given the grid cell of the footprint's bottom-front-left corner, the
    part's *unrotated* footprint dimensions, and its height in plates.

    `local_offset` (dx, dz), in LDU, corrects for parts whose origin is NOT
    at the horizontal center of their own footprint -- true for every
    brick/plate/tile checked so far (offset (0, 0)), but demonstrably
    false for slopes: parts/3040b.dat + s/3040s01.dat's raw geometry spans
    local Z in [-30, +10], not the symmetric [-20, +20] a centered 2-stud
    footprint would have, a 10 LDU (half-stud) asymmetry -- confirmed
    empirically wrong before being caught in code: an earlier version
    assumed uniform centering for every part, and the user caught the
    resulting misaligned slopes directly in Studio. `local_offset` is
    given in the part's own unrotated frame and rotated here by the same
    `rotation` applied to the footprint, via Rotation.rotate_offset --
    it has to be, since a fixed asymmetry in the part's local frame points
    in a different world direction depending on which way the part is
    turned.

    `y_anchor` ("top" | "bottom") picks which end of the part's own local
    Y range sits at Y=0 -- see module docstring for why this isn't
    universal (bricks/plates/tiles/3-plate-slopes are top-anchored, the
    2-plate slope family is bottom-anchored, confirmed from each family's
    own raw geometry, not assumed to match).

    Returns (ldraw_x, ldraw_y, ldraw_z) in LDU, ready to write directly into
    an LDR line type 1.
    """
    eff_width, eff_depth = rotation.rotate_footprint(width_studs, depth_studs)
    offset_x, offset_z = rotation.rotate_offset(*local_offset)

    ldraw_x = (pos.x * STUD_LDU) + (eff_width * STUD_LDU) // 2 + offset_x
    ldraw_z = (pos.z * STUD_LDU) + (eff_depth * STUD_LDU) // 2 + offset_z
    if y_anchor == "top":
        # The part's origin is its TOP, so the top of the footprint's grid
        # cell range -- not its bottom -- is what lands at the origin.
        ldraw_y = -((pos.y + height_plates) * PLATE_HEIGHT_LDU)
    elif y_anchor == "bottom":
        ldraw_y = -(pos.y * PLATE_HEIGHT_LDU)
    else:
        raise ValueError(f"Unknown y_anchor {y_anchor!r}, expected 'top' or 'bottom'")

    return ldraw_x, ldraw_y, ldraw_z


def studs_to_ldu(studs: float) -> int:
    return round(studs * STUD_LDU)


def plates_to_ldu(plates: float) -> int:
    return round(plates * PLATE_HEIGHT_LDU)
