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

# ---------------------------------------------------------------------------------------------------------- sulfur
POCKET_R, POCKET_TOP, POCKET_BOTTOM = 40, 14, 46     # the sulfur caves under a geyser: radius, and depth under the geyser's ground
CHAMBER_R, CHAMBER_H = 12, 5                         # the cavern in the middle of the pocket (always open)
WARMTH = 13                                          # light over a geyser's pool where water freezes (see sulfur)
GEYSER_SIZES = ("sulfur_spring_small_", "sulfur_spring_medium_")   # the vanilla spring templates used
PAD_R = 14                                           # the ground is level this far around a geyser
def flag_big(layout):
    """writes "geyser": true/false into every island of the layout (once; the owner edits the flags afterwards)"""
    for i in layout["islands"]:
        i.setdefault("geyser", i["radius"] >= BIG_RADIUS and not is_basin(i))
def geyser(bp, i, layout, islands):
    """the place of an island's geyser -> {x, y, z} (y: the ground there, the first free block) or None"""
    if not i.get("geyser") or is_basin(i) or "sulfur" in OFF: return None
    R = i["radius"]; amp = min(bp.RELIEF.get(layout_biome(i), bp.DEFAULT_RELIEF), 0.5 * i["thickness"])
    a = i["shape_seed"] % 360
    # a quarter of the radius from the centre, turned (then moved outwards) until it is clear of the sinkholes, of the spawn
    # point and of every island above or below (a tier, an islet)
    for far in (0.25, 0.35, 0.45, 0.55, 0.62):
        for turn in range(10):
            x = round(i["x"] + far * R * math.cos(math.radians(a + 37 * turn))); z = round(i["z"] + far * R * math.sin(math.radians(a + 37 * turn)))
            if all(math.hypot(x - s["x"], z - s["z"]) > s["radius"] + 80 for s in layout.get("sinkholes", [])) and math.hypot(x, z) > 150 \
               and all(j is i or math.hypot(x - j["x"], z - j["z"]) > j["radius"] + 24 for j in islands):
                return {"x": x, "y": i["y_top"] - round(0.6 * amp) - 2, "z": z}
    return {"x": x, "y": i["y_top"] - round(0.6 * amp) - 2, "z": z}
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
        (ROOT / "layout" / "geysers.json").write_text(json.dumps({
            "note": "generated by tools/build_pack.py from the \"geyser\" flags of islands.json. x/z: where the sulfur spring feature is placed "
                    "(its potent sulfur block lies within 8 blocks of it); y: the ground there (the ground is level 8 blocks around, +-4 with the seed)",
            "geysers": [{"island": i["id"], **g} for i, g in sites]}, indent=1) + "\n")
        (ROOT / "layout" / "sulfur_caves.json").write_text(json.dumps({
            "note": "generated by tools/build_pack.py: one pocket of minecraft:sulfur_caves under every geyser (a cylinder), with an open chamber in its middle",
            "sulfur_caves": [{"island": i["id"], **pocket(g)} for i, g in sites]}, indent=1) + "\n")
    if not sites: return None, None
    air = mc("matching_block_tag", tag="minecraft:air")
    # the geyser: the vanilla sulfur spring on the ground at the fixed place (under a tier too: no heightmap)
    # (down to the ground through whatever the chunk next door has already grown over the place - leaves, a trunk, flowers:
    # with a search through air only, two of 25 geysers were missing, one under a flower)
    tree = mc("any_of", predicates=[mc("matching_block_tag", tag="minecraft:leaves"), mc("matching_block_tag", tag="minecraft:logs")])
    # The vanilla feature picks one of ten templates by weight; here only the small and medium ones (weights as in vanilla):
    # in the test the two geysers that were missing of 25 fit the share of the large ones, which never appeared.
    spring = json.loads((HERE / "vanilla_feature" / "sulfur_spring.json").read_text())
    spring["features"] = [e for e in spring["features"] if any(k in json.dumps(e) for k in GEYSER_SIZES)]
    assert spring["type"] == "minecraft:weighted_random_selector" and len(spring["features"]) == len(GEYSER_SIZES)
    bp.write(f"data/{bp.NS}/worldgen/feature/geyser.json", spring)
    bp.write(f"data/{bp.NS}/worldgen/placed_feature/geyser.json", {"feature": bp.ref("geyser"), "placement": [
        mc("fixed_placement", positions=[[g["x"], g["y"] + 8, g["z"]] for i, g in sites]),
        mc("environment_scan", direction_of_search="down", max_steps=20, target_condition=mc("all_of", predicates=[mc("solid"), mc("not", predicate=tree)])),
        mc("offset", x=0, y=1, z=0)]})
    # Where water freezes (snowy plains, peaks) the spring's pool would be ice and the geyser "dry": a light block (invisible,
    # level 13) over the water above every potent sulfur block of those springs keeps it open (ice from generation melts).
    cold = [g for i, g in sites if bp.vanilla_biome(layout_biome(i))["temperature"] < 0.15]
    potent = lambda dy: mc("matching_blocks", blocks="minecraft:potent_sulfur", offset=[0, dy, 0])
    bp.write(f"data/{bp.NS}/worldgen/placed_feature/geyser_warmth.json", {
        "feature": {"type": "minecraft:simple_block", "to_place": {"id": "minecraft:light", "properties": {"level": str(WARMTH), "waterlogged": "false"}}},
        # (from the geyser's own position: the feature then runs with the geyser's chunk, after the geyser)
        "placement": [mc("fixed_placement", positions=[[g["x"], g["y"], g["z"]] for g in cold]), mc("offset", x=-8, y=-8, z=-8), mc("cuboid", xz_size=15, y_size=12),
                      mc("block_predicate_filter", predicate=mc("all_of", predicates=[air, mc("matching_blocks", blocks="minecraft:water", offset=[0, -1, 0]),
                                                                                      mc("any_of", predicates=[potent(-2), potent(-3)])]))]})
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
    # one geyser per big island: the springs the biome grows up to the surface by itself (rooted_sulfur_spring) are replaced by the fixed one
    biome["features"] = [[x for f in step for x in ([bp.ref("geyser")] + ([bp.ref("geyser_warmth")] if cold else []) if f == "minecraft:rooted_sulfur_spring" else [f])]
                         for step in biome["features"]]
    biome["carvers"] = []
    # the surface rule of the biome (sulfur and cinnabar in bands of a 3D noise) for every block of a pocket; heights first
    lo, hi = min(g["y"] for i, g in sites) - POCKET_BOTTOM - 8, max(g["y"] for i, g in sites) - POCKET_TOP + 8
    above = lambda y: {"type": "minecraft:y_above", "anchor": {"absolute": y}, "surface_depth_multiplier": 0, "add_stone_depth": False}
    cond = lambda c, then: {"type": "minecraft:condition", "if_true": c, "then_run": then}
    rule = cond(above(lo), cond({"type": "minecraft:not", "invert": above(hi)},
                cond({"type": "minecraft:biome", "biome_is": "minecraft:sulfur_caves"}, "minecraft:overworld/biome_surface/sulfur_caves")))
    print(f"sulfur: {len(sites)} geysers (islands of radius {BIG_RADIUS} or more that are not sea basins), a pocket of sulfur caves "
          f"{POCKET_TOP}..{POCKET_BOTTOM} blocks under each")
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
