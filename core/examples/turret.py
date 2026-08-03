"""Phase 0 milestone: hand-build a ~20-part model with the brickforge API
and export it to LDR.

A small hollow turret, 4x4 studs footprint, 3 brick-courses of walls with
alternating (log-cabin style) orientation between courses so vertical seams
never line up two courses in a row -- the same seam-stagger principle
DESIGN.md calls out for the real legalizer, applied here by hand. Capped
with a sealed plate roof, four corner merlons, a tile medallion, a center
spire, and two banner accents.

Run:
    python examples/turret.py
"""

from pathlib import Path

from brickforge import Model, PartCatalog, Rotation, save_ldr

WALL_COLOR = 71  # Light_Bluish_Gray
MERLON_COLOR = 72  # Dark_Bluish_Gray
MEDALLION_COLOR = 4  # Red
SPIRE_COLOR = 19  # Tan
BANNER_COLOR = 14  # Yellow


def build() -> Model:
    catalog = PartCatalog.load_default()
    model = Model(catalog=catalog)

    # --- Courses 1 & 3: long walls run north/south (z=0 and z=3), short
    # walls fill east/west gaps. Footprint ring is 4x4 studs, 1 stud thick,
    # leaving a 2x2 hollow core.
    #
    # Catalog footprints are verified against raw part geometry (see
    # catalog/parts_v1.yaml): 3010 "Brick 1 x 4" is (4,1) [x,z] unrotated
    # (long side already along X), and 3004 "Brick 1 x 2" is (2,1)
    # unrotated (long side already along X). So the north/south walls
    # (need x:4 z:1) take 3010 with NO rotation, and the west/east walls
    # (need x:1 z:2) take 3004 rotated 90 degrees to swap its (2,1) into
    # (1,2). ---
    def course_a(y: int) -> None:
        model.place("3010", WALL_COLOR, 0, y, 0)  # north wall, x:0-4 z:0-1
        model.place("3010", WALL_COLOR, 0, y, 3)  # south wall, x:0-4 z:3-4
        model.place("3004", WALL_COLOR, 0, y, 1, rotation=Rotation.YAW_90)  # west wall, x:0-1 z:1-3
        model.place("3004", WALL_COLOR, 3, y, 1, rotation=Rotation.YAW_90)  # east wall, x:3-4 z:1-3

    # --- Course 2: rotated 90 degrees from course A/C so no vertical seam
    # runs through two consecutive courses. Here the long walls (need x:1
    # z:4) take 3010 rotated 90 degrees to swap (4,1) into (1,4), and the
    # short walls (need x:2 z:1) take 3004 with no rotation (already (2,1)). ---
    def course_b(y: int) -> None:
        model.place("3010", WALL_COLOR, 0, y, 0, rotation=Rotation.YAW_90)  # west wall, x:0-1 z:0-4
        model.place("3010", WALL_COLOR, 3, y, 0, rotation=Rotation.YAW_90)  # east wall, x:3-4 z:0-4
        model.place("3004", WALL_COLOR, 1, y, 0)  # north wall, x:1-3 z:0-1
        model.place("3004", WALL_COLOR, 1, y, 3)  # south wall, x:1-3 z:3-4

    course_a(0)  # plates 0-3  (brick course 1)
    course_b(3)  # plates 3-6  (brick course 2)
    course_a(6)  # plates 6-9  (brick course 3)

    # --- Roof: a single 4x4 plate seals the top of the hollow tower. ---
    model.place("3031", WALL_COLOR, 0, 9, 0)  # plates 9-10

    # --- Four corner merlons (battlements), one brick tall. ---
    for (x, z) in [(0, 0), (3, 0), (0, 3), (3, 3)]:
        model.place("3005", MERLON_COLOR, x, 10, z)  # plates 10-13

    # --- Center medallion, flush with the roof, inside the merlon ring.
    # Three of the four cells are a flat tile (no studs); the fourth (1,1)
    # is a plate instead, so the spire standing on it actually clips onto a
    # stud rather than just resting on bare tile with no connection. ---
    model.place("3024", MEDALLION_COLOR, 1, 10, 1)  # plate, gives the spire a stud
    model.place("3070b", MEDALLION_COLOR, 2, 10, 1)
    model.place("3070b", MEDALLION_COLOR, 1, 10, 2)
    model.place("3070b", MEDALLION_COLOR, 2, 10, 2)

    # --- Center spire, one brick tall, clipped onto the medallion plate. ---
    model.place("3005", SPIRE_COLOR, 1, 11, 1)  # plates 11-14

    # --- Two banner accents on opposite merlons. ---
    model.place("3024", BANNER_COLOR, 0, 13, 0)
    model.place("3024", BANNER_COLOR, 3, 13, 3)

    return model


def main() -> None:
    model = build()
    print(f"Built turret: {len(model)} parts")

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "turret.ldr"
    save_ldr(model, out_path, name="BrickForgerAI Phase 0 Turret")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
