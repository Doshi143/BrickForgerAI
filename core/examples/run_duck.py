"""Ad-hoc run of the full pipeline (mesh -> repair -> surface refinement ->
LDR) against a new test mesh (Khronos glTF-Sample-Assets "Duck", CC-BY 3.0
Sony -- a standard glTF conformance test model, not part of the permanent
example suite). Reuses structural_report.py's report_and_save unchanged."""

from pathlib import Path

from brickforge.pipeline.mesh_to_model import mesh_to_model_full
from structural_report import OUT_DIR, report_and_save

OUT_DIR.mkdir(exist_ok=True)

duck = mesh_to_model_full(Path(__file__).parent / "meshes" / "duck.glb", 24)
report_and_save(duck.model, "duck", solid_grid=duck.solid_grid)
