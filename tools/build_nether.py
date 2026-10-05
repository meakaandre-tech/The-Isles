#!/usr/bin/env python3
"""The Nether of The Isles (Minecraft Java 26.3): as tall as the Overworld, made of stacked cavern layers.

Called by tools/build_pack.py (build(write, out_mods)); writes into datapack/
  data/minecraft/dimension/the_nether.json, dimension_type/the_nether.json
  data/the_isles/worldgen/noise_settings/nether.json, material_rule/nether.json, noise/nether_holes.json
  data/minecraft/worldgen/placed_feature/*.json   the Nether features that pick a height, once per layer
  data/minecraft/worldgen/structure/bastion_remnant.json, nether_fossil.json, structure_set/*, carver/nether_cave.json
and into datapack-mods/ the Nether sulfur ore of Create: Gunsmithing.
Vanilla 26.3 inputs: tools/vanilla_nether/.

Every layer is a vanilla Nether stretched in height: netherrack floor, lava sea, open cavern, ceiling. Between two
layers there is only netherrack (about 35 blocks); bedrock exists at the bottom and at the top of the dimension.
"""
import copy, json
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
FIRST = MIN_Y + 16
FLOOR, ROOF = 32, 24      # blocks over which a layer's floor / ceiling fades from solid rock to the cavern noise
# LAVA: the lava seas are aquifers. The game puts an aquifer's surface at 40 * floor(y / 40) + 20 + 3 * floor(10 * spread / 3),
# so with spread 0.45 every layer whose floor starts 16 blocks under a multiple of 40 can have its sea 39 blocks above
# the start of its floor, and nowhere else.
LAVA = 39
SPREAD = 0.45
# Shafts: where this 2D noise is high, the rock between two layers gives way to the cavern noise (same x/z in every
# layer), and a little wider no lava is generated, so the shafts start on dry ground.
HOLE, HOLE_DRY = 0.42, 0.25
CAVE_PROBABILITY = 0.75   # vanilla 0.2 per chunk for 128 blocks of height

def layers():
    out, b = [], FIRST
    for h in HEIGHTS + [None]:
        t = TOP if h is None else b + h
        out.append({"k": len(out), "bottom": b, "top": t, "lava": b + LAVA})
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
    hole = mc("clamp", input=mc("mul", left=mc("sub", left=f"{NS}:nether/holes", right=HOLE), right=8.0), min=0.0, max=1.0)
    hole = mc("cache", input=hole)
    out = []
    for l in LAYERS:
        floor = grad(l["bottom"], 0.0, l["bottom"] + FLOOR, 1.0)
        roof = grad(l["top"] - ROOF, 1.0, l["top"], 0.0)
        if l["k"] > 0: floor = mc("max", left=floor, right=hole)
        if l["k"] < len(LAYERS) - 1: roof = mc("max", left=roof, right=hole)
        out.append(mc("lerp", alpha=floor, first=2.5, second=mc("lerp", alpha=roof, first=0.9375, second="minecraft:nether/base_3d_noise")))
    return mc("add", left=mc("squeeze", input=mc("interpolated", cell_size_xz=4, cell_size_y=8,
              input=mc("mul", left=mc("blend_density", input=by_layer(out)), right=0.64))), right=mc("beardifier"))

def climate(noise):
    """a different 2D biome map in every layer; the layer at y 0 has the map of the vanilla Nether"""
    n = mc("noise", noise=noise, xz_scale=0.25, y_scale=1.0)
    return by_layer([mc("slice", axis="y", coordinate=(l["k"] - 6) * 1024, input=n) for l in LAYERS])

def aquifers():
    th, vals = [], [-1.0]
    for l in LAYERS:
        th += [l["bottom"] + 16, l["bottom"] + 56]; vals += [0.6, -1.0]
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
    seq = json.loads((HERE / "material_rule.json").read_text())["sequence"]
    head, body = seq[:3], seq[3:]     # bedrock floor, bedrock roof, netherrack under the roof | the biome rules
    assert head[0] == "minecraft:bedrock_floor" and head[1] == "minecraft:bedrock_roof"
    out = list(head)
    for l in reversed(LAYERS):
        rule = {"type": "minecraft:sequence", "sequence": shift_rule(body, l["lava"])}
        if l["k"] > 0:
            rule = {"type": "minecraft:condition", "then_run": rule, "if_true": {
                "type": "minecraft:y_above", "anchor": {"absolute": l["bottom"]}, "surface_depth_multiplier": 0, "add_stone_depth": False}}
        out.append(rule)
    return {"type": "minecraft:sequence", "sequence": out}

def anchor(a, l):
    if "absolute" in a: return {"absolute": a["absolute"] - 32 + l["lava"]}
    if "above_bottom" in a: return {"absolute": l["bottom"] + a["above_bottom"]}
    return {"absolute": l["top"] - a["below_top"]}
def per_layer(height):
    """a height provider of the vanilla Nether -> the same one in a random layer"""
    def one(l):
        h = dict(height); h["min_inclusive"] = anchor(height["min_inclusive"], l); h["max_inclusive"] = anchor(height["max_inclusive"], l)
        return h
    return {"type": "minecraft:weighted_list", "distribution": [{"data": one(l), "weight": 1} for l in LAYERS]}
def layered_feature(d):
    """every layer gets the attempts the vanilla Nether gets per chunk"""
    d = copy.deepcopy(d)
    for p in d["placement"]:
        if p["type"] == "minecraft:height_range": p["height"] = per_layer(p["height"])
    d["placement"].insert(0, mc("count", count=len(LAYERS)))
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
    write(f"data/{NS}/worldgen/material_rule/nether.json", surface_rule())
    n = 0
    for f in sorted((HERE / "placed_feature").glob("*.json")):
        write(f"data/minecraft/worldgen/placed_feature/{f.name}", layered_feature(json.loads(f.read_text()))); n += 1
    # caves: the vanilla carver starts at y 0 and up
    cave = json.loads((HERE / "nether_cave.json").read_text())
    cave["y"]["min_inclusive"] = {"above_bottom": 0}; cave["probability"] = CAVE_PROBABILITY
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
    # Create: Gunsmithing sulfur ore (y 10..117 of the vanilla Nether, 16 per chunk): the same in every layer
    write("data/cgs/worldgen/placed_feature/sulfur_ore_placed.json", layered_feature({"feature": "cgs:sulfur_ore", "placement": [
        mc("count", count=16), mc("in_square"),
        mc("height_range", height=mc("uniform", min_inclusive={"above_bottom": 10}, max_inclusive={"below_top": 10})), mc("biome")]}), out_mods)
    print(f"nether: {len(LAYERS)} layers, lava at y " + " ".join(str(l["lava"]) for l in LAYERS) + f", {n} features per layer")

if __name__ == "__main__":
    for l in LAYERS: print(l)
