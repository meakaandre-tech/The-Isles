#!/usr/bin/env python3
"""Builds the The Isles data pack (Minecraft Java 26.3, pack format 121) from layout/islands.json.

Every island in the layout becomes a set of flat (x/z) density functions; per layer of islands that do not touch,
one function turns them into terrain (see terrain()). Biomes are assigned per island through the multi-noise
"temperature" input, which carries a per-island code.
"""
import fnmatch, json, math, os, shutil, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import providers as prov
import build_terrain as bt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "datapack"            # the pack with vanilla biomes: committed, released
OUT_MODS = ROOT / "datapack-mods"
BUILD = ROOT / "build"             # the pack with the biomes of the providers in vendor/: never committed (see README)
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
def bid(b): return b if ":" in b else f"minecraft:{b}"   # biomes are named without "minecraft:" in here; others keep their namespace
def bfile(b): return "data/{}/worldgen/biome/{}.json".format(*bid(b).split(":", 1))

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
def vanilla_biome(name): return json.loads((Path(__file__).parent / "vanilla_biome" / f"{name}.json").read_text())
def climate_biome(name, d=None):
    """the biome file with a climate that does not depend on the altitude, or None when nothing has to change; d: a
    provider's version of the biome (default: the vanilla one)"""
    d = d or vanilla_biome(name)
    if d["temperature"] < 0.15 or d.get("temperature_modifier") == "frozen": return None
    if not d["has_precipitation"]:
        # Dry biomes (desert, savanna, badlands: 2.0) get no snow, but water freezes by the same altitude rule: above y -535 a
        # village's well and farm water were ice. Their colours are those of temperature 1 and more, which WARM is too.
        if d["temperature"] < 1.0: return None
        d["temperature"] = WARM; return d
    grass, foliage, dry = json.loads((Path(__file__).parent / "vanilla_biome_colors.json").read_text())[name]
    eff = d.setdefault("effects", {})
    eff.setdefault("grass_color", grass); eff.setdefault("foliage_color", foliage); eff.setdefault("dry_foliage_color", dry)
    d["temperature"] = WARM
    return d

def climate_other(d):
    """the same for a biome that is not a vanilla one (the cave world's): its colours are those of the vanilla biome with the
    same - or the nearest - temperature and downfall -> (file or None, name of that vanilla biome)"""
    if not d["has_precipitation"] or d["temperature"] < 0.15 or d.get("temperature_modifier") == "frozen": return None, None
    colors = json.loads((Path(__file__).parent / "vanilla_biome_colors.json").read_text())
    twin = min(sorted(colors), key=lambda n: (lambda v: (v["temperature"] - d["temperature"]) ** 2 + (v["downfall"] - d["downfall"]) ** 2)(vanilla_biome(n)))
    grass, foliage, dry = colors[twin]
    eff = d.setdefault("effects", {})
    eff.setdefault("grass_color", grass); eff.setdefault("foliage_color", foliage); eff.setdefault("dry_foliage_color", dry)
    d["temperature"] = WARM
    return d, twin

def mc(t, **kw): return {"type": f"minecraft:{t}", **kw}
def depth_mods(d0, d1):
    """placement modifiers that move a position (d0 + 16 * Binomial(n, 1/2) + 0..15) blocks under the top block of its column, at most d1"""
    down = lambda y: mc("offset", x=0, y=y, z=0)
    mods = [mc("heightmap", heightmap="OCEAN_FLOOR_WG")]
    base = d0 + 1                        # the heightmap is the first free block above the ground
    while base > 0:
        mods.append(down(-min(16, base))); base -= 16
    mods += [mc("randomly_selected", placements=[down(0), down(-16)])] * max(0, round((d1 - d0) / 16) - 1)
    return mods + [down({"type": "minecraft:uniform", "min_inclusive": -15, "max_inclusive": 0})]
def ore_placement(feature, count, d0, d1, last):
    """count attempts per chunk, each at a depth of depth_mods(d0, d1)"""
    mods = [mc("rarity_filter", chance=-count) if isinstance(count, int) and count < 0 else mc("count", count=count),
            mc("in_square")] + depth_mods(d0, d1) + [{"type": last}]
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

def tree(fn, items):
    """fold(fn, items) as a balanced tree (a chain of 200 nested functions is a deep recursion for the game's parser)"""
    items = list(items)
    while len(items) > 1: items = [fn(items[k], items[k + 1]) if k + 1 < len(items) else items[k] for k in range(0, len(items), 2)]
    return items[0]
def flat(f): return mc("slice", axis="y", coordinate=0, input=f)   # f only depends on x and z: computed once per column

def island_fields(i):
    """The parts of an island that only depend on x and z: (inside its footprint 1/0, surface height, bottom height, edge term).
    Its density is  clamp(min((surface - y) / 8, (y - bottom) / 12, edge) + 0.55 * rag, -1, 1)  inside the footprint and -1 outside.

    A sea basin (tools/build_terrain.py fills it with water): the rim rises to the island's top within 6 blocks and stays
    there, a ring at least RING blocks wide, 7 blocks above the water; inside the ring the floor drops by up to 0.3 of the
    thickness. Under the ring and the floor there are at least 26 blocks of rock from 10 blocks in from the rim."""
    R, top, t = i["radius"], i["y_top"], i["thickness"]
    basin = i["kind"] == "basin"
    sea = bt.basin_shape(i) if basin else None
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
    if basin:  # bowl: the rim ring stays up, the interior drops (a little less where the relief noise is low)
        surface = sub(sub(top, mul(rim, sub(1, clamp(mul(e, R / 6), 0, 1)))),
                      mul(mul(sea["depth"], clamp(mul(sub(e, sea["e0"]), 1 / sea["slope"]), 0, 1)), add(0.85, mul(0.15, RELIEF_N))))
    g = i.get("geyser_at")
    if g:   # level ground around the geyser, at the height layout/geysers.json gives
        gd = mc("distance_to_point", metric="euclidean", point=[g["x"], 0, g["z"]])
        pad = clamp(mul(sub(bt.PAD_R, gd), 1 / 6), 0, 1)
        surface = add(surface, mul(pad, sub(g["y"], surface)))
    write(f"data/{NS}/worldgen/density_function/surface/{i['key']}.json", mc("cache", input=surface))
    surface = ref(f"surface/{i['key']}")
    body = max(12, (t - amp - (sea["depth"] if basin else 0)) / 1.3)
    if basin: c = clamp(mul(e, 1 / 0.25), 0, 1)
    taper = add(mul(0.4, mc("sqrt", input=c)), mul(0.6, c))
    thick = mul(mul(body, taper), add(1, mul(0.3, UNDER)))
    if basin: thick = dmax(thick, mul(26, clamp(mul(e, R / 10), 0, 1)))
    bottom = sub(surface, thick)
    if g:   # rock under the chamber of the sulfur caves below the geyser, wherever the island is thin there
        floor = bt.pocket(g)["chamber"]["y"] - bt.CHAMBER_H - bt.FLOOR - 14
        bottom = sub(bottom, mul(clamp(mul(sub(2 * bt.PAD_R, gd), 1 / 8), 0, 1), clamp(sub(bottom, floor), 0, 1000)))
    write(f"data/{NS}/worldgen/density_function/inside/{i['key']}.json", mc("cache", input=choice(d, 0, R + PAD, 1, 0)))
    return ref(f"inside/{i['key']}"), surface, bottom, mul(e, R / 12)

def layers(islands):
    """groups of islands whose padded footprints do not touch (stacked tiers and the islets above an island go to further groups)"""
    out = []
    for i in sorted(islands, key=lambda i: -i["radius"]):
        for g in out:
            if all(math.hypot(i["x"] - j["x"], i["z"] - j["z"]) > i["radius"] + j["radius"] + 2 * PAD + 8 for j in g): g.append(i); break
        else: out.append([i])
    return out

def terrain(islands, nocave=()):
    """The density of the world: the highest of the layers' densities.

    The 26.3 density functions are evaluated for a whole chunk at once and nothing in them is skipped: a range_choice or
    an interval_select computes every branch for every point and then picks. A function per island therefore costs every
    chunk the sum of all 240 islands, wherever it is (measured: 60 to 80% of the generation time, void as much as land).
    So everything that only depends on x and z is combined per layer on one flat slice (25 points per chunk instead of
    12,725) - surface, bottom and edge of whichever island of the layer the column belongs to - and only the last step,
    the same for every island, runs on the whole chunk, once per layer. The values are the same as before."""
    BIG = 1000.0
    parts, levels = [], []
    hollow = bt.cave_noise(sys.modules[__name__])
    for n, group in enumerate(layers(islands)):
        group = sorted(group, key=lambda i: i["key"])
        f = {i["key"]: island_fields(i) for i in group}
        inside = [v[0] for v in f.values()]
        fields = {"surface": tree(add, [mul(v[0], v[1]) for v in f.values()]), "bottom": tree(add, [mul(v[0], v[2]) for v in f.values()]),
                  # the island's edge term inside a footprint, -BIG (nothing) outside
                  "edge": add(tree(add, [mul(v[0], v[3]) for v in f.values()]), mul(sub(tree(add, inside), 1), BIG))}
        # Caves (tools/build_terrain.py): the depth of the cave zone's roof under the surface, per island; it goes up through
        # the surface where the entrance noise is high. Islands without caves have no flat field at all.
        caved = [i for i in group if bt.has_caves(i, nocave)]
        pockets = [i for i in caved if i.get("geyser_at")]
        # (the chamber of the sulfur caves under a geyser: how near its axis a column is; the cave zone reaches up to it there)
        near = lambda i: clamp(mul(sub(bt.CHAMBER_R, mc("distance_to_point", metric="euclidean", point=[i["geyser_at"]["x"], 0, i["geyser_at"]["z"]])), 1 / 6), 0, 1)
        def ctop(i):
            """the top of an island's cave zone: under the height cave_top and 12 blocks under the ground; 16 blocks above the
            ground where the entrance noise is high"""
            S_i = f[i["key"]][1]
            base = dmin(sub(S_i, 12), float(bt.cave_top(sys.modules[__name__], i)))
            out = add(base, mul(ref("hollow/entrance"), sub(add(S_i, 16), base)))
            if i.get("geyser_at"): out = dmax(out, add(mul(near(i), add(sub(S_i, 16), 100000.0)), -100000.0))
            return out
        if caved:
            fields["ctop"] = tree(add, [mul(f[i["key"]][0], ctop(i) if bt.has_caves(i, nocave) else -100000.0) for i in group])
        if pockets:
            fields["pnear"] = tree(add, [mul(f[i["key"]][0], near(i)) for i in pockets])
            fields["py"] = tree(add, [mul(f[i["key"]][0], bt.pocket(i["geyser_at"])["chamber"]["y"]) for i in pockets])
        for i in group: levels.append((i, f[i["key"]]))
        for k, v in fields.items(): write(f"data/{NS}/worldgen/density_function/layer/{n}_{k}.json", flat(v))
        S, B, E = (ref(f"layer/{n}_{k}") for k in ("surface", "bottom", "edge"))
        solid = dmin(dmin(mul(sub(S, Y), 1 / 8), mul(sub(Y, B), 1 / 12)), E)
        part = clamp(add(solid, mul(0.55, RAG)), -1, 1)
        if caved:
            inner = dmin(dmin(sub(ref(f"layer/{n}_ctop"), Y), sub(sub(Y, B), bt.FLOOR)), sub(mul(E, 12.0), bt.SIDE))
            cave = hollow
            if pockets:
                band = clamp(mul(sub(bt.CHAMBER_H + 3, mc("abs", input=sub(Y, ref(f"layer/{n}_py")))), 1 / 3), 0, 1)
                cave = dmin(cave, sub(1.5, mul(3.0, mul(ref(f"layer/{n}_pnear"), band))))
            part = dmin(part, add(cave, mul(3.2, sub(1, clamp(mul(inner, 1 / bt.FADE), 0, 1)))))   # >= 1.7 (no effect) outside the zone
        parts.append(part)
        print(f"layer {n}: {len(group)} islands, {len(caved)} with caves")
    # The height above which the surface rule runs (the router's chunk_surface_level): one number per island, the lowest of
    # the islands of a column, far below everything where there is none (see build_terrain.surface_floor).
    low = tree(dmin, [choice(ref(f"dist/{i['key']}"), 0, i["radius"] + PAD, float(bt.surface_floor(sys.modules[__name__], i)), 100000.0) for i, v in levels])
    write(f"data/{NS}/worldgen/density_function/surface_level.json", flat(choice(low, -50000, 50000, low, float(MIN_Y - 64))))
    return tree(dmax, parts)

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
        "type": "minecraft:jigsaw", "biomes": [bid(b) for b in biomes], "dimension_padding": JIGSAW_PADDING,
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

# ---------------------------------------------------------------------------------------------------------------------
# Biome packs ("providers", tools/providers.py). Geophilic and Overrealm replace vanilla biome files; installed on top of
# The Isles they would undo the climate fix below (the world would be snow-covered again) and bring features that pick
# absolute heights. So the generator reads their files from vendor/ and writes the final biome files itself:
#   * per vanilla biome of the layout, the first provider of layout/biome_sources.json that ships it is used,
#   * that biome file gets the same treatment as a vanilla one (climate, pinned colours),
#   * the provider's own namespaces, tags and replaced vanilla features are copied, and every placement in them that
#     picks an absolute height is rewritten to a depth under the island surface (island_placement),
#   * what is built at the generator's sea level (icebergs: the bottom of the world here) is taken out of the biomes.
VANILLA_MIN, VANILLA_TOP, VANILLA_GROUND, MAX_DEPTH = -64, 319, 64, 128
SEA_LEVEL_FEATURES = {"minecraft:iceberg"}                                  # feature types built at the sea level
SEA_LEVEL_IDS = {"minecraft:iceberg_packed", "minecraft:iceberg_blue"}      # the vanilla features of those types
# a provider's files under data/minecraft/ that The Isles has to own; they are left out (and listed by the build)
OWNED = ("dimension/", "dimension_type/", "worldgen/noise_settings/", "worldgen/density_function/", "worldgen/world_preset/",
         "worldgen/multi_noise_biome_source_parameter_list/", "worldgen/structure/", "worldgen/structure_set/", "worldgen/biome/",
         "worldgen/material_rule/")
LEGACY = ("worldgen/configured_feature/", "tags/worldgen/configured_feature/", "worldgen/biome_overlays/")   # not read by 26.3

def vanilla_y(anchor):
    if "absolute" in anchor: return anchor["absolute"]
    if "above_bottom" in anchor: return VANILLA_MIN + anchor["above_bottom"]
    if "below_top" in anchor: return VANILLA_TOP - anchor["below_top"]
def height_span(h):
    """lowest and highest vanilla y of a height provider, None when it is not understood"""
    if not isinstance(h, dict): return None
    if "min_inclusive" in h and "max_inclusive" in h:
        lo, hi = vanilla_y(h["min_inclusive"]), vanilla_y(h["max_inclusive"])
        return None if lo is None or hi is None else (lo, hi)
    if "distribution" in h:
        spans = [height_span(e["data"]) for e in h["distribution"]]
        return None if None in spans else (min(s[0] for s in spans), max(s[1] for s in spans))
    y = vanilla_y(h.get("value", h))
    return None if y is None else (y, y)
ROCK_BELOW = mc("block_predicate_filter", predicate=mc("any_of", predicates=[
    mc("matching_block_tag", tag="minecraft:base_stone_overworld", offset=[0, -k, 0]) for k in (1, 2, 3, 4, 6, 8, 10, 12, 14, 16)]))
def island_placement(obj, log):
    """Rewrites, in place and at any depth of obj, every placement list with a height_range: a height y of the vanilla
    world becomes (64 - y) blocks under the island surface (at most MAX_DEPTH; the distribution becomes roughly uniform),
    like the pack's ores. The position must have rock within 16 blocks under it: a thin island ends above the depth asked
    for, and nothing may be placed in the open under it."""
    if isinstance(obj, list):
        for v in obj: island_placement(v, log)
    elif isinstance(obj, dict):
        pl = obj.get("placement")
        if "feature" in obj and isinstance(pl, list):
            out = []
            for m in pl:
                span = height_span(m.get("height")) if m.get("type") == "minecraft:height_range" else None
                if m.get("type") == "minecraft:height_range" and span is None: log["not understood"] = log.get("not understood", 0) + 1
                if span is None: out.append(m); continue
                d0 = min(MAX_DEPTH - 16, max(0, VANILLA_GROUND - span[1])); d1 = min(MAX_DEPTH, max(d0 + 16, VANILLA_GROUND - span[0]))
                out += depth_mods(d0, d1) + [ROCK_BELOW]; log["moved"] = log.get("moved", 0) + 1
            obj["placement"] = out
        for v in obj.values(): island_placement(v, log)

class Sources:
    """which pack every biome comes from: layout/biome_sources.json and the providers found in vendor/"""
    def __init__(self, packs):
        cfg = json.loads((ROOT / "layout" / "biome_sources.json").read_text())
        self.order, self.overrides, self.drop = cfg["order"], cfg.get("biomes", {}), cfg.get("drop_features", [])
        self.by_island = cfg.get("islands", {})
        cw = cfg.get("cave_world") or {}
        self.cave, self.cave_island = packs.get(cw.get("provider")), cw.get("island", "S1")   # tools/build_caves.py
        self.packs = {k: v for k, v in packs.items() if v.biomes()}
        self.has = {k: set(v.biomes()) for k, v in self.packs.items()}
        self.warnings = []
        for pid in self.order:
            if pid != "vanilla" and pid not in prov.manifest(): self.warnings.append(f"'{pid}' in the order is not in layout/providers.json")
            elif pid != "vanilla" and pid not in self.packs: self.warnings.append(f"{pid} is not in vendor/: its biomes fall through to the next provider")
        for pid, p in self.packs.items():
            if not p.supports: self.warnings.append(f"{pid} ({p.path.name}) is for pack format {p.format[0]}..{p.format[1]}, not {prov.FORMAT}")
            elif not p.tested: self.warnings.append(f"{pid} ({p.path.name}) is not the version this was tested with ({p.meta.get('version')})")
    def target(self, i):
        """another biome id for an island, asked for in biome_sources.json: "islands": {"A6": "orealm:x"} for one island,
        "biomes": {"minecraft:forest": "orealm:x"} for every island of a layout biome. Any id works that is a vanilla
        biome or a biome file of a provider in vendor/; otherwise the island keeps its biome (with a warning).
        -> the biome as the generator names it, or None"""
        lay = i.get("layout_biome", i["biome"])
        want = self.by_island.get(i["id"])
        if want is None:
            for k in (lay, i["biome"]):
                v = self.overrides.get(f"minecraft:{k}", self.overrides.get(k))
                if v is not None and ":" in v: want = v; break
        if want is None: return None
        if want.startswith("minecraft:") and (Path(__file__).parent / "vanilla_biome" / f"{want[10:]}.json").exists(): return want[10:]
        if not want.startswith("minecraft:") and any(bfile(want) in p.files for p in self.packs.values()): return want
        w = f"{want} (asked for in biome_sources.json) is not a vanilla biome and no pack in vendor/ has it: {lay} is kept"
        if w not in self.warnings: self.warnings.append(w)
        return None
    def of(self, biome):
        if ":" in biome:   # a biome of a provider's own namespace
            return next(pid for pid in self.order + sorted(self.packs) if pid in self.packs and bfile(biome) in self.packs[pid].files)
        want = self.overrides.get(f"minecraft:{biome}", self.overrides.get(biome))
        if want is not None and ":" in want: want = None   # (a biome id, see target)
        if want is not None:
            if want == "vanilla" or biome in self.has.get(want, ()): return want
            self.warnings.append(f"{biome}: {want} asked for in biome_sources.json but it does not ship that biome (or is not in vendor/)")
        for pid in self.order:
            if pid == "vanilla" or biome in self.has.get(pid, ()): return pid
        return "vanilla"
    def lookup(self, pid, kind, name):
        """a worldgen file of a provider by id, None when it is not the provider's"""
        ns, path = name.split(":", 1) if ":" in name else ("minecraft", name)
        return self.packs[pid].json(f"data/{ns}/worldgen/{kind}/{path}.json")
    def at_sea_level(self, pid, placed, seen=None):
        """does this placed feature (or anything it selects from) build at the generator's sea level"""
        seen = seen if seen is not None else set()
        def walk(o):
            if isinstance(o, str):
                if o in SEA_LEVEL_IDS: return True
                if o in seen or ":" not in o: return False
                seen.add(o)
                return any(walk(d) for d in (self.lookup(pid, "placed_feature", o), self.lookup(pid, "feature", o)) if d is not None)
            if isinstance(o, dict): return o.get("type") in SEA_LEVEL_FEATURES or any(walk(v) for v in o.values())
            if isinstance(o, list): return any(walk(v) for v in o)
            return False
        return walk(placed)
    def biome(self, pid, name):
        """the provider's biome file without the features that cannot work here -> (file, [features taken out])"""
        d = self.packs[pid].json(bfile(name)); gone = []
        for step in d["features"]:
            for f in list(step):
                if any(fnmatch.fnmatch(f, pat) for pat in self.drop) or (not f.startswith("minecraft:") and self.at_sea_level(pid, f)):
                    step.remove(f); gone.append(f)
        return d, gone
    def copy(self, used):
        """the providers' own content into the pack (lowest priority first, so the first of the order wins a shared file)"""
        log = {}
        for pid in [p for p in reversed(self.order) if p in used and p in self.packs]:
            n = skipped = 0; moved = {}
            for rel, data in sorted(self.packs[pid].files.items()):
                ns, sub = rel.split("/", 2)[1:]
                if any(sub.startswith(x) for x in LEGACY): continue
                if ns == "minecraft" and any(sub.startswith(x) for x in OWNED):
                    if not sub.startswith("worldgen/biome/"): skipped += 1; self.warnings.append(f"{pid} ships {rel}: left out (The Isles owns it)")
                    continue
                p = OUT / rel; p.parent.mkdir(parents=True, exist_ok=True)
                if rel.endswith(".json"):
                    try: d = json.loads(data)
                    except ValueError: self.warnings.append(f"{pid}: {rel} is not valid JSON, left out"); continue
                    if sub.startswith(("worldgen/placed_feature/", "worldgen/feature/")): island_placement(d, moved)
                    if sub.startswith("tags/") and p.exists():   # two providers add to the same tag
                        old = json.loads(p.read_text())
                        if not d.get("replace"): d["values"] = old["values"] + [v for v in d["values"] if v not in old["values"]]
                    p.write_text(json.dumps(d, indent=1) + "\n")
                else: p.write_bytes(data)
                n += 1
            log[pid] = (n, moved)
        return log

def pack_zip(src, dst):
    """a zip of a pack folder that does not change when its files do not"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(p for p in src.rglob("*") if p.is_file()):
            z.writestr(zipfile.ZipInfo(f.relative_to(src).as_posix(), (2026, 1, 1, 0, 0, 0)), f.read_bytes(), zipfile.ZIP_DEFLATED)

def main():
    """datapack/ with the vanilla biomes, then - when vendor/ holds a provider - build/the-isles/ with theirs"""
    global OUT
    build(None)
    shutil.rmtree(BUILD, ignore_errors=True)
    want = os.environ.get("ISLES_PROVIDERS")   # none | a comma-separated list | unset: everything in vendor/
    packs = {} if want == "none" else prov.load(set(want.split(",")) if want else None)
    src = Sources(packs)
    if not src.packs and not src.cave:
        print("no provider in vendor/ (or ISLES_PROVIDERS=none): vanilla biomes only"); return
    OUT = BUILD / "the-isles"
    try: build(src)
    finally: OUT = ROOT / "datapack"
    pack_zip(BUILD / "the-isles", BUILD / "the-isles.zip"); pack_zip(OUT_MODS, BUILD / "the-isles-mods.zip")
    print(f"with provider biomes -> {BUILD / 'the-isles.zip'} (for your own worlds; not to be redistributed)")

def build(src):
    layout = json.loads((ROOT / "layout" / "islands.json").read_text())
    islands = layout["islands"]
    for n, i in enumerate(islands):
        i["key"] = f"{n:03d}_{i['id'].lower()}"
        if pack_biome(i) != i["biome"]: i["layout_biome"], i["biome"] = i["biome"], pack_biome(i)
    for a, b in BIOME_SUBSTITUTE.items():
        print(f"{a} -> {b} on {sum(1 for i in islands if i.get('layout_biome') == a)} islands")
    me = sys.modules[__name__]
    for i in islands:   # sulfur geysers (the "geyser" flags of the layout): the ground is levelled around them
        g = bt.geyser(me, i, layout, islands)
        if g: i["geyser_at"] = g
    if OUT.exists(): shutil.rmtree(OUT)

    replaced = {}   # biome ids asked for in biome_sources.json -> the layout biomes they stand in for
    for i in islands:
        t = src.target(i) if src else None
        if t and t != i["biome"]:
            i.setdefault("layout_biome", i["biome"]); replaced.setdefault(t, set()).add(i["biome"]); i["biome"] = t
    for t, was in sorted(replaced.items()):
        print(f"{bid(t)} instead of {' '.join(sorted(was))} on {sum(1 for i in islands if i['biome'] == t and 'layout_biome' in i)} islands (biome_sources.json)")
    SULFUR = "sulfur_caves"
    assert not any(i["biome"] == SULFUR for i in islands)
    # (the rim ring of a sea basin has a shore biome, see biome_term)
    biomes = sorted({i["biome"] for i in islands} | {bt.shore_biome(i) for i in islands if bt.is_basin(i)})
    source = {b: src.of(b) if src else "vanilla" for b in biomes}
    used = sorted(set(source.values()) - {"vanilla"})
    if src:   # the providers' own files first: whatever the generator writes after this replaces theirs
        for pid, (n, moved) in src.copy(used).items():
            print(f"{pid} ({src.packs[pid].path.name}): {n} files copied, {moved.get('moved', 0)} fixed-height placements moved under the island surface"
                  + (f", {moved['not understood']} height ranges NOT understood" if moved.get("not understood") else ""))
    code = {b: round(-1.8 + 0.07 * k, 4) for k, b in enumerate(biomes + [SULFUR], 1)}
    VOID = -1.8
    assert max(code.values()) < 1.95

    credit = "".join(f"\n{src.packs[p].meta['name']} biomes by {src.packs[p].meta['author']}" for p in used)
    write("pack.mcmeta", {"pack": {"description": "The Isles - hand-placed floating island world" + (credit + "\nown use only, not for redistribution" if used else ""),
                                   "pack_format": 121, "min_format": [121, 0], "max_format": [121, 0]}})
    # --- noises
    for name, octave, count in [("edge", -7, 3), ("relief", -7, 4), ("under", -5, 3), ("rag", -5, 3)]:
        write(f"data/{NS}/worldgen/noise/{name}.json", {"base_octave": octave, "octave_count": count})
        write(f"data/{NS}/worldgen/density_function/noise/{name}.json",
              mc("cache", input=mc("noise", noise=ref(name), xz_scale=1.0, y_scale=1.0 if name == "rag" else 0.0)))
    for axis in "xz":
        write(f"data/{NS}/worldgen/density_function/{axis}.json",
              mc("gradient", axis=axis, from_coordinate=-100000, to_coordinate=100000, from_value=-100000.0, to_value=100000.0))
    # --- islands
    for i in islands: write(f"data/{NS}/worldgen/density_function/dist/{i['key']}.json", dist_fn(i))
    land = terrain(islands, nocave={src.cave_island} if src and src.cave else ())
    caves = None
    if src and src.cave:   # the cave world inside the spawn island (tools/build_caves.py)
        import build_caves
        caves = build_caves.Caves(sys.modules[__name__], src.cave, layout, islands, src.cave_island)
        land = caves.carve(land); caves.files()
    write(f"data/{NS}/worldgen/density_function/terrain.json", land)

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
        if bt.is_basin(i):
            # A sea basin: the sea's biome only inside the rim ring; the ring and the margin past the rim are a shore biome.
            # The sea is filled by features of the sea biome (tools/build_terrain.py): no column outside the ring gets water.
            return choice(ref(f"edge/{i['key']}"), bt.basin_shape(i)["e_sea"], 2, val,
                          choice(ref(f"edge/{i['key']}"), -BIOME_MARGIN / i["radius"], 2, code[bt.shore_biome(i)] - VOID, 0))
        # The biome ends BIOME_MARGIN blocks past the island's own rim (enough for the colour blending and the ragged
        # edge) instead of at the full radius: the rim is drawn in by up to a fifth of the radius, and every empty
        # column inside the biome is a place where a structure can start with nothing under it.
        return choice(ref(f"edge/{i['key']}"), -BIOME_MARGIN / i["radius"], 2, val, 0)
    def has_stack(i): return i["id"] == i["cluster"] + "1" and i["cluster"] in tiers
    # one flat slice for the islands with one biome (through the grid: a single lookup, as /locate does, only computes its
    # own cell), and the three stacks, whose biome changes with the height
    # Below the lowest island everything is void biome: a structure that starts over an empty column gets the bottom of
    # the world as its height, and with the island's biome there it would be built on the world floor (igloos, treasure).
    floor = min(i["y_bottom"] for i in islands) - 64
    base = tree(add, [flat(grid([i for i in mains if not has_stack(i)], lambda hit: tree(add, [biome_term(i) for i in hit]) if hit else 0))]
                     + [biome_term(i) for i in mains if has_stack(i)])
    # The pockets of sulfur caves under the geysers (cylinders): which columns are in one and at which height its middle is
    # are flat fields; per point there is only the test of the height. (The game fills a chunk's biomes for all its points
    # at once and computes every branch: with the pockets as branches by height of the lookup above, every chunk took a
    # quarter longer to generate, void included.)
    pk = [bt.pocket(i["geyser_at"]) for i in mains if i.get("geyser_at")]
    if pk:
        inside = lambda p: choice(mc("distance_to_point", metric="euclidean", point=[p["x"], 0, p["z"]]), 0, p["radius"], 1, 0)
        write(f"data/{NS}/worldgen/density_function/pocket/inside.json", flat(tree(add, [inside(p) for p in pk])))
        write(f"data/{NS}/worldgen/density_function/pocket/middle.json", flat(tree(add, [mul(inside(p), (p["y_min"] + p["y_max"]) / 2) for p in pk])))
        half = (pk[0]["y_max"] - pk[0]["y_min"]) / 2
        q = mul(ref("pocket/inside"), clamp(mul(sub(half, mc("abs", input=sub(Y, ref("pocket/middle")))), 1000.0), 0, 1))
        base = add(mul(sub(1, q), base), mul(q, code[SULFUR] - VOID))
    write(f"data/{NS}/worldgen/density_function/biome_code.json", add(VOID, mul(choice(Y, floor, 100000, 1, 0), base)))

    # --- noise settings, surface rule, dimension
    final = add(mc("squeeze", input=mc("interpolated", cell_size_xz=CELL_XZ, cell_size_y=CELL_Y,
                input=mul(mc("blend_density", input=ref("terrain")), 0.64))), mc("beardifier"))
    router = {"chunk_surface_level": ref("surface_level"), "continents": 0.0, "depth": 0.0, "erosion": 0.0, "ridges": 0.0,
              "vegetation": 0.0, "temperature": ref("biome_code"), "final_density": final}
    if caves: caves.router(router)
    write(f"data/{NS}/worldgen/noise_settings/isles.json", {
        "default_block": "minecraft:stone", "default_fluid": "minecraft:water", "disable_mob_generation": False,
        "legacy_random_source": False, "material_rule": ref("isles"), "noise": noise_range(islands),
        "noise_router": router, "sea_level": MIN_Y, "spawn_target": []})
    # The vanilla overworld only runs its surface rule near the surface (above_preliminary_surface). Without a limit the
    # badlands branch turns a whole column into terracotta bands, and the band lookup throws below y -192
    # (ArrayIndexOutOfBoundsException in MaterialSystem.getBand), which kills chunk generation there.
    near_surface = {"type": "minecraft:stone_depth", "offset": SURFACE_RULE_DEPTH, "add_surface_depth": True,
                    "secondary_depth_range": 0, "surface_type": "floor"}
    # With caves inside the islands the rule must not run on cave floors (grass, sand, terracotta in the dark): it only runs
    # above the "preliminary surface" of the column, which the router gets as one height per island, under the lowest ground
    # of its relief (terrain(), build_terrain.surface_floor). Caves start below it.
    sulfur_biome, sulfur_rule = bt.sulfur(me, islands, layout)
    write(f"data/{NS}/worldgen/material_rule/isles.json", {"type": "minecraft:sequence", "sequence": ([caves.surface_rule()] if caves else []) +
        ([sulfur_rule] if sulfur_rule else []) + [
        {"type": "minecraft:condition", "if_true": {"type": "minecraft:above_preliminary_surface"},
         "then_run": {"type": "minecraft:condition", "if_true": near_surface, "then_run": "minecraft:overworld/surface"}}]})
    bt.surface(me, islands)
    if sulfur_biome: write(bfile(SULFUR), sulfur_biome)
    sea_features = bt.seas(me, islands)
    bt.springs(me)
    # the game's cave carvers tunnel through anything, undersides and sea floors included: off (the caves are in the terrain)
    for f in sorted((Path(__file__).parent / "vanilla_carver").glob("*.json")):
        write(f"data/minecraft/worldgen/carver/{f.name}", {**json.loads(f.read_text()), "probability": 0.0})
    write(f"data/{NS}/worldgen/biome/void.json", {
        "attributes": {"minecraft:gameplay/natural_mob_spawns": {"argument": {"spawn_costs": {}, "spawns_by_category": {
            k: [] for k in ["ambient", "axolotls", "creature", "misc", "monster", "underground_water_creature", "water_ambient", "water_creature"]}},
            "modifier": "overlay"}, "minecraft:visual/sky_color": "#78a7ff"},
        "carvers": [], "downfall": 0.5, "effects": {"water_color": "#3f76e4"}, "features": [], "has_precipitation": False, "temperature": 0.5})
    def point(c):
        p = {"temperature": [round(c - 0.03, 4), round(c + 0.03, 4)], "humidity": 0, "continentalness": 0, "erosion": 0, "weirdness": 0, "depth": 0, "offset": 0}
        return caves.island_point(p) if caves else p
    entries = [{"biome": VOID_BIOME, "parameters": point(VOID)}] + [{"biome": bid(b), "parameters": point(code[b])} for b in biomes + ([SULFUR] if sulfur_biome else [])]
    if caves:
        entries += caves.entries()
        for l in caves.log: print(l)
    write("data/minecraft/dimension/overworld.json", {"type": "minecraft:overworld", "generator": {
        "type": "minecraft:noise", "biome_source": {"type": "minecraft:multi_noise", "biomes": entries}, "settings": ref("isles")}})
    dim = json.loads((Path(__file__).parent / "vanilla_overworld_dimension_type.json").read_text())
    dim.update(min_y=MIN_Y, height=HEIGHT, logical_height=HEIGHT)
    # Look. Below y 63 the game draws a black disc over the lower half of the sky (the horizon of a non-flat world is
    # hard-coded in the client), and islands are down to y -1350. The sky is drawn through the sky fog: with the fog
    # ending a few blocks out, the whole dome, the disc included, takes the fog colour at every altitude.
    dim["attributes"].update({"minecraft:visual/sky_fog_end_distance": SKY_FOG_END, "minecraft:visual/fog_color": FOG_COLOR,
                              "minecraft:visual/cloud_height": CLOUD_HEIGHT})
    write("data/minecraft/dimension_type/overworld.json", dim)
    # --- no snow line: rainy biomes stay rainy at any altitude
    warm = []
    for b in biomes:
        d, gone = src.biome(source[b], b) if source[b] != "vanilla" else (None, [])
        if ":" in b:   # a provider's own biome: constant climate, colours of the nearest vanilla climate
            if gone: print(f"{b} ({source[b]}): taken out {' '.join(gone)}")
            c, twin = climate_other(d)
            if c: warm.append(b); print(f"{b} ({source[b]}): constant climate, colours of {twin} where it sets none")
            c = c or d
            if b in sea_features: c["features"] = c["features"] + [[]] * (1 - len(c["features"])); c["features"][0] = sea_features[b] + c["features"][0]
            write(bfile(b), c); continue
        if d is not None:
            v = vanilla_biome(b)
            odd = (d["temperature"], d["downfall"]) != (v["temperature"], v["downfall"]) and not {"grass_color", "foliage_color"} <= set(d.get("effects", {}))
            if gone: print(f"{b} ({source[b]}): taken out {' '.join(gone)}")
        c = climate_biome(b, d)
        extra = caves.surface_features() if caves and b == caves.island["biome"] else []
        if extra:   # (the water of the sinkholes: after everything else of the biome at the cave island's surface)
            c = c or d or vanilla_biome(b); c["features"] = c["features"] + [[]] * (11 - len(c["features"])); c["features"][10] = c["features"][10] + extra
        if b in sea_features:   # the water of the sea basins, before everything that grows in it
            c = c or d or vanilla_biome(b); c["features"] = c["features"] + [[]] * (1 - len(c["features"])); c["features"][0] = sea_features[b] + c["features"][0]
        if c and d and odd: src.warnings.append(f"{b} ({source[b]}): temperature/downfall differ from vanilla and the colours are not set; the vanilla colours are pinned")
        if c: warm.append(b)
        if c or d: write(f"data/minecraft/worldgen/biome/{b}.json", c or d)
    print(f"{len(warm)} of {len(biomes)} biomes get a constant climate")
    # A provider's own biome is in none of the vanilla biome tags (structures, mob rules and the mods' ores go by them),
    # unless its pack says so: it joins the tags of the layout biomes it stands in for.
    member = json.loads((Path(__file__).parent / "vanilla_biome_tags.json").read_text()); join = {}
    for t, was in replaced.items():
        if ":" in t:
            for tag in {tag for w in was for tag in member.get(w, [])}: join.setdefault(tag, []).append(t)
    for tag, ids in sorted(join.items()):
        ns, name = tag.split(":", 1); p = OUT / f"data/{ns}/tags/worldgen/biome/{name}.json"
        old = json.loads(p.read_text()) if p.exists() else {"values": []}
        old["values"] += [v for v in sorted(ids) if v not in old["values"]]
        write(f"data/{ns}/tags/worldgen/biome/{name}.json", old)
    if src:
        n = {b: sum(1 for i in islands if i["biome"] == b) for b in biomes}
        print("biome -> provider (islands)")
        for pid in src.order:
            mine = [b for b in biomes if source[b] == pid]
            print(f"  {pid}: {len(mine)} biomes, {sum(n[b] for b in mine)} islands: " + " ".join(f"{b}({n[b]})" for b in mine))
        for pid, has in src.has.items():
            lost = sorted(b for b in has & set(biomes) if source[b] != pid)
            if lost: print(f"  {pid} also ships, not used: {' '.join(lost)}")
        for w in src.warnings: print(f"WARNING: {w}")
    # Snow and ice: freeze_top_layer has no placement but a biome check, which the game makes at the bottom of the chunk -
    # void biome there (see biome_code). Without the check the feature still decides column by column from the biome at
    # the surface.
    write("data/minecraft/worldgen/placed_feature/freeze_top_layer.json", {"feature": "minecraft:freeze_top_layer", "placement": []})
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
    # --- the Nether: stacked layers over the same height (tools/build_nether.py)
    import build_nether
    build_nether.build(write, OUT_MODS)
    files = sum(1 for p in OUT.rglob("*") if p.is_file())
    print(f"{len(islands)} islands, {len(biomes)} biomes, {files} files -> {OUT}")

if __name__ == "__main__":
    main()
