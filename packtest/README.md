# Pack test

Runs The Isles in the real game on GitHub Actions: Minecraft 26.3, Fabric Loader 0.19.5, Java 25.
Nothing here is part of the data pack; `tools/build_pack.py` and `datapack/` do not depend on it.

## Running it

Push to the `pack-test` branch (or start the "Pack test" workflow by hand). The workflow has one job per group of
phases (`vanilla`, `terrain`, `pack`, `perf`; they run side by side, about an hour for everything - the client script of `pack` is the longest) and a `report` job:

1. each job rebuilds `datapack/` and `datapack-mods/` from `layout/islands.json` - with the biome packs named in
   `packtest/providers` it also builds `build/the-isles/` and tests that one (see "Biome packs" below) -, zips them and runs `packtest/run.sh`
   with its phases; while it runs, a snapshot of its logs is pushed every 3 minutes to `ci-logs-vanilla`,
   `ci-logs-terrain`, `ci-logs-pack`, `ci-logs-perf`,
2. the `report` job puts the logs together, writes `report.txt` and `verdict.txt` (`packtest/tools/report.py`) and
   force-pushes everything, screenshots included, to the `ci-logs` branch,
3. if `packtest/publish` exists and the verdict is PASS, it publishes the two zips as release `pack-test-latest`. The
   release is always built without providers (vanilla biomes): nothing of the biome packs leaves the runner.

`packtest/tools/wait.sh` waits for the run of HEAD and unpacks `ci-logs`; `packtest/tools/sheet.py` makes contact
sheets of the screenshots. Start with `report.txt` and `verdict.txt`.

## Phases (`packtest/phases`, any of)

| Phase | What runs | What it answers |
|---|---|---|
| `vanilla` | dedicated server, Fabric API + The Isles only | does the world load and generate without errors; islands where the layout says, right biome, empty void, build limits, every structure (`/locate`, then its blocks counted around the island surface, in the rest of the columns and on the world floor), pre-generation time and heap |
| `terrain` | the same server in a job of its own, then `tools/scan.py` on its saved world (without this phase the section runs inside `vanilla`) | the terrain features: every geyser block by block against `layout/geysers.json`, the springs in freezing biomes, water under and outside all 33 sea basins, structures in the basins, caves, bands and snow line, sulfur caves |
| `baseline` | the same server without The Isles (vanilla generator) | reference for time and heap |
| `pack` | every mod of `mods.tsv` + both data packs, a real client under Xvfb, then a restart | boot log, ores per island, oil, a Create line / diesel engine / reactor / gun / hypertube across the void, spawn, respawn, mobs, weather, portals, the look of the sky at three altitudes, screenshots |
| `perf` | one fresh world per line of `perf.txt`: the pack built by an older commit (`@commit`) or with generator settings (`ISLES_OFF=caves` leaves a feature out) | generation time of the same land / void / stacked-tier / sea-basin regions, heap, tick times, a `/locate` that finds nothing; thread dumps while generating, summed up by step in the report |
| `speed` | servers with subsets of the mods (`speed.txt`) | which mods change the generation time |
| `nether` | Fabric API + The Isles (with `nethermods`: every mod and `datapack-mods`), then a client; with `netherperf` first the variants of `nether-perf.txt` (time, heap, profile, block counts of two layers; `nperfonly`: only those - the two words have to be let through by the `case` of the workflow's phases step) | the Nether: generation time and heap of 64 chunks, columns through all layers, blocks per layer, bedrock, structures per layer, views and mob counts in two layers, four portals (`nether-phase.sh`, `gen_nether.py`, screenshots `nether-NN.png`, `nether-stacks.txt`) |
| `netherbase` | the same server without The Isles | the vanilla Nether as reference for time, heap and block counts |
| `bisect` | one fresh world per line of `bisect.txt` (island ids) | which island breaks generation |

## Files

| File | |
|---|---|
| `gen.py` | writes the probe data pack (functions `packtest:col`, `biome`, `top`, ...) and every console command file and the client script from the layout; edit the scenarios here |
| `run.sh`, `pack-phase.sh` | start servers and the client, feed the console (`#poll`, `#wait`, `#loc`, `#time`, `#heap`, `#prof`, `#sleep` directives), take screenshots |
| `mods.tsv` | download URL and file name of every mod of the pack |
| `client/` | empty Loom project that only launches the 26.3 Fabric client with `run/mods` |
| `client-options.txt` | extra `options.txt` lines (key bindings must be legacy numbers: `key_key.use:22` is U) |
| `debugmod/`, `debug` | test-only mod, built in the run when the file `debug` exists: prints chunk generation exceptions that the game otherwise swallows (see below) |
| `view-distance` | server view distance and client render distance |
| `tools/scan.py` | reads the saved world of the terrain phase (region files, no game needed): where the blocks are that the fills marked (water under a sea floor or past a rim: position, the structure piece or neighbouring island they belong to, the blocks around), and every structure that starts in a basin's chunks - its pieces against the water level and the ground under them, chests; `scan.py selftest` checks the reader against a region file it writes itself |
| `known.txt` | regexes of failures that are known findings; they are listed in the report but do not fail the run |
| `quick` | while iterating: the only sections to run (words used by `on()` in `gen.py`, e.g. `islands-few structures look biomes biomeviews`; with `terrain`, any of `geysers pockets seas tcaves surfaces` limits that section to those parts; `cavemobs` is the client's count in two islands' caves); delete it for a full run |
| `providers` | ids of `layout/providers.json` the tested pack is built with; only packs with a public download reach the runner (`geophilic`); no file = vanilla biomes |
| `server-only`, `exclude.txt`, `no-mods-datapack`, `publish` | switches: no client; regexes of mod jars to leave out; pack phase without `datapack-mods`; publish the release |

## Things worth knowing

* A chunk generation exception on a worker thread is only "relayed" to the server thread. If that thread is waiting
  for the very chunk (`/forceload add` loads synchronously in 26.3), the server hangs with nothing in the log but
  `Parent chunk missing`. `debugmod` prints the real exception (`PACKTEST delayed crash`).
* 1,500 force-loaded chunks of this height do not fit in a 5 GB heap; the probes drop their tickets per island.
* The headless client needs `SDL_VIDEO_FORCE_EGL=1` (Xvfb has no sRGB GLX visual) and Mesa's EGL packages.
* Screenshots come from software rendering (llvmpipe); frame rates there say nothing about a real GPU.
* `@s`, `@p`, `@r` inside a `say` are selectors: tags printed with `say` must not contain `@`.
* Create Nuclear only assembles a reactor while a player is online (its check loops over the players), so the
  controller is placed by the client script.
* The 26.3 density functions are evaluated for a whole chunk at once and nothing is skipped (`range_choice` and
  `interval_select` compute every branch for every point). `slice` is the way to compute something once per column.

## Findings (26.3, October 2026)

Fixed in the generator (each its own commit on `pack-test`):

| Finding | Evidence | Fix |
|---|---|---|
| Chunk generation dies in badlands below y -192; the server hangs | `ArrayIndexOutOfBoundsException` in `MaterialSystem.getBand`, J cluster never loads | the vanilla surface rule only runs 48 blocks deep |
| `eroded_badlands` raises stone pillars from the ground up to y 64..90 | ground at y 74 in the footprint of T4 (top y -1000), y 65 on J2 (top y -460) | the generator uses `badlands` there |
| The whole world is snow-covered, rain falls as snow | snow layer on the spawn plains at y 57; screenshots | rainy biomes are written with a temperature that survives the altitude, colours pinned |
| Ores only in the vanilla height band | zinc, lead, uranium and diamonds only in the spawn island; coal only above y 500 | ore placement by depth under the island surface; `datapack-mods` for the mod ores |
| Ice spikes hang down to y 50 from island rims | screenshot of e3; 322 packed ice blocks under it after a first, weaker fix | spikes only where the nine columns under them have rock |
| Icebergs at the bottom of the world | they are built at the generator's sea level (y -2032) | switched off |
| Structures at fixed heights: trial chambers at y -40..-20 in rock shells in mid-air, strongholds and mineshafts in the lowest 100 layers, no way into the End | 4,709 stone bricks and 2,204 planks counted on the world floor, none elsewhere | see "Structures" below |
| Structures start over empty columns of an island's biome (an igloo and a treasure were located over the void) | `/locate` answers with ground at y -2032 | the biome follows the island's rim (24 blocks past it), and the 500 layers under the lowest island are void biome, so a start that falls to the bottom of the world is rejected; `freeze_top_layer` (snow, ice) lost its biome check, which the game makes at the bottom of the chunk |
| Below y 63 the lower half of the sky is black | screenshots at y 0 and y -1500 | the whole sky is drawn in the fog colour (`sky_fog_end_distance` 3) |
| Every chunk pays for all 240 islands; void costs as much as land | thread dumps: 60-80% of the generation in the terrain function; 256 void chunks 21 s | terrain from flat per-layer fields: 256 land chunks 32 s -> 15 s, void 21 s -> 7 s, three stacked tiers (64 chunks) 13 s -> 6-7 s, same heights at every probe |

### Seas, caves, surfaces, sulfur (`tools/build_terrain.py`)

What they are: main README. Tested by the section `terrain` of the `vanilla` phase (`terrain_probes()` in `gen.py`; the
pack with Geophilic's biomes, Fabric API only) and by views in the client script; numbers of run cb6946e, the same in run
e9e0dc8, which passed every check and published the release (cb6946e passed them too, but the report script stumbled over
the new section's labels). The scans
count blocks with `fill ... replace`, column profiles say for every second block whether it is air.

**What Minecraft 26.3 has for sulfur** (from the server jar's data and classes): blocks `sulfur`, `cinnabar` (and their
building variants), `sulfur_spike`, `potent_sulfur`; the biome `minecraft:sulfur_caves` (sulfur cubes, its own surface
rule of sulfur and cinnabar bands from a 3D noise); the features `sulfur_spring` (ten templates
`spring/sulfur_spring_{small,medium,large,extra_large}_N`: 8x11x9 to 16x11x16 blocks of tuff, granite, stone, sulfur,
cinnabar and spikes around a pool, with one potent sulfur block over a magma block - two in the extra large one),
`rooted_sulfur_spring` (grows a spring up to the surface above a sulfur cave, like an azalea above a lush cave),
`sulfur_pool`, `sulfur_spike`, `sulfur_spike_cluster`. There is no geyser block or structure: the geyser is the state
of `potent_sulfur` (`PotentSulfurBlock`, property `potent_sulfur_state`): without a water source above it `dry`; over a
block of `#causes_continuous_geyser_eruptions` (lava source) `continuous`; over `#causes_periodic_geyser_eruptions`
(magma block) `dormant`, and its block entity counts down to `erupting` and back; otherwise `wet` (gas bubbles only).

| | Evidence |
|---|---|
| Geysers | all 25 of `layout/geysers.json`, checked block by block (run 73711d0): the potent sulfur block is at exactly the listed block on all 25 (26 vents: the spawn island's extra large spring has two), a magma block under it, a water source over it, state `dormant` right after generation on every one. Templates now: 1 extra large (S1), 8 large (radius 300 and more), 9 medium, 7 small, all four rotations. The ground around the spring is at the listed height (bare on the desert island C1 on all four sides, 11 blocks out; elsewhere a plant, a snow layer or the spring's tuff stands on it); the one on the spawn island was `erupting` 27 s after its chunks loaded. |
| Geysers where water freezes | L1 (medium), e1 (large), m1 (small), each in fresh chunks: at generation the vent is `dormant` with open water over it and the hidden light block above (before: `dry`, the pool's top was ice from the game's freezing step - a large spring has two blocks of water over its vent and was never dry, the others have one). A block of ice put on the vent by hand, as a world generated before this change has it, melted after 94 s, 27 s and 339 s at the normal random tick speed (a random tick comes every 68 s on average), `dry` -> `dormant` on L1 and m1. Then 2,400 ticks sprinted (`tick sprint`) at `random_tick_speed` 100, which is 80,000 ticks (67 minutes) of frost as far as freezing and melting go: the vent still open and `dormant` on all three, while a control pool put up 18 blocks away under the open sky had frozen on all three. An eruption followed within 30 s of waiting on each. |
| What went wrong on the way | the spring's place was first searched through air only: under a flower, or leaves, that the chunk next door had already grown, no geyser (2 of 25) - the large templates had been taken out for that, wrongly. In deserts, savannas and badlands the pool was ice: the game freezes water by altitude in dry biomes too (also a village's well) - those biomes now get the constant climate as well. The listed positions were where the feature was asked for, not where the block ended up (template and rotation came from the world's seed, the height from the ragged ground: up to 2 blocks off sideways and 4 in height, 8 on k1, where the spring sat on ground higher than listed). |
| Sulfur caves | five pockets scanned (S1, F1, P1, c1, j1; 89x41x89 blocks each): 51,769..67,760 sulfur, 45,143..67,773 cinnabar, 16..148 spikes in four of them, sulfur pools with water in two (one with its potent sulfur block), the biome at the chamber's centre is `minecraft:sulfur_caves` in all five, the chamber is open in four (in F1 a pool or spike stands at the tested block); no sulfur or cinnabar 12 blocks above a pocket. No sulfur ore (`cgs:sulfur_ore` is off in `datapack-mods`; the pack phase's Nether scan lists it with whatever it counts, nothing checks it). |
| Seas | six basins (d2 warm, M2 frozen, N4 cold, D4 lukewarm, K3 ocean, I4 warm): 34,260 to 947,385 blocks of water from the floor to the designed level (8 under the top), water (ice on M2: 50,734 blocks) at the level in the middle and air above it. Above the level over the middle of the sea: 0 in all six. Under the sea floor and under the island (down to 220 blocks below it): 0 in five; **60 under M2** (same number in three runs, source not found - not the sea: nothing moves, see below). Outside the rim (the four corners of the square around the island, three basins): 0. After a block update at the surface and 30 s: 0 under the three basins. On N4's shore ring 673 blocks of water lie above the sea's level: pools of Geophilic's stony shore, not the sea. |
| Sea life | kelp 147..1,213 tops and 396..4,177 stems in the cold, lukewarm and normal seas, seagrass 449..1,342 and tall seagrass 190..562 in all but the frozen one, 2,018 and 2,020 coral blocks in the two warm ones (23 sea pickles in one), clay; floors of sand (warm, lukewarm) or gravel. Animals around a player in the warm sea d5 for 100 s at night (whole mod pack): 20 and 21 tropical fish, 1 and 0 drowned in the two runs; no cod, salmon, pufferfish, squid, dolphin or turtle (see "Open"). |
| Caves | air in a box of 128x128 columns of the body, from 6 blocks under the caves' top level down: S1 3.2%, C1 5.2%, E1 5.3%, T1 4.7%, A1 4.0%, R1 12.9% (H1's box reaches below its underside and does not count); no `cave_air` (the carvers are off). Ores in the same boxes as before (C1: 2,096 coal, 8,150 iron, 2,010 copper, 328 diamond). Nine column profiles per island: caves in 8 of 9 columns of S1 (600 thick), 6 of T1 (347), 4 of R1, 3 of C1, 2 of E1 and A1, 1 of H1; none in the 18 columns of S2 and C2 (96 thick; 157 thick with 45 blocks of relief). Rock between the lowest cave and the underside in those 26 columns: 24 blocks at least (24, 24, 26, 30, 30, ...), so no column opens downwards. Entrances (air on a 6-block grid 22 blocks under the lowest ground, over the middle of the island): 2 on S1 (a circle of 150 blocks), 2 on C1, 3 on T1; on R1 and A1 the grid of this run reached past the rim (an earlier run with the grid over the middle: 3 and 4). |
| Portal rooms | the located `the_isles:stronghold` has its 12 frames and 554 stone bricks (the structure is buried by the game's own terrain adaptation, caves do not cut it). |
| Bands | all seven terracotta colours on J1 (y -575..-496, far below the y -192 where the game's table ends), Jt2, Jt3 and C2; red sand on the low ground of J1 and Jt3. Layer by layer on the three tiers of the mesa stack (61x61 columns, 12 layers each): in all 30 layers that hold blocks the colour of the pattern is the most frequent one (e.g. Jt2 y -333: 286 brown, 50 plain - the plain ones are the vanilla rule's speckles). |
| Snow line | windswept forest A5 (top -90, line -118): 2,781 snow blocks above the line, none below. Windswept hills E4: no ground reaches its line (390) in the sampled 128x128 columns. The peak tiers are snowy biomes and unchanged: 15,448 snow blocks on Pt2 (jagged peaks), 19,315 on Qt3 (snowy slopes). |

Screenshots (`client-NN.png` after `VIEW terrain ...`, run cb6946e: 51-53 the warm sea d5 from above, from its shore and under
water - sand ring, turquoise water, a coral reef with sea grass; 55 the frozen sea M5, frozen over inside a snowy ring; 57-59
C1's caves from inside the rock; 60 C1 from above with one cave mouth some 60 blocks across and the geyser's mound; 62 the
wooded badlands tier Jt2 with its bands and coarse dirt on top; 63 the snow cap on the highest point of A5; 65 the
spring on the spawn plains - yellow sulfur with spikes around a pool, cinnabar and tuff at its foot; 69 the one on the
snowy plains of L1; 70 the chamber of the sulfur caves under the spawn island's geyser, cinnabar and sulfur walls. 61, the
whole mesa stack from 190 blocks away, shows only sky: out of the client's render distance.)

**Mobs in the caves** (run 73711d0, whole mod pack): a player in creative mode in a 3x3x3 room cut into the rock at the caves'
level, 100 blocks from the island's centre, at noon (the surface is lit: what spawns, spawns in the dark), 150 s, mobs
counted in the island's body below the caves' top. C1 (desert): 7 skeletons, 5 creepers, 4 spiders, 8 bats. R1 (swamp):
7 zombies, 4 skeletons, 7 creepers, 3 spiders, 2 bogged, 8 bats (in the whole loaded area 11 zombies, 5 skeletons, 8
creepers, 4 spiders). Nothing to fix: the caves are dark air in the island's own biome, and the game's spawning finds them.

What was not measured: the seas, caves and sulfur of the build with Overrealm and Dwarfhollow
(built and checked statically: every JSON parses, every feature, placed feature, biome, block and biome tag and template
reference resolves - 0 problems in 2,460 files).

**Generation time** per feature (perf phase, same runner, Fabric API only, seconds; polled once a second, so +-1):

| Pack | 256 chunks of land (spawn island) | 256 of void | 64 through three tiers | 64 in a sea basin (d1) |
|---|---|---|---|---|
| before (commit 693f2b4) | 16.2 | 6.9 | 5.9 | 5.9 |
| now | 17.2 | 8.0 | 6.9 | 8.0 |
| now without caves | 16.2 | 7.0 | 6.9 | 8.0 |
| now without the seas' water | 17.2 | 8.0 | 7.0 | 6.9 |
| now without geysers and sulfur caves | 16.2 | 8.0 | 7.0 | 7.9 |
| now with the vanilla surface rule | 17.2 | 8.0 | 6.9 | 7.9 |
| now with Geophilic's biomes | 17.2 | 8.0 | 7.0 | |

So: land +6%, void +16%, tiers +17%, a sea basin +36%. The caves' three noises cost about a second per 256 chunks
wherever they are computed (everywhere: nothing is skipped), the water of a sea about a second per 64 chunks of basin,
the rest is within the second the polling can see. Heap with the land loaded 0.56 to 0.90 GB as before. Three things
cost far more before they were changed, all for the same reason - the game computes these functions for every column
or point of a chunk at once and every branch of a selection with them:

* the surface level the surface rule needs (so that cave floors stay stone) as the real surface of whichever island the
  column is in: +40% on every chunk, void too. Now one height per island.
* the sulfur caves' biome as branches by height inside the biome lookup: +25%. Now a flat mask and a test of the height.
* (earlier, the cave world) aquifers: five times.

### Biome packs (Geophilic 3.7, Overrealm 0.3.1)

How the generator uses them is in the main README. The test builds the pack with both and runs everything on that
build (run 31f9796; the released zips are the vanilla build, which the generator still writes byte for byte as before).

* **Getting them to the runner.** Geophilic is downloaded from Modrinth (`tools/providers.py fetch`, sha256 checked), so
  the test can build with it (`packtest/providers`). Overrealm and Dwarfhollow have no public download and may not be
  redistributed: the workflow does not test them any more. The findings below that involve them come from runs 31f9796
  (pack-test) and 3f2a634 (dwarfhollow), for which the zips were handed to each job encrypted for a key pair that only
  existed in that job (branches `ci-key-*` / `ci-vendor-*`). That put ciphertext of the packs on a public repository,
  which is still an upload of them; the hand-over was taken out again (scripts and workflow step) and the leftover
  branches are to be deleted. With those two packs the pack is now built and checked locally only.
* **Geophilic alone** (run 4a96523, partial: what the workflow can still test, and the fall-back when Overrealm is not
  there - 30 biomes from Geophilic, 18 vanilla). No error or warning from the data packs. Geophilic's desert on C5 (55
  cacti, 61 dead bushes, 71 bone blocks, sandstone), forest on A6 (2,680 logs, 26,304 leaves, 2,101 leaf litter), birch
  forest on f2 (2,595 logs, 1,000 flowers, 6 pumpkins); no snow on any of them, nothing in the open under the twelve
  sampled islands (whole footprints: air only). The run's verdict says FAIL because a partial run skips the sections
  three checks need (build limits, reactor); nothing was published, the release is still the one of run 31f9796.
* **Loading.** No error or warning from the data packs: 0 lines with Fabric API only, the same single mod warning as
  before with the whole mod pack.
* **What grows** (96x96 columns around the centre of an island, from the upper part of the body to 60 above the top;
  `SCAN on-<island>` in the report):

  | Island | Biome, from | Blocks counted |
  |---|---|---|
  | C5 | desert, Overrealm | 174 cactus, 575 bushes, 91 dead bushes, 16 logs (desert trees), 97 bone blocks and 2 chests (its buried ruins), 38,000 granite (boulders), 5,000 coarse dirt |
  | A6 | forest, Overrealm | 10,104 logs, 31,348 leaves, 677 ferns, 779 leaf litter, 1,636 podzol, 107 (mossy) cobblestone, 1 chest |
  | T4 | badlands, Overrealm (on a tier at y -1000) | 1,308 short grass, 73 bushes, sandstone and terracotta bands |
  | d5 | warm ocean, Overrealm (dry basin) | 3,437 logs and 9,661 leaves (palms); no coral, sponge, kelp or sea grass: they need water |
  | M5 | frozen ocean, Overrealm (dry basin) | 8,663 snow layers, 57,523 tuff (spikes), 172 logs, 1 chest |
  | f2 | birch forest, Overrealm | 10,753 logs, 17,611 leaves, 913 flowers, 3,612 short grass, 512 calcite |
  | E5 | taiga, Geophilic | 2,104 logs, 21,298 leaves, 1,245 podzol, 662 ferns, 94 cobblestone (rocks) |
  | H7 | jungle, Geophilic | 6,381 logs, 21,980 leaves, 1,225 short grass, 106 cobblestone |
  | c4 | savanna, Geophilic | 425 logs, 2,330 leaves, 2,514 short grass, 2,523 coarse dirt |
  | Q2 | cherry grove, Geophilic | 1,452 logs, 19,136 leaves, 2,244 flowers, 308 cobblestone, 76 water (its deltas) |

  No snow layer in any biome that rains in vanilla (the report's snow check covers every probed island).
* **Under the islands.** A box 40 to 160 blocks under the bottom of each of those islands: empty in all twelve. The whole
  footprint 40 to 200 blocks below, 20 seconds after generation: only air under eight of ten; 10 and 44 blocks of water
  under M5 and f2 - streams from the game's own springs, which every biome has below y 192, also the vanilla ones - and
  vines, leaves and roots of rim trees under the swamp island n3. Overrealm puts 64 more water springs per chunk into
  low caves (they are meant for flooded ocean caves): on an island they ran out of the underside in several columns
  (first run: water under M5, two columns under d5 in the screenshots), so that feature is left out
  (`drop_features`).
* **Fixed heights.** 63 placements of Overrealm that pick an absolute height (cave vegetation and disks, dungeons, spikes)
  are generated by depth under the surface; its ruins were found that way (bone blocks, chests). Geophilic has none.
* **Structures** as before: the pack's stronghold, villages, trial chambers, ruined portals, outpost, pyramid, wrecks,
  ruins, igloo, hut and trail ruins were located on islands with nothing on the world floor (table in the report).
* **Screenshots** (`client-NN.png` after `VIEW biome ...`: from above, from just over the ground, from the side with the
  void under it) of the twelve islands: Overrealm's desert (banded sand and coarse dirt, cacti, boulders), forest and
  tall birch forest, striped badlands, the frozen basin with tuff spikes; Geophilic's taiga with fallen logs, jungle,
  savanna, cherry grove with bamboo, swamp; the vanilla mangrove swamp. Nothing hangs from a rim or stands under an
  island except the water streams mentioned above.
* **Dry sea basins.** The warm ocean basin d5 is a palm grove: Overrealm plants palms "where no water is above the sea
  floor", which in a dry basin is everywhere. Left as it is (it will sort itself out when the basins hold water); to
  have bare sea floors until then, add `orealm:tree/*` and `orealm:veg_patch/*islands*` to `drop_features`.
* **Generation time**, same runner, Fabric API only (perf phase): 256 chunks of land 15.1 -> 17.2 s, 256 of void 6.9 -> 7.0 s,
  three stacked tiers 6.9 -> 6.9 s (vanilla biomes -> with both packs; on another runner 10.0 / 4.9 / 4.9 -> 10.0 / 4.9 / 3.9).
  36 chunks around the centre of an island took 4 to 8 seconds for every sampled biome.
* **Whole mod pack** (32 mods, client): verdict PASS. Ores per 64x64 columns as before, the mods' included (S1: 1,043 coal,
  1,138 iron, 442 diamond, 1,243 zinc; B1: 1,341 zinc, 1,097 lead; M1: 1,842 uranium); animals and monsters spawn on the
  Geophilic plains of the spawn island (16 zombies, 17 skeletons, 24 creepers in a night).

### Cave world in the spawn island (Dwarfhollow 0.1)

What it is and how it is fitted in: main README. Tested in run 3f2a634 of the `dwarfhollow` branch (see "Getting them to the runner" above). Sections `caves` (server) and `caveviews` (client) of `gen.py`.

* **Loading.** Its 131 configured and 119 placed features, 15 biomes and surface rule are for Minecraft 1.21.5; converted
  by `tools/convert81.py` they load in 26.3 without an error or warning. Two things had to be found by running it: disks
  need a `type` on their rule based state provider, and an offset reaches 16 blocks at most (wider patches take two).
* **Shell.** Twelve columns from above the surface to below the underside (`VPROFILE`, every second block): rock between
  the ground and the first cavern of the cave world 80 to 200 blocks, between the last cavern and the underside 44 to
  308; where the island is thinner than about 120 blocks (five of the columns, towards the rim) there are no caverns.
  Lines outwards at y -60 and -160 (`HPROFILE`): 152 and 30 blocks of rock between the last cavern and the void.
  Under the island (140 layers below the middle): no water, nothing. The blocks of air above the cave world's ceiling
  (y 30..38 under the spawn point) are the trial chambers; the game's cave carvers are off inside the cave world's
  footprint.
* **Biomes** down a column every 40 blocks (`VBIOME`): plains, plains (y 50, 10), then highlands (`orichalc_highlands`,
  `bronze_sanctuary`, `honeycomb_caves`), midlands (`shadow_woods`, `floral_grove`, `dry_midlands`), `black_sea` /
  `ocean` at the bottom, and plains again in the floor shell.
* **Inside** (48x48 columns, three depth bands, `SCAN cave-*`): 5 to 23% of the blocks are open in the middle of the island
  at this seed (the cave world's own noise decides, some regions are mostly rock); grass, mud, moss, sculk, basalt,
  prismarine, deepslate by biome; trees (722 logs, 5,193 leaves in the upper band), giant mushrooms; 1,432 light blocks
  in the upper band (Dwarfhollow lights its caverns with invisible light sources); its ores (upper band, 9 chunks: 2,715
  coal, 2,944 iron, 2,529 copper; lower: diamonds, redstone, gold, lapis).
* **Sinkholes.** All six open from the surface to y -110..-150. SK1: the ramp shows in a column near the wall as slabs
  8 to 16 thick every 36 blocks with 22 to 26 blocks of headroom, down to the cavern at its foot. Water landings SK2 and
  SK3: 1,205 and 2,323 blocks of water on the floor, no snow, 2 and 19 blocks of ice.
* **Seas.** Water where the cave world reaches below y -338: 1,312 and 512 blocks in two 48x48 boxes (y -395..-339) under
  the middle of the island, with air above it; none towards the rim, where the island ends higher up. They are ponds on
  cavern floors rather than seas: at this seed and this depth most of the storey is open space or rock.
* **Mobs**, 90 seconds around a player at the foot of SK1 (whole mod pack): 25 zombies, 15 skeletons, 16 creepers, 11 spiders, 10 bats, 1 enderman, 1 slime; 4 cows, 8 sheep,
  1 pig, 9 chickens, 1 armadillo. No witch, cave spider, glow squid, bogged, stray, drowned or axolotl there. Server
  tick 18.5 ms on average with the client in the cavern (P99 134 ms).
* **Screenshots** (`client-NN.png` after `VIEW cave ...`): the sinkhole from above and from its rim with the ramp winding
  down; at its foot orange honeycomb terraces with birches, bamboo and a giant mushroom; the water landing from above;
  from inside the rock (a spectator sees the caverns around) floating pieces of land with cherry trees in pink fog,
  groves with dark oaks, a deepslate tunnel with lapis at y -320. Without night vision the caverns are dark between
  the lit patches.
* **Time.** Same runner, Fabric API only, seconds for 256 chunks of land inside the spawn island / 256 of void / 64 with
  three tiers: vanilla biomes 15.1 / 6.9 / 6.9, with
  Geophilic and Overrealm 15.2 / 7.0 / 5.9, with the cave world as well 39.4 / 10.0 / 8.0.
  The spawn island is the expensive part: surface rule and features of a decorated cave world in 600 layers of rock.
  What was tried: with the climate noises computed for every point of the world the void took 40% longer (6.9 instead
  of 4.9 s; the game asks for the climate point by point, so they are now behind a test of height and distance);
  a coarser grid for the cave noise changed nothing (6.9 s with 4 and with 8 block cells); aquifers for the seas made
  every chunk five times slower (void 10 -> 51 s), so the water is placed as a feature.
  Heap with the 256 land chunks loaded: about 1.0 to 1.3 GB (0.5 to 1.1 without the cave world).

### Structures

All of this is in the data pack (`tools/build_pack.py`, function `structures`; vanilla files in `tools/vanilla_structure/`).

| Structure | Where it generates now | How |
|---|---|---|
| villages, pillager outpost, trail ruins, abandoned camps | on the island surface, as in vanilla | already follow the terrain; a start within 48 blocks of the bottom of the world is dropped |
| trial chambers | 32..48 blocks under the island surface, cased in rock where they stick out of a thin island | `project_start_to_heightmap` + `start_height` |
| ancient city | 60 blocks under the surface (no island has `deep_dark`, so none generate) | the same |
| ruined portals (all Overworld kinds) | on or half buried in the surface | the `underground` and `in_mountain` setups, which pick a height between the bottom of the world and the surface, became `partly_buried` |
| desert pyramid, jungle temple, swamp hut, igloo, shipwrecks, ocean ruins, buried treasure | on the island surface / basin floor | they take their height from the terrain under them |
| stronghold | off | the code moves it below the generator's sea level, which here has to be the bottom of the world |
| mineshaft, mineshaft (mesa) | off | same call for the normal kind; the mesa kind picks a height between the sea level and the surface |
| ocean monument | off | built at y 39..61 in code |
| woodland mansion | off while no dark forest or pale garden island is 76 or higher (none is) | only generates where the ground is at y 60 or more, in code |
| `the_isles:stronghold` (new) | a sealed stone brick room with the twelve empty End portal frames over lava, 30 blocks under the surface; three in the spawn island, about 530 to 1,000 blocks from the spawn point (found at -544 -208 and 112 560 with the test seed), more further out where a ring position meets an island | jigsaw structure in the vanilla `strongholds` set (rings: distance 12, spread 3, count 9); `#eye_of_ender_located` points to it |

What data cannot do: put a vanilla stronghold, mineshaft or monument inside an island (their heights are in the game's
code), and stop a structure whose start is on an island from reaching past the rim: a pyramid, hut or wreck that
stands within a few blocks of the rim takes the lowest ground under it, and a village house past the rim is built on
its own patch of ground at the level of the island surface. The report lists every located structure with its blocks
counted near the surface, elsewhere in the columns and in the lowest 200 layers.

### Look

* The sky: one colour (`#a4c5ff`, between the vanilla sky and fog colours) in every direction and at every altitude;
  day and night still darken it. The price is the vanilla gradient from sky blue overhead to pale at the horizon.
  The black disc itself is client code (`SkyRenderer.shouldRenderDarkDisc`: camera below y 63 unless the world is a
  superflat one); it is still drawn, the sky fog now covers it completely.
* Clouds: the game has one cloud height per dimension (or per biome, and every biome of the layout occurs at many
  altitudes), so one layer stays at y 192, near the middle of the islands (half of them are above it). It can be moved
  (`CLOUD_HEIGHT` in the generator) or switched off (`cloud_color` with alpha 0), not made to follow islands.
* The darkening near the bottom of the world (client: the lowest 32 layers) and the horizon of non-flat worlds cannot
  be changed by data. Nothing of the layout is that low.

### Performance

Same runner, same seed, Fabric API only (perf phase, `packtest/perf.txt`); seconds until every chunk of the region is
loaded, polled once a second:

| Pack | 256 chunks of land | 256 chunks of void | 64 chunks, 3 stacked tiers | `/locate` that finds nothing | tick P50 with the land loaded |
|---|---|---|---|---|---|
| before (commit 3d88f92) | 22.1 | 16.0 | 9.9 | 16.2 (mansion), 14.2 (jungle temple) | 10.6 ms |
| now | 11.0 | 4.9 | 4.9 | 0.2 (a structure that is off), 8.2 (jungle temple) | 5.1 ms |
| now, terrain only computed in the layers that hold islands (`ISLES_TRIM_NOISE=1`) | 10.0 | 4.9 | 4.9 | 8.2 | 6.3 ms |
| now, 8-block cells (`ISLES_CELL_XZ=8`) | 10.0 | 4.9 | 4.9 | 8.2 | 5.7 ms |

(Run bc71477. Two earlier runs on slower runners: 32.3 / 21.2 / 13.0 before, 15.2 / 7.0 / 6.9 now. In the thread dumps the
terrain function went from 60-80% of the samples to about 40%, what is left is the game's own loop over the 4,064
layers. The P99 tick time is the tick of the `forceload` itself and says nothing.)

The two switches are not used: after the flat fields they gain nothing that can be measured, and the second one makes
the terrain coarser. Heap after a full collection with the 256 land chunks loaded was between 510 and 820 MB in all
variants (the difference between two runs of the same pack is as large as between packs): a loaded chunk still costs
about three times a vanilla one, because of the 254 sections of height.

Left to do, by expected gain (none of it done here):

1. Pre-generate inside a world border (the layout is 8,000 x 8,000 blocks = 250,000 chunks; at the measured 17 to 36
   chunks a second on a 4-core runner that is 2 to 4 hours, once): no generation lag at all afterwards.
2. View distance / simulation distance: the cost of a loaded chunk is the height. View distance 12 -> 8 loads 289
   instead of 625 chunks per player (less than half the memory and light work); simulation distance 6 is enough for
   Create contraptions near the player.
3. Heap: 6 GB for the server with a few players at view distance 12 (the pack test's 5 GB heap ran out with 1,500
   force-loaded chunks); G1 with default settings is fine.
4. World height: every chunk has 254 sections because the world is 4,064 high. Islands use y -1456..1402; a world
   of y -1536..1663 (3,200) would cut memory, light and generation by about a fifth, but moves the build limits and
   needs a new world.
5. C2ME is already in the pack (0.4.2-alpha for 26.3) with its default settings; with the old generator the same 256
   land chunks took 19 s with and without the mods, so it changes little on 4 cores. Its thread count
   (`config/c2me.toml`) is worth a try on the owner's CPU.
6. In the mods, not the pack: `/locate` and explorer maps for structures that can exist but are rare (jungle temple:
   10 s) still block the server thread; that is vanilla behaviour.

### Nether

Built by `tools/build_nether.py` (called from `build_pack.py`); numbers from the `nether` job (every mod, client) and its
vanilla reference (`netherbase`), 4-core runner.

* **Shape.** Same height as the Overworld (y -2032..2031, `logical_height` 4064, ceiling). Twelve cavern layers, each a
  vanilla Nether stretched in height: bottoms at y -2016, -1656, -1336, -1056, -696, -376, -16, 304, 664, 944, 1264, 1624
  (heights 280..408). Between two layers there is only netherrack, about 35 blocks; bedrock exists in the bottom 5 and
  top 5 blocks of the dimension (0 bedrock in every other layer box, 12,286 / 12,352 at the bottom / roof).
  Where a 2D noise is high the rock between layers gives way to the cavern noise - shafts at the same x/z through all
  layers, on ground without lava; the cave carver also runs over the whole height.
* **Lava.** One sea per layer, 39 blocks above the layer bottom (y -1977, -1617, -1297, -1017, -657, -337, 23, 343, 703,
  983, 1303, 1663). They are aquifers: `sea_level` has to be the bottom of the world (the game floods every cave below it),
  and an aquifer's surface can only be at 40n + 23, which is why the layer heights are multiples of 40.
* **Biomes.** The five vanilla Nether biomes, a different map in every layer (the layer at y 0 has the vanilla map).
  The surface rule is the vanilla one per layer, its heights moved with the lava; it is only asked for the blocks under
  a ceiling or a floor (everything else it could answer is netherrack, which the block already is).
* **Scale and portals.** `coordinate_scale` 1: a portal comes out at the same x/y/z, the Nether under the map is as large
  as the map (one constant, `COORDINATE_SCALE`; with the vanilla 8 the map would be 1000 x 1000 blocks of Nether).
  Lowest island (M4, y -1351) -> Nether 1106 -1362 -3137; highest (K6, y 1374) -> Nether -2486 1374 -1285 (71 above that
  layer's lava, probably the game's own obsidian platform); Nether 300 -1257 300 -> spawn island at y 53;
  Nether 2000 1023 -1000 -> the game's platform in the void at the same place. Every arrival stood in a portal on obsidian.
* **Ores, features.** Every Nether feature that picks a height gets the vanilla attempts per chunk in every layer. Per
  64x64 layer box: quartz 670..3,434 (vanilla Nether box 2,667), gold 276..1,151 (971), ancient debris 17..36 (25),
  glowstone 14..161 (50). The sulfur ore of Create: Gunsmithing is switched off (`datapack-mods`): 0 in every layer.
* **Structures.** Bastions and fossils go to a random layer (the grid of bastions/fortresses is 10 chunks instead of 27, so a
  layer has the vanilla number of bastions). Fortresses (y 48..70) and Nether ruined portals (y 32..100) have their
  heights in the game's code: they only exist in the layer at y -16..303, which is placed so that they stand above its
  lava as in vanilla.
* **Mobs.** After 240 s around a player: 81 piglins, 34 hoglins, 17 striders, 11 zombified piglins, 1 ghast in the layer at
  y -16; 34 piglins, 10 hoglins, 10 striders, 3 zombified piglins, 2 ghasts, 2 skeletons, 1 enderman in the layer at y 944.
* **Performance.** 64 chunks: 20.9 s with every mod (38.9 s before, the vanilla Nether 2.8 s), 46.1 s with Fabric API only
  (115.0 s before, vanilla 4.3 s); a first trip through a portal: see "Nether generation speed" below.
* **What data cannot do.** Fortresses and ruined portals in other layers; natural spawning picks a random height of the
  whole column (most attempts are far from the player; it works, the rate against vanilla is not measured); mobs placed at
  chunk generation only appear in the top layer; basalt columns do not rise out of the lava seas; caves carved below a
  lava surface stay dry until a block update.

#### Nether generation speed

Measured by the `netherperf` variants (`packtest/nether-perf.txt`, `nether-phase.sh`; run 469e9eb): one fresh world per
variant, one after the other on the same 4-core runner with nothing else running. Timed: `forceload` of 8 x 8 chunks,
then of 3 x 3 chunks 4,000 blocks away (what a first trip through a portal makes the server thread wait for), asked five
times a second; live objects from the class histogram with the 64 chunks loaded; one thread dump a second. Two runs of
the same variant differ by up to a tenth. The full `nether` job builds the client next to the server: its 64-chunk
time is not comparable (37.4 s in the same run; the 70.5 s of the earlier text was such a number, 34.6..38.9 s here).

| | 64 chunks | 9 chunks elsewhere (portal) | live objects |
|---|---|---|---|
| every mod: vanilla Nether | 2.8 s | 0.9 s | 277 MB |
| every mod: before (commit 693f2b4) | 38.9 s | 12.6 s | 560 MB |
| every mod: now | 20.9 s | 7.0 s | 562 MB |
| Fabric API only: vanilla Nether | 4.3 s | 1.3 s | 169 MB |
| Fabric API only: before | 115.0 s | 59.5 s | 523 MB |
| Fabric API only: now | 46.1 s | 20.5 s | 525 MB |

Where the time went before (thread dumps of the worker threads; Fabric API only / every mod): surface rule 50% / 42%,
3D noise 27% / 13% (C2ME computes it in native code), aquifer 7% / 12%, features 3% / 22%, writing the blocks into the
sections 4% / 5%, light 3% / 0%. What was changed (`tools/build_nether.py`; the blocks are the same - the four probe
columns have the same lava runs as in the run before and 33 of their 48 air counts per layer are identical, the other
15 differ by 1 to 16 blocks (vegetation and vines are not placed identically in two runs of one pack either); the block counts of two layer boxes are equal within what two
runs of one pack differ - ores, glowstone, basalt, blackstone and magma to the block, netherrack within 34 of 750,000):

1. **3D noise once.** The game computes every branch of an `interval_select` for every point, and each of the twelve
   branches held the vanilla function with its own reference to `nether/base_3d_noise` (40 octaves): it was computed
   twelve times per point. Now the layers only select the two fades (floor, ceiling: functions of y and the flat shaft
   noise) and the noise is computed once. Alone: 115.0 -> 75.3 s (Fabric API only), 34.6 -> 26.0 s (every mod).
2. **Surface rule behind its depth conditions.** The rule was asked for every solid block of the column (about 2,800 of
   4,064): twelve height tests, a biome lookup and the vanilla rule down to its last line "netherrack". Everything else
   it can answer needs `under_ceiling`, `under_floor` or `on_floor`; those three are now tested first and the rule
   (`material_rule/nether_layers.json`) only runs behind them. Alone: 115.0 -> 91.0 s, 34.6 -> 29.1 s.
3. **Floor features ask for the biome first.** Nearly every chunk has all five biomes somewhere in its column, so every
   chunk runs every feature and the biome filter at the end threw four of five found floors away; the filter now also
   stands before the search for the floor. 21.8 -> 20.9 s (every mod), 47.0 -> 46.1 s (Fabric API only): within the
   noise of two runs. On a biome border a position can now fail the first of the two filters.

What is left (now, Fabric API only / every mod): surface rule 26% / 31% (the game's loop over every block of the
column and five conditions per solid block), writing the blocks 16% / 6%, aquifer 14% / 22%, 3D noise 13% / 6%,
light 11% / 0%, features 10% / 31%, the other density functions 6% / 3%. Measured and not done:

* `cell_size_y` 16 instead of 8 (`ISLES_NETHER_CELL_Y=16`): 46.1 -> 40.8 s with Fabric API only, with every mod 20.5 ->
  18.2 s in one run and 20.9 -> 21.7 s in the other (nothing that can be told from the noise), and the caverns change shape
  (the block counts of a layer move by a tenth, no glowstone in one of two boxes): the look is not the vanilla one.
* No features at all: 20.5 -> 17.8 s and 20.9 -> 19.3 s in two runs with every mod, 46.1 -> 38.0 s with Fabric API only
  (the twelve layers of ores, vegetation and deltas cost a tenth to a sixth); no cave carver: 20.1 and 23.0 s, 44.5 s
  (nothing). The lava seas themselves cost nothing (`ISLES_NETHER_OFF=aquifer`: 22.8 s, 45.1 s); what costs is that the game, as soon as a world has aquifers, searches the twelve
  nearest aquifer cells for every block that is not solid. Only a Nether without aquifers avoids that, and without them
  there is one lava level for the whole height (`sea_level`).
* Not reachable from a data pack: the loop over 4,064 blocks per column in terrain, surface rule, light and heightmaps;
  the 254 sections per chunk in memory (a loaded chunk is about 5 MB of live objects, the vanilla Nether's 0.3 MB) and
  on disk; the number of chunks a portal generates.

**Fewer layers** (not applied; `ISLES_NETHER_LAYERS`, same total height, same seed and runner):

| Layers | what changes | 64 chunks, every mod | portal (9 chunks) | live objects | 64 chunks, Fabric API only | portal | live objects |
|---|---|---|---|---|---|---|---|
| 12 (the pack) | layers 280..408 high, about 35 blocks of rock between | 20.9 s | 7.0 s | 562 MB | 46.1 s | 20.5 s | 525 MB |
| 8 | taller layers (480..568), same rock between | 19.9 s | 6.8 s | 550 MB | 41.5 s | 19.8 s | 513 MB |
| 6 | taller layers (640..688), same rock between | 19.7 s | 7.3 s | 541 MB | 40.0 s | 18.3 s | 507 MB |
| 6, `ISLES_NETHER_CAVERN=320` | caverns as high as now (320), 320..368 blocks of solid netherrack between them | 18.3 s | 6.4 s | 539 MB | 33.0 s | 16.1 s | 502 MB |

Fewer layers of the same total height hardly help (with every mod the differences are inside the noise of two runs; six
layers with half of the height solid rock gain an eighth, a quarter without the performance mods): the cost is the
height, not the number of layers.

**Portals.** A portal whose other side has no portal yet makes the server thread (every player waits) look at the 33 x 33
columns around the target: up to 3 x 3 chunks are generated completely, with their neighbours for features and light,
and each column is then searched from the top of the dimension to the bottom. That is in the game's code
(`PortalForcer.createPortal`); a data pack cannot make it fewer chunks, only make the chunks faster. The 9 chunks
took 12.6 s before and 7.0 s now with every mod (59.5 -> 20.5 s with Fabric API only) on a server alone. With the test
client (software rendering) on the same four cores, a real first trip through a portal on an island whose Nether did not
exist froze the server thread for 14.8 s (23..30 s before, 41..48 s without the performance mods); the client stayed
connected and arrived in a portal on obsidian.
Where that is too long: generate the Nether around the place first - in the console
`execute in minecraft:the_nether run forceload add <x-32> <z-32> <x+32> <z+32>` (5 x 5 chunks: about 8 to 10 s with
every mod at the rate measured here), then `forceload remove` with the same numbers; the portal tests with a
generated destination arrive without a wait. All Nether under the islands is 98,800 chunks: at the measured 3 chunks a second about 9 hours;
the Nether under one island of radius 100 is 250 chunks, a minute and a half.

### Open

* Create Diesel Generators: a pumpjack needs a pipe down to a block tagged `createdieselgenerators:oil_deposit`
  (bedrock); The Isles has no bedrock. The owner's decision: pumpjacks will pump from oil nodes, in the mod; nothing
  is done about it in the pack. Oil amounts per chunk are there (6 to 8 million mB in plains, desert, savanna,
  badlands and ocean islands).
* A Nether portal lit under an empty column of the Overworld makes a portal with a 4-block platform in the void
  (the Nether of this pack is being built on the `nether` branch).
* Sea animals: cod, salmon, pufferfish, squid, dolphins, nautilus, turtles and the drowned of open oceans do not spawn in
  the basins (their rules compare with the world's sea level, in code); tropical fish and drowned do, by biome tag.
  Icebergs, blue ice and monuments stay off for the same kind of reason. For the mod.
* 60 blocks of water under the frozen basin M2 (none under five other seas): source not found.
* Not done: cave biomes (lush, dripstone) and deepslate inside islands, swamp ponds, a snow line on taiga islands (their
  relief never reaches the vanilla line), geysers on the eight sea-basin mains (flag them in the layout to try: the
  build says it places none on a basin).
* Create Nuclear: a reactor is only assembled or taken apart while a player is online.
* Hypertubes: one tube piece is at most 40 blocks long (`BezierConnection.MAX_DISTANCE`); longer lines need a block
  to carry an accelerator every 40 blocks.
