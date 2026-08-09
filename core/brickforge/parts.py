"""Part catalog: loads catalog/parts_v1.yaml and catalog/colors.yaml into
typed, queryable objects. See that file's header for field definitions and
provenance of the part numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml

from .lattice import Rotation, STUD_LDU

Coverage = str  # "full" | "none"


@dataclass(frozen=True)
class Part:
    id: str  # LDraw part number, e.g. "3001"
    name: str
    category: str  # brick | plate | tile | slope | snot
    footprint: tuple[int, int]  # (x_studs, z_studs) at YAW_0
    height_plates: int
    top: Coverage
    bottom: Coverage
    local_offset: tuple[int, int] = (0, 0)  # (dx, dz) LDU; see lattice.placement_to_ldraw
    y_anchor: str = "top"  # "top" | "bottom"; see lattice.py module docstring
    # Which face (in the part's own UNROTATED local frame) carries a
    # sideways-facing stud, and exactly where on that face -- both fields
    # verified from raw .dat geometry per part, the same discipline as
    # local_offset, not assumed from the part's category or name. None
    # for every part that isn't a SNOT connector (the overwhelming
    # majority of the catalog). See core/brickforge/snot.py for how these
    # are consumed -- `side_stud_offset` defaults to (0, None) meaning
    # "centered on the face, at half the part's own height," an
    # approximation confirmed WRONG for the one real part measured so far
    # (87087: real offset is 10 LDU from top, not the 12 LDU half-height
    # default) -- always prefer setting this explicitly once a part's
    # real geometry has actually been checked, rather than trusting the
    # default silently.
    side_stud_face: str | None = None  # "+x" | "-x" | "+z" | "-z", or None
    side_stud_offset: tuple[int, int | None] = (0, None)
    # How many side studs sit in a row on side_stud_face, evenly spaced
    # STUD_LDU apart and centered on side_stud_offset's own `along` --
    # default 1 (every SNOT part until this field was added, e.g. 87087,
    # has exactly one). Verified against real raw .dat geometry for the
    # one multi-stud part in this catalog so far, not assumed from the
    # part's name: 30414.dat's four `stud2a.dat` placements sit at local
    # X = -30, -10, 10, 30 (fetched from library.ldraw.org) -- exactly
    # what side_stud_local_positions() below produces for
    # side_stud_offset=(0, 10), side_stud_count=4.
    side_stud_count: int = 1

    @property
    def ldraw_file(self) -> str:
        return f"{self.id}.dat"

    def side_stud_local_positions(self) -> list[tuple[int, int]]:
        """(along, from_top) LDU pairs, one per stud in this part's side-stud
        row, in the part's own unrotated local frame (same along/from_top
        convention as side_stud_offset -- along measured from the part's
        own footprint center). Empty if this part has no side stud at all.
        Symmetric about side_stud_offset's own `along`, STUD_LDU apart --
        see side_stud_count's own docstring for the real geometry this is
        verified against."""
        if self.side_stud_face is None:
            return []
        along, from_top = self.side_stud_offset
        n = self.side_stud_count
        span = STUD_LDU * (n - 1)
        return [(along + STUD_LDU * k - span // 2, from_top) for k in range(n)]

    def footprint_at(self, rotation: Rotation) -> tuple[int, int]:
        return rotation.rotate_footprint(*self.footprint)

    def top_studs(self, rotation: Rotation) -> list[tuple[int, int]]:
        """Local (x, z) cell offsets (0-indexed, post-rotation footprint)
        that carry a top stud connector."""
        if self.top == "none":
            return []
        w, d = self.footprint_at(rotation)
        return [(x, z) for x in range(w) for z in range(d)]

    def bottom_studs(self, rotation: Rotation) -> list[tuple[int, int]]:
        if self.bottom == "none":
            return []
        w, d = self.footprint_at(rotation)
        return [(x, z) for x in range(w) for z in range(d)]


class PartCatalog:
    """Loads and indexes the YAML part/colour catalog."""

    def __init__(self, parts: dict[str, Part], colors: dict[int, str]):
        self._parts = parts
        self._colors = colors

    @classmethod
    def load_default(cls) -> "PartCatalog":
        catalog_dir = resources.files("brickforge") / "catalog"
        return cls.load(catalog_dir / "parts_v1.yaml", catalog_dir / "colors.yaml")

    @classmethod
    def load(cls, parts_path: Path, colors_path: Path) -> "PartCatalog":
        with open(parts_path, "r", encoding="utf-8") as f:
            parts_raw = yaml.safe_load(f)["parts"]

        parts: dict[str, Part] = {}
        for entry in parts_raw:
            side_stud_offset_raw = entry.get("side_stud_offset", [0, None])
            part = Part(
                id=str(entry["id"]),
                name=entry["name"],
                category=entry["category"],
                footprint=tuple(entry["footprint"]),
                height_plates=int(entry["height_plates"]),
                top=entry["top"],
                bottom=entry["bottom"],
                local_offset=tuple(entry.get("local_offset", (0, 0))),
                y_anchor=entry.get("y_anchor", "top"),
                side_stud_face=entry.get("side_stud_face"),
                side_stud_offset=(side_stud_offset_raw[0], side_stud_offset_raw[1]),
                side_stud_count=int(entry.get("side_stud_count", 1)),
            )
            parts[part.id] = part

        with open(colors_path, "r", encoding="utf-8") as f:
            colors_raw = yaml.safe_load(f)["colors"]
        colors = {int(code): name for code, name in colors_raw.items()}

        return cls(parts, colors)

    def get(self, part_id: str) -> Part:
        try:
            return self._parts[str(part_id)]
        except KeyError as exc:
            raise KeyError(f"Unknown part id {part_id!r} in catalog") from exc

    def color_name(self, code: int) -> str:
        try:
            return self._colors[code]
        except KeyError as exc:
            raise KeyError(f"Unknown LDraw color code {code!r} in catalog") from exc

    def has_color(self, code: int) -> bool:
        return code in self._colors

    def __contains__(self, part_id: str) -> bool:
        return str(part_id) in self._parts

    def __iter__(self):
        return iter(self._parts.values())

    def __len__(self) -> int:
        return len(self._parts)
