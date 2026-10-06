# The Isles

A hand-placed floating-island world for Minecraft Java **26.3**, built as a data pack (no mod needed).

- 8,000 × 8,000 world, full 4,064-block height (y −2032 to 2031)
- 240 islands in 33 groups, one biome per island, positions fixed by `layout/islands.json`
- Old-style floating island shapes: ragged rims, tapered undersides, loose chunks
- Stacked mountain tiers (High Peaks, Alpine, Mesa)

![Top-down layout](layout/map-top.png)

## Status

Prototype 0.2: terrain, biomes, ores, seas, caves, sulfur geysers. Tested in the game by `packtest/` (Minecraft 26.3 with Fabric API alone,
and with the Create mod pack it is made for); the test, its findings and what is still open are in
[`packtest/README.md`](packtest/README.md) and on the `ci-logs` branch.

| Done | Not yet |
|---|---|
| Island terrain from the layout | |
| One biome per island, tiers switch biome by height | |
| Water in the 33 sea-basin islands, each at its own level, with sea floor, plants, corals, ice on the frozen ones | Cod, salmon, squid, dolphins, turtles and drowned in open water: their spawn rules compare with the world's sea level in the game's code (the bottom of the world here). Tropical fish and drowned spawn through biome tags. Needs the mod. |
| Caves in the 182 main land islands, inside a rock shell, with entrances | Cave biomes (lush, dripstone) and deepslate inside islands |
| Cave world inside the spawn island, and its sinkholes (with Dwarfhollow, see below) | Icebergs and blue ice (built at the world's sea level in code), ocean monuments (y 39..61 in code) |
| Max world height | |
| Ores follow the surface of each island (depth instead of absolute height) | |
| Rain or snow by biome, not by altitude; water no longer freezes in deserts, savannas and badlands | |
| Badlands: red sand, terracotta bands and wooded tops relative to each island, the same bands on every tier of the mesa stack; snow caps on the windswept hills | Swamp ponds (the rule puts water at y 62; on an island's rim it would run off) |
| One sulfur geyser per big island (25) and a pocket of sulfur caves under it | Sulfur nodes (the mod) |
| | A way into the End other than the pack's own portal rooms (vanilla strongholds generate at the bottom of the world), oil deposits for Create Diesel Generators (no bedrock) |
| | Structures the game puts at fixed heights (mineshafts, monuments: off) |

## Using it

1. Run `python3 tools/build_pack.py`, or take the zip from a release.
2. Put the pack in the world's `datapacks` folder **before the world is first created**. It replaces the Overworld, so it cannot be added to an existing world.
3. With Create, Create Nuclear and Create: Gunsmithing, add `datapack-mods` (or its zip) the same way: their ores
   then follow the islands too. It does not load without those mods.
4. Biome packs (Geophilic, Overrealm) are **not** installed next to it: they are built in, see below.
5. Set a world border of 8,000 centred on 0, 0 and pre-generate inside it.

## Biome packs: Geophilic and Overrealm

The released zip has the vanilla biomes. Geophilic and Overrealm replace vanilla biome files; installed on top of
The Isles they would undo what it does to those files (the climate that keeps rain from turning into snow at
altitude) and bring features that pick fixed heights. So the generator takes their files and writes the final biomes
itself, into one pack:

1. Put the packs you downloaded into `vendor/` (zip or unpacked folder, any file name that contains the pack's name).
   `python3 tools/providers.py fetch` downloads the ones with a public address (Geophilic).
2. `python3 tools/build_pack.py` - it prints which pack every biome comes from and writes `build/the-isles.zip`
   (and `build/the-isles-mods.zip`, the same as `datapack-mods`).
3. Use `build/the-isles.zip` **instead of** the released zip, alone: it contains what it needs of the providers
   (their `geophilic:` / `orealm:` features, tags, templates). Do not also install Geophilic or Overrealm.

| Pack | What | Where | Licence |
|---|---|---|---|
| [Geophilic](https://modrinth.com/datapack/geophilic) 3.7, bebebea_loste | biome overhaul (31 vanilla biomes for 26.3) | Modrinth | All Rights Reserved |
| [Overrealm](https://www.patreon.com/posts/overrealm-data-148060790) 0.3.1, kanokarob | "Overworld Makeover" (18 vanilla biomes: forests, desert, badlands, oceans) | the author's Patreon | none in the pack; the author's terms for his packs forbid redistribution, also of modified parts |

Neither may be redistributed. That is why nothing of them is in this repository or in its releases: `vendor/` and
`build/` are ignored by git, and `build/the-isles.zip` is for your own worlds and servers only.

### Which pack a biome comes from

`layout/biome_sources.json`:

```json
{ "order": ["overrealm", "geophilic", "vanilla"], "biomes": {}, "islands": {}, "drop_features": ["orealm:sequence/jellyfish", "orealm:spring/ocean_caves"] }
```

For every vanilla biome of the layout the first pack of `order` that ships that biome for 26.3 is used; `vanilla`
always has it. With Overrealm 0.3.1 and Geophilic 3.7: Overrealm 17 biomes (91 islands), Geophilic 23 (122), vanilla 8
(27). Nothing has to be edited when a pack grows: Overrealm 0.3.1 has no `taiga`, so the six taiga islands are
Geophilic's; drop an Overrealm zip that has `data/minecraft/worldgen/biome/taiga.json` into `vendor/` (remove the
old one or keep it, the last by name wins), run `tools/build_pack.py`, and the table it prints shows `taiga` under
`overrealm`. To decide by hand: `"biomes": {"minecraft:taiga": "geophilic"}` (or `"vanilla"`). Swapping the first two
names of `order` prefers Geophilic wherever both have a biome. A build with other versions than the tested ones
(`layout/providers.json`) says so; it also lists anything of a pack it left out.

A pack can also bring biomes with ids of their own (`orealm:...`). Those are assigned by id, to every island of a layout
biome or to single islands (ids of `layout/islands.json`):

```json
"biomes":  {"minecraft:taiga": "geophilic", "minecraft:meadow": "orealm:some_new_biome"},
"islands": {"A6": "orealm:some_new_biome", "C5": "minecraft:savanna"}
```

Any vanilla biome or biome file of a pack in `vendor/` works; an id nobody has is reported by the build and the island
keeps its biome. Such a biome gets the constant climate, the colours of the vanilla biome with the nearest climate where
it sets none, and it joins the vanilla biome tags of the biomes it replaces (structures, mob rules and the mods' ores
go by tags). Its ground is the default grass and dirt unless it is one of the ids the vanilla surface rule knows:
a pack's own surface rule is part of its noise settings, which The Isles replaces. The island keeps its shape (relief
follows the layout biome). These two keys only act in the build with packs (`build/`), not in the vanilla `datapack/`.
No generator code is involved in any of this. (The old `overrealm` column of the layout said which islands have a biome
that Overrealm ships; the build now works that out and prints it, the column is gone.)

What the build does to a provider's files, for any version:

* the biome file gets The Isles' climate and pinned colours like a vanilla one; its mob spawns, sounds and colours stay,
* placements that pick an absolute height (cave vegetation, cave disks, buried dungeons, springs: 63 in Overrealm
  0.3.1, none in Geophilic) become a depth under the island's surface - height `y` of a vanilla world is `64 - y`
  blocks down, at most 128 - and need rock within 16 blocks under them, so nothing is placed in the open under a
  thin island,
* what the game builds at the generator's sea level (icebergs; here the bottom of the world) and the features listed
  in `drop_features` (Overrealm's 64 springs per chunk for flooded ocean caves) are taken out,
* `eroded_badlands` islands use the pack's `badlands` (see the findings),
* files of a pack that The Isles has to own (dimension, noise settings, structures) are left out and listed.

The sea-basin islands hold water (see "Seas" below), so Overrealm's ocean floors are under water like in its own
world: its jellyfish are back in, its water features find the sea they expect. Its icebergs stay out (the game builds
an iceberg at the world's sea level, whatever the pack asks for).

## Cave world: Dwarfhollow inside the spawn island

With a copy of [Dwarfhollow](https://www.patreon.com/posts/dwarfhollow-135712745) 0.1 (kanokarob, "Cavernous World",
the author's Patreon; no licence in the pack, his terms forbid redistribution) in `vendor/`, `tools/build_pack.py`
also builds its cave world into the spawn island S1 (`tools/build_caves.py`, switched by `"cave_world"` in
`layout/biome_sources.json`). Like the biome packs it only goes into `build/the-isles.zip`. Without the pack the
island is solid rock as before.

Dwarfhollow by itself replaces the Overworld by one cave world of 384 layers (y -64..320): rock full of caverns,
15 biomes in three storeys - highlands, midlands, and seas at the bottom - lit by invisible light blocks, with its own
ores, geodes, trees and ground cover. In The Isles:

| | |
|---|---|
| Where | inside S1 only; the surface stays `plains`, the islets above and the other islands are untouched |
| Heights | not scaled: Dwarfhollow's y is world y + 331. Its ceiling is at y -11, its floor at y -395; highlands down to about y -150, midlands to y -340, seas below (sea level y -337) |
| What is missing where the island is thinner | the island is 600 thick only near the middle and its underside is irregular (y -250..-520 there, rising to the rim); the cave world ends 32 blocks above the underside wherever that is, so the lower storeys only exist towards the middle |
| Shell | at least 56 blocks of rock under the surface (the portal rooms, 30 blocks down, stay in rock), 32 above the underside, 28 in from the rim; the carving fades out over 12 more blocks. The game's cave carvers are off in the cave biomes (they tunnel through anything) |
| Biomes | Dwarfhollow's own biome list and climate noises inside that zone; the pack's ores are filtered by biome, so inside it the vanilla ores are Dwarfhollow's own (coal, copper, iron, gold, redstone, lapis, diamond, emerald at its heights, in its rock) |
| Zinc and lead | the mods add their ore feature to every biome of the Overworld, the cave world's too, but the pack's placement only reaches 128 blocks under the surface (y -73 here) and the mods' ores only replace stone, deepslate and tuff. So `datapack-mods` gives both features a second placement: y -395..-11, only in the cave world's biomes (`#the_isles:cave_world`, empty without Dwarfhollow), 24 zinc and 33 lead attempts per chunk (the density of the other islands), into the rock Dwarfhollow's own ores replace (`#the_isles:cave_stone_ores`, `cave_deepslate_ores`: also amethyst, calcite, packed and blue ice) |
| Entrances | the six sinkholes of `layout/islands.json`: shafts from the surface down to y -110..-150 that open into a cavern. SK1 (radius 60, 140 blocks from the spawn point) has a ramp winding down its wall, one turn per 36 blocks; SK2 and SK3 ("water landing") have water on their floor; SK4-SK6 are sheer drops |
| Seas | water up to Dwarfhollow's sea level (y -338) wherever the cave world reaches that deep. It is placed block by block inside the zone, like a feature: the world's own sea level has to stay at the bottom of the world, and aquifers made every chunk five times slower |
| Left out of Dwarfhollow | its dimension and dimension type, its noise settings (terrain and surface rule are rebuilt here), and its functions, predicates and entity tag: they only move the world spawn and respawning players under its bedrock ceiling |

Its files are for pack format 81 (Minecraft 1.21.5); `tools/convert81.py` converts features, biomes and the surface rule to
the 26.3 formats at build time. One thing is done differently: its features are spread with `count_on_every_layer`,
which walks the whole column for every layer - 2,000 blocks of void under the island for each of 73 features - so they
get random heights inside the cave world and a short search for the floor instead (12 attempts per unit of count).

It costs generation time everywhere, because the game evaluates the cave noise for every chunk of the world, and more
inside S1 (surface rule and features of a decorated cave world); numbers in `packtest/README.md`. To build without it, keep the Dwarfhollow zip out of `vendor/` (or run
`ISLES_PROVIDERS=overrealm,geophilic python3 tools/build_pack.py`): the spawn island is then solid rock and nothing
of this costs anything.

## Seas, caves, surfaces, sulfur (`tools/build_terrain.py`)

**Seas.** Every sea-basin island (`"kind": "basin"`, 33 of them) holds a sea at its own level, 8 blocks under its listed
top. The rim rises to the top within 6 blocks and stays there, a ring 30 blocks wide or more; inside it the floor drops
by up to 0.3 of the island's thickness (19 to 66 blocks; the water is 7 less deep). The water is not the game's sea
(the generator's sea level has to stay at the bottom of the world, or the void floods) and not an aquifer either:
aquifers decide per 16 x 12 x 16 cell, which needs some 40 blocks of rock around a sea to be tight; every block of air
below a possible water level is sampled, also the 2,000 blocks of void under a basin (five times the generation time
when the cave world's seas were tried that way); and a cell takes the lowest level of 13 chunks around it, which mixes
neighbouring basins at different heights. So the sea is filled in by a feature, like the cave world's: in every column
of the sea's biome the air from the water level down to the floor becomes water. What keeps it in: the ring is solid at
the water level all the way round, and only the inside of the ring has the sea's biome - the ring and the margin past
the rim are a shore biome (beach, stony shore or snowy beach), where nothing is filled. The surface rule cannot see
water that a feature places, so the floor is made by a second feature: sand in the warm and lukewarm seas, gravel in
the others; the vanilla sea plants, corals, clay and gravel patches, wrecks, ruins and treasure then generate as in any
ocean. The frozen seas freeze over. The game's own springs are placed by depth and only with rock around them, so no
stream leaves an island.

*Sea animals.* The spawn rules of cod, salmon, pufferfish, squid, dolphins, nautilus, turtles and of drowned in oceans
are code that compares the height with the world's sea level: in a sea 3,000 blocks above it they never pass. Two rules
have a biome tag instead, which the pack sets: tropical fish spawn at any height in the warm and lukewarm seas, drowned
spawn in all seas the way they do in rivers. Everything else needs the mod (one line: the sea level a spawn rule sees).

**Caves.** Every main land island (182; not the tiers, the islets above islands, or the basins) has tunnels and caverns
from three 3D noises in the terrain's own function. They stay inside a shell: they start under the island's lowest
ground (36 blocks under it), end 16 blocks above the underside and 20 in from the rim, and fade out over the last 10
blocks, so islands thinner than about 80 blocks have none and nothing opens to the void. Where a wide 2D noise is high
the cave zone comes up through the ground: those are the entrances. The game's own cave and canyon carvers are off
(they tunnel through undersides). With Dwarfhollow the spawn island keeps its cave world instead; without it, it has
ordinary caves like the others. Cave floors stay stone: the surface rule only runs above the island's "preliminary
surface", which the generator gives the game as one height per island.

**Surfaces.** The vanilla surface rule tests fixed heights in the badlands (red sand below y 74, bands above, forest
floor on wooded badlands above y 97) and draws the terracotta bands from a table that only exists above y -192 (that
was a crash). Both are per island now: on every badlands island the rule's heights are moved so that vanilla y 74 lies
a quarter of the relief above the island's lowest ground, and the bands come from a rule that works at any height with
one pattern for the whole world, so the three tiers of the mesa stack line up. The windswept hills, gravelly hills and
windswept forest get snow blocks on the upper part of their relief (the vanilla snow line is a height above sea level,
too). Peaks, frozen peaks and stony peaks need nothing: their rules go by steepness and noise, not by height.

**Sulfur geysers and sulfur caves.** Minecraft 26.3 has no block called geyser: the geyser is `minecraft:potent_sulfur`
with a water source above it. Over a magma block it erupts periodically (state `dormant` -> `erupting`, driven by its
block entity's countdown), over a lava source continuously, over anything else it only bubbles (`wet`), without water it
is `dry`. The game generates them as "sulfur springs" (`minecraft:sulfur_spring`: ten templates of tuff, granite,
sulfur and cinnabar around a small pool with one potent sulfur block over magma, two in the largest), which grow up to
the surface above the `minecraft:sulfur_caves` biome, and as sulfur pools inside that biome. The Isles places exactly
one spring on every island flagged `"geyser": true` in `layout/islands.json` - the flag was written once for every
island of radius 230 or more that is not a sea basin: the 25 main land islands of the clusters - and none anywhere
else. It stands a quarter of the radius from the island's centre (clear of sinkholes, the spawn point, anything
stacked above, and the rim), on a patch of level ground. Nothing about it depends on the world's seed: each island has
its own template and rotation (the size by the island's radius - extra large on the spawn island, large from radius 300,
medium from 250, small below; which of the templates and which way round by the island's shape seed), the ground is
level at a fixed height for 12 blocks around (no ragged noise, no cave entrance within 32 blocks; under the three
tier stacks, where the only free place is in the outer part of the island, the rim is held 20 blocks away from it)
and the spring is put there without a search. `layout/geysers.json` lists, for every geyser, the block of its potent
sulfur (`x`, `y`, `z`; both blocks of the extra large one under `vents`), the template and rotation, and the ground
it stands on. Under each lies a pocket of sulfur caves
(a cylinder of radius 40, 14 to 46 blocks under the geyser's ground) with the biome's own rock (sulfur and cinnabar),
spikes, pools and mobs, an open chamber in its middle and the ordinary caves running through it;
`layout/sulfur_caves.json` lists them for the mod's sulfur nodes. On the three islands where water freezes (L1, e1,
m1) the game turns the top of the pool to ice when it generates the chunk, and a spring with one block of water over
its vent is then `dry`: there the ice over the vent is made water again right after the game's freezing step, and a
hidden light block (level 13) over it keeps it open - water does not freeze at a block light of 10 or more, ice under
it melts (a world generated before this has the light but still the ice: it melts by itself, in a minute or two).

## Editing the layout

`layout/islands.json` is the source of truth. Each island has a position, radius, top and bottom height, biome, and the
`geyser` flag (true: a sulfur geyser and sulfur caves; `python3 tools/build_terrain.py flags` writes the flag for islands
that have none). `layout/geysers.json` and `layout/sulfur_caves.json` are written by the build. Change it, rerun `tools/build_pack.py`, and `tools/preview.py` draws a quick offline check (it uses stand-in noise, so shapes are only indicative).

## Layout of this repo

| Path | What |
|---|---|
| `layout/` | Island list, maps |
| `layout/providers.json`, `layout/biome_sources.json` | The biome packs the generator can use, and which pack each biome comes from |
| `tools/build_pack.py` | Generates `datapack/` and `datapack-mods/` from the layout, and `build/` with the biome packs of `vendor/` |
| `tools/build_terrain.py` | Seas, caves, island-relative surface rule, geysers and sulfur caves |
| `tools/providers.py` | Finds, downloads and reads the biome packs |
| `tools/preview.py` | Offline sanity check |
| `tools/vanilla_*` | Vanilla 26.3 data the generator starts from |
| `datapack/` | Generated pack (vanilla biomes), committed for convenience |
| `datapack-mods/` | Generated add-on for the mod pack (mod ores), committed for convenience |
| `packtest/` | In-game test on GitHub Actions |
