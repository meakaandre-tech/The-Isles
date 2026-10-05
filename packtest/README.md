# Pack test

Runs The Isles in the real game on GitHub Actions: Minecraft 26.3, Fabric Loader 0.19.5, Java 25.
Nothing here is part of the data pack; `tools/build_pack.py` and `datapack/` do not depend on it.

## Running it

Push to the `pack-test` branch (or start the "Pack test" workflow by hand). The workflow has one job per group of
phases (`vanilla`, `pack`, `perf`; they run side by side, about 45 minutes for everything) and a `report` job:

1. each job rebuilds `datapack/` and `datapack-mods/` from `layout/islands.json` - with the biome packs named in
   `packtest/providers` it also builds `build/the-isles/` and tests that one (see "Biome packs" below) -, zips them and runs `packtest/run.sh`
   with its phases; while it runs, a snapshot of its logs is pushed every 3 minutes to `ci-logs-vanilla`,
   `ci-logs-pack`, `ci-logs-perf`,
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
| `baseline` | the same server without The Isles (vanilla generator) | reference for time and heap |
| `pack` | every mod of `mods.tsv` + both data packs, a real client under Xvfb, then a restart | boot log, ores per island, oil, a Create line / diesel engine / reactor / gun / hypertube across the void, spawn, respawn, mobs, weather, portals, the look of the sky at three altitudes, screenshots |
| `perf` | one fresh world per line of `perf.txt`: the pack built by an older commit (`@commit`) or with generator settings | generation time of the same land / void / stacked-tier regions, heap, tick times, a `/locate` that finds nothing; thread dumps while generating, summed up by step in the report |
| `speed` | servers with subsets of the mods (`speed.txt`) | which mods change the generation time |
| `nether` | Fabric API + The Isles (with `nethermods`: every mod and `datapack-mods`), then a client | the Nether: generation time and heap of 64 chunks, columns through all layers, blocks per layer, bedrock, structures per layer, views and mob counts in two layers, four portals (`nether-phase.sh`, `gen_nether.py`, screenshots `nether-NN.png`, `nether-stacks.txt`) |
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
| `known.txt` | regexes of failures that are known findings; they are listed in the report but do not fail the run |
| `quick` | while iterating: the only sections to run (words used by `on()` in `gen.py`, e.g. `islands-few structures look biomes biomeviews`); delete it for a full run |
| `providers` | ids of `layout/providers.json` the tested pack is built with (`overrealm geophilic`); no file = vanilla biomes |
| `tools/vendor-recv.sh`, `tools/vendor-send.sh` | how a job gets a provider that has no public download: see "Biome packs" |
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

### Biome packs (Geophilic 3.7, Overrealm 0.3.1)

How the generator uses them is in the main README. The test builds the pack with both and runs everything on that
build (run 31f9796; the released zips are the vanilla build, which the generator still writes byte for byte as before).

* **Getting them to the runner.** Geophilic is downloaded from Modrinth (`tools/providers.py fetch`, sha256 checked).
  Overrealm has no public download and may not be redistributed, and this repository is public. So a job makes an RSA
  key pair that only exists in its memory, pushes the public key to the branch `ci-key-<job>` and waits four minutes for
  `ci-vendor-<job>`: the zip encrypted for that key (`vendor-recv.sh`). `vendor-send.sh`, run by whoever has the pack
  while the test runs, answers every new key and deletes those branches afterwards. What is pushed can only be read by a
  job that no longer exists. When nobody answers, the job goes on with what it has (Geophilic) and says so in `build.txt`.
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
  The surface rule is the vanilla one per layer, its heights moved with the lava.
* **Scale and portals.** `coordinate_scale` 1: a portal comes out at the same x/y/z, the Nether under the map is as large
  as the map (one constant, `COORDINATE_SCALE`; with the vanilla 8 the map would be 1000 x 1000 blocks of Nether).
  Lowest island (M4, y -1351) -> Nether 1106 -1362 -3137; highest (K6, y 1374) -> Nether -2486 1374 -1285 (71 above that
  layer's lava, probably the game's own obsidian platform); Nether 300 -1257 300 -> spawn island at y 53;
  Nether 2000 1023 -1000 -> the game's platform in the void at the same place. Every arrival stood in a portal on obsidian.
* **Ores, features.** Every Nether feature that picks a height gets the vanilla attempts per chunk in every layer. Per
  64x64 layer box: quartz 670..3,434 (vanilla Nether box 2,667), gold 276..1,151 (971), ancient debris 17..36 (25),
  glowstone 14..161 (50), Gunsmithing sulfur ore 334..1,447 (`datapack-mods`; 1,515 in the vanilla Nether).
* **Structures.** Bastions and fossils go to a random layer (the grid of bastions/fortresses is 10 chunks instead of 27, so a
  layer has the vanilla number of bastions). Fortresses (y 48..70) and Nether ruined portals (y 32..100) have their
  heights in the game's code: they only exist in the layer at y -16..303, which is placed so that they stand above its
  lava as in vanilla.
* **Mobs.** After 240 s around a player: 81 piglins, 34 hoglins, 17 striders, 11 zombified piglins, 1 ghast in the layer at
  y -16; 34 piglins, 10 hoglins, 10 striders, 3 zombified piglins, 2 ghasts, 2 skeletons, 1 enderman in the layer at y 944.
* **Performance.** 64 chunks: 70.5 s with every mod (157.6 s with Fabric API only, before the feature placement was
  changed) - the vanilla Nether takes 7.2 s. Heap with them loaded 0.8..1.3 GB (vanilla 0.19). What is left is terrain noise
  and the surface rule, both proportional to the height. A portal or teleport into Nether that does not exist yet
  generates about 16 chunks on the server thread: 41..48 s without the performance mods (the client timed out both
  times), 23..30 s with them. Pre-generate the Nether around portals, or use fewer layers (`HEIGHTS`).
* **What data cannot do.** Fortresses and ruined portals in other layers; natural spawning picks a random height of the
  whole column (most attempts are far from the player; it works, the rate against vanilla is not measured); mobs placed at
  chunk generation only appear in the top layer; basalt columns do not rise out of the lava seas; caves carved below a
  lava surface stay dry until a block update.

### Open

* Create Diesel Generators: a pumpjack needs a pipe down to a block tagged `createdieselgenerators:oil_deposit`
  (bedrock); The Isles has no bedrock. The owner's decision: pumpjacks will pump from oil nodes, in the mod; nothing
  is done about it in the pack. Oil amounts per chunk are there (6 to 8 million mB in plains, desert, savanna,
  badlands and ocean islands).
* A Nether portal lit under an empty column of the Overworld makes a portal with a 4-block platform in the void
  (the Nether of this pack is being built on the `nether` branch).
* Create Nuclear: a reactor is only assembled or taken apart while a player is online.
* Hypertubes: one tube piece is at most 40 blocks long (`BezierConnection.MAX_DISTANCE`); longer lines need a block
  to carry an accelerator every 40 blocks.
