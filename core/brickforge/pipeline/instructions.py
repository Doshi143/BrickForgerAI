"""Build-order and parts-tally logic for auto-generated build instructions
(DESIGN.md's "### Instructions" section, Phase 4). Deliberately pure and
rendering-agnostic -- this module only decides WHAT each step contains and
in what order; turning that into pictures is the web backend's job
(web/backend/app/pipeline/instructions_pdf.py), same separation this
project already keeps between core/brickforge (the product) and the web
app (the delivery mechanism).

Build order: bottom-up by internal-grid Y layer, one step per distinct
layer present -- exactly what DESIGN.md's "### Instructions" section
specifies for studs-up sculptures. SNOT sub-assemblies are NOT split into
their own callout steps here: SNOT isn't wired into the live web pipeline
(brickforge_bridge.py never passes snot_children through), so every brick
`build_steps` sees is an ordinary top/bottom-stud placement. Revisit this
the same session SNOT resumes, not before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..model import Brick, Model


@dataclass(frozen=True)
class PartTally:
    """One row of a parts callout box or bill-of-materials: this many of
    this exact (part, colour) combination."""

    part_id: str
    part_name: str
    color_code: int
    color_name: str
    count: int


@dataclass(frozen=True)
class BuildStep:
    """One page of the instructions: every brick newly placed at a given
    internal-grid Y layer. `brick_indices` are indices into the *original*
    model's `.bricks` list (not the reordered/stepped export below), so a
    caller that already has the source Model can look bricks up directly."""

    index: int  # 0-based step number, ascending by y_layer
    y_layer: int  # internal grid y (plate units) this step corresponds to
    brick_indices: tuple[int, ...]
    running_total: int  # total bricks placed through and including this step


def build_steps(model: Model) -> list[BuildStep]:
    """Partition every brick in `model` into layer-steps, bottom-up. Every
    brick index appears in exactly one step, and running_total on the last
    step always equals len(model) -- a real invariant, checked by
    test_pipeline_instructions.py, not just asserted here."""
    by_layer: dict[int, list[int]] = {}
    for i, brick in enumerate(model.bricks):
        by_layer.setdefault(brick.pos.y, []).append(i)

    steps: list[BuildStep] = []
    running = 0
    for step_index, y in enumerate(sorted(by_layer)):
        indices = tuple(by_layer[y])
        running += len(indices)
        steps.append(BuildStep(index=step_index, y_layer=y, brick_indices=indices, running_total=running))
    return steps


def tally(model: Model, indices: Iterable[int]) -> list[PartTally]:
    """Group the given brick indices by (part, colour) and count them,
    sorted by descending count then part/colour name for a legible
    callout box or BOM -- the actual counts are what matter for buying
    parts, ordering is purely cosmetic."""
    counts: dict[tuple[str, int], int] = {}
    for i in indices:
        brick: Brick = model.bricks[i]
        key = (brick.part.id, brick.color)
        counts[key] = counts.get(key, 0) + 1

    rows = [
        PartTally(
            part_id=part_id,
            part_name=model.catalog.get(part_id).name,
            color_code=color_code,
            color_name=model.catalog.color_name(color_code),
            count=count,
        )
        for (part_id, color_code), count in counts.items()
    ]
    rows.sort(key=lambda t: (-t.count, t.part_name, t.color_name))
    return rows


def bill_of_materials(model: Model) -> list[PartTally]:
    """The full parts list for the whole model -- every brick, once."""
    return tally(model, range(len(model.bricks)))


def stepped_ldr_text(model: Model, steps: list[BuildStep], name: str) -> str:
    """LDR text for the same model, geometry and colour untouched, but with
    brick lines reordered so every step's bricks are contiguous and
    separated by a real `0 STEP` meta-command (see ldr_writer.to_ldr's own
    docstring for why this is a standard LDraw command, not a
    BrickForgerAI invention). Lets any STEP-aware renderer -- three.js's
    LDrawLoader (`computeBuildingSteps`), Studio, LeoCAD -- walk the model
    bottom-up by layer.

    Purely a rendering-time artifact: never written as the canonical
    model.ldr (that file's own brick order is untouched, see
    brickforge_bridge.py), and reordering lines changes nothing about
    what's actually built, only the order this specific export lists them
    in."""
    from ..ldr_writer import to_ldr  # local import: avoid a cycle at module load time

    order = [i for step in steps for i in step.brick_indices]
    reordered = Model(catalog=model.catalog, bricks=[model.bricks[i] for i in order])

    boundaries: list[int] = []
    running = 0
    for step in steps[:-1]:  # no marker needed after the last step
        running += len(step.brick_indices)
        boundaries.append(running)

    return to_ldr(reordered, name, step_boundaries=tuple(boundaries))
