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
| `server-only`, `exclude.txt`, `no-mods-datapack`, `publish` | switches: no client; regexes of mod jars to leave out; pack phase without `datapack-mods`; publish the release |

## Things worth knowing

* A chunk generation exception on a worker thread is only "relayed" to the server thread. If that thread is waiting
  for the very chunk (`/forceload add` loads synchronously in 26.3), the server hangs with nothing in the log but
  `Parent chunk missing`. `debugmod` prints the real exception (`PACKTEST delayed crash`).
* 1,500 force-loaded chunks of this height do not fit in a 5 GB heap; the probes drop their tickets per island.
* The headless client needs `SDL_VIDEO_FORCE_EGL=1` (Xvfb has no sRGB GLX visual) and Mesa's EGL packages.
* Screenshots come from software rendering (llvmpipe); frame rates there say nothing about a real GPU.
