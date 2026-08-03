# BrickForgerAI — Architecture & Build Plan

> Text prompt → physically stable brick sculpture → LDR + Studio file + parts list + instructions.

---

## 0. Verdict on the proposed pipeline

`prompt → image → mesh → brickify → LDR + instructions`

This is the **right pipeline**. It is what every credible attempt converges on, for good reasons:

- Image-first is cheaper to iterate than text-to-3D and gives a natural **user approval gate** before you spend GPU money.
- Image-to-3D is a solved-enough commodity (TRELLIS, Tripo, Meshy, Hunyuan3D, Rodin). Do not build this.
- The mesh→brick step is the only place with defensible IP. Correct instinct to focus there.

Scoping to **sculpture-style builds** rather than minifig-scale System builds is also correct and is the single most important product decision in this document. Minifig-scale set design is an open research problem (semantic part selection, greebling, play features); sculpture is a *geometry + physics* problem, which is tractable today.

### Amendments

| # | Change | Why |
|---|---|---|
| 1 | Insert a **mesh conditioning** stage between mesh and brickify | Single-image meshes are non-watertight, arbitrarily scaled/oriented, and have sub-brick-thickness features. Feeding them raw into a voxelizer is the #1 cause of garbage output. |
| 2 | Voxelize at **plate resolution (20×20×8 LDU)**, not brick resolution | Anisotropic voxels are the native brick lattice. Merge plates→bricks later as an optimization, not a constraint. |
| 3 | **Hollow + internal lattice** before tiling | A solid 30 cm sculpture is ~40,000 parts and unsellable. A shelled one is 2,000–6,000. |
| 4 | **Colour quantization happens before tiling**, not after | A part can only span voxels of one colour. Tiling first then colouring produces either wrong colours or forced 1×1s. |
| 5 | Add an **inventory feasibility pass** (part × colour actually purchasable) with re-colour fallback | This is the difference between a toy and a product. Half of BrickLink's colour space doesn't exist in most slopes. |
| 6 | Add a **buildability / step-ordering** pass | "Stable" ≠ "assemblable". A model can be statically sound but impossible to build without floating sub-assemblies. |
| 7 | Stage SNOT as **v2**, not v1 | Slopes + tiles + a good stability solver already beats Brickalize/Mosaic-class output. SNOT is the moat, but it multiplies the search space and should land on a working v1. |
| 8 | Don't use "LEGO" in the product name, domain, or ad copy | See §8. |

### Full amended pipeline

```
prompt
  └─► [1] prompt conditioning (LLM rewrite → sculpture-friendly subject)
      └─► [2] image gen (gpt-image-1)                    ── USER GATE ──
          └─► [3] image→mesh (TRELLIS dev / Tripo prod)  ── USER GATE ──
              └─► [4] mesh conditioning
                    · orient upright, scale to target stud footprint
                    · watertight repair (winding number / TSDF)
                    · thin-feature detection → thicken or flag
                    · brickability-aware simplification
                  └─► [5] voxelize @ plate lattice (20×20×8 LDU), colour-sampled
                      └─► [6] shell + internal support lattice + base
                          └─► [7] colour quantization → constrained palette
                              └─► [8] LEGALIZATION (tiling w/ full part catalogue)
                                  └─► [9] structural analysis → repair loop  ◄──┐
                                      └─► [10] surface refinement (slopes/tiles)┘
                                          └─► [11] inventory feasibility + BOM
                                              └─► [12] build-order + instructions
                                                  └─► LDR / MPD / .io, PDF, XML wanted list
```

Steps 9 and 10 iterate: surface refinement removes studs and weakens joints, so it re-enters structural analysis.

---

## 1. The lattice (get this right first)

All geometry in **LDU** (1 LDU = 0.4 mm).

| Quantity | LDU | mm |
|---|---|---|
| Stud pitch (X, Z) | 20 | 8.0 |
| Plate height (Y) | 8 | 3.2 |
| Brick height (Y) | 24 | 9.6 |

**The SNOT identity: 5 plates = 40 LDU = 2 studs.** This is the only clean commensurability between the vertical and horizontal lattices, and it is the anchor for every sideways-mounted sub-assembly. Any SNOT module must return to a 40-LDU boundary to re-mate with the studs-up lattice. Build this constraint into the data model from day one — retrofitting it is painful.

**Y axis is negative-up in LDraw.** Decide the internal convention now (recommend: internal grid is Y-up, integer plate units; convert only at LDR serialization) and write it down.

### Core data model

```python
Voxel  = (x, y, z)          # integers; y in plate units
Part   = (part_num, color_id, matrix3x3, translation_ldu)
Brick  = Part + occupancy footprint + stud/anti-stud connector list
Model  = list[Brick] + ConnectivityGraph
```

Every catalogue part needs, precomputed once:
- occupancy set (which lattice cells it fills, per orientation)
- **top connectors** (stud positions) and **bottom connectors** (anti-stud / tube positions)
- for slopes: which faces are "finished" (sloped surface) vs raw
- for brackets: the transform from parent lattice to child (rotated) lattice

Generate this table by parsing the LDraw parts library geometry once, then hand-correct. Don't try to derive it at runtime.

---

## 2. Step 4 — Mesh conditioning

Most-underrated stage. Concretely:

1. **Orient & scale.** PCA + a small classifier (or just ask the mesh model for an upright GLB — TRELLIS/Tripo output is usually already Y-up). Scale so the bounding box maps to the user's chosen size, expressed in **studs**, e.g. "24 studs wide" or "300 mm tall".
2. **Watertight.** Fast winding numbers (libigl) or TSDF fusion + marching cubes. `Manifold` (Emmett Lalish) is a good MIT-licensed option.
3. **Thin-feature detection.** Compute the shape diameter function / local thickness. Any region thinner than ~1 stud (20 LDU) will either vanish at voxelization or become a 1-brick-wide cantilever that snaps. Options, in order of preference:
   - dilate/thicken the region (fingers, ears, tails, sword blades)
   - if it's a long thin protrusion, plan for an internal armature (bar/Technic pin) or a support strut
   - if it's below ~0.4 studs, delete it and warn the user
4. **Brickability-aware simplification.** Low-pass the surface at the voxel scale before sampling, so you don't alias fine texture into noisy single-stud colour speckle.

**Design the resolution slider as a product feature.** Small (≈16 studs / ~800 parts), Medium (≈28 / ~3,000), Large (≈40 / ~8,000). Price tiers map directly onto it.

---

## 3. Steps 5–7 — Voxelization, shelling, colour

### Voxelize
Solid-voxelize into the anisotropic plate lattice (ray-stabbing or winding-number sign test per cell centre, plus a conservative surface pass so thin walls survive). Sample the texture at each surface cell's nearest surface point → per-voxel RGB.

### Shell
Erode the solid by N layers (N ≈ 2 plates on walls, more on the base) and keep:
- the shell,
- a **support lattice** in the interior — the practical choice is a periodic grid of internal walls (every 4–6 studs in X and Z, full height), not a fancy topology-optimized truss. Grid walls are simple, tile into long bricks (cheap, strong), and give the structural solver something to work with.
- **Interlock the shell to the lattice**: shell and lattice must share bricks at junctions, otherwise you get a hollow skin sitting on an unconnected skeleton.

### Colour quantization
- Target palette: a **curated 30–45 colours**, not all ~200 BrickLink colours. Selection criterion: available *today* in the core catalogue (1×1..1×4 plates/bricks/tiles + 45° slopes) at sane prices. Pull from Rebrickable's part/colour data.
- Quantize in **CIELAB** with a spatially-aware step, not naive nearest-neighbour per voxel: penalize colour changes between adjacent voxels. A small graph-cut / bilateral pass here dramatically improves how the sculpture reads and *also* enlarges the mergeable regions for the tiler → fewer, bigger parts. This one pass improves both aesthetics and cost.
- Optional per-user constraint: "use only colours I own" / "max 12 colours".
- Ordered dithering is a trap on sculptures (reads as noise, forces 1×1s). Offer it off by default.

---

## 4. Step 8 — Legalization (the core algorithm)

**Input:** a coloured plate-lattice occupancy grid.
**Output:** a set of catalogue parts exactly covering it, minimizing cost and maximizing structural quality.

### 4.1 Formulation

This is a set-partitioning problem. Exact ILP is intractable at 100k cells, so: **greedy construction + local search**, which is what the literature (Testuz et al. 2013; Luo et al. 2015) does and what actually ships.

Objective (weighted sum, tune on real builds):

```
J = w_count · Σ parts
  + w_price · Σ part price
  + w_seam  · Σ vertical-seam alignment penalty
  - w_conn  · Σ inter-layer stud connections
  + w_rare  · Σ rarity/availability penalty
```

The **seam term matters more than part count.** Aligned vertical seams across layers = a crack. Staggering bricks like brickwork is what makes a sculpture survive being picked up. Most naive brickifiers ignore this and it's why their output falls apart.

### 4.2 Algorithm

```
1. Initialize: every cell → 1×1 plate.
2. Merge pass (per layer, randomized order):
     repeat: pick a random part, attempt to merge with a compatible
     neighbour into a larger catalogue part (same colour, same layer,
     footprint in catalogue). Accept if ΔJ < 0.
3. Vertical merge: 3 vertically-stacked, footprint-identical plates
     of the same colour → 1 brick. Big win: −2/3 part count, stronger.
4. Split-and-remerge (simulated annealing):
     pick a random region, shatter all parts in it back to 1×1,
     re-run merge with a different random seed. Accept on ΔJ, with
     temperature. ~10–50 rounds.
5. Emit connectivity graph.
```

Testuz's split-and-remerge is the key move — pure greedy merging gets stuck in bad local minima with long parts blocking better global tilings.

### 4.3 Part catalogue, v1 (~70 types)

- **Bricks:** 1×1, 1×2, 1×3, 1×4, 1×6, 1×8, 1×10, 1×12, 1×16, 2×2, 2×3, 2×4, 2×6, 2×8, 2×10
- **Plates:** same range + 2×2..6×6, 4×8, 6×8, 6×10
- **Tiles:** 1×1, 1×2, 1×3, 1×4, 1×6, 1×8, 2×2, 2×4
- **Slopes 45°:** 3040 (2×1), 3039 (2×2), 3038 (2×3), 3037 (2×4); inverted 3665 (2×1), 3660 (2×2)
- **Slopes 33°:** 4286 (3×1), 3298 (3×2); **30°:** 54200 "cheese" (1×1), 85984 (2×1)
- **Slopes 65°/75°:** 3684, 3685, 4460 for steep faces
- **Curved:** 50950 (1×2), 11477 (1×2), 15068 (2×2) — these do a *lot* of work on organic sculptures
- **Jumpers:** 3794/15573 (1×2), 87580 (2×2) — half-stud offsets, big quality lever
- **SNOT (v2):** 87087 (1×1 w/ stud on side), 4070 headlight, 99207/99780/44728 brackets, 4733 (1×1 4-sided)

Store as a data table with: LDraw part number, footprint, height, connector map, allowed colours, median BrickLink price, availability score.

### 4.4 Where slopes and tiles enter

Do this **after** the box tiling, as a surface-refinement pass (step 10):

- Scan the surface for **stair-step patterns** in the voxel field. A 1-plate rise over a 1-stud run ≈ 30–45°; match the local surface normal to the best slope part and substitute, provided nothing sits on top of it.
- **Tiles** replace top-facing plates that carry no load above them → removes the "pixelated staircase with visible studs" look that screams *auto-generated*.
- Every substitution **removes stud connections**. Feed each substitution to the structural checker and reject the ones that create a weak point. This is exactly the 9↔10 loop.

Rough rule that will serve you well: **slopes on the outward-facing shell, plain bricks on the internal lattice.** Never let the optimizer spend money on aesthetics the user cannot see.

---

## 5. Step 9 — Structural analysis

Follow **Luo et al., "Legolization: Optimizing LEGO Designs" (SIGGRAPH Asia 2015)**. Summary of the method to implement:

1. Build a graph: nodes = parts, edges = stud–antistud connections (weight = number of studs shared).
2. **Cheap pre-check:** find articulation points and bridges in the connectivity graph. A single-stud connection holding a large sub-tree is a guaranteed failure. Fix these first — they're most of the real-world breakage and cost almost nothing to detect.
3. **Force analysis:** static equilibrium per part under gravity. Each connection resists tension, shear, and torque up to a capacity. Solve as an LP/QP (scipy + HiGHS handles tens of thousands of variables) for internal forces; flag connections exceeding capacity.
4. **Capacities must be empirically calibrated.** Published per-stud values vary; measure your own with a luggage scale and a jig, once. Tension (pull-apart) is far weaker than shear. Document the numbers in `physics.yaml`.
5. **Repair loop:** at each weak region, apply moves — enlarge parts to bridge the seam, add a cross-layer overlapping brick, add a hidden internal brace, thicken locally. Re-solve. Cap at N iterations; if it won't converge, surface a warning + heatmap to the user rather than shipping a lie.

Ship the **stability heatmap in the UI**. It's a visible, screenshot-able differentiator that competitors don't have.

---

## 6. Steps 11–12 — Output

### Inventory feasibility
Query part × colour against Rebrickable (free API, good data) and/or BrickLink. If a needed combination doesn't exist or is absurdly expensive, either substitute the nearest available colour or fall back to a plainer part. Report an estimated price range and part count to the user *before* they pay.

### Files
- **`.ldr` / `.mpd`** — canonical output. Studio, LeoCAD, LDView, and Bricklink all open it. Multi-part models as MPD with submodels per region.
- **`.io`** — Studio's own format. It's a zip container; simplest reliable path is to ship LDR and document the one-click Studio import, then add native `.io` writing once you have a paying user who asks.
- **BrickLink Wanted List XML** — one click to a filled cart. This is your monetization hook and it is trivial to generate.
- **CSV / Rebrickable-compatible part list.**

### Instructions
1. **Build-order:** bottom-up by layer is correct for studs-up sculptures. Within a layer, order back-to-front. SNOT sub-assemblies become **callouts** (separate mini-sequences merged in at their attach step) — exactly how real instructions handle them.
2. **Rendering:** use **three.js `LDrawLoader`** (MIT) in a headless Chromium, or in-browser for the live preview. Same code path serves the interactive viewer and the PDF export — big saving. Alternative: shell out to LPub3D/LDView (GPL, but you're running it server-side as a separate process for a SaaS, which is not distribution).
3. Per step: new parts highlighted, a call-out box with that step's parts and quantities, rotation arrows where needed. Page layout → HTML → `print-to-PDF`.

---

## 7. Tech stack & system architecture

```
Next.js (Vercel)                    ── UI, three.js LDrawLoader preview
      │  REST
FastAPI (Fly.io / Render)           ── auth, credits, job submission
      │
Redis + RQ/Celery                   ── job queue, per-stage retries
      ├─► image worker    → OpenAI gpt-image-1
      ├─► mesh worker     → Modal/RunPod GPU (TRELLIS) | Tripo/Meshy API
      └─► brick worker    → CPU, the `brickforge` core (this is the product)
                              ├─ voxelize, shell, quantize  (numpy)
                              ├─ legalize                    (Python → Rust)
                              ├─ structure                   (scipy HiGHS)
                              └─ export                      (LDR / XML / PDF)
Postgres (Supabase)   ── users, jobs, models
R2 / S3               ── meshes, LDR, renders, PDFs
Stripe                ── credit packs
```

**Language call:** prototype the whole legalizer in Python + numpy. When the merge/anneal loop becomes the bottleneck (it will, around 20k+ parts), port *just* that loop to Rust via PyO3. Do not start in Rust — you'll iterate on the algorithm 50 times.

**Make every stage a pure function on serializable artifacts** (`mesh.glb → voxels.npz → model.json → model.ldr`). You will want to re-run stage 8 with different weights on a cached stage 6 output constantly during tuning. This also gives you free resumability and a debugging CLI.

### Cost per generation (order of magnitude)

| Stage | Cost |
|---|---|
| Image (gpt-image-1) | $0.04 – 0.19 |
| Mesh (Tripo/Meshy API, or TRELLIS on serverless GPU) | $0.05 – 0.30 |
| Brickify (CPU, 1–5 min) | $0.01 – 0.05 |
| **Total COGS** | **~$0.15 – 0.55** |

Comfortable margin at $5–15 per model or a credit subscription. The gating cost is your own time, not inference.

---

## 8. Legal & commercial

- **LEGO® is a registered trademark.** Do not use it in the product name, domain, logo, or paid ad copy. Nominative reference in body copy with a disclaimer ("not affiliated with, endorsed, or sponsored by the LEGO Group; LEGO® is a trademark of the LEGO Group") is standard practice. `BrickForgerAI` is fine.
- **LDraw parts library** is CCAL 2.0 (Creative Commons Attribution) — commercial use is fine, attribution required. Include the notice.
- **BrickLink is owned by the LEGO Group.** Read their API terms before you depend on it commercially; Rebrickable's terms are friendlier for a start.
- **User-uploaded / prompt-generated IP:** users will prompt for Pikachu and Baby Yoda. Have a ToS and a content filter. Selling instructions for a copyrighted character is the fastest way to a takedown.
- **Monetization ladder:** free preview (low-res, watermarked render) → paid digital pack (LDR + PDF + wanted list) → physical kit fulfilment (highest revenue, hardest ops — do not do this before v3).

---

## 9. Roadmap

**Phase 0 — Foundations (1–2 weeks)**
LDU/lattice library, part catalogue table with connector maps, LDR writer, three.js viewer. *Milestone: hand-write a 20-part model in code, open it in Studio.*

**Phase 1 — Brickifier v1, offline (3–5 weeks)**
Voxelize → shell → quantize → legalize (bricks/plates only) → LDR. CLI: `brickforge mesh.glb --studs 24 -o out.ldr`. *Milestone: a recognizable, hollow, buildable 1,000-part model from a downloaded mesh.*

**Phase 2 — Structure (2–4 weeks)**
Connectivity graph, articulation detection, force LP, repair loop, stability heatmap. *Milestone: physically build one and confirm it survives being picked up. Do this for real — it will invalidate assumptions.*

**Phase 3 — Surface quality (3–4 weeks)**
Slopes, tiles, curved slopes, jumpers, colour-aware quantization. *Milestone: side-by-side against Brickalize output where yours is obviously better.*

**Phase 4 — Instructions & outputs (2–3 weeks)**
Build ordering, step renderer, PDF, BOM, BrickLink XML, inventory check.

**Phase 5 — Web product (3–4 weeks)**
Next.js UI, gpt-image-1, mesh API, queue, Stripe, gates. *Milestone: first paying user.*

**Phase 6 — SNOT (open-ended, the moat)**
Bracket-mounted sideways panels on the 5-plate/2-stud lattice; region-growing on near-vertical surfaces; SNOT sub-assemblies as instruction callouts.

Phases 0–5 are ~4 months of solid part-time work to a sellable v1. Phase 6 is where you stop having competitors.

---

## 10. Decisions still open

1. **Target output size / price tier** — drives resolution, part count, and whether physical fulfilment is ever in scope.
2. **Digital-only vs. kit fulfilment** — changes the whole back half (inventory, packing, shipping).
3. **Self-host TRELLIS vs. commercial 3D API at launch** — margin vs. ops burden.
4. **Do you own a decent brick collection for physical validation?** Phase 2 is much weaker without at least one real build.

---

## References worth reading before Phase 1

- Testuz, Weber, Pauly — *Automatic Generation of Constructable Brick Sculptures* (Eurographics 2013). Split-and-remerge legalization + connectivity graph.
- Luo, Yue, Huang, Chung, Imai, Nishita, Chen — *Legolization: Optimizing LEGO Designs* (SIGGRAPH Asia 2015). Force-based structural analysis and repair. **The single most important paper for this project.**
- Stephenson — *Modelling of LEGO* / LDraw spec documents. Lattice and part geometry conventions.
- Kim, Xiong, et al. — surveys on automated brick assembly. Useful for what *doesn't* work.
- LDraw.org Official Model Repository — free test corpus of real models.
