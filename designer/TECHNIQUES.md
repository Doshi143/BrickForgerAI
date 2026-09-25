# Detailed mode: building-technique catalogue

Phase 1 research deliverable (2026-09-25). What skilled builders do for each build type, which real
parts they use, how those parts connect, and what it would take to teach each technique to the
designer engine - ranked, with a proposed build order. **Nothing here is implemented yet.** The
founder approves the order before Phase 2 starts.

How to read this:

- **Part IDs are LDraw file names**, each checked against the official LDraw library on
  2026-09-25 (title shown). LDraw names often differ from BrickLink/LEGO numbers (e.g. 4073 has
  moved to 6141, 3040 to 3040b). A checked ID only proves the part exists. Its footprint, origin,
  anchoring, stud and connector positions and hollow underside must still be **measured from the
  geometry before use**, and every new part and technique still gets a Studio check (see the
  engine lessons in HANDOFF.md: every one of those assumptions has been wrong at least once).
- **Effort** is engine work, not spec work:
  - **S**: studs-up grid placement only, uses existing machinery (tile_level, verified, sculpt
    caps). A few days of sessions.
  - **M**: new parts plus a new placement rule, or uses the existing yaw-only SNOT frames.
  - **L**: needs a new connection type (clip/bar, hinge, bar-in-stud), measured from LDraw and
    added to the connectivity graph.
  - **XL**: needs non-right-angle placement (arbitrary rotation, collision on oriented boxes) or a
    whole subsystem (Technic pins/axles).
- **Payoff** combines how visible the gain is and how many prompts benefit (common prompts:
  animals, vehicles, buildings, plants, objects, scenes).
- **Surface**: how the spec gets it - `auto` (engine applies it with no spec text), `option`
  (a keyword on an existing command), or `command` (a new bounded DSL command).

What the engine can express today (for context): plates, bricks, tiles, 2-plate and 3-plate
curved slopes, yaw-only placement on the stud grid, sideways panels on 87087/30414 anchors, and
"attached" details (glass, door leaf, wheels) linked to a host. Only straight stud connections
create graph edges; nothing can be placed at an angle other than 0/90/180/270 degrees yaw.

---

## Status (2026-09-25 overnight, local commits)

Built and tested (unit tests + renders; Studio checks pending): 1 gradients, 2 water, 3 trees
(round, bush, palm), 4 car lights, 5 wedge plates on `poly` edges, 6 facades (texture, quoins,
window types), 7 large eyes, 8 spikes/teeth (`scatter ... top rot=`), 9 slope-brick roofs,
10 rockwork, 11 greebling, 12 round columns, 14 horns (curved blade in an open stud),
15 palm leaves (stud-mounted, no clips needed), 16 hinged flaps, 17 ball-joint limbs,
18 Technic gears.  Not done: 13 jumper offsets, 19 Technic frames, 20 microscale, clip/bar
connections as such, most of the automatic details in section 3 (quoins/lights done).

## 1. Ranked catalogue

| # | Technique | Build types | Key parts (LDraw) | Connection | Effort | Payoff | Surface |
|---|-----------|-------------|-------------------|------------|--------|--------|---------|
| 1 | Colour gradients and dithering | all (water, grass, rock, fur, sky) | none new | studs | S | High | auto + option |
| 2 | Water surface with depth gradient | scenes, gardens, harbours, islands | 3070b 3069b 63864 2431 98138 6141 | studs | S | High | command |
| 3 | Trees, bushes, flowers v2 (several styles) | landscapes, gardens, scenes | 3062b 3941 2417 2423 32607 6255 30176 24866 3742 2435 | studs | S-M | High | command/option |
| 4 | Vehicle detailing (lights, grilles, arches, exhausts) | cars, trucks, trains | 4070 98138 2412b 3788 50745 98282 4589 | studs + SNOT | M | High | auto |
| 5 | Wedge plates for sleek outlines | aircraft, boats, spaceships, car noses | 43722a 43723a 41769a 41770a 51739 24299 24307 2450 30357 | studs | S-M | High | auto in sculpt |
| 6 | Building facades v2 (windows, sills, arches, quoins, textures, cornice) | buildings, castles, modulars | 60592 60593 60601 60602 3659 6182 6005 98283 30136 2431 3665a 4070 | studs (+SNOT for cornice) | S-M | High | option |
| 7 | Eyes v2 (sizes and styles) | animals, creatures, characters, robots | 14769 4150 98138 6141 3794b 15573 | studs / SNOT | S-M | High | option |
| 8 | Teeth, spikes, claws, horns (plate type) | dinosaurs, dragons, cacti, hedgehogs | 49668 15070 15208 4589 | studs | S | Med-High | command |
| 9 | Roofs v2 (shingles, ridge caps, chimneys, dormers) | houses, castles, modulars | 54200 85984 3044b 3043 3048b 3040b 3039 4286 3298 | studs | M | Med-High | option |
| 10 | Rockwork | landscapes, castles, bases, caves | 3040b 3039 4286 3298 3665a 54200 85984 + colour mix | studs (+SNOT later) | M | High | command |
| 11 | Greebling / surface texture | machines, spaceships, vehicles, robots | 2412b 6141 98138 4589 3794b | studs | S | Medium | auto |
| 12 | Round shapes (dishes, domes, round tiles) | food, objects, towers, fountains | 4032a 14769 4150 2654a 4740 3960 30367a 3942b 6143 | studs | S-M | Medium | option in sculpt |
| 13 | Jumper (half-stud) offsets | faces, centred details, chimneys | 3794b 15573 87580 18674 | studs (half-stud) | M | Medium | auto |
| 14 | SNOT holders with detail in the hole | spikes, lamps, trunks, faces | 4070 4733 47905 85861 87747 | studs + bar-in-stud | M-L | Medium | command |
| 15 | Clip and bar connections | palm trees, railings, antennas, plants on stems | 61252 4085c 15712 60478 48729a 87994 30374 10884 37695 | clip/bar | L | Medium | command |
| 16 | Hinged angles (plate and click hinges) | roofs, wings, tails, heads, boat bows, rock faces | 2429 2430 3937 3938 44301a 44302a 44567a 60471 | hinge | L-XL | High | option |
| 17 | Ball-joint chains (`limb`) | tentacles, trunks, necks, tails, snakes | 14417 14418 14419 | ball | XL | Very high (weakest category) | command |
| 18 | Technic decoration (gears, beams, axles on Technic bricks) | robots, mechs, cranes, machines | 3700 3701 6541 4274 2780 3705 3706 3648b 3647 32270 32523 | pin/axle | L | Medium | option |
| 19 | Technic frames and chassis | cranes, mechs, big vehicles, trusses | 32524 32316 32278 32140 32526 32348 6536 32184 6558 3713 | pin/axle | XL | Medium | command |
| 20 | Microscale mode | cities, landmarks, dioramas | 3024 6141 98138 3070b 4589 + normal parts | studs | M | Low-Med | setting |

The order of this table is the recommended priority: payoff per unit of effort, weighted toward
the categories that most prompts hit. Items 16 and 17 are ranked below their payoff only because
they need the Phase 2 foundations (new connection types plus angled placement). Once those exist,
17 becomes the single biggest quality jump for creatures.

---

## 2. Techniques in detail

### 1. Colour gradients and dithering
- **Looks like:** natural colour transitions instead of hard single-colour blocks - water that
  darkens with depth, grass fading to soil, rock with mixed greys, shaded fur. Builders blend over
  4-6 rows with ratios of about 80/20, 60/40, 40/60, 20/80, with a few intermediate-colour
  pieces scattered just outside the zone so it doesn't look mechanical.
  [The Brick Fantastic: blending colours](https://www.thebrickfantastic.com/how-to-blend-lego-colors-for-natural-gradients-and-shading/)
- **Colour families that blend** (LDraw codes checked in LDConfig): blue family: dark blue 272,
  blue 1, medium blue 73, medium azure 322, white 15; green family: dark green 288, green 2,
  bright green 10, lime 27, yellowish green 326, olive green 330; earth family: dark brown 308,
  reddish brown 70, dark orange 484, medium nougat 84, tan 19, dark tan 28; greys: dark bluish
  grey 72, light bluish grey 71, white 15.
- **Engine:** a `paint` variant `paint A>B axis=y|x|z` (gradient) plus seeded per-cell dithering
  at the boundary. Colour is already per cell before tiling, so this is pure colour assignment.
  The tiler must keep merging same-colour cells into big parts, so dithered zones get more small
  parts: cap the zone width.
- **Effort S, payoff High.** Also the basis of items 2 and 10.

### 2. Water surface with depth gradient
- **Looks like:** a transparent tiled surface over coloured plates, shallow near the shore and
  darker offshore, with sparkle and foam. Shallow water is trans-light-blue 1x2 tiles and 1x3
  plates one to three studs out from shore, with trans-clear mixed in. Occasional exposed
  trans studs read as ripples, white 1x1 round plates as foam, and darker plates underneath read
  as depth. Randomised tile layout for natural water, regular lines for pools.
  [The Brick Fantastic: beach gradient](https://www.thebrickfantastic.com/how-to-build-a-lego-beach-and-shoreline-with-a-gradient-of-depth/),
  [Geneva D: water](https://genevadurand.com/2017/07/25/making-waves-water-with-lego-bricks/),
  [The Brick Blogger: water](https://thebrickblogger.com/2011/11/lego-building-technique-lego-water/)
- **Parts:** tiles 3070b, 3069b, 63864, 2431, round tile 98138, round plate 6141, all in trans
  light blue 43, trans clear 47, trans dark blue 33 or trans medium blue 41, over plates in dark
  blue 272 / blue 1 / medium azure 322.
- **Engine:** new `water REGION L [depth=shore|uniform]`: the bottom layer's colour comes from
  distance to the region's edge (the dithered gradient from item 1), the top layer is trans tiles
  with a seeded share of exposed trans round plates, and optional white 6141 foam along the
  shoreline. Two crossed layers, verified like a floor slab.
- **Effort S, payoff High** for any scene with water (ponds, harbours, islands, fountains).

### 3. Trees, bushes and flowers v2
- **Looks like:** several tree styles instead of one pyramid. A 1x1 round-brick trunk (3062b)
  with leaves 2417/2423 on studs at several levels; wider trunks from 2x2 round bricks (3941)
  or staggered rings; canopies layered dark green inside, green in the middle, lime/olive at the
  sunlit edges. Bushes from clusters of 2423, 6255 and 32607. Flowers as 24866 (5 petals) or
  33291 on stems, or 3742 flower heads. Bamboo via 30176.
  [BrickNerd: foliage parts guide](https://bricknerd.com/home/lush-landscaping-a-builders-guide-to-lego-foliage-3-20-25),
  [How to build it: tree tips](https://htbi-moc.com/blogs/guides/tips-for-building-different-types-of-lego-trees),
  [Brickbuilt tree tutorial](http://www.brickbuilt.org/?p=7587)
- **Parts (checked):** 3062b brick 1x1 round, 3941 brick 2x2 round, 2417 leaves 6x5, 2423
  leaves 4x3, 32607 leafy 1x1 plate, 6255 plant 1x1 with 3 large leaves, 30176 bamboo 1x1,
  24866 plate 1x1 with 5 petals, 3742 plant flower, 2435 (already in table).
- **Engine:** `tree X Z L [style=round|layered|pine|bamboo] [height=N] [leaf=COLOUR|COLOUR]`,
  `bush X Z L [size=]`, `flowers REGION L [colours]`. All studs-up: trunk stacks, leaf parts on
  studs at chosen levels, canopy colours dithered. Leaves are irregular parts: their bounding
  boxes must be measured, and collision against neighbours needs a looser tolerance.
- **Effort S-M, payoff High** (every garden, park, landscape and village).

### 4. Vehicle detailing
- **Looks like:** a car reads as a car because of its lights, grille, wheel arches and trim, not
  its body block. Headlights are headlight bricks (4070) with a trans-clear 1x1 round tile in the
  front stud; grilles are 1x2 grille tiles (2412b); wheel arches come from mudguard plates
  (3788 mudguard 2x4, 50745 4x2.5x2 with arch, 98282 4x2.5x1, 28326 4x3x1). Gaps around
  mudguards are closed with 1x2 inverted slopes; smoother noses use sideways cheese slopes and
  tiles. Exhausts are 1x1 cones (4589).
  [New Elementary: mudguards](https://www.newelementary.com/2017/10/lego-part-28326-mudguard-3x4-plate-vehicle-4x3-arch-curved.html),
  [BrickNerd: six-wide cars](https://bricknerd.com/home/six-wide-how-to-fit-a-minifig-in-a-custom-car-10-24-24)
- **Engine:** an automatic pass on wheeled sculpts (`wheels`): front face gets headlights (4070
  plus 98138 trans-clear, or trans-yellow 46) and a grille band (2412b); back face gets
  trans-red lights; mudguards replace the body cells over each axle when the axle spacing and
  width match a mudguard's measured footprint. 4070's front stud is a side stud facing out, so
  the existing SNOT frame code should be able to hold the lamp tile (to be confirmed).
- **Effort M, payoff High** (cars, trucks, buses and trains are very common prompts; the flat
  sports car in the 2026-09-25 comparison is the kind of result this addresses).

### 5. Wedge plates for sleek outlines
- **Looks like:** angled wing edges, pointed noses and boat bows instead of stepped rectangles.
  Builders step down 2-3 times with wedge plates and curved slopes rather than one steep jump;
  plate-and-tile sandwiches give crisp thin wing edges; bows are wedge plates plus inverted
  slopes.
  [Military LEGO: aircraft](http://militarylego.blogspot.com/2010/05/building-scale-models-of-aircraft-in.html),
  [How to build it: boats](https://htbi-moc.com/blogs/guides/lego-yacht-mocs-from-sleek-day-boats-to-mega-superyachts)
- **Parts (checked):** 43722a/43723a wing 2x3 right/left, 41769a/41770a wing 2x4 right/left,
  51739 wing 2x4, 24299/24307 wing 2x2 left/right, 2450 plate 3x3 without corner, 30357 plate
  3x3 with 2x2 round corner, 41747/41748 wedge 2x6 double right/left (brick height).
- **Engine:** wedge plates sit on the stud grid at yaw 0/90/180/270, so no angled placement is
  needed. The sculpt tiler gets a rule: where a layer's outline steps diagonally (a staircase
  edge in plan), cover the step with the matching left/right wedge instead of a stepped plate
  pair. Same idea as the existing curved-slope caps, but in plan instead of in section. Needs
  each wedge's cut-corner geometry measured, and collision on the cut side.
- **Effort S-M, payoff High** for aircraft, boats, spaceships and car noses (currently blocky).

### 6. Building facades v2
- **Looks like:** set-like facades: a repeated window module with subtle variation, sills under
  windows, arches over doors, contrasting corner quoins, stringcourse bands between floors, a
  cornice at the roofline, and textured walls (embossed-brick 1x2, log bricks for cabins).
  [How to build it: buildings like a pro](https://htbi-moc.com/blogs/guides/how-to-build-a-lego-building-like-a-pro),
  [Brick Architect: modular standard](https://brickarchitect.com/2025/getting-started-moc-lego-modular-building-standard/)
- **Parts (checked):** 60592/60593 window 1x2x2 and 1x2x3 with glass 60601/60602, 3659 arch
  1x4, 6182 arch 1x4x2, 6005 arch 1x3x2 curved top, 98283 brick 1x2 with embossed bricks,
  30136 log brick 1x2, 2431 tile (sills), 3665a inverted slope (cornice), 4070 headlight brick
  (cornice or sill detail facing out), 3185 lattice fence and 30055 spindled fence (balconies).
- **Engine:** options on `building`: `window=4x3|2x2|2x3|arched`, `sills=1`, `quoins=COLOUR`,
  `band=COLOUR` (tile stringcourse), `cornice=1`, `texture=plain|masonry|log`, `balcony=1`.
  Nearly all studs-up: a window module is a pattern of openings, frames and glass like today's
  1x4x3; quoins and textures are colour or part-id swaps inside the existing wall courses. The
  cornice with inverted slopes is studs-up; the headlight-brick variant uses the SNOT frame.
- **Effort S-M, payoff High.** Buildings are already the strongest category, and this is what
  moves them from good to set-like.

### 7. Eyes v2
- **Looks like:** expressive eyes sized to the head: large "cute" eyes from a white 2x2 round
  tile with a black 1x1 round tile or plate offset toward the front, small eyes as a single black
  1x1 round tile, fierce eyes with a coloured ring. Offsets use jumper plates for a half-stud
  shift. Printed eye tiles exist but are left out (printed parts complicate the parts list and
  sourcing).
  [BrickNerd: SNOT basics](https://bricknerd.com/home/snot-basics-geometry-techniques-and-pitfalls-3-18-2021)
- **Parts (checked):** 14769 tile 2x2 round, 4150 tile 2x2 round, 98138 tile 1x1 round, 6141
  plate 1x1 round, 3794b / 15573 jumper plate 1x2.
- **Engine:** `eye X Y size=small|large style=cute|plain|fierce`: an extension of the existing
  eye, which already paints or SNOT-mounts a 3-plate patch. The large eye needs a 2x2 SNOT
  patch (two anchors, or a 2x2 bracket 44728/99207 later).
- **Effort S-M, payoff High** (animals are among the most common prompts; faces decide whether
  they look alive).

### 8. Teeth, spikes, claws and horns (plate type)
- **Looks like:** spiky dragon backs, dinosaur teeth, cactus spines and hedgehog quills. Tooth
  plates in a row along a ridge; cones for thicker spikes. Scattered small plates and wedge tiles
  give scales and ridges.
  [How to build it: dragons](https://htbi-moc.com/blogs/guides/lego-moc-dragon-breathe-fire-into-your-builds)
- **Parts (checked):** 49668 plate 1x1 with tooth in-line, 15070 plate 1x1 with tooth
  perpendicular, 15208 plate 1x2 with 3 teeth in-line, 4589 cone 1x1.
- **Engine:** `spikes COLOUR along=x|z line X0..X1 Y Z [every=1|2]` or an automatic ridge rule on
  sculpt tops: tooth plates are ordinary plates (stud on bottom), so they sit on the top studs of
  the sculpt surface; the tooth direction comes from yaw. Needs the tooth geometry measured so
  collision is right.
- **Effort S, payoff Medium-High** for dinosaurs, dragons, cacti, monsters.

### 9. Roofs v2
- **Looks like:** textured roofs instead of smooth slope fields: staggered 1x1/1x2 cheese-slope
  shingles, stepped slope rows with plates between for overlapping-shingle shadow lines,
  alternating slope sizes, ridge caps (double slopes), chimneys, dormers, and round tiles for a
  storybook look.
  [BrickNerd: 15 ways to build a roof](https://bricknerd.com/home/15-ways-to-build-a-lego-roof-6-7-22),
  [The Brick Blogger: shingles](https://thebrickblogger.com/2017/01/lego-shingles-roofing-techniques/),
  [Geneva D: roofs](https://genevadurand.com/2017/08/03/roofs-with-lego-bricks/)
- **Parts (checked):** 54200 and 85984 cheese slopes (in table), 3040b slope 45 2x1, 3039 slope
  45 2x2, 3044b slope 45 2x1 double (ridge), 3043 slope 45 2x2 double, 3048b slope 45 1x2
  triple (hip corner), 4286/3298 slope 33 3x1/3x2.
- **Engine:** roof options `style=smooth|shingle|slate|storybook`, `chimney=left|right`,
  `dormers=N`. Shingles are studs-up (cheese slopes on plate steps); real 45- and 33-degree
  slopes give straight pitched roofs instead of curved caps. Each slope family's anchoring and
  facing must be measured independently (the core pipeline's slope history shows why).
- **Effort M, payoff Medium-High.**

### 10. Rockwork
- **Looks like:** cliffs and boulders from many slopes and inverted slopes in varied directions
  and sizes, never a repeating pattern, in two or three mixed greys or browns, with plants tucked
  into gaps. More advanced versions mix in SNOT slopes and hinged sections for striations.
  [BrickNerd: rockwork](https://bricknerd.com/home/lego-rockwork-techniques-lets-get-rocking-1-26-23),
  [Geneva D: rockwork](https://genevadurand.com/2021/08/18/lego-rockwork-techniques/),
  [Tips&Bricks: terrain](https://www.tipsandbricks.co.uk/post/2498-beginner-series-lesson-12-landscaping-terrain-rockwork/)
- **Parts:** the slope families from item 9 plus inverted 3665a and cheese slopes, in dark
  bluish grey 72, light bluish grey 71, dark tan 28, reddish brown 70.
- **Engine:** `sculpt ... texture=rock`: cap the sculpt's steps with a seeded random choice of
  slope type, size and facing (rather than the uniform curved caps), dither 2-3 colours, and let
  `scatter` put plants in the remaining exposed studs. Studs-up version first; SNOT and hinged
  striations after Phase 2.
- **Effort M, payoff High** (every landscape, castle hill, cave or display base).

### 11. Greebling and surface texture
- **Looks like:** small relief detail on large flat areas of machines and spaceships - grille
  tiles, 1x1 round plates, cones, offset jumpers. Keep it to the outline's shade, block the
  outline first, and don't overdo it.
  [The Brick Blogger: greebling](https://thebrickblogger.com/2015/07/lego-building-technique-greebling/),
  [BrickNerd: greeble greatness](https://bricknerd.com/home/achieving-greeble-greatness-3-18-24)
- **Parts:** 2412b grille tile, 6141 round plate, 98138 round tile, 4589 cone, 3794b jumper.
- **Engine:** automatic on large flat tops of sculpts tagged as machines/vehicles (or
  `detail=greeble`): replace a seeded share of the top tiles with grille tiles and add a few 1x1
  round plates, capped by density and never on the model's silhouette edge. All studs-up.
- **Effort S, payoff Medium.**

### 12. Round shapes
- **Looks like:** burgers, cakes, fountains, towers and domes built from round plates, round
  tiles, dishes and cones instead of square steps.
- **Parts (checked):** 4032a plate 2x2 round, 14769/4150 tile 2x2 round, 2654a dish 2x2, 4740
  dish 2x2 inverted, 3960 dish 4x4 inverted, 30367a cylinder 2x2 with dome top, 3942b cone
  2x2x2, 6143 brick 2x2 round, plus 3941/87081 (in table).
- **Engine:** in `sculpt`, a small `cyl y` (radius 1 or 2) or a ball's top/bottom cap maps to the
  matching round part stack instead of square plates; a `dome` cap option uses dishes. Studs-up,
  centred on stud corners (2x2 round parts are centred between studs, which the grid handles).
- **Effort S-M, payoff Medium** (food, objects, props, lamp posts, columns).

### 13. Jumper (half-stud) offsets
- **Looks like:** details centred on an odd-width face - a chimney in the middle of a 4-wide
  roof, an eye centred on a 3-wide head, a single antenna on a 2-wide top.
- **Parts (checked):** 3794b and 15573 jumper plate 1x2, 87580 plate 2x2 with 1 centre stud,
  18674 plate 2x2 round with 1 centre stud.
- **Engine:** the engine's grid is whole studs. A jumper gives a stud at a half-stud position,
  so the engine needs half-stud stud positions (a stud position lookup already exists; the grid
  cell model does not). Mostly automatic: used by items 7, 9 and 11 when a feature's centre is at
  a half stud.
- **Effort M, payoff Medium.**

### 14. SNOT holders with detail in the hole
- **Looks like:** the founder's example - SNOT bricks with small parts in their studs or holes
  to make spikes, lamps or trunks. A headlight brick (4070) holds a round tile (a lamp) or a
  claw; a brick with studs on four sides (4733) holds tooth plates on every side (a spiky ball, a
  branching trunk); a 1x1 round plate with open stud (85861) holds a bar-ended curved blade
  (87747) as a horn or claw.
  [BrickNerd: SNOT basics](https://bricknerd.com/home/snot-basics-geometry-techniques-and-pitfalls-3-18-2021),
  [Brick Architect: SNOT parts](https://brickarchitect.com/parts/category-3)
- **Parts (checked):** 4070 brick 1x1 with headlight, 4733 brick 1x1 with studs on four sides,
  47905 brick 1x1 with studs on two opposite sides, 32952 brick 1x1x1.667 with studs on 1 side,
  11211 brick 1x2 with two studs on one side, 85861 plate 1x1 round with open stud, 87747 bar
  0.5L with curved blade 2L.
- **Engine:** the side-stud bricks use the existing SNOT frames (M). A bar in an open stud is a
  new, simple connection (axis-aligned, like a stud) (L-lite). Note the known tolerance issue: a
  headlight brick is exactly two plates thick without the usual clearance, so pairing it with
  other SNOT parts needs care.
- **Effort M-L, payoff Medium.**

### 15. Clip and bar connections
- **Looks like:** palm trees with sword leaves on clips, foliage on stems, railings and
  ladders, antennas, lamp posts, flags.
  [Brick Architect: articulation parts](https://brickarchitect.com/parts/category-106)
- **Parts (checked):** 61252 plate 1x1 with clip horizontal, 4085c plate 1x1 with clip vertical,
  15712 tile 1x1 with clip, 60478 plate 1x2 with handle on end, 48729a bar with clip, 87994 bar
  3L, 30374 bar 4L, 10884 swordleaf 6x5 with C-clip, 37695 plant stem with 3 leaves with bar and
  pin holes.
- **Engine:** a new connection type in `parts_table.json` (clip axis, bar axis and length,
  measured from geometry) and in the graph. Axis-aligned uses (vertical bars, horizontal
  railings) work without angled placement; anything that pivots on the clip needs item 16's
  angled placement.
- **Effort L, payoff Medium.**

### 16. Hinged angles
- **Looks like:** roofs at any pitch, wings with dihedral, heads and tails tilted naturally,
  boat bows and angled rock faces - the main tool builders use to escape the right-angle grid.
  [BrickNerd: joint techniques](https://bricknerd.com/home/joint-effort-lego-joint-techniques-for-articulated-builds-1-17-25),
  [Brickset: Creator tiger review](https://brickset.com/article/67633)
- **Parts (checked):** 2429/2430 hinge plate 1x4 base/top (free angle), 3937/3938 hinge 1x2
  base/top, 44301a/44302a hinge plate 1x2 locking with single/dual finger (click steps),
  44567a single finger on side, 60471 locking 9-position with dual finger on side.
- **Engine:** needs Phase 2: a hinge connection (axis, allowed angles: continuous for 2429/2430,
  discrete steps for the locking ones), arbitrary rotation matrices for everything mounted on
  the far side, and collision on oriented boxes instead of grid cells. The sub-assembly on the
  hinge is built in its own frame (like today's SNOT frames, but tilted).
- **Effort L-XL, payoff High.**

### 17. Ball-joint chains (`limb`)
- **Looks like:** smoothly curving tentacles, trunks, necks, tails and snakes: short segments
  joined by ball joints, each turned a little, capped with curved slopes. Large animal sets
  segment bodies with ball joints and use click hinges for limbs and necks (examples: the
  Creator tiger and T. rex sets).
  [BrickNerd: joint techniques](https://bricknerd.com/home/joint-effort-lego-joint-techniques-for-articulated-builds-1-17-25),
  [Brickset: tiger review](https://brickset.com/article/67633),
  [The Rambling Brick: Creator T. rex](https://ramblingbrick.com/2024/05/29/31151-creator-t-rex/)
- **Parts (checked):** 14417 plate 1x2 with ball joint on side, 14418 plate 1x2 with socket,
  14419 plate 1x2 with socket and ball (the chain link).
- **Engine:** `limb FROM TO [curve=] [thickness=1|2] [colour]`: solve a chain of 14419 links (plus
  a segment of plates/slopes around each link for thickness) along a curve between two points,
  each link's rotation within the joint's measured range, with oriented-box collision against
  the body and each other. The chain is one connected piece by construction (every link clicks
  into the previous one). This is the known top gap (octopus, elephant, dragon, giraffe neck).
- **Effort XL, payoff Very high** for the weakest category in the evaluation.

### 18. Technic decoration
- **Looks like:** gears, axles and beams showing on robots, mechs, cranes and machines - Technic
  as texture rather than structure. Technic bricks with a half pin also act as side studs.
  [Brick Architect: Technic parts](https://brickarchitect.com/parts/category-12),
  [Belle-Ve Bricks: greebling](https://bellevebricks.com/greebling-lego-technique/)
- **Parts (checked):** 3700 Technic brick 1x2 with hole, 3701 1x4 with holes, 6541 1x1 with
  hole, 4274 pin 1/2, 2780 pin with friction, 3705/3706 axle 4/6, 3648b gear 24 tooth, 3647 gear
  8 tooth, 32270 gear 12 tooth double bevel, 32523 beam 3.
- **Engine:** Technic bricks are ordinary bricks with a hole (studs-up); the new connections
  are pin-in-hole and axle-in-hole along the hole's axis, axis-aligned, so no angled placement is
  needed for decoration (a gear on a pin in a Technic brick's side hole). A half-stud height
  offset (the hole is 0.1 mm higher than a SNOT stud) is ignorable in the model but must not
  confuse collision.
- **Effort L, payoff Medium.**

### 19. Technic frames and chassis
- **Looks like:** liftarm skeletons for cranes, mechs, big vehicles and trusses; triangulated
  beams for strength; bent liftarms for curves.
  [Doctor Engine: liftarms](https://doctorengine.info/post/lego-backbone-of-creation/),
  [Technic Brick Power](https://technicbrickpower.com/)
- **Parts (checked):** 32524/32316/32278 beam 7/5/15, 43857 beam 2, 32140 beam 2x4 bent 90,
  32526 beam 3x5 bent 90, 32348 beam 4x4 bent 53.13, 6536 cross block 1x2, 32184 cross block
  1x3, 6558 long pin with friction, 3713 bush.
- **Engine:** a pin/axle connection graph with holes as connectors, plus angled parts (32348 is
  53.13 degrees) - so it needs the Phase 2 rotation work too. The largest subsystem here; worth
  it only if mechanical subjects turn out to be common.
- **Effort XL, payoff Medium.**

### 20. Microscale
- **Looks like:** cities, landmarks and dioramas where one stud is a metre or more; detail from
  the smallest parts (1x1 plates, round plates, tiles, cones), framed with a dark tile border or
  a trans-blue water edge.
  [The Brick Blogger: micro-scale](https://thebrickblogger.com/2013/11/building-with-lego-micro-scale-building/),
  [The Earl of Bricks: microscale](https://theearlofbricks.com/blog-microscale-lego-building/)
- **Engine:** a `scale=micro` setting that changes PROMPT guidance and the building command's
  module sizes (1-stud windows, 3-plate storeys). Connectionless micro techniques are excluded
  (see below).
- **Effort M, payoff Low-Medium.**

---

## 3. Automatic detailing (no spec text needed)

Applied by the engine after the spec is built, each seeded (the same spec always gives the same
model), density-capped, and re-checked for connectivity like any other engine repair. Each gets
its own on/off switch in `CONFIG`, so one that misbehaves can be turned off in one line.

| Detail | Where it applies | Parts | Effort |
|--------|------------------|-------|--------|
| Colour dithering at colour boundaries | large single-colour natural areas (grass, water, rock, fur) | none new | S |
| Exposed studs as texture | grass and ground stay studded; paths, water and roofs get tiles (today tiling is all-or-nothing per model) | none new | S |
| Window sills and lintels | every `building` window | 2431, 3659 | S |
| Corner quoins | `building` with trim colour | wall bricks | S |
| Headlights, grille, tail lights | wheeled sculpts, front and back faces | 4070, 98138, 2412b | M |
| Greebling | large flat tops of machines/vehicles | 2412b, 6141, 98138 | S |
| Round-part caps | round columns and small cylinders | 98138, 14769, 6141 | S |
| Jumper centring | a single detail on an even-width face | 3794b, 15573 | M |
| Plants at base edges | gardens and landscapes (existing `scatter`, made automatic on green bases) | 32607, 24866, 33291 | S |
| Exposed-stud warning | report studs left exposed where a smooth finish was asked for (known gap) | - | S |

---

## 4. Proposed build order

**Batch 1 - studs-up techniques on today's engine** (fastest visible gains, no new connection
types):
1. Colour gradients and dithering (1), then water (2) on top of it.
2. Vehicle detailing (4) and wedge plates (5) - fixes the flat-slab cars, planes and boats.
3. Eyes v2 (7) and plate-type spikes/teeth (8) - animals and creatures.
4. Building facades v2 (6) and roofs v2 (9) - buildings from good to set-like.
5. Trees/bushes/flowers v2 (3) and rockwork (10) - landscapes and scenes.
6. Greebling (11), round shapes (12), and the automatic details in section 3.

**Batch 2 - Phase 2 foundations** (as the handoff describes): connection types measured from
LDraw (clip/bar, hinge, ball, bar-in-stud, pin/axle), arbitrary rotation plus oriented-box
collision, and the `limb` chain primitive (17). Then hinged angles (16) for roofs, wings, heads
and tails.

**Batch 3 - techniques that need Batch 2:** SNOT holders with parts in the hole (14), clip and
bar uses (15), Technic decoration (18), rock striations with SNOT/hinged slopes, and only if
mechanical prompts justify it, Technic frames (19). Microscale (20) whenever convenient.

Each technique, per the handoff: a bounded DSL command or automatic pass, unit tests including a
hostile-size test, a rendered example, a before/after on a benchmark prompt, a founder Studio
check, and one compact recipe line in PROMPT.md. PROMPT.md is already about 4,200 tokens
(measured: the API reported 4,189 cache-write tokens on 2026-09-25), i.e. at the ~4-5k point the
handoff flagged. The cost is still small: at $5 per million cache-write tokens, every 1,000 more
tokens adds about $0.005 to a job that misses the cache (cache reads are ~25x cheaper), so even
8,000 tokens would add only ~$0.02 per cache miss against a ~$0.13 job. Recipe lines must stay
tight anyway (a longer prompt also costs attention), and whether 1-hour caching pays off should
be measured once traffic is known. None of this adds API calls, so the per-job cost target (mean
<= ~$0.20) is unaffected.

**Benchmark prompts to watch per batch:** Batch 1 - red sports car, steam train, jet, a garden
with a pond, a cottage, a modular building, a dragon, a cactus in a pot; Batch 2 - octopus with
tentacles, elephant, giraffe, snake, a bird with open wings.

---

## 5. Deliberately left out

- **Connectionless techniques** (loose-brick rockwork, balanced micro parts, rubber bands, flex
  tubing threaded through leaves): they break the guarantee that every model is one connected,
  buildable piece.
- **Printed parts and stickers** (eye tiles, printed windows): they complicate the parts list and
  sourcing, and plain-part versions look nearly as good at this scale.
- **Minifigures and characters as figures**: out of scope for sculpture-style builds.
- **Parts outside current production** where a common alternative exists (sourcing matters for a
  buildable parts list).

---

## 6. Sources

- Brick Architect: [SNOT parts](https://brickarchitect.com/parts/category-3), [articulation
  parts](https://brickarchitect.com/parts/category-106), [Technic parts](https://brickarchitect.com/parts/category-12),
  [modular building standard](https://brickarchitect.com/2025/getting-started-moc-lego-modular-building-standard/)
- BrickNerd: [SNOT basics](https://bricknerd.com/home/snot-basics-geometry-techniques-and-pitfalls-3-18-2021),
  [rockwork](https://bricknerd.com/home/lego-rockwork-techniques-lets-get-rocking-1-26-23),
  [foliage parts](https://bricknerd.com/home/lush-landscaping-a-builders-guide-to-lego-foliage-3-20-25),
  [joint techniques](https://bricknerd.com/home/joint-effort-lego-joint-techniques-for-articulated-builds-1-17-25),
  [15 roofs](https://bricknerd.com/home/15-ways-to-build-a-lego-roof-6-7-22),
  [six-wide cars](https://bricknerd.com/home/six-wide-how-to-fit-a-minifig-in-a-custom-car-10-24-24),
  [greebling](https://bricknerd.com/home/achieving-greeble-greatness-3-18-24)
- New Elementary: [mudguards](https://www.newelementary.com/2017/10/lego-part-28326-mudguard-3x4-plate-vehicle-4x3-arch-curved.html),
  [Botanical flower bouquet review](https://www.newelementary.com/2020/12/lego-review-botanical-10280.html)
- Geneva D: [water](https://genevadurand.com/2017/07/25/making-waves-water-with-lego-bricks/),
  [rockwork](https://genevadurand.com/2021/08/18/lego-rockwork-techniques/),
  [roofs](https://genevadurand.com/2017/08/03/roofs-with-lego-bricks/)
- The Brick Blogger: [water](https://thebrickblogger.com/2011/11/lego-building-technique-lego-water/),
  [shingles](https://thebrickblogger.com/2017/01/lego-shingles-roofing-techniques/),
  [greebling](https://thebrickblogger.com/2015/07/lego-building-technique-greebling/),
  [micro-scale](https://thebrickblogger.com/2013/11/building-with-lego-micro-scale-building/)
- The Brick Fantastic: [colour blending](https://www.thebrickfantastic.com/how-to-blend-lego-colors-for-natural-gradients-and-shading/),
  [beach gradient](https://www.thebrickfantastic.com/how-to-build-a-lego-beach-and-shoreline-with-a-gradient-of-depth/)
- How to build it: [buildings](https://htbi-moc.com/blogs/guides/how-to-build-a-lego-building-like-a-pro),
  [trees](https://htbi-moc.com/blogs/guides/tips-for-building-different-types-of-lego-trees),
  [dragons](https://htbi-moc.com/blogs/guides/lego-moc-dragon-breathe-fire-into-your-builds),
  [boats](https://htbi-moc.com/blogs/guides/lego-yacht-mocs-from-sleek-day-boats-to-mega-superyachts)
- Others: [Brickbuilt tree tutorial](http://www.brickbuilt.org/?p=7587),
  [Tips&Bricks terrain](https://www.tipsandbricks.co.uk/post/2498-beginner-series-lesson-12-landscaping-terrain-rockwork/),
  [Military LEGO aircraft](http://militarylego.blogspot.com/2010/05/building-scale-models-of-aircraft-in.html),
  [Brickset tiger review](https://brickset.com/article/67633),
  [The Rambling Brick T. rex](https://ramblingbrick.com/2024/05/29/31151-creator-t-rex/),
  [Doctor Engine liftarms](https://doctorengine.info/post/lego-backbone-of-creation/),
  [The Earl of Bricks microscale](https://theearlofbricks.com/blog-microscale-lego-building/)
- Part IDs: official LDraw library (library.ldraw.org), titles checked 2026-09-25; colour codes
  from its LDConfig.ldr.
