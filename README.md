# The Isles

A hand-placed floating-island world for Minecraft Java **26.3**, built as a data pack (no mod needed).

- 8,000 × 8,000 world, full 4,064-block height (y −2032 to 2031)
- 240 islands in 33 groups, one biome per island, positions fixed by `layout/islands.json`
- Old-style floating island shapes: ragged rims, tapered undersides, loose chunks
- Stacked mountain tiers (High Peaks, Alpine, Mesa)

![Top-down layout](layout/map-top.png)

## Status

Prototype 0.1: **terrain and biomes only**, not yet tested in-game.

| Done | Not yet |
|---|---|
| Island terrain from the layout | Water in the sea-basin islands (they generate as dry bowls) |
| One biome per island, tiers switch biome by height | Cave world inside the spawn island, and its sinkholes |
| Max world height | Cave systems, ores and deepslate inside islands at any altitude |
| | Surface rules that depend on fixed heights (snow lines, badlands bands) |

## Using it

1. Run `python3 tools/build_pack.py`, or take the zip from a release.
2. Put the pack in the world's `datapacks` folder **before the world is first created**. It replaces the Overworld, so it cannot be added to an existing world.
3. Biome packs go in the same folder and load above this one.
4. Set a world border of 8,000 centred on 0, 0 and pre-generate inside it.

## Editing the layout

`layout/islands.json` is the source of truth. Each island has a position, radius, top and bottom height, and biome. Change it, rerun `tools/build_pack.py`, and `tools/preview.py` draws a quick offline check (it uses stand-in noise, so shapes are only indicative).

## Layout of this repo

| Path | What |
|---|---|
| `layout/` | Island list, maps |
| `tools/build_pack.py` | Generates `datapack/` from the layout |
| `tools/preview.py` | Offline sanity check |
| `datapack/` | Generated pack, committed for convenience |
