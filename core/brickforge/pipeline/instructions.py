"""Build-order and parts-tally logic for auto-generated build instructions
(DESIGN.md's "### Instructions" section, Phase 4). Deliberately pure and
rendering-agnostic -- this module only decides WHAT each step contains and
in what order; turning that into pictures is the web backend's job
(web/backend/app/pipeline/instructions_pdf.py), same separation this
project already keeps between core/brickforge (the product) and the web
app (the delivery mechanism).

Build order: connectivity-driven growth from the ground, capped per step
-- NOT a plain "one step per Y layer" partition (that was the original,
simpler version; see below for why it was replaced). SNOT sub-assemblies
are NOT split into their own callout steps here: SNOT isn't wired into the
live web pipeline (brickforge_bridge.py never passes snot_children
through), so every brick `build_steps` sees is an ordinary top/bottom-stud
placement. Revisit this the same session SNOT resumes, not before.

**Two real, founder-reported problems with the original one-step-per-layer
version, both fixed by the same underlying change:** (1) a single busy
layer with dozens or hundreds of bricks became one single overloaded step
-- there was no cap at all, just every brick sharing a Y value dumped into
one step regardless of count. (2) layer-only grouping has zero
connectivity awareness, so a brick's step assignment depended purely on
its height, not on whether it was anywhere near what had actually been
built so far -- a structurally separate cluster (a repair pillar, a
disconnected-looking region that happens to share a Y value with unrelated
geometry) could sit unbuilt for many steps while every OTHER same-or-lower
layer finished, then suddenly appear, which reads as "attached much later"
with no visual buildup to it.

The fix: grow the model outward from GROUND, wave by wave, the same
directed "does this brick have real support already placed under it"
question `structure/weakpoints.py::find_ungrounded_bricks` already asks
for a different reason (there, it's deliberately too strict a bar for
judging structural soundness -- see that module's own docstring on why
undirected connectivity is what drives repair instead. Here, that same
strictness is exactly correct: a build step can only place a brick once
something it actually rests on is already sitting there, and directed
"resting on" is precisely what real, physical build order requires,
keystone bracing or not). A brick becomes eligible the step after
something it shares a stud connection with -- and sits strictly below it
-- gets placed; GROUND seeds every y=0 brick as eligible from step one.
Within each step, capped at `max_bricks_per_step`, eligible bricks are
ordered bottom-up then back-to-front (Y, then Z, then X -- DESIGN.md's own
"within a layer, order back-to-front" spec, approximated with grid
coordinates since there's no camera to compute a true view-relative
order from). This can never place a floating segment before its
attachment point, because it can't become eligible until that attachment
point already has a step -- fixing problem (2) as a direct consequence of
the same change that fixes (1), not a second, separate mechanism.

A handful of bricks (genuinely keystone-braced, with no straight-down
support chain at all -- the same rare case `find_ungrounded_bricks` flags
as directed-unreachable even on a structurally sound model) may never
become eligible through this growth process. Rather than looping forever
or silently dropping them, once the eligible pool runs dry with bricks
still remaining, whatever's left is swept in (still capped per step,
still ordered bottom-up/back-to-front) as its own final wave -- correct
by construction (every brick still appears exactly once, see
`build_steps`'s own docstring), just without the same growth guarantee
for that specific handful.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..model import Brick, Model
from ..structure.graph import GROUND, build_connectivity_graph

# Real physical LEGO instruction booklets vary a lot (1 piece for a fiddly
# join, 15+ for a repeated flat run), but "however many happen to share a
# Y value" had no ceiling at all -- a dense layer could be hundreds of
# bricks in one step. 8 is a reasonable, conservative default for a single
# callout page to stay legible; exposed as a parameter rather than a
# hardcoded constant so it can be tuned without touching this function.
DEFAULT_MAX_BRICKS_PER_STEP = 8


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
    """One page of the instructions: up to `max_bricks_per_step` bricks that
    became eligible (real support already placed under them) in the same
    growth wave. `brick_indices` are indices into the *original* model's
    `.bricks` list (not the reordered/stepped export below), so a caller
    that already has the source Model can look bricks up directly.

    A step's bricks are no longer guaranteed to share one exact Y -- a
    single growth wave can include a low-lying brick and a taller,
    already-supported neighbor at the same time once the cap allows room
    for both. `y_layer` is kept as the MINIMUM y among the step's own
    bricks (not their only y), which is why the existing bottom-up
    ordering guarantee (ascending across steps) still holds even though a
    step's own contents can span more than one layer."""

    index: int  # 0-based step number
    y_layer: int  # min internal grid y (plate units) among this step's bricks
    brick_indices: tuple[int, ...]
    running_total: int  # total bricks placed through and including this step


def build_steps(model: Model, *, max_bricks_per_step: int = DEFAULT_MAX_BRICKS_PER_STEP) -> list[BuildStep]:
    """Partition every brick in `model` into steps by growing outward from
    the ground, wave by wave, capped at `max_bricks_per_step` per step.
    Every brick index appears in exactly one step, and running_total on the
    last step always equals len(model) -- a real invariant, checked by
    test_pipeline_instructions.py, not just asserted here. See module
    docstring for why this replaced a plain one-step-per-Y-layer partition."""
    n = len(model.bricks)
    if n == 0:
        return []

    graph = build_connectivity_graph(model)

    def sort_key(i: int) -> tuple[int, int, int]:
        pos = model.bricks[i].pos
        return (pos.y, pos.z, pos.x)  # bottom-up, then back-to-front (DESIGN.md)

    def supports(lower: int | str, upper: int) -> bool:
        """True if `lower` (an already-placed brick index, or GROUND)
        physically supports `upper` from below -- the same directed
        "resting on" test find_ungrounded_bricks uses, not a plain
        graph edge (an edge alone doesn't say which side is underneath)."""
        return lower == GROUND or model.bricks[lower].pos.y < model.bricks[upper].pos.y

    placed = [False] * n
    remaining = set(range(n))
    available = {i for i in remaining if graph.has_edge(GROUND, i)}

    steps: list[BuildStep] = []
    running = 0
    step_index = 0

    while remaining:
        if not available:
            # No brick currently has real support already placed under it
            # -- a genuinely keystone-braced remainder (see module
            # docstring). Never loop forever or drop bricks: sweep in
            # whatever's left as its own wave, same ordering and cap as
            # every other step.
            available = set(remaining)

        chunk = tuple(sorted(available, key=sort_key)[:max_bricks_per_step])

        newly_placed = []
        for i in chunk:
            placed[i] = True
            remaining.discard(i)
            available.discard(i)
            newly_placed.append(i)

        for i in newly_placed:
            for neighbor in graph.neighbors(i):
                if (
                    isinstance(neighbor, int)
                    and neighbor in remaining
                    and neighbor not in available
                    and supports(i, neighbor)
                ):
                    available.add(neighbor)

        running += len(chunk)
        y_layer = min(model.bricks[i].pos.y for i in chunk)
        steps.append(BuildStep(index=step_index, y_layer=y_layer, brick_indices=chunk, running_total=running))
        step_index += 1

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
