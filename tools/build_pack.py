#!/usr/bin/env python3
"""Builds the The Isles data pack (Minecraft Java 26.3, pack format 121) from layout/islands.json.

Every island in the layout becomes a density function; a coarse x/z grid selects which
islands are evaluated at a position, so cost per sample stays small. Biomes are assigned
per island through the multi-noise "temperature" input, which carries a per-island code.
"""
import json, math, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "datapack"
OUT_MODS = ROOT / "datapack-mods"
NS = "the_isles"
MIN_Y, HEIGHT = -2032, 4064
# Generation cost (measured by packtest's perf phase, see packtest/README.md). The environment variables are for those
# measurements only.
CELL_XZ, CELL_Y = int(os.environ.get("ISLES_CELL_XZ", 4)), int(os.environ.get("ISLES_CELL_Y", 8))   # density is computed on this grid and interpolated
TRIM_NOISE = os.environ.get("ISLES_TRIM_NOISE", "0") == "1"   # terrain is only computed in the layers that hold islands
CELL = 512          # grid cell size for the island lookup
PAD = 8             # footprint padding in blocks
SURFACE_RULE_DEPTH = 48   # the vanilla surface rule only runs this many blocks into the ground (see main)
VOID_BIOME = f"{NS}:void"
BIOME_MARGIN = 24   # an island's biome reaches this many blocks past its (noise-warped) rim, see biome_term
# Look (dimension type attributes, see main): one cloud layer is all the game offers (one height per dimension or biome,
# and every biome occurs at many altitudes), so it stays where the vanilla one is, near the middle of the islands.
CLOUD_HEIGHT = 192.33
FOG_COLOR = "#a4c5ff"     # the whole sky takes this colour (between the vanilla sky #78a7ff and fog #c0d8ff)
SKY_FOG_END = 3.0
# Structures (see structures()): depth of the buried ones under the island surface, strongholds around the spawn
TRIAL_DEPTH, CITY_DEPTH, PORTAL_ROOM_DEPTH = (-48, -32), -60, -30
STRONGHOLD_RINGS = {"distance": 12, "spread": 3, "count": 9}
JIGSAW_PADDING = {"bottom": 48, "top": 0}   # a jigsaw start this close to the bottom of the world is dropped

# surface relief (blocks) by biome; anything not listed uses DEFAULT_RELIEF
RELIEF = {"jagged_peaks": 190, "frozen_peaks": 160, "stony_peaks": 130, "snowy_slopes": 90, "grove": 50,
          "windswept_hills": 80, "windswept_gravelly_hills": 80, "windswept_forest": 70, "windswept_savanna": 80,
          "savanna_plateau": 40, "badlands": 45, "eroded_badlands": 70, "wooded_badlands": 45, "meadow": 34,
          "cherry_grove": 30, "old_growth_pine_taiga": 26, "old_growth_spruce_taiga": 26, "taiga": 24,
          "jungle": 30, "bamboo_jungle": 24, "sparse_jungle": 22, "dark_forest": 22, "desert": 12,
          "plains": 12, "sunflower_plains": 12, "swamp": 5, "mangrove_swamp": 5, "beach": 4, "snowy_beach": 4,
          "stony_shore": 16, "mushroom_fields": 18, "snowy_plains": 10, "ice_spikes": 10}
DEFAULT_RELIEF = 18
# Biomes the game treats specially by id, replaced in the generated pack (the layout keeps its own names).
# eroded_badlands: the surface builder raises stone pillars from the ground up to y 64..90 wherever the column's ground
# is lower (MaterialSystem.erodedBadlandsExtension, not data driven) - on a floating island that is a pillar up to
# 1,100 blocks tall, and in the empty columns of the biome footprint a stone column down to the bottom of the world.
BIOME_SUBSTITUTE = {"eroded_badlands": "badlands"}
def pack_biome(i): return BIOME_SUBSTITUTE.get(i["biome"], i["biome"])   # the biome the generated pack uses for an island

# Ores. The vanilla ore features pick an absolute height (or one counted from the bottom of the world, 2,000 blocks
# below anything), so most islands get none and no island gets diamonds. The pack replaces their placement by a
# depth below the island's own surface: what the vanilla overworld has at y is put (64 - y) blocks under the ground.
# (placed feature, feature, count or -rarity, shallowest depth, deepest depth); counts are the vanilla ones scaled by
# the share of the vanilla height range that lies inside the vanilla world and under y 64 (the diamond and lower redstone
# ranges are centred on the vanilla bottom, so half of their attempts never land). Ores that only exist above y 64
# (coal_upper, iron_upper, the *_upper stone blobs) and cave decoration keep their vanilla placement.
ORES = [("ore_coal_lower", "ore_coal_buried", 5, 0, 64), ("ore_copper", "ore_copper_small", 12, 0, 80),
        ("ore_iron_middle", "ore_iron", 10, 8, 88), ("ore_iron_small", "ore_iron_small", 10, 0, 128),
        ("ore_gold", "ore_gold_buried", 4, 32, 128), ("ore_gold_lower", "ore_gold_buried", {"type": "minecraft:uniform", "min_inclusive": 0, "max_inclusive": 1}, 112, 128),
        ("ore_gold_extra", "ore_gold", 7, 0, 32), ("ore_redstone", "ore_redstone", 4, 48, 128), ("ore_redstone_lower", "ore_redstone", 4, 96, 128),
        ("ore_diamond", "ore_diamond_small", 4, 48, 128), ("ore_diamond_buried", "ore_diamond_buried", 2, 48, 128),
        ("ore_diamond_large", "ore_diamond_large", -18, 48, 128), ("ore_diamond_medium", "ore_diamond_medium", 2, 68, 128),
        ("ore_lapis", "ore_lapis", 2, 32, 96), ("ore_lapis_buried", "ore_lapis_buried", 4, 0, 128), ("ore_emerald", "ore_emerald", 5, 0, 80),
        ("ore_infested", "ore_infested", 14, 0, 128), ("ore_dirt", "ore_dirt", 3, 0, 64), ("ore_gravel", "ore_gravel", 5, 0, 128),
        ("ore_granite_lower", "ore_granite", 2, 4, 64), ("ore_diorite_lower", "ore_diorite", 2, 4, 64),
        ("ore_andesite_lower", "ore_andesite", 2, 4, 64), ("ore_tuff", "ore_tuff", 2, 64, 128)]
# The same for the ores of the mods of the owner's pack. These go into a second data pack (datapack-mods/): a data
# pack that names a mod's feature does not load without that mod.
MOD_ORES = [("create", "zinc_ore", "create:zinc_ore", 8, 0, 128, "create:config_filter"),
            ("create", "striated_ores_overworld", "create:striated_ores_overworld", -18, 0, 96, "create:config_filter"),
            ("createnuclear", "uranium_ore", "createnuclear:uranium_ore", 6, 0, 128, "create:config_filter"),
            ("createnuclear", "striated_ores_overworld", "createnuclear:striated_ores_overworld", -18, 0, 96, "create:config_filter"),
            ("cgs", "lead_ore_placed", "cgs:lead_ore", 11, 0, 128, "minecraft:biome")]

# Climate. The game cools a biome by 0.00125 per block above "sea level + 17" and snows below 0.15. The sea level of this
# world has to be its bottom (anything else floods the void: lava below y -54, the default fluid below the sea level),
# so every biome would be 2,000 blocks "up a mountain": snow cover and snowfall on plains, jungles and beaches alike.
# The biomes that rain in the vanilla overworld are therefore written into the pack with a temperature that stays above
# 0.15 up to the build limit; their grass and leaf colours, which the game derives from the temperature, are pinned to
# the vanilla values (tools/vanilla_biome_colors.json, read off the vanilla colormaps at each biome's own
# temperature and downfall). Biomes that snow in vanilla are left alone. Input: tools/vanilla_biome/ (26.3).
WARM = 5.5
def climate_biome(name):
    d = json.loads((Path(__file__).parent / "vanilla_biome" / f"{name}.json").read_text())
    if not d["has_precipitation"] or d["temperature"] < 0.15 or d.get("temperature_modifier") == "frozen": return None
    grass, foliage, dry = json.loads((Path(__file__).parent / "vanilla_biome_colors.json").read_text())[name]
    eff = d.setdefault("effects", {})
    eff.setdefault("grass_color", grass); eff.setdefault("foliage_color", foliage); eff.setdefault("dry_foliage_color", dry)
    d["temperature"] = WARM
    return d

def mc(t, **kw): return {"type": f"minecraft:{t}", **kw}
def ore_placement(feature, count, d0, d1, last):
    """count attempts per chunk, each (d0 + 16 * Binomial(n, 1/2) + 0..15) blocks under the top block of its column, at most d1"""
    down = lambda y: mc("offset", x=0, y=y, z=0)
    mods = [mc("rarity_filter", chance=-count) if isinstance(count, int) and count < 0 else mc("count", count=count),
            mc("in_square"), mc("heightmap", heightmap="OCEAN_FLOOR_WG")]
    base = d0 + 1                        # the heightmap is the first free block above the ground
    while base > 0:
        mods.append(down(-min(16, base))); base -= 16
    mods += [mc("randomly_selected", placements=[down(0), down(-16)])] * max(0, round((d1 - d0) / 16) - 1)
    mods += [down({"type": "minecraft:uniform", "min_inclusive": -15, "max_inclusive": 0}), {"type": last}]
    return {"feature": feature, "placement": mods}
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

def write(rel, obj, out=None):
    p = (out or OUT) / rel; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1) + "\n")

def dist_fn(i):
    return mc("slice", axis="y", coordinate=0, input=mc("distance_to_point", metric="euclidean", point=[i["x"], 0, i["z"]]))

def island_density(i):
    R, top, t = i["radius"], i["y_top"], i["thickness"]
    basin = i["kind"] == "basin"
    amp = 0 if basin else min(RELIEF.get(i.get("layout_biome", i["biome"]), DEFAULT_RELIEF), 0.5 * t)   # the shape follows the layout biome
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

def nbt_structure(size, blocks):
    """a structure template (gzipped NBT, 26.3 layout: palette entries are {id, properties}); blocks: {(x, y, z): (id, {props})}"""
    import gzip, struct
    def name(n): b = n.encode(); return struct.pack(">H", len(b)) + b
    def tag(t, n, payload): return bytes([t]) + name(n) + payload
    def ints(n, v): return tag(9, n, bytes([3]) + struct.pack(">i", len(v)) + b"".join(struct.pack(">i", x) for x in v))
    def comps(n, items): return tag(9, n, bytes([10 if items else 0]) + struct.pack(">i", len(items)) + b"".join(items))
    palette, index, out = [], {}, []
    for pos in sorted(blocks):
        bid, props = blocks[pos]; key = (bid, tuple(sorted(props.items())))
        if key not in index:
            index[key] = len(palette)
            body = tag(8, "id", name(bid))
            if props: body += tag(10, "properties", b"".join(tag(8, k, name(v)) for k, v in sorted(props.items())) + b"\0")
            palette.append(body + b"\0")
        out.append(ints("pos", list(pos)) + tag(3, "state", struct.pack(">i", index[key])) + b"\0")
    root = ints("size", list(size)) + comps("entities", []) + comps("blocks", out) + comps("palette", palette) + tag(3, "DataVersion", struct.pack(">i", 5023))
    return gzip.compress(tag(10, "", root + b"\0"), mtime=0)

def portal_room():
    """the room of the_isles:stronghold: 11 x 8 x 11, stone brick shell, a floor of bricks with the lava pit, the twelve empty frames on it"""
    B = {}
    brick = ("minecraft:stone_bricks", {})
    for x in range(11):
        for y in range(8):
            for z in range(11):
                shell = x in (0, 10) or y in (0, 7) or z in (0, 10)
                B[(x, y, z)] = brick if shell or y == 1 else ("minecraft:air", {})
    for x in (4, 5, 6):
        for z in (4, 5, 6): B[(x, 1, z)] = ("minecraft:lava", {"level": "0"})
    frame = lambda facing: ("minecraft:end_portal_frame", {"eye": "false", "facing": facing})
    for k in (4, 5, 6):
        B[(k, 2, 3)] = frame("south"); B[(k, 2, 7)] = frame("north"); B[(3, 2, k)] = frame("east"); B[(7, 2, k)] = frame("west")
    for x, z in ((1, 1), (1, 9), (9, 1), (9, 9)): B[(x, 2, z)] = ("minecraft:torch", {})
    return nbt_structure((11, 8, 11), B)

def structures(islands, biomes):
    """Every vanilla Overworld structure relative to its island. tools/vanilla_structure/ holds the 26.3 files.

    The game takes a structure's height either from the terrain under it (a heightmap) or from a number: an absolute
    height, or the generator's sea level, which here is the bottom of the world. The first kind already follows the
    islands. Of the second kind the jigsaw structures have a data switch (project_start_to_heightmap) and so have the
    ruined portals (their setups); the rest is hard-coded and is switched off here (an empty biome list, which also
    takes them out of /locate and of the per-chunk structure search):
      stronghold, mineshaft, mineshaft_mesa   moved under the sea level by the code -> the lowest layers of the world
      monument                                built at y 39..61
      mansion                                 only where the ground is at y 60 or higher (kept when a dark forest or pale
                                              garden island is that high)
    Without the stronghold nothing leads to the End, so the pack has one of its own: the_isles:stronghold, a sealed
    End portal room buried under the surface, placed like the vanilla one (rings around the origin: the first three
    lie in the spawn island) and found by eyes of ender."""
    src = Path(__file__).parent / "vanilla_structure"
    report = {}
    high_dark = any(i["biome"] in ("dark_forest", "pale_garden") and i["y_top"] >= 76 for i in islands)
    off = {"stronghold", "mineshaft", "mineshaft_mesa", "monument"} | (set() if high_dark else {"mansion"})
    for f in sorted(src.glob("*.json")):
        d = json.loads(f.read_text()); name = f.stem; how = None
        if name in off:
            d["biomes"] = []; how = "off"
        elif d["type"] == "minecraft:jigsaw":
            d["dimension_padding"] = JIGSAW_PADDING
            if "project_start_to_heightmap" in d: how = "surface (as in vanilla), not at the bottom of the world"
            else:
                d["project_start_to_heightmap"] = "OCEAN_FLOOR_WG"
                lo, hi = TRIAL_DEPTH if name == "trial_chambers" else (CITY_DEPTH, CITY_DEPTH)
                d["start_height"] = {"absolute": lo} if lo == hi else {"type": "minecraft:uniform", "min_inclusive": {"absolute": lo}, "max_inclusive": {"absolute": hi}}
                how = f"{-hi}..{-lo} blocks under the island surface" if lo != hi else f"{-lo} blocks under the island surface"
        elif d["type"] == "minecraft:ruined_portal":
            for su in d["setups"]:
                if su["placement"] in ("underground", "in_mountain"): su["placement"] = "partly_buried"
            how = "on or half in the island surface"
        if how:
            write(f"data/minecraft/worldgen/structure/{name}.json", d); report[name] = how
    # the pack's own way to the End
    (OUT / f"data/{NS}/structure").mkdir(parents=True, exist_ok=True)
    (OUT / f"data/{NS}/structure/portal_room.nbt").write_bytes(portal_room())
    write(f"data/{NS}/worldgen/template_pool/portal_room.json", {"elements": [{"element": {
        "element_type": "minecraft:single_pool_element", "location": ref("portal_room"), "processors": {"processors": []},
        "projection": "rigid"}, "weight": 1}], "fallback": "minecraft:empty"})
    write(f"data/{NS}/worldgen/structure/stronghold.json", {
        "type": "minecraft:jigsaw", "biomes": [f"minecraft:{b}" for b in biomes], "dimension_padding": JIGSAW_PADDING,
        "max_distance_from_center": 80, "project_start_to_heightmap": "OCEAN_FLOOR_WG", "size": 1, "spawn_overrides": {},
        "start_height": {"absolute": PORTAL_ROOM_DEPTH}, "start_pool": ref("portal_room"), "step": "underground_structures",
        "terrain_adaptation": "bury", "use_expansion_hack": False})
    write("data/minecraft/worldgen/structure_set/strongholds.json", {"placement": {
        "type": "minecraft:concentric_rings", "preferred_biomes": "#minecraft:stronghold_biased_to", "salt": 0, **STRONGHOLD_RINGS},
        "structures": [{"structure": ref("stronghold"), "weight": 1}]})
    write("data/minecraft/tags/worldgen/structure/eye_of_ender_located.json", {"replace": True, "values": [ref("stronghold")]})
    return report

def noise_range(islands):
    """the layers the generator fills: the whole world, or (TRIM_NOISE) only those that can hold an island, in steps of 16"""
    if not TRIM_NOISE: return {"height": HEIGHT, "min_y": MIN_Y}
    lo = min(i["y_bottom"] for i in islands) - 96; hi = max(i["y_top"] for i in islands) + 96
    lo = max(MIN_Y, lo // 16 * 16); hi = min(MIN_Y + HEIGHT, -(-hi // 16) * 16)
    return {"height": hi - lo, "min_y": lo}

def main():
    layout = json.loads((ROOT / "layout" / "islands.json").read_text())
    islands = layout["islands"]
    for n, i in enumerate(islands):
        i["key"] = f"{n:03d}_{i['id'].lower()}"
        if pack_biome(i) != i["biome"]: i["layout_biome"], i["biome"] = i["biome"], pack_biome(i)
    for a, b in BIOME_SUBSTITUTE.items():
        print(f"{a} -> {b} on {sum(1 for i in islands if i.get('layout_biome') == a)} islands")
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
        if stack: return choice(ref(f"dist/{i['key']}"), 0, i["radius"] + PAD, val, 0)
        # The biome ends BIOME_MARGIN blocks past the island's own rim (enough for the colour blending and the ragged
        # edge) instead of at the full radius: the rim is drawn in by up to a fifth of the radius, and every empty
        # column inside the biome is a place where a structure can start with nothing under it.
        return choice(ref(f"edge/{i['key']}"), -BIOME_MARGIN / i["radius"], 2, val, 0)
    write(f"data/{NS}/worldgen/density_function/biome_code.json",
          add(VOID, grid(mains, lambda hit: fold(add, [biome_term(i) for i in hit]) if hit else 0)))

    # --- noise settings, surface rule, dimension
    final = add(mc("squeeze", input=mc("interpolated", cell_size_xz=CELL_XZ, cell_size_y=CELL_Y,
                input=mul(mc("blend_density", input=ref("terrain")), 0.64))), mc("beardifier"))
    write(f"data/{NS}/worldgen/noise_settings/isles.json", {
        "default_block": "minecraft:stone", "default_fluid": "minecraft:water", "disable_mob_generation": False,
        "legacy_random_source": False, "material_rule": ref("isles"), "noise": noise_range(islands),
        "noise_router": {"chunk_surface_level": 0.0, "continents": 0.0, "depth": 0.0, "erosion": 0.0, "ridges": 0.0,
                         "vegetation": 0.0, "temperature": ref("biome_code"), "final_density": final},
        "sea_level": MIN_Y, "spawn_target": []})
    # The vanilla overworld only runs its surface rule near the surface (above_preliminary_surface). Without a limit the
    # badlands branch turns a whole column into terracotta bands, and the band lookup throws below y -192
    # (ArrayIndexOutOfBoundsException in MaterialSystem.getBand), which kills chunk generation there.
    near_surface = {"type": "minecraft:stone_depth", "offset": SURFACE_RULE_DEPTH, "add_surface_depth": True,
                    "secondary_depth_range": 0, "surface_type": "floor"}
    write(f"data/{NS}/worldgen/material_rule/isles.json", {"type": "minecraft:sequence", "sequence": [
        {"type": "minecraft:condition", "if_true": near_surface, "then_run": "minecraft:overworld/surface"}]})
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
    # --- no snow line: rainy biomes stay rainy at any altitude
    warm = [b for b in biomes if (d := climate_biome(b)) and not write(f"data/minecraft/worldgen/biome/{b}.json", d)]
    print(f"{len(warm)} of {len(biomes)} biomes get a constant climate")
    # --- vanilla features with a hard-coded height
    # Ice spikes fill the 3x3 columns under their base with packed ice down to y 50 while they meet air: at the rim of an
    # island that is a pillar hanging hundreds of blocks into the void. Only place them where all nine columns have rock.
    # (the fill also passes through snow and dirt, so ask for rock under the soil)
    under = [{"type": "minecraft:matching_block_tag", "tag": "minecraft:base_stone_overworld", "offset": [dx, -7, dz]}
             for dx in (-1, 0, 1) for dz in (-1, 0, 1)]
    write("data/minecraft/worldgen/placed_feature/ice_spike.json", {"feature": "minecraft:ice_spike", "placement": [
        mc("count", count=3), mc("in_square"), mc("heightmap", heightmap="MOTION_BLOCKING"),
        mc("block_predicate_filter", predicate={"type": "minecraft:all_of", "predicates": under}), mc("biome")]})
    # Icebergs are built at the generator's sea level, which here is the bottom of the world: under the frozen ocean
    # islands they would float at y -2032. Off until those islands hold water.
    for name in ("iceberg_packed", "iceberg_blue"):
        write(f"data/minecraft/worldgen/placed_feature/{name}.json", {"feature": f"minecraft:{name}", "placement": [mc("count", count=0)]})
    # --- structures follow the islands
    for name, how in structures(islands, biomes).items(): print(f"structure {name}: {how}")
    # --- ores follow the island surface
    for name, feature, count, d0, d1 in ORES:
        write(f"data/minecraft/worldgen/placed_feature/{name}.json", ore_placement(f"minecraft:{feature}", count, d0, d1, "minecraft:biome"))
    if OUT_MODS.exists(): shutil.rmtree(OUT_MODS)
    write("pack.mcmeta", {"pack": {"description": "The Isles - ores of Create, Create Nuclear and Gunsmithing follow the islands",
                                   "pack_format": 121, "min_format": [121, 0], "max_format": [121, 0]}}, OUT_MODS)
    for ns, name, feature, count, d0, d1, last in MOD_ORES:
        write(f"data/{ns}/worldgen/placed_feature/{name}.json", ore_placement(feature, count, d0, d1, last), OUT_MODS)
    files = sum(1 for p in OUT.rglob("*") if p.is_file())
    print(f"{len(islands)} islands, {len(biomes)} biomes, {files} files -> {OUT}")

if __name__ == "__main__":
    main()
