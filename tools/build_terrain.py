#!/usr/bin/env python3
"""Seas, caves, island-relative surfaces, sulfur geysers and sulfur caves of The Isles (called by tools/build_pack.py).

Seas. The generator's sea level has to stay at the bottom of the world, and the game's aquifers do not fit islands: they
decide per 16 x 12 x 16 cell (a sea would need about 40 blocks of rock around it to be tight), every block of air below
a possible water level is sampled (the void under a basin: the five-fold generation time measured for the cave world),
and a cell takes the lowest level of 13 chunks around it (neighbouring basins at different heights). So a basin is
filled like the cave world's seas, by features: from the island's water level every column of air is filled down to the
sea floor. What keeps it tight is the shape (basin_shape): a rim ring that is solid at the water level all the way
round, and the sea's biome only inside that ring - the ring itself and the margin past the rim are a shore biome, which
has no sea feature.

Caves. Noise caves in the terrain's own function, per layer of islands like everything else: a zone under the island's
lowest ground (cave_top), FLOOR above the underside and SIDE in from the rim; where the 2D entrance noise is high the
zone comes up through the ground.

Surfaces. The vanilla surface rule tests fixed heights for the badlands (63, 74, 97, 256) and builds its terracotta
bands from a table that ends at y -192; both are replaced per island (surface()).

Sulfur. Minecraft 26.3 has the sulfur caves biome and the sulfur spring feature (templates with one or two potent
sulfur blocks over magma under water: the geyser). Every island flagged "geyser" in layout/islands.json gets one spring
at a fixed place and a pocket of sulfur caves under it.
"""
import copy, json, math, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OFF = set(os.environ.get("ISLES_OFF", "").split(","))   # seas, caves, surface, sulfur: left out (for the cost measurements of packtest's perf phase)
BIG_RADIUS = 230          # islands at least this wide are "big" (flag_big writes the flag into the layout)

# ---------------------------------------------------------------------------------------------------------- seas
SEA_BELOW_TOP = 8         # the highest water block is this far under the island's listed top (the rim's crest)
RING, SHORE = 30, 14      # blocks from the rim to where the bowl starts; the sea biome starts SHORE blocks before that
SHORE_BIOME = {"warm_ocean": "beach", "lukewarm_ocean": "beach", "deep_lukewarm_ocean": "beach", "ocean": "beach", "deep_ocean": "beach",
               "cold_ocean": "stony_shore", "deep_cold_ocean": "stony_shore", "frozen_ocean": "snowy_beach", "deep_frozen_ocean": "snowy_beach"}
SAND_FLOOR = {"warm_ocean", "lukewarm_ocean", "deep_lukewarm_ocean"}
def is_basin(i): return i["kind"] == "basin"
def basin_shape(i):
    R, t = i["radius"], i["thickness"]
    e0 = max(0.16, RING / R)
    depth = round(0.3 * t)
    # (slope: the floor reaches its depth within a tenth of the radius, or less steeply than 60 degrees)
    return {"e0": e0, "e_sea": e0 - SHORE / R, "depth": depth, "slope": max(0.1, 0.6 * depth / R), "water": i["y_top"] - SEA_BELOW_TOP}
def layout_biome(i): return i.get("layout_biome", i["biome"])
def shore_biome(i): return SHORE_BIOME.get(layout_biome(i), "beach")

def seas(bp, islands):
    """the sea of every basin -> {biome: [placed features for its first generation step]}"""
    mc, out = bp.mc, {}
    air = mc("matching_block_tag", tag="minecraft:air")
    basins = [i for i in islands if is_basin(i)]
    if "seas" in OFF: return {}
    for i in basins:
        s = basin_shape(i); R = i["radius"] + bp.PAD
        chunks = [[cx * 16, s["water"], cz * 16] for cx in range((i["x"] - R) // 16, (i["x"] + R) // 16 + 1) for cz in range((i["z"] - R) // 16, (i["z"] + R) // 16 + 1)
                  if math.hypot(min(max(i["x"], cx * 16), cx * 16 + 15) - i["x"], min(max(i["z"], cz * 16), cz * 16 + 15) - i["z"]) <= R]
        # a column of water from the water level down while the block above the next one is air: exactly the air of the column
        (bp.OUT / f"data/{bp.NS}/worldgen/placed_feature/sea").mkdir(parents=True, exist_ok=True)
        (bp.OUT / f"data/{bp.NS}/worldgen/placed_feature/sea/{i['key']}.json").write_text(json.dumps({
            "feature": {"type": "minecraft:block_column", "direction": "down", "prioritize_tip": False,
                        "allowed_placement": mc("matching_block_tag", tag="minecraft:air", offset=[0, 1, 0]),
                        "layers": [{"height": s["depth"] + 12, "provider": {"id": "minecraft:water", "properties": {"level": "0"}}}]},
            # (a cuboid is at least two layers high: both are put back on the water level, the second attempt finds water)
            "placement": [mc("fixed_placement", positions=chunks), mc("cuboid", xz_size=15, y_size=1), mc("height_range", height={"absolute": s["water"]}),
                          mc("block_predicate_filter", predicate=air), mc("biome")]}, separators=(",", ":")) + "\n")
        out.setdefault(i["biome"], []).append(bp.ref(f"sea/{i['key']}"))
    # the sea floor: the surface rule cannot know about water that features place, so what it made of the floor (grass,
    # dirt) becomes what the vanilla rule gives under water: sand in the warm seas, gravel in the others
    for name, block in (("sand", "minecraft:sand"), ("gravel", "minecraft:gravel")):
        bp.write(f"data/{bp.NS}/worldgen/placed_feature/sea_floor_{name}.json", {
            "feature": {"type": "minecraft:block_column", "direction": "down", "prioritize_tip": False,
                        "allowed_placement": mc("matching_blocks", blocks=["minecraft:grass_block", "minecraft:dirt"], offset=[0, 1, 0]),
                        "layers": [{"height": 4, "provider": {"id": block}}]},
            "placement": [mc("cuboid", xz_size=15, y_size=1), mc("heightmap", heightmap="OCEAN_FLOOR_WG"),
                          mc("block_predicate_filter", predicate=mc("matching_fluids", fluids="minecraft:water")),
                          mc("offset", x=0, y=-1, z=0),
                          mc("block_predicate_filter", predicate=mc("matching_blocks", blocks=["minecraft:grass_block", "minecraft:dirt"])), mc("biome")]})
    for i in basins:
        f = bp.ref("sea_floor_sand" if layout_biome(i) in SAND_FLOOR else "sea_floor_gravel")
        if f not in out[i["biome"]]: out[i["biome"]].append(f)
    # Fish. The spawn rules of cod, salmon, squid, dolphins, nautilus, turtles and of drowned in oceans compare the height
    # with the world's sea level (code), which is the bottom of the world: they cannot spawn in a basin. Two rules have a
    # biome tag instead: tropical fish at any height, and drowned as in rivers.
    seas_ = sorted({bp.bid(i["biome"]) for i in basins})
    bp.write("data/minecraft/tags/worldgen/biome/allows_tropical_fish_spawns_at_any_height.json",
             {"values": sorted({bp.bid(i["biome"]) for i in basins if layout_biome(i) in SAND_FLOOR})})
    bp.write("data/minecraft/tags/worldgen/biome/more_frequent_drowned_spawns.json", {"values": seas_})
    print(f"seas: {len(basins)} basins, water up to {SEA_BELOW_TOP} under the top, " + ", ".join(f"{b.split(':')[1]} {len(v) - 1}" for b, v in sorted((bp.bid(k), v) for k, v in out.items())))
    return out

# ---------------------------------------------------------------------------------------------------------- caves
FLOOR, SIDE, FADE = 16, 20, 10.0     # rock above the underside, in from the rim; the carving fades out over FADE blocks
TUNNEL, CAVERN = 0.085, 0.6         # tunnels where two noises are both this close to 0, caverns where a third is above this
ENTRANCE = 0.68                      # the caves come up through the ground where the entrance noise is above this
def surface_floor(bp, i):
    """The surface rule runs above this height in the island's columns (the router's chunk_surface_level; the rule starts
    about 5 blocks lower): 24 blocks under the lowest ground the island's relief can have. One number per island: the game
    computes the level for 256 columns of every chunk at once and nothing is skipped, so anything that follows the real
    surface (a sum over all islands) costs every chunk, void included - measured: 40% more generation time."""
    low = i["y_top"] - (basin_shape(i)["depth"] if is_basin(i) else min(bp.RELIEF.get(layout_biome(i), bp.DEFAULT_RELIEF), 0.5 * i["thickness"]))
    return round(low - 24)
def cave_top(bp, i):
    """the caves of an island start under this height (and 12 blocks under the ground where that is lower): below the layers
    the surface rule works on, so cave floors stay stone"""
    return surface_floor(bp, i) - 12
def has_caves(i, nocave=()): return "caves" not in OFF and i["layer"] == "main" and not is_basin(i) and i["id"] not in nocave
def cave_noise(bp):
    """-> the name of the cave density (below 0: open), shared by all layers"""
    for n, octave in (("hollow_a", -6), ("hollow_b", -6), ("hollow_c", -6), ("entrance", -6)):
        bp.write(f"data/{bp.NS}/worldgen/noise/{n}.json", {"base_octave": octave, "octave_count": 1})
    n3 = lambda n, y: bp.mc("noise", noise=bp.ref(n), xz_scale=1.0, y_scale=y)
    tunnel = bp.mul(bp.sub(bp.dmax(bp.mc("abs", input=n3("hollow_a", 1.6)), bp.mc("abs", input=n3("hollow_b", 1.6))), TUNNEL), 10.0)
    cavern = bp.mul(bp.sub(CAVERN, n3("hollow_c", 2.0)), 6.0)
    bp.write(f"data/{bp.NS}/worldgen/density_function/hollow/noise.json", bp.mc("cache", input=bp.clamp(bp.dmin(tunnel, cavern), -1.5, 1.5)))
    bp.write(f"data/{bp.NS}/worldgen/density_function/hollow/entrance.json",
             bp.mc("cache", input=bp.flat(bp.clamp(bp.mul(bp.sub(bp.mc("noise", noise=bp.ref("entrance"), xz_scale=1.0, y_scale=0.0), ENTRANCE), 8.0), 0, 1))))
    return bp.ref("hollow/noise")

def springs(bp):
    """The game's water and lava springs pick a height of the whole world and open wherever one side of the rock is free: in
    an island's underside or rim that is a stream into the void (water was counted under M5 and f2). Here they are placed by
    depth under the surface and only with rock 10 blocks to every side and 10 and 16 blocks below - in cave walls well
    inside the island."""
    mc = bp.mc
    rock = mc("block_predicate_filter", predicate=mc("all_of", predicates=[
        mc("matching_block_tag", tag="minecraft:base_stone_overworld", offset=o) for o in ([10, 0, 0], [-10, 0, 0], [0, 0, 10], [0, 0, -10], [0, -10, 0], [0, -16, 0])]))
    for name, feature, count, d0, d1 in (("spring_water", "minecraft:spring_water", 12, 8, 128), ("spring_lava", "minecraft:spring_lava_overworld", 3, 40, 128)):
        bp.write(f"data/minecraft/worldgen/placed_feature/{name}.json", {"feature": feature, "placement":
                 [mc("count", count=count), mc("in_square")] + bp.depth_mods(d0, d1) + [rock, mc("biome")]})

def geodes(bp):
    """The game puts amethyst geodes at a height of the whole world below y 30, wherever at most one of a few points around
    the centre is air or water: only the islands below y 30 had any, and there at any height of the body - one under the sea
    floor of the frozen basin M2 was open to the sea and full of water (the 60 blocks of water the pack test counted under
    that floor), one near an underside would break through it. Here they are placed like the ores, 24 to 128 blocks under
    the surface (the sea floor in a basin), and only with rock 12 blocks to every side, above and below (a geode is up to
    9 blocks in radius), in every island that is thick enough."""
    mc = bp.mc
    rock = mc("block_predicate_filter", predicate=mc("all_of", predicates=[
        mc("matching_block_tag", tag="minecraft:base_stone_overworld", offset=o) for o in ([12, 0, 0], [-12, 0, 0], [0, 0, 12], [0, 0, -12], [0, 12, 0], [0, -12, 0], [0, -16, 0])]))
    bp.write("data/minecraft/worldgen/placed_feature/amethyst_geode.json", {"feature": "minecraft:amethyst_geode", "placement":
             [mc("rarity_filter", chance=24), mc("in_square")] + bp.depth_mods(24, 128) + [rock, mc("biome")]})

# ---------------------------------------------------------------------------------------------------------- sulfur
POCKET_R, POCKET_TOP, POCKET_BOTTOM = 40, 14, 46     # the sulfur caves under a geyser: radius, and depth under the geyser's ground
CHAMBER_R, CHAMBER_H = 12, 5                         # the cavern in the middle of the pocket (always open)
WARMTH = 13                                          # light over a geyser's pool where water freezes (see sulfur)
PAD_R, PAD_FADE = 12, 8                              # the ground is level this far around a geyser, and comes back to the island's relief over the fade
CLEAR = PAD_R + PAD_FADE                             # nothing else within this distance of a geyser: rim, cave entrance
# The vanilla spring templates (minecraft:spring/<name>, 26.3): size x/y/z and their potent sulfur blocks (x, y, z in the
# template, water blocks above). The template feature centres the template on its position (x and z minus half the size)
# and the spring feature puts it 7 blocks down: the layers 0..6 are in the ground, the pool's surface is the ground's top block.
SPRINGS = {"small": {"sulfur_spring_small_1": ((8, 11, 9), [(3, 6, 4, 1)]), "sulfur_spring_small_2": ((9, 11, 8), [(4, 5, 4, 1)]),
                     "sulfur_spring_small_3": ((9, 11, 9), [(4, 5, 5, 1)]), "sulfur_spring_small_4": ((9, 11, 9), [(4, 5, 3, 1)])},
           "medium": {"sulfur_spring_medium_1": ((11, 11, 11), [(4, 5, 7, 1)]), "sulfur_spring_medium_2": ((12, 11, 11), [(6, 5, 5, 1)]),
                      "sulfur_spring_medium_3": ((12, 11, 12), [(6, 5, 6, 1)])},
           "large": {"sulfur_spring_large_1": ((13, 11, 12), [(5, 4, 5, 2)]), "sulfur_spring_large_2": ((12, 11, 13), [(5, 4, 7, 2)])},
           "extra_large": {"sulfur_spring_extra_large_1": ((16, 11, 16), [(6, 4, 6, 2), (10, 4, 8, 2)])}}
GEYSER_SIZES = (("extra_large", 1000), ("large", 300), ("medium", 250), ("small", 0))   # the size of the spring by the island's radius (at least)
ROTATIONS = ("none", "clockwise_90", "180", "counterclockwise_90")
SPRING_DEPTH = 7
def flag_big(layout):
    """writes "geyser": true/false into every island of the layout (once; the owner edits the flags afterwards)"""
    for i in layout["islands"]:
        i.setdefault("geyser", i["radius"] >= BIG_RADIUS and not is_basin(i))
def spring_of(i):
    """which spring an island gets: the size by its radius, template and rotation by its shape seed -> (size, template, rotation)"""
    size = next(name for name, r in GEYSER_SIZES if i["radius"] >= r)
    names = sorted(SPRINGS[size])
    return size, names[i["shape_seed"] % len(names)], ROTATIONS[(i["shape_seed"] // 7) % 4]
def vents(g):
    """the potent sulfur blocks of the spring at g -> [(x, y, z, water blocks above)] (the rotation as the game's template feature does it)"""
    (sx, sy, sz), potent = SPRINGS[g["size"]][g["template"]]
    out = []
    for lx, ly, lz, wa in potent:
        dx, dz = {"none": (lx - sx // 2, lz - sz // 2), "clockwise_90": (sz // 2 - lz, lx - sx // 2),
                  "180": (sx // 2 - lx, sz // 2 - lz), "counterclockwise_90": (lz - sz // 2, sx // 2 - lx)}[g["rotation"]]
        out.append((g["x"] + dx, g["y"] - SPRING_DEPTH + ly, g["z"] + dz, wa))
    return out
def rim_margin(i, x, z):
    """the island's edge term (1 at the centre, 0 at the rim) CLEAR blocks further out than x/z, with the rim drawn in as far as the
    edge noise can (see build_pack.island_fields): positive = the level ground around a geyser there cannot reach the rim"""
    R = i["radius"]; shrink = max(0.05, min(0.2, 40 / R + 0.04))
    return 1 - (math.hypot(x - i["x"], z - i["z"]) + CLEAR) / R - 2 * shrink
def geyser(bp, i, layout, islands):
    """the place of an island's geyser -> {x, y, z, size, template, rotation} (y: the ground there, the first free block) or None"""
    if not i.get("geyser") or is_basin(i) or "sulfur" in OFF: return None
    R = i["radius"]; amp = min(bp.RELIEF.get(layout_biome(i), bp.DEFAULT_RELIEF), 0.5 * i["thickness"])
    a = i["shape_seed"] % 360
    size, template, rotation = spring_of(i)
    # a quarter of the radius from the centre, turned (then moved outwards) until it is clear of the sinkholes, of the spawn
    # point, of every island above or below (a tier, an islet) and of the rim; the place furthest from the rim when none is
    best = None
    for far in (0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.62):
        for turn in range(20):
            x = round(i["x"] + far * R * math.cos(math.radians(a + 37 * turn))); z = round(i["z"] + far * R * math.sin(math.radians(a + 37 * turn)))
            if all(math.hypot(x - s["x"], z - s["z"]) > s["radius"] + 80 for s in layout.get("sinkholes", [])) and math.hypot(x, z) > 150 \
               and all(j is i or math.hypot(x - j["x"], z - j["z"]) > j["radius"] + 24 for j in islands):
                m = rim_margin(i, x, z)
                if best is None or m > best[0] + 1e-9: best = (m, x, z)
                if m >= 0.05: break
        if best and best[0] >= 0.05: break
    if best is None: print(f"WARNING: no place for a geyser on {i['id']}"); return None
    g = {"x": best[1], "y": i["y_top"] - round(0.6 * amp) - 2, "z": best[2], "size": size, "template": template, "rotation": rotation}
    if best[0] < 0.05:   # (under a stack of tiers there is no better place: the rim is held out around the geyser, see build_pack.island_fields)
        g["hold"] = True; print(f"geyser of {i['id']}: {best[0]:.2f} from the rim at the edge noise's worst, the rim is held {CLEAR} blocks away from it")
    return g
def pocket(g): return {"x": g["x"], "z": g["z"], "radius": POCKET_R, "y_min": g["y"] - POCKET_BOTTOM, "y_max": g["y"] - POCKET_TOP,
                       "chamber": {"x": g["x"], "y": g["y"] - (POCKET_TOP + POCKET_BOTTOM) // 2, "z": g["z"], "radius": CHAMBER_R}}

def sulfur(bp, islands, layout, sea_biomes=()):
    """geyser and sulfur cave files -> (the sulfur caves biome file or None, the surface rule for the pockets or None)"""
    mc = bp.mc
    sites = [(i, i.get("geyser_at")) for i in islands]
    sites = [(i, g) for i, g in sites if g]
    for i in islands:
        if i.get("geyser") and is_basin(i): print(f"WARNING: {i['id']} is flagged for a geyser but is a sea basin (no dry ground): none placed")
    if bp.OUT == ROOT / "datapack" and not OFF - {""}:   # (the layout files are written by the build of the public pack)
        note = ("generated by tools/build_pack.py from the \"geyser\" flags of islands.json. x/y/z: the potent sulfur block of the geyser (the block "
                "that erupts; a magma block under it, water over it), the same block in every world; vents: every potent sulfur block of the spring (two in "
                "an extra large one, the first is x/y/z); ground: where the spring stands (y: the first free block of the level ground around it); "
                "template, rotation: the vanilla minecraft:spring/ template placed there")
        rows = [{"island": i["id"], **dict(zip("xyz", vents(g)[0][:3])), "vents": [list(v[:3]) for v in vents(g)], "size": g["size"],
                 "template": g["template"], "rotation": g["rotation"], "ground": {k: g[k] for k in "xyz"}} for i, g in sites]
        (ROOT / "layout" / "geysers.json").write_text('{\n "note": ' + json.dumps(note) + ',\n "geysers": [\n' + ",\n".join("  " + json.dumps(r) for r in rows) + "\n ]\n}\n")
        (ROOT / "layout" / "sulfur_caves.json").write_text(json.dumps({
            "note": "generated by tools/build_pack.py: one pocket of minecraft:sulfur_caves under every geyser (a cylinder), with an open chamber in its middle",
            "sulfur_caves": [{"island": i["id"], **pocket(g)} for i, g in sites]}, indent=1) + "\n")
    if not sites: return None, None
    air = mc("matching_block_tag", tag="minecraft:air")
    # The geyser: a vanilla sulfur spring at the fixed place. The vanilla feature picks one of ten templates and one of four
    # rotations with the world's seed and is put on whatever ground it finds; here every island has its template and its
    # rotation (spring_of), the ground around the place is level at a fixed height (build_pack.island_fields; no ragged
    # noise, no cave entrance there) and the spring is placed at that height without a search: the potent sulfur block is at
    # the same block in every world, layout/geysers.json lists it.
    spring = json.loads((HERE / "vanilla_feature" / "sulfur_spring.json").read_text())
    assert spring["type"] == "minecraft:weighted_random_selector"
    by_size = {}
    for e in spring["features"]:
        seq = e["data"]["feature"]; t = seq["features"][-1]["feature"]
        assert seq["type"] == "minecraft:sequence" and t["type"] == "minecraft:template" and seq["features"][-1]["placement"] == [mc("offset", x=0, y=-SPRING_DEPTH, z=0)]
        size = next(k for k in SPRINGS if all(x["data"]["id"].split("/")[-1] in SPRINGS[k] for x in t["templates"]))
        assert len(t["templates"]) == len(SPRINGS[size]); by_size[size] = seq
    refs = []
    for i, g in sites:
        name = f"geyser/{g['template'].replace('sulfur_spring_', '')}_{g['rotation']}"
        seq = copy.deepcopy(by_size[g["size"]])
        seq["features"][-1]["feature"]["templates"] = [{"data": {"id": f"minecraft:spring/{g['template']}", "rotations": [g["rotation"]]}, "weight": 1}]
        bp.write(f"data/{bp.NS}/worldgen/feature/{name}.json", seq)
        bp.write(f"data/{bp.NS}/worldgen/placed_feature/geyser/{i['key']}.json", {"feature": bp.ref(name), "placement": [
            mc("fixed_placement", positions=[[g["x"], g["y"], g["z"]]])]})
        refs.append(bp.ref(f"geyser/{i['key']}"))
    # Where water freezes (snowy plains, peaks) the top of the spring's pool turns to ice at generation, and a spring with one
    # block of water over its potent sulfur is then "dry". Two features at the exact block over every vent of those springs:
    # after the game's freezing step the ice there is water again (geyser_thaw), and a light block (invisible, level 13) over
    # it keeps it open - water does not freeze at a block light of 10 or more, and ice next to it melts.
    cold = [v for i, g in sites if bp.vanilla_biome(layout_biome(i))["temperature"] < 0.15 for v in vents(g)]
    if cold:
        bp.write(f"data/{bp.NS}/worldgen/placed_feature/geyser_warmth.json", {
            "feature": {"type": "minecraft:simple_block", "to_place": {"id": "minecraft:light", "properties": {"level": str(WARMTH), "waterlogged": "false"}}},
            "placement": [mc("fixed_placement", positions=[[x, y + wa + 1, z] for x, y, z, wa in cold]), mc("block_predicate_filter", predicate=air)]})
        bp.write(f"data/{bp.NS}/worldgen/placed_feature/geyser_thaw.json", {
            "feature": {"type": "minecraft:simple_block", "to_place": {"id": "minecraft:water", "properties": {"level": "0"}}},
            "placement": [mc("fixed_placement", positions=[[x, y + wa, z] for x, y, z, wa in cold]),
                          mc("block_predicate_filter", predicate=mc("matching_blocks", blocks="minecraft:ice"))]})
    # the vanilla features of the biome pick heights of the whole world: here a depth under the island's surface (the pockets
    # lie POCKET_TOP..POCKET_BOTTOM under it), with the vanilla attempts scaled to that height
    src = HERE.parent / "tools"
    depth = lambda: bp.depth_mods(POCKET_TOP - 6, POCKET_BOTTOM + 8)
    def placed(name, count, tail):
        bp.write(f"data/minecraft/worldgen/placed_feature/{name}.json", {"feature": f"minecraft:{name}", "placement":
                 [mc("count", count=count), mc("in_square")] + depth() + tail + [mc("biome")]})
    placed("sulfur_pool", 48, [mc("block_predicate_filter", predicate=mc("solid")),
           mc("environment_scan", direction_of_search="up", max_steps=32, target_condition=air), mc("offset", x=0, y=-1, z=0),
           mc("block_predicate_filter", predicate=mc("matching_blocks", blocks="minecraft:sulfur"))])
    placed("sulfur_spike_cluster", mc("uniform", min_inclusive=10, max_inclusive=20), [])
    placed("sulfur_spike", mc("uniform", min_inclusive=40, max_inclusive=56), [mc("count", count=mc("uniform", min_inclusive=1, max_inclusive=5)),
           mc("offset", x=mc("clamped_normal", deviation=3.0, max_inclusive=10, mean=0.0, min_inclusive=-10),
              y=mc("clamped_normal", deviation=0.6, max_inclusive=2, mean=0.0, min_inclusive=-2),
              z=mc("clamped_normal", deviation=3.0, max_inclusive=10, mean=0.0, min_inclusive=-10))])
    biome = json.loads((HERE / "vanilla_biome" / "sulfur_caves.json").read_text())
    # one geyser per big island: the springs the biome grows up to the surface by itself (rooted_sulfur_spring) are replaced by the fixed ones
    biome["features"] = [[x for f in step for x in (refs + ([bp.ref("geyser_warmth")] if cold else []) if f == "minecraft:rooted_sulfur_spring" else [f])]
                         for step in biome["features"]]
    assert sum(r in step for step in biome["features"] for r in refs) == len(refs)
    if cold:   # (after freeze_top_layer, in its step)
        step = next(s for s in biome["features"] if "minecraft:freeze_top_layer" in s); step.insert(step.index("minecraft:freeze_top_layer") + 1, bp.ref("geyser_thaw"))
    biome["carvers"] = []
    # the surface rule of the biome (sulfur and cinnabar in bands of a 3D noise) for every block of a pocket; heights first
    lo, hi = min(g["y"] for i, g in sites) - POCKET_BOTTOM - 8, max(g["y"] for i, g in sites) - POCKET_TOP + 8
    above = lambda y: {"type": "minecraft:y_above", "anchor": {"absolute": y}, "surface_depth_multiplier": 0, "add_stone_depth": False}
    cond = lambda c, then: {"type": "minecraft:condition", "if_true": c, "then_run": then}
    rule = cond(above(lo), cond({"type": "minecraft:not", "invert": above(hi)},
                cond({"type": "minecraft:biome", "biome_is": "minecraft:sulfur_caves"}, "minecraft:overworld/biome_surface/sulfur_caves")))
    sizes = {k: sum(1 for i, g in sites if g["size"] == k) for k in SPRINGS}
    print(f"sulfur: {len(sites)} geysers (islands of radius {BIG_RADIUS} or more that are not sea basins: " + ", ".join(f"{n} {k}" for k, n in sizes.items() if n)
          + f"; {len(cold)} vents kept open in freezing biomes), a pocket of sulfur caves {POCKET_TOP}..{POCKET_BOTTOM} blocks under each")
    return biome, rule

# ---------------------------------------------------------------------------------------------------------- surfaces
BADLANDS = ("badlands", "eroded_badlands", "wooded_badlands")
SNOW_CAPS = {"windswept_hills": 0.48, "windswept_gravelly_hills": 0.48, "windswept_forest": 0.4}   # snow on this upper share of the relief
BAND_PERIOD = ["terracotta"] * 5 + ["orange_terracotta"] * 3 + ["terracotta"] * 2 + ["yellow_terracotta"] * 2 + ["terracotta"] * 4 + ["brown_terracotta"] * 2 + \
              ["orange_terracotta"] * 4 + ["terracotta"] * 3 + ["red_terracotta"] * 2 + ["terracotta"] * 2 + ["white_terracotta", "light_gray_terracotta", "white_terracotta"] + \
              ["terracotta"] * 4 + ["orange_terracotta"] * 2 + ["yellow_terracotta"] + ["terracotta"] * 5 + ["red_terracotta"] + ["orange_terracotta"] * 3 + \
              ["terracotta"] * 3 + ["brown_terracotta"] * 3 + ["terracotta"] * 4 + ["light_gray_terracotta"] + ["orange_terracotta"] * 2 + ["terracotta"] * 3
def relief(bp, i): return min(bp.RELIEF.get(layout_biome(i), bp.DEFAULT_RELIEF), 0.5 * i["thickness"])
def y_groups(bp, members):
    """the height ranges of the islands in members, cut apart where they overlap -> [(lo, hi, island)], lowest first"""
    out = []
    for i in sorted(members, key=lambda i: i["y_top"]):
        lo, hi = i["y_top"] - round(relief(bp, i)) - 14 - bp.SURFACE_RULE_DEPTH, i["y_top"] + 12
        if out and lo < out[-1][1]:
            mid = (lo + out[-1][1]) // 2; out[-1] = (out[-1][0], mid, out[-1][2]); lo = mid
        if hi > lo: out.append((lo, hi, i))
    return out
def surface(bp, islands):
    """The vanilla surface rule (tools/vanilla_material_rule/surface.json) with its fixed heights made relative to the islands.

    The rule has no way to ask which island a block belongs to, only for the biome and the height. So every island of a biome
    gets the range of heights of its own surface, and inside that range the rule's heights are moved to that island: vanilla
    y 74 (where the badlands turn from red sand to banded terracotta) is a quarter of the relief above the island's lowest
    ground. The terracotta bands themselves come from a table of the game that is only valid above y -192 (the crash this
    pack once had); they are replaced by a rule with the same kind of bands at any height - one pattern for the whole world,
    so the tiers of a stack line up. Snow line: the windswept hills, which the game caps with snow above y 120 or so, get
    snow blocks on the upper part of their relief."""
    if "surface" in OFF: return
    rule = json.loads((HERE / "vanilla_material_rule" / "surface.json").read_text())
    above = lambda y, sd=0, stone=False: {"type": "minecraft:y_above", "anchor": {"absolute": y}, "surface_depth_multiplier": sd, "add_stone_depth": stone}
    cond = lambda c, then: {"type": "minecraft:condition", "if_true": c, "then_run": then}
    seq = lambda items: {"type": "minecraft:sequence", "sequence": items}
    block = lambda b: {"type": "minecraft:block", "result_state": f"minecraft:{b}"}
    between = lambda lo, hi, then: cond(above(lo), cond({"type": "minecraft:not", "invert": above(hi)}, then))
    bad = [i for i in islands if layout_biome(i) in BADLANDS]
    groups = y_groups(bp, bad)
    # --- bands: a tree of height tests over the ranges that hold badlands
    runs = []
    for lo, hi, i in groups:
        for y in range(lo, hi):
            b = BAND_PERIOD[y % len(BAND_PERIOD)]
            if runs and runs[-1][1] == y and runs[-1][2] == b: runs[-1] = (runs[-1][0], y + 1, b)
            else: runs.append((y, y + 1, b))
    def tree(rs):
        if len(rs) == 1: return block(rs[0][2])
        h = len(rs) // 2
        return seq([cond(above(rs[h][0]), tree(rs[h:])), tree(rs[:h])])
    if runs: bp.write(f"data/{bp.NS}/worldgen/material_rule/bands.json", tree(runs))
    def shifted(o, dy):
        if isinstance(o, list): return [shifted(v, dy) for v in o]
        if not isinstance(o, dict): return o
        if o.get("type") == "minecraft:bandlands": return bp.ref("bands")
        if o.get("type") == "minecraft:y_above": return {**o, "anchor": {"absolute": o["anchor"]["absolute"] + dy}}
        return {k: shifted(v, dy) for k, v in o.items()}
    def per_island(then):
        return seq([between(lo, hi, shifted(then, round(i["y_top"] - 0.75 * relief(bp, i)) - 74)) for lo, hi, i in groups])
    def is_badlands(c):
        b = c.get("biome_is") if isinstance(c, dict) and c.get("type") == "minecraft:biome" else None
        return b is not None and all(x.split(":")[1] in BADLANDS for x in ([b] if isinstance(b, str) else b))
    def is_frozen_sea(c):
        b = c.get("biome_is") if isinstance(c, dict) and c.get("type") == "minecraft:biome" else None
        return b is not None and all(x.split(":")[1] in ("frozen_ocean", "deep_frozen_ocean") for x in ([b] if isinstance(b, str) else b))
    def walk(o):
        # The frozen oceans' rule (holes in the top layer: air above the water level, water below) is left out: with the sea
        # filled in afterwards it put single water blocks on ledges of the island's underside (60 counted under M2).
        if isinstance(o, list): return [walk(v) for v in o if not (isinstance(v, dict) and v.get("type") == "minecraft:condition" and is_frozen_sea(v["if_true"]))]
        if not isinstance(o, dict): return o
        if o.get("type") == "minecraft:condition" and is_badlands(o["if_true"]) and groups: return {**o, "then_run": per_island(o["then_run"])}
        if o.get("type") == "minecraft:condition" and isinstance(o.get("then_run"), dict) and o["then_run"].get("type") == "minecraft:condition" and is_frozen_sea(o["then_run"]["if_true"]):
            return {**o, "then_run": cond({"type": "minecraft:biome", "biome_is": bp.VOID_BIOME}, block("stone"))}   # (a rule that never applies)
        return {k: walk(v) for k, v in o.items()}
    rule = walk(rule)
    # --- snow line
    caps = []
    for b, share in SNOW_CAPS.items():
        g = y_groups(bp, [i for i in islands if layout_biome(i) == b])
        if g: caps.append(cond({"type": "minecraft:biome", "biome_is": sorted({bp.bid(i["biome"]) for lo, hi, i in g})},
                               seq([between(lo, hi, cond(above(round(i["y_top"] - share * relief(bp, i)), 2), block("snow_block"))) for lo, hi, i in g])))
    if caps: rule["sequence"].insert(0, cond("minecraft:on_floor", seq(caps)))
    bp.write("data/minecraft/worldgen/material_rule/overworld/surface.json", rule)
    print(f"surface: badlands heights and bands per island on {len(groups)} islands ({len(runs)} bands), snow line on "
          f"{sum(1 for i in islands if layout_biome(i) in SNOW_CAPS)} windswept islands")

if __name__ == "__main__":   # python3 tools/build_terrain.py flags: write the "geyser" flags into layout/islands.json
    import sys
    if sys.argv[1:] == ["flags"]:
        p = ROOT / "layout" / "islands.json"; layout = json.loads(p.read_text()); flag_big(layout)
        p.write_text(json.dumps(layout, indent=1) + "\n")
        print(sum(1 for i in layout["islands"] if i["geyser"]), "islands flagged")
