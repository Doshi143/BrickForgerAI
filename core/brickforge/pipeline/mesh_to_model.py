"""End-to-end orchestration: mesh file -> Model.

Chains condition -> voxelize -> shell -> quantize -> legalize. Each stage
is independently testable and re-runnable (see brickforge/pipeline/*.py);
this function just wires them together with sensible defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import trimesh

from ..model import Model
from ..parts import PartCatalog
from .color import quantize_grid_colors
from .grid import VoxelGrid
from .legalize import DEFAULT_RESTARTS, legalize
from .shell import shell_and_support
from .voxelize import condition_mesh, voxelize_mesh


@dataclass
class MeshToModelResult:
    model: Model
    solid_grid: VoxelGrid  # the pre-shell, pre-legalize solid occupancy -- same
    # (x, y, z) index space as the final Model's placements, since shelling
    # and legalization never shift or resize the grid. Lets structural
    # repair (structure/bridge.py) tell "inside the sculpture's original
    # silhouette" apart from "genuinely outside it, in open air" -- the
    # distinction a shelled/hollow Model can't answer on its own, since the
    # hollow interior and the open exterior both just look like "empty."


def mesh_to_model_full(
    mesh_path: str | Path,
    target_width_studs: int,
    catalog: PartCatalog | None = None,
    shell_thickness: int = 2,
    support_pitch: int = 5,
    seed: int = 0,
    restarts: int = DEFAULT_RESTARTS,
) -> MeshToModelResult:
    catalog = catalog or PartCatalog.load_default()

    mesh = trimesh.load(mesh_path, force="mesh")
    conditioned = condition_mesh(mesh, target_width_studs)
    voxels = voxelize_mesh(conditioned)
    shelled = shell_and_support(voxels, shell_thickness=shell_thickness, support_pitch=support_pitch)
    color_codes = quantize_grid_colors(shelled.occupied, shelled.color)
    model = legalize(shelled, color_codes, catalog, seed=seed, restarts=restarts)
    return MeshToModelResult(model=model, solid_grid=voxels)


def mesh_to_model(
    mesh_path: str | Path,
    target_width_studs: int,
    catalog: PartCatalog | None = None,
    shell_thickness: int = 2,
    support_pitch: int = 5,
    seed: int = 0,
    restarts: int = DEFAULT_RESTARTS,
) -> Model:
    return mesh_to_model_full(
        mesh_path,
        target_width_studs,
        catalog=catalog,
        shell_thickness=shell_thickness,
        support_pitch=support_pitch,
        seed=seed,
        restarts=restarts,
    ).model
