"""Part catalog: loads catalog/parts_v1.yaml and catalog/colors.yaml into
typed, queryable objects. See that file's header for field definitions and
provenance of the part numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml

from .lattice import Rotation

Coverage = str  # "full" | "none"


@dataclass(frozen=True)
class Part:
    id: str  # LDraw part number, e.g. "3001"
    name: str
    category: str  # brick | plate | tile | slope
    footprint: tuple[int, int]  # (x_studs, z_studs) at YAW_0
    height_plates: int
    top: Coverage
    bottom: Coverage
    local_offset: tuple[int, int] = (0, 0)  # (dx, dz) LDU; see lattice.placement_to_ldraw
    y_anchor: str = "top"  # "top" | "bottom"; see lattice.py module docstring

    @property
    def ldraw_file(self) -> str:
        return f"{self.id}.dat"

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
