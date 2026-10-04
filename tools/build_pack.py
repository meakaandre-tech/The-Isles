#!/usr/bin/env python3
"""Builds the The Isles data pack (Minecraft Java 26.3, pack format 121) from layout/islands.json.

Every island in the layout becomes a density function; a coarse x/z grid selects which
islands are evaluated at a position, so cost per sample stays small. Biomes are assigned
per island through the multi-noise "temperature" input, which carries a per-island code.
"""
import json, math, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "datapack"
NS = "the_isles"
MIN_Y, HEIGHT = -2032, 4064
CELL = 512          # grid cell size for the island lookup
PAD = 8             # footprint padding in blocks
VOID_BIOME = f"{NS}:void"

# surface relief (blocks) by biome; anything not listed uses DEFAULT_RELIEF
RELIEF = {"jagged_peaks": 190, "frozen_peaks": 160, "stony_peaks": 130, "snowy_slopes": 90, "grove": 50,
          "windswept_hills": 80, "windswept_gravelly_hills": 80, "windswept_forest": 70, "windswept_savanna": 80,
          "savanna_plateau": 40, "badlands": 45, "eroded_badlands": 70, "wooded_badlands": 45, "meadow": 34,
          "cherry_grove": 30, "old_growth_pine_taiga": 26, "old_growth_spruce_taiga": 26, "taiga": 24,
          "jungle": 30, "bamboo_jungle": 24, "sparse_jungle": 22, "dark_forest": 22, "desert": 12,
          "plains": 12, "sunflower_plains": 12, "swamp": 5, "mangrove_swamp": 5, "beach": 4, "snowy_beach": 4,
          "stony_shore": 16, "mushroom_fields": 18, "snowy_plains": 10, "ice_spikes": 10}
DEFAULT_RELIEF = 18

def mc(t, **kw): return {"type": f"minecraft:{t}", **kw}
def add(a, b): return mc("add", left=a, right=b)
def sub(a, b): return mc("sub", left=a, right=b)
def mul(a, b): return mc("mul", left=a, right=b)
def dmin(a, b): return mc("min", left=a, right=b)
def dmax(a, b): return mc("max", left=a, right=b)
def clamp(a, lo, hi): return mc("clamp", input=a, min=lo, max=hi)
def choice(inp, lo, hi, inside, outside):
    return mc("range_choice", input=inp, min_inclusive=lo, max_exclusive=hi, when_in_range=inside, when_out_of_range=outside)
def ref(name): return f"{NS}:{name}"
def fold(fn, items):
    out = items[0]
    for i in items[1:]: out = fn(out, i)
    return out

Y = "minecraft:y"
EDGE, RELIEF_N, UNDER, RAG = ref("noise/edge"), ref("noise/relief"), ref("noise/under"), ref("noise/rag")

def write(rel, obj):
    p = OUT / rel; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1) + "\n")

def dist_fn(i):
    return mc("slice", axis="y", coordinate=0, input=mc("distance_to_point", metric="euclidean", point=[i["x"], 0, i["z"]]))

def island_density(i):
    R, top, t = i["radius"], i["y_top"], i["thickness"]
    basin = i["kind"] == "basin"
    amp = 0 if basin else min(RELIEF.get(i["biome"], DEFAULT_RELIEF), 0.5 * t)
    shrink = max(0.05, min(0.2, 40 / R + 0.04))
    d = ref(f"dist/{i['key']}")
    # e: 1 at the centre, 0 at the (noise-warped) rim, negative outside. The rim never passes R.
    e = mc("cache", input=sub(sub(1, mul(d, 1 / R)), mul(shrink, add(1, EDGE))))
    write(f"data/{NS}/worldgen/density_function/edge/{i['key']}.json", e)
    e = ref(f"edge/{i['key']}")
    c = clamp(mul(e, 1 / 0.6), 0, 1)
    rim = min(10, 0.1 * t)
    surface = sub(sub(top, mul(0.5 * amp, sub(1, RELIEF_N))), mul(rim, sub(1, c)))
    if basin:  # bowl: rim stays up, interior drops
        surface = sub(surface, mul(0.3 * t, clamp(mul(sub(e, 0.16), 4), 0, 1)))
    write(f"data/{NS}/worldgen/density_function/surface/{i['key']}.json", mc("cache", input=surface))
    surface = ref(f"surface/{i['key']}")
    body = max(12, (t - amp - (0.3 * t if basin else 0)) / 1.3)
    taper = add(mul(0.4, mc("sqrt", input=c)), mul(0.6, c))
    bottom = sub(surface, mul(mul(body, taper), add(1, mul(0.3, UNDER))))
    solid = dmin(dmin(mul(sub(surface, Y), 1 / 8), mul(sub(Y, bottom), 1 / 12)), mul(e, R / 12))
    return choice(d, 0, R + PAD, clamp(add(solid, mul(0.55, RAG)), -1, 1), -1)

def grid(islands, leaf):
    """interval_select on x then z; each leaf gets the islands whose padded footprint touches that cell."""
    half = max(max(abs(i["x"]), abs(i["z"])) + i["radius"] for i in islands) + 2 * PAD
    n = math.ceil(half / CELL)
    edges = [k * CELL for k in range(-n + 1, n)]
    cols = []
    for cx in range(-n, n):
        rows = []
        for cz in range(-n, n):
            x0, z0 = cx * CELL, cz * CELL
            hit = []
            for i in islands:
                nx = min(max(i["x"], x0), x0 + CELL); nz = min(max(i["z"], z0), z0 + CELL)
                if math.hypot(i["x"] - nx, i["z"] - nz) <= i["radius"] + 2 * PAD: hit.append(i)
            rows.append(leaf(hit))
        cols.append(mc("interval_select", input=ref("z"), thresholds=edges, functions=rows))
    return mc("interval_select", input=ref("x"), thresholds=edges, functions=cols)

def main():
    layout = json.loads((ROOT / "layout" / "islands.json").read_text())
    islands = layout["islands"]
    for n, i in enumerate(islands): i["key"] = f"{n:03d}_{i['id'].lower()}"
    if OUT.exists(): shutil.rmtree(OUT)

    biomes = sorted({i["biome"] for i in islands})
    code = {b: round(-1.8 + 0.07 * k, 4) for k, b in enumerate(biomes, 1)}
    VOID = -1.8
    assert max(code.values()) < 1.95

    write("pack.mcmeta", {"pack": {"description": "The Isles - hand-placed floating island world", "pack_format": 121,
                                   "min_format": [121, 0], "max_format": [121, 0]}})
    # --- noises
    for name, octave, count in [("edge", -7, 3), ("relief", -7, 4), ("under", -5, 3), ("rag", -5, 3)]:
        write(f"data/{NS}/worldgen/noise/{name}.json", {"base_octave": octave, "octave_count": count})
        write(f"data/{NS}/worldgen/density_function/noise/{name}.json",
              mc("cache", input=mc("noise", noise=ref(name), xz_scale=1.0, y_scale=1.0 if name == "rag" else 0.0)))
    for axis in "xz":
        write(f"data/{NS}/worldgen/density_function/{axis}.json",
              mc("gradient", axis=axis, from_coordinate=-100000, to_coordinate=100000, from_value=-100000.0, to_value=100000.0))
    # --- islands
    for i in islands:
        write(f"data/{NS}/worldgen/density_function/dist/{i['key']}.json", dist_fn(i))
        write(f"data/{NS}/worldgen/density_function/island/{i['key']}.json", island_density(i))
    write(f"data/{NS}/worldgen/density_function/terrain.json",
          grid(islands, lambda hit: fold(dmax, [ref(f"island/{i['key']}") for i in hit]) if hit else -1))

    # --- biome code: one main island per column; stacked tiers switch biome by height
    mains = [i for i in islands if i["layer"] == "main"]
    tiers = {}
    for i in islands:
        if i["layer"] == "tier": tiers.setdefault(i["cluster"], []).append(i)
    def biome_term(i):
        val = code[i["biome"]] - VOID
        stack = sorted(tiers.get(i["cluster"], []), key=lambda t: t["y_bottom"]) if i["id"] == i["cluster"] + "1" else []
        if stack:
            levels, below = [], i
            for t in stack:
                levels.append((below["y_top"] + t["y_bottom"]) / 2); below = t
            val = mc("interval_select", input=Y, thresholds=levels,
                     functions=[code[i["biome"]] - VOID] + [code[t["biome"]] - VOID for t in stack])
        return choice(ref(f"dist/{i['key']}"), 0, i["radius"] + PAD, val, 0)
    write(f"data/{NS}/worldgen/density_function/biome_code.json",
          add(VOID, grid(mains, lambda hit: fold(add, [biome_term(i) for i in hit]) if hit else 0)))

    # --- noise settings, surface rule, dimension
    final = add(mc("squeeze", input=mc("interpolated", cell_size_xz=4, cell_size_y=8,
                input=mul(mc("blend_density", input=ref("terrain")), 0.64))), mc("beardifier"))
    write(f"data/{NS}/worldgen/noise_settings/isles.json", {
        "default_block": "minecraft:stone", "default_fluid": "minecraft:water", "disable_mob_generation": False,
        "legacy_random_source": False, "material_rule": ref("isles"), "noise": {"height": HEIGHT, "min_y": MIN_Y},
        "noise_router": {"chunk_surface_level": 0.0, "continents": 0.0, "depth": 0.0, "erosion": 0.0, "ridges": 0.0,
                         "vegetation": 0.0, "temperature": ref("biome_code"), "final_density": final},
        "sea_level": MIN_Y, "spawn_target": []})
    write(f"data/{NS}/worldgen/material_rule/isles.json", {"type": "minecraft:sequence", "sequence": ["minecraft:overworld/surface"]})
    write(f"data/{NS}/worldgen/biome/void.json", {
        "attributes": {"minecraft:gameplay/natural_mob_spawns": {"argument": {"spawn_costs": {}, "spawns_by_category": {
            k: [] for k in ["ambient", "axolotls", "creature", "misc", "monster", "underground_water_creature", "water_ambient", "water_creature"]}},
            "modifier": "overlay"}, "minecraft:visual/sky_color": "#78a7ff"},
        "carvers": [], "downfall": 0.5, "effects": {"water_color": "#3f76e4"}, "features": [], "has_precipitation": False, "temperature": 0.5})
    def point(c): return {"temperature": [round(c - 0.03, 4), round(c + 0.03, 4)], "humidity": 0, "continentalness": 0,
                          "erosion": 0, "weirdness": 0, "depth": 0, "offset": 0}
    entries = [{"biome": VOID_BIOME, "parameters": point(VOID)}] + [{"biome": f"minecraft:{b}", "parameters": point(code[b])} for b in biomes]
    write("data/minecraft/dimension/overworld.json", {"type": "minecraft:overworld", "generator": {
        "type": "minecraft:noise", "biome_source": {"type": "minecraft:multi_noise", "biomes": entries}, "settings": ref("isles")}})
    dim = json.loads((Path(__file__).parent / "vanilla_overworld_dimension_type.json").read_text())
    dim.update(min_y=MIN_Y, height=HEIGHT, logical_height=HEIGHT)
    write("data/minecraft/dimension_type/overworld.json", dim)
    files = sum(1 for p in OUT.rglob("*") if p.is_file())
    print(f"{len(islands)} islands, {len(biomes)} biomes, {files} files -> {OUT}")

if __name__ == "__main__":
    main()
