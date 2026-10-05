# Pack test

Runs The Isles in the real game on GitHub Actions: Minecraft 26.3, Fabric Loader 0.19.5, Java 25.
Nothing here is part of the data pack; `tools/build_pack.py` and `datapack/` do not depend on it.

## Running it

Push to the `pack-test` branch (or start the "Pack test" workflow by hand). The workflow has one job per group of
phases (`vanilla`, `pack`, `perf`; they run side by side, about 45 minutes for everything) and a `report` job:

1. each job rebuilds `datapack/` and `datapack-mods/` from `layout/islands.json`, zips them and runs `packtest/run.sh`
   with its phases; while it runs, a snapshot of its logs is pushed every 3 minutes to `ci-logs-vanilla`,
   `ci-logs-pack`, `ci-logs-perf`,
2. the `report` job puts the logs together, writes `report.txt` and `verdict.txt` (`packtest/tools/report.py`) and
   force-pushes everything, screenshots included, to the `ci-logs` branch,
3. if `packtest/publish` exists and the verdict is PASS, it publishes the two zips as release `pack-test-latest`.

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
| `quick` | while iterating: the only sections to run (words used by `on()` in `gen.py`, e.g. `islands-few structures look`); delete it for a full run |
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
