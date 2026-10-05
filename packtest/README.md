# Pack test

Runs The Isles in the real game on GitHub Actions: Minecraft 26.3, Fabric Loader 0.19.5, Java 25.
Nothing here is part of the data pack; `tools/build_pack.py` and `datapack/` do not depend on it.

## Running it

Push to the `pack-test` branch (or start the "Pack test" workflow by hand). The workflow

1. rebuilds `datapack/` and `datapack-mods/` from `layout/islands.json` and zips them,
2. runs `packtest/run.sh`,
3. force-pushes logs, the report and screenshots to the `ci-logs` branch (a snapshot every 3 minutes while it runs),
4. if `packtest/publish` exists and the verdict is PASS, publishes the two zips as release `pack-test-latest`.

`packtest/tools/wait.sh` waits for the run of HEAD and unpacks `ci-logs`; `packtest/tools/sheet.py` makes contact
sheets of the screenshots. Start with `report.txt` (written by `packtest/tools/report.py`) and `verdict.txt`.

## Phases (`packtest/phases`, any of)

| Phase | What runs | What it answers |
|---|---|---|
| `vanilla` | dedicated server, Fabric API + The Isles only | does the world load and generate without errors; islands where the layout says, right biome, empty void, build limits, structures, pre-generation time and heap |
| `baseline` | the same server without The Isles (vanilla generator) | reference for time and heap |
| `pack` | every mod of `mods.tsv` + both data packs, a real client under Xvfb, then a restart | boot log, ores per island, oil, a Create line / diesel engine / reactor / gun / hypertube across the void, spawn, respawn, mobs, weather, portals, screenshots |
| `speed` | servers with subsets of the mods (`speed.txt`) | which mods change the generation time |
| `bisect` | one fresh world per line of `bisect.txt` (island ids) | which island breaks generation |

## Files

| File | |
|---|---|
| `gen.py` | writes the probe data pack (functions `packtest:col`, `biome`, `top`, ...) and every console command file and the client script from the layout; edit the scenarios here |
| `run.sh`, `pack-phase.sh` | start servers and the client, feed the console (`#poll`, `#wait`, `#loc`, `#time`, `#heap`, `#sleep` directives), take screenshots |
| `mods.tsv` | download URL and file name of every mod of the pack |
| `client/` | empty Loom project that only launches the 26.3 Fabric client with `run/mods` |
| `client-options.txt` | extra `options.txt` lines (key bindings must be legacy numbers: `key_key.use:22` is U) |
| `debugmod/`, `debug` | test-only mod, built in the run when the file `debug` exists: prints chunk generation exceptions that the game otherwise swallows (see below) |
| `view-distance` | server view distance and client render distance |
| `known.txt` | regexes of failures that are known findings; they are listed in the report but do not fail the run |
| `server-only`, `exclude.txt`, `no-mods-datapack`, `publish` | switches: no client; regexes of mod jars to leave out; pack phase without `datapack-mods`; publish the release |

## Things worth knowing

* A chunk generation exception on a worker thread is only "relayed" to the server thread. If that thread is waiting
  for the very chunk (`/forceload add` loads synchronously in 26.3), the server hangs with nothing in the log but
  `Parent chunk missing`. `debugmod` prints the real exception (`PACKTEST delayed crash`).
* 1,500 force-loaded chunks of this height do not fit in a 5 GB heap; the probes drop their tickets per island.
* The headless client needs `SDL_VIDEO_FORCE_EGL=1` (Xvfb has no sRGB GLX visual) and Mesa's EGL packages.
* Screenshots come from software rendering (llvmpipe); frame rates there say nothing about a real GPU.

## Findings so far (26.3, October 2026)

Fixed in the generator (each its own commit on `pack-test`):

| Finding | Evidence | Fix |
|---|---|---|
| Chunk generation dies in badlands below y -192; the server hangs | `ArrayIndexOutOfBoundsException` in `MaterialSystem.getBand`, J cluster never loads | the vanilla surface rule only runs 48 blocks deep |
| `eroded_badlands` raises stone pillars from the ground up to y 64..90 | ground at y 74 in the footprint of T4 (top y -1000), y 65 on J2 (top y -460) | the generator uses `badlands` there |
| The whole world is snow-covered, rain falls as snow | snow layer on the spawn plains at y 57; screenshots | rainy biomes are written with a temperature that survives the altitude, colours pinned |
| Ores only in the vanilla height band | zinc, lead, uranium and diamonds only in the spawn island; coal only above y 500 | ore placement by depth under the island surface; `datapack-mods` for the mod ores |
| Ice spikes hang down to y 50 from island rims | screenshot of e3; 322 packed ice blocks under it after a first, weaker fix | spikes only where the nine columns under them have rock |
| Icebergs at the bottom of the world | they are built at the generator's sea level (y -2032) | switched off |

Open (see `known.txt` and the report of the run):

* Structures the game puts at fixed heights or at its sea level: trial chambers at y -40..-20 in a shell of rock
  wherever an island's biome column is (one hangs 280 blocks over I1), strongholds and mineshafts in the lowest 100
  layers of the world (4,709 stone bricks, 2,204 planks counted there, none elsewhere). There is no usable way
  into the End. Limiting the biome to a band around each island removes most of this but makes failed structure
  searches ten times slower (commits "an island's biome only surrounds the island" and its revert).
* Create Diesel Generators: a pumpjack needs a pipe down to a block tagged `createdieselgenerators:oil_deposit`
  (bedrock); The Isles has no bedrock. Oil amounts per chunk are there (6 to 8 million mB in plains, desert, savanna,
  badlands and ocean islands).
* Below y 63 the lower half of the sky is black (the client's horizon is hard-coded for non-flat worlds); clouds
  stay at y 192; a Nether portal lit under an empty column makes a portal with a 4-block platform in the void.
* `/locate` (and explorer maps) for a structure that exists nowhere blocks the server for about 16 s.
* A loaded chunk costs about three times the memory of a vanilla one (4,064 blocks of sections and light);
  empty chunks cost almost as much to generate as land.
