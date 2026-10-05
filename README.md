# The Isles

A hand-placed floating-island world for Minecraft Java **26.3**, built as a data pack (no mod needed).

- 8,000 × 8,000 world, full 4,064-block height (y −2032 to 2031)
- 240 islands in 33 groups, one biome per island, positions fixed by `layout/islands.json`
- Old-style floating island shapes: ragged rims, tapered undersides, loose chunks
- Stacked mountain tiers (High Peaks, Alpine, Mesa)

![Top-down layout](layout/map-top.png)

## Status

Prototype 0.1: terrain, biomes and ores. Tested in the game by `packtest/` (Minecraft 26.3 with Fabric API alone,
and with the Create mod pack it is made for); the test, its findings and what is still open are in
[`packtest/README.md`](packtest/README.md) and on the `ci-logs` branch.

| Done | Not yet |
|---|---|
| Island terrain from the layout | Water in the sea-basin islands (they generate as dry bowls) |
| One biome per island, tiers switch biome by height; the void biome above and below | Cave world inside the spawn island, and its sinkholes |
| Max world height | Cave systems and deepslate inside islands |
| Ores follow the surface of each island (depth instead of absolute height) | Surface rules that depend on fixed heights (badlands bands below y 63) |
| Rain or snow by biome, not by altitude | A way into the End (no strongholds), oil deposits for Create Diesel Generators (no bedrock) |

## Using it

1. Run `python3 tools/build_pack.py`, or take the zip from a release.
2. Put the pack in the world's `datapacks` folder **before the world is first created**. It replaces the Overworld, so it cannot be added to an existing world.
3. With Create, Create Nuclear and Create: Gunsmithing, add `datapack-mods` (or its zip) the same way: their ores
   then follow the islands too. It does not load without those mods.
4. Biome packs go in the same folder and load above this one. The pack overrides the vanilla biomes that rain
   (temperature and colours, see `tools/build_pack.py`); a biome pack that replaces them has to do the same or
   the islands are snow-covered.
5. Set a world border of 8,000 centred on 0, 0 and pre-generate inside it.

## Editing the layout

`layout/islands.json` is the source of truth. Each island has a position, radius, top and bottom height, and biome. Change it, rerun `tools/build_pack.py`, and `tools/preview.py` draws a quick offline check (it uses stand-in noise, so shapes are only indicative).

## Layout of this repo

| Path | What |
|---|---|
| `layout/` | Island list, maps |
| `tools/build_pack.py` | Generates `datapack/` and `datapack-mods/` from the layout |
| `tools/preview.py` | Offline sanity check |
| `tools/vanilla_*` | Vanilla 26.3 data the generator starts from |
| `datapack/` | Generated pack, committed for convenience |
| `datapack-mods/` | Generated add-on for the mod pack (mod ores), committed for convenience |
| `packtest/` | In-game test on GitHub Actions |
