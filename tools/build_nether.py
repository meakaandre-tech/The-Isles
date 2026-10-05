#!/usr/bin/env python3
"""The Nether of The Isles (Minecraft Java 26.3): as tall as the Overworld, made of stacked cavern layers.

Called by tools/build_pack.py (build(write, out_mods)); writes into datapack/
  data/minecraft/dimension/the_nether.json, dimension_type/the_nether.json
  data/the_isles/worldgen/noise_settings/nether.json, material_rule/nether.json, nether_layers.json, noise/nether_holes.json
  data/minecraft/worldgen/placed_feature/*.json   the Nether features that pick a height, once per layer
  data/minecraft/worldgen/structure/bastion_remnant.json, nether_fossil.json, structure_set/*, carver/nether_cave.json
and into datapack-mods/ an override that switches off the sulfur ore of Create: Gunsmithing.
Vanilla 26.3 inputs: tools/vanilla_nether/.

Every layer is a vanilla Nether stretched in height: netherrack floor, lava sea, open cavern, ceiling. Between two
layers there is only netherrack (about 35 blocks); bedrock exists at the bottom and at the top of the dimension.
"""
import copy, json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent / "vanilla_nether"
NS = "the_isles"
MIN_Y, HEIGHT = -2032, 4064
TOP = MIN_Y + HEIGHT
# 1 block in the Nether = 1 block in the Overworld: the Nether under the 8000 x 8000 map is as large as the map, and a
# portal comes out at the same x/y/z. (Vanilla is 8; then the map would correspond to 1000 x 1000 blocks of Nether.)
COORDINATE_SCALE = 1.0
# Layer heights from the bottom up. Each is a multiple of 40 (see LAVA) except the last, which takes what is left.
# The seventh layer starts at y -16, so its lava is at y 23 and the structures the game places at fixed heights
# (fortress y 48..70, ruined portal y 32..100) stand in it like in the vanilla Nether.
HEIGHTS = [360, 320, 280, 360, 320, 360, 320, 360, 280, 320, 360]
# Generation cost (packtest's "netherperf" variants, see packtest/README.md). The environment variables are for those
# measurements; the pack is built with the defaults.
#   ISLES_NETHER_LAYERS=8|6       fewer, taller layers over the same height
#   ISLES_NETHER_CAVERN=<blocks>  with fewer layers: caverns no taller than this, solid netherrack above them instead
#   ISLES_NETHER_OLD=noise,surface,features   the density function / surface rule / placement of the floor features as
#                                 they were before (noise, surface: the same blocks, slower)
#   ISLES_NETHER_OFF=aquifer,carver,features   leave a part out (what does it cost)
#   ISLES_NETHER_CELL_Y, ISLES_NETHER_CELL_XZ   interpolation grid of the terrain (vanilla 8 and 4)
ENV = os.environ.get
OLD, OFF = set(ENV("ISLES_NETHER_OLD", "").split(",")), set(ENV("ISLES_NETHER_OFF", "").split(","))
CELL_XZ, CELL_Y = int(ENV("ISLES_NETHER_CELL_XZ", 4)), int(ENV("ISLES_NETHER_CELL_Y", 8))
HEIGHTS = {12: HEIGHTS, 8: [520, 480, 480, 520, 520, 480, 480], 6: [680, 640, 680, 680, 680]}[int(ENV("ISLES_NETHER_LAYERS", 12))]
CAVERN = int(ENV("ISLES_NETHER_CAVERN", 0))
FIRST = MIN_Y + 16
FLOOR, ROOF = 32, 24      # blocks over which a layer's floor / ceiling fades from solid rock to the cavern noise
# LAVA: the lava seas are aquifers. The game puts an aquifer's surface at 40 * floor(y / 40) + 20 + 3 * floor(10 * spread / 3),
# so with spread 0.45 every layer whose floor starts 16 blocks under a multiple of 40 can have its sea 39 blocks above
# the start of its floor, and nowhere else.
LAVA = 39
SPREAD = 0.45
# Shafts: where this 2D noise is high, the rock between two layers gives way to the cavern noise (same x/z in every
# layer), and a little wider no lava is generated, so the shafts start on dry ground.
HOLE, HOLE_DRY = 0.55, 0.42
CAVE_PROBABILITY = 0.75   # vanilla 0.2 per chunk for 128 blocks of height

def layers():
    out, b = [], FIRST
    for h in HEIGHTS + [None]:
        t = TOP if h is None else b + h     # where the next layer starts; "top": where this one's ceiling is solid
        out.append({"k": len(out), "bottom": b, "top": min(t, b + CAVERN) if CAVERN else t, "lava": b + LAVA})
        b = t
    assert all((l["bottom"] + 16) % 40 == 0 for l in out) and any(l["bottom"] == -16 for l in out)
    return out
LAYERS = layers()

def mc(t, **kw): return {"type": f"minecraft:{t}", **kw}
Y = "minecraft:y"
def by_layer(values):
    return mc("interval_select", input=Y, thresholds=[l["bottom"] for l in LAYERS[1:]], functions=values)
def grad(y0, v0, y1, v1): return mc("gradient", axis="y", from_coordinate=y0, from_value=v0, to_coordinate=y1, to_value=v1)

def density():
    """Every layer is the vanilla Nether's function: lerp(floor, 2.5, lerp(roof, 0.9375, base_3d_noise)). The game computes
    every branch of an interval_select for every point, so the layers only select the two fades (functions of y, plus the
    flat shaft noise); the 3D noise - 40 octaves, nearly all of the cost - is computed once, not once per layer."""
    hole = mc("clamp", input=mc("mul", left=mc("sub", left=f"{NS}:nether/holes", right=HOLE), right=8.0), min=0.0, max=1.0)
    hole = mc("cache", input=hole)
    floors, roofs = [], []
    for l in LAYERS:
        floor = grad(l["bottom"], 0.0, l["bottom"] + FLOOR, 1.0)
        roof = grad(l["top"] - ROOF, 1.0, l["top"], 0.0)
        if l["k"] > 0: floor = mc("max", left=floor, right=hole)
        if l["k"] < len(LAYERS) - 1: roof = mc("max", left=roof, right=hole)
        floors.append(floor); roofs.append(roof)
    noise = "minecraft:nether/base_3d_noise"
    def cavern(floor, roof): return mc("lerp", alpha=floor, first=2.5, second=mc("lerp", alpha=roof, first=0.9375, second=noise))
    if "noise" in OLD: inner = by_layer([cavern(f, r) for f, r in zip(floors, roofs)])
    else: inner = cavern(by_layer(floors), by_layer(roofs))
    return mc("add", left=mc("squeeze", input=mc("interpolated", cell_size_xz=CELL_XZ, cell_size_y=CELL_Y,
              input=mc("mul", left=mc("blend_density", input=inner), right=0.64))), right=mc("beardifier"))

def climate(noise):
    """a different 2D biome map in every layer; the layer at y 0 has the map of the vanilla Nether"""
    n = mc("noise", noise=noise, xz_scale=0.25, y_scale=1.0)
    return by_layer([mc("slice", axis="y", coordinate=(l["k"] - 6) * 1024, input=n) for l in LAYERS])

def aquifers():
    th, vals = [], [-1.0]
    for l in LAYERS:
        th += [l["bottom"] + 16, l["bottom"] + 56]; vals += [0.6, -1.0]
    if "aquifer" in OFF: th, vals = th[:1], [-1.0, -1.0]
    return {"barrier": 0.0, "lava": 0.0, "surface_level": float(TOP), "fluid_level_spread": SPREAD,
            "fluid_level_floodedness": mc("interval_select", input=Y, thresholds=th, functions=vals),
            "exclusion": mc("sub", left=f"{NS}:nether/holes", right=HOLE_DRY)}

def shift_rule(rule, lava):
    """the vanilla surface rule with its absolute heights (all relative to the vanilla lava level 32) moved to a layer"""
    r = copy.deepcopy(rule)
    def walk(o):
        if isinstance(o, dict):
            if set(o) == {"absolute"}: o["absolute"] += lava - 32
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(r); return r

def surface_rule():
    """The vanilla rule per layer. It is asked for every solid block of the column, and everything it can answer except
    netherrack - which the block already is - needs one of three depth conditions (under a ceiling, under / on a floor),
    so those are tested first: the 2,800 blocks of a column that are inside the rock cost three comparisons instead of
    a biome lookup and a walk through the layers."""
    seq = json.loads((HERE / "material_rule.json").read_text())["sequence"]
    head, body = seq[:3], seq[3:]     # bedrock floor, bedrock roof, netherrack under the roof | the biome rules
    assert head[0] == "minecraft:bedrock_floor" and head[1] == "minecraft:bedrock_roof"
    if "surface" not in OLD: head, body = seq[:2], seq[2:]     # (netherrack under the roof changes nothing in the rock: behind the depth conditions too)
    cond = lambda c, r: {"type": "minecraft:condition", "if_true": c, "then_run": r}
    out = []
    for l in reversed(LAYERS):
        rule = {"type": "minecraft:sequence", "sequence": shift_rule(body, l["lava"])}
        if l["k"] > 0:
            rule = cond({"type": "minecraft:y_above", "anchor": {"absolute": l["bottom"]}, "surface_depth_multiplier": 0, "add_stone_depth": False}, rule)
        out.append(rule)
    layers = {"type": "minecraft:sequence", "sequence": out}
    if "surface" in OLD: return {"type": "minecraft:sequence", "sequence": head + out}, None
    assert body[-1] == NETHERRACK and gates(body[:-1]) <= set(GATES), gates(body[:-1])
    return {"type": "minecraft:sequence", "sequence": head + [cond(g, f"{NS}:nether_layers") for g in GATES]}, layers
GATES = ["minecraft:under_ceiling", "minecraft:under_floor", "minecraft:on_floor"]
NETHERRACK = {"type": "minecraft:block", "result_state": "minecraft:netherrack"}
def gates(rules):
    """the conditions that the rules need before they answer anything: every path to a block goes through one of them"""
    found = set()
    def walk(r, seen):
        if isinstance(r, str): raise AssertionError(r)
        if r["type"] == "minecraft:sequence":
            for x in r["sequence"]: walk(x, seen)
        elif r["type"] == "minecraft:condition":
            walk(r["then_run"], seen | ({r["if_true"]} if isinstance(r["if_true"], str) else set()))
        elif r != NETHERRACK:
            hit = seen & set(GATES)
            found.add(min(hit) if hit else "ungated: " + json.dumps(r))
    for r in rules: walk(r, set())
    return found

def anchor(a, l):
    if "absolute" in a: return {"absolute": a["absolute"] - 32 + l["lava"]}
    if "above_bottom" in a: return {"absolute": l["bottom"] + a["above_bottom"]}
    return {"absolute": l["top"] - 1 - a["below_top"]}
def per_layer(height):
    """a height provider of the vanilla Nether -> the same one in a random layer"""
    def one(l):
        h = dict(height); h["min_inclusive"] = anchor(height["min_inclusive"], l); h["max_inclusive"] = anchor(height["max_inclusive"], l)
        return h
    return {"type": "minecraft:weighted_list", "distribution": [{"data": one(l), "weight": 1} for l in LAYERS]}
# count_on_every_layer (fungi, forest vegetation, deltas, basalt columns) walks down the whole column once per floor it
# finds: with twelve layers that was a third of the generation time. Replaced by random heights in every layer, each
# dropped onto the floor below it (at most 32 blocks; FLOOR_TRIES makes up for the attempts that find none).
# Nearly every chunk has all five biomes somewhere in its column, so every chunk runs every feature and the biome filter
# at the end of the placement throws four of five positions away: the same filter is also asked before the search for
# the floor (a layer has one biome map from bottom to top, so both answers agree except on a biome border).
FLOOR_TRIES = 12
def on_floors(count):
    air = {"type": "minecraft:matching_block_tag", "tag": "minecraft:air"}
    return [mc("count", count=FLOOR_TRIES), mc("count", count=count), mc("in_square"),
            mc("height_range", height=mc("uniform", min_inclusive={"absolute": 32}, max_inclusive={"below_top": 8})),
            mc("block_predicate_filter", predicate=air)] + ([] if "features" in OLD else [mc("biome")]) + [
            mc("environment_scan", direction_of_search="down", max_steps=32, target_condition={"type": "minecraft:solid"}, allowed_search_condition=air),
            mc("offset", x=0, y=1, z=0)]
def layered_feature(d):
    """every layer gets the attempts the vanilla Nether gets per chunk"""
    d = copy.deepcopy(d)
    if d["placement"][0]["type"] == "minecraft:count_on_every_layer":
        d["placement"] = on_floors(d["placement"][0]["count"]) + d["placement"][1:]
    for p in d["placement"]:
        if p["type"] == "minecraft:height_range": p["height"] = per_layer(p["height"])
    d["placement"].insert(0, mc("count", count=0 if "features" in OFF else len(LAYERS)))
    return d

def build(write, out_mods):
    """write(rel, obj, out=None) is build_pack.write"""
    dim = json.loads((HERE / "dimension_type.json").read_text())
    dim.update(min_y=MIN_Y, height=HEIGHT, logical_height=HEIGHT, coordinate_scale=COORDINATE_SCALE)
    write("data/minecraft/dimension_type/the_nether.json", dim)
    write("data/minecraft/dimension/the_nether.json", {"type": "minecraft:the_nether", "generator": {
        "type": "minecraft:noise", "biome_source": {"type": "minecraft:multi_noise", "preset": "minecraft:nether"}, "settings": f"{NS}:nether"}})
    write(f"data/{NS}/worldgen/noise/nether_holes.json", {"base_octave": -7, "octave_count": 2})
    write(f"data/{NS}/worldgen/density_function/nether/holes.json",
          mc("cache", input=mc("noise", noise=f"{NS}:nether_holes", xz_scale=1.0, y_scale=0.0)))
    write(f"data/{NS}/worldgen/noise_settings/nether.json", {
        "aquifers": aquifers(), "default_block": "minecraft:netherrack", "default_fluid": "minecraft:lava",
        "disable_mob_generation": False, "legacy_random_source": True, "material_rule": f"{NS}:nether",
        "noise": {"height": HEIGHT, "min_y": MIN_Y},
        "noise_router": {"chunk_surface_level": 0.0, "continents": 0.0, "depth": 0.0, "erosion": 0.0, "ridges": 0.0,
                         "final_density": density(), "temperature": climate("minecraft:nether/temperature"),
                         "vegetation": climate("minecraft:nether/vegetation")},
        # the bottom of the world, like the Overworld of this pack: the game floods every cave below "sea level" with the
        # default fluid; the lava seas come from the aquifers above
        "sea_level": MIN_Y, "spawn_target": []})
    rule, per_layer_rule = surface_rule()
    write(f"data/{NS}/worldgen/material_rule/nether.json", rule)
    if per_layer_rule: write(f"data/{NS}/worldgen/material_rule/nether_layers.json", per_layer_rule)
    n = 0
    for f in sorted((HERE / "placed_feature").glob("*.json")):
        write(f"data/minecraft/worldgen/placed_feature/{f.name}", layered_feature(json.loads(f.read_text()))); n += 1
    # caves: the vanilla carver starts at y 0 and up
    cave = json.loads((HERE / "nether_cave.json").read_text())
    cave["y"]["min_inclusive"] = {"above_bottom": 0}; cave["probability"] = 0.0 if "carver" in OFF else CAVE_PROBABILITY
    write("data/minecraft/worldgen/carver/nether_cave.json", cave)
    # structures. Bastions (a jigsaw structure with a start height) and fossils go to a random layer; fortresses and
    # ruined portals have their heights in the game's code and stay in the layer around y 0. One layer therefore gets a
    # twelfth of the bastions, so the grid is tightened from 27 to 10 chunks and the weights changed to keep the vanilla
    # number of bastions per layer and of fortresses in theirs.
    bastion = json.loads((HERE / "bastion_remnant.json").read_text())
    bastion["start_height"] = {"type": "minecraft:weighted_list", "distribution": [
        {"data": {"absolute": l["lava"] + 1}, "weight": 1} for l in LAYERS]}
    write("data/minecraft/worldgen/structure/bastion_remnant.json", bastion)
    fossil = json.loads((HERE / "nether_fossil.json").read_text())
    fossil["height"] = per_layer(fossil["height"])
    write("data/minecraft/worldgen/structure/nether_fossil.json", fossil)
    write("data/minecraft/worldgen/structure_set/nether_complexes.json", {
        "placement": {"type": "minecraft:random_spread", "salt": 30084232, "separation": 4, "spacing": 10},
        "structures": [{"structure": "minecraft:fortress", "weight": 2}, {"structure": "minecraft:bastion_remnant", "weight": 3 * len(LAYERS)}]})
    write("data/minecraft/worldgen/structure_set/nether_fossils.json", {
        "placement": {"type": "minecraft:random_spread", "salt": 14357921, "separation": 0, "spacing": 1},
        "structures": [{"structure": "minecraft:nether_fossil", "weight": 1}]})
    # Create: Gunsmithing sulfur ore: switched off (owner's decision: sulfur ore generates nowhere; sulfur comes from nodes)
    write("data/cgs/worldgen/placed_feature/sulfur_ore_placed.json",
          {"feature": "cgs:sulfur_ore", "placement": [mc("count", count=0)]}, out_mods)
    print(f"nether: {len(LAYERS)} layers, lava at y " + " ".join(str(l["lava"]) for l in LAYERS) + f", {n} features per layer")

if __name__ == "__main__":
    for l in LAYERS: print(l)
