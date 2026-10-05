#!/usr/bin/env python3
"""Generates the probe data pack and the server console command files of the pack test from layout/islands.json.

  python3 packtest/gen.py <out-dir>

Writes <out-dir>/probes/ (a data pack with helper functions, namespace packtest) and
<out-dir>/commands-<name>.txt files that packtest/run.sh feeds to the server console.
Console directives understood by run.sh: "#sleep N", "#poll N command ## regex", "#wait N ## regex".
"""
import json, math, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1]
L = json.load(open(ROOT + '/layout/islands.json'))
sys.path.insert(0, ROOT + '/tools')
from build_pack import pack_biome
for i in L['islands']: i['biome'] = pack_biome(i)   # what the generated pack uses
I = {i['id']: i for i in L['islands']}
MIN_Y, TOP_Y = L['min_y'], L['min_y'] + L['height'] - 1
# packtest/quick: words naming the only sections to run while iterating (see the uses of on() below); no file = everything
QUICK = set(open(ROOT + '/packtest/quick').read().split()) if os.path.exists(ROOT + '/packtest/quick') else None
def on(name): return QUICK is None or name in QUICK

# islands that get probed: spawn, mountain tiers, sea basins, highest, lowest, edge, a "high" islet and a spread of biomes
by = lambda f: f(L['islands'], key=lambda i: i['y_top'])
SAMPLE = ['S1', 'S2', 'Sh4', 'P1', 'Pt2', 'Pt3', 'Q1', 'Qt2', 'Qt3', 'J1', 'Jt2', 'Jt3', 'D1', 'K1', by(max)['id'], by(min)['id'],
          max(L['islands'], key=lambda i: max(abs(i['x']), abs(i['z'])) + i['radius'])['id'],
          'C1', 'E1', 'F1', 'H1', 'R1', 'T1', 'e1', 'M1', 'N1', 'I1']
for b in ['mushroom_fields', 'ice_spikes', 'mangrove_swamp', 'cherry_grove', 'pale_garden', 'bamboo_jungle', 'savanna',
          'snowy_slopes', 'beach', 'stony_shore', 'frozen_peaks', 'eroded_badlands', 'windswept_hills']:
    c = [i for i in L['islands'] if i['biome'] == b and i['id'] not in SAMPLE]
    if c: SAMPLE.append(c[0]['id'])
SAMPLE = list(dict.fromkeys(SAMPLE))

def void_points(n=12):
    """points at least 120 blocks outside every island footprint, spread over the map"""
    pts = []
    for gx in range(-3600, 3601, 600):
        for gz in range(-3600, 3601, 600):
            if all(math.hypot(gx - i['x'], gz - i['z']) > i['radius'] + 120 for i in L['islands']): pts.append((gx, gz))
    step = max(1, len(pts) // n)
    return pts[::step][:n]

# ------------------------------------------------------------------ probe data pack
P = OUT + '/probes'; F = P + '/data/packtest/function'
os.makedirs(F, exist_ok=True)
json.dump({"pack": {"description": "The Isles pack test probes", "min_format": 121, "max_format": 121}}, open(P + '/pack.mcmeta', 'w'))
def fn(name, lines): open(f'{F}/{name}.mcfunction', 'w').write('\n'.join(lines) + '\n')

biomes = sorted({'minecraft:' + i['biome'] for i in L['islands']}) + ['the_isles:void']
fn('biome', [f'execute if biome ~ ~ ~ {b} run say BIOME {b}' for b in biomes] +
   ['execute ' + ' '.join(f'unless biome ~ ~ ~ {b}' for b in biomes) + ' run say BIOME other'])
TOPS = ['air', 'water', 'ice', 'packed_ice', 'blue_ice', 'snow', 'snow_block', 'powder_snow', 'grass_block', 'dirt', 'sand', 'red_sand', 'sandstone',
        'gravel', 'stone', 'deepslate', 'podzol', 'coarse_dirt', 'mud', 'mycelium', 'clay', 'calcite', 'lava', 'moss_block', 'pale_moss_block',
        'rooted_dirt', 'bedrock', 'andesite', 'granite', 'diorite', 'tuff']
TAGS = ['leaves', 'logs', 'terracotta', 'flowers', 'slabs']
for name, dy in (('top', -1), ('at', 0)):
    fn(name, [f'execute if block ~ ~{dy} ~ minecraft:{b} run say {name.upper()} {b}' for b in TOPS] +
       [f'execute if block ~ ~{dy} ~ #minecraft:{t} run say {name.upper()} #{t}' for t in TAGS] +
       ['execute ' + ' '.join([f'unless block ~ ~{dy} ~ minecraft:{b}' for b in TOPS] + [f'unless block ~ ~{dy} ~ #minecraft:{t}' for t in TAGS])
        + f' run say {name.upper()} other'])
# packtest:col - run at an x/z: says the ground height (first motion-blocking, leaves ignored), what is there and the biome
fn('col', ['kill @e[type=minecraft:marker,tag=pt]',
           'execute positioned over motion_blocking_no_leaves run summon minecraft:marker ~ ~ ~ {Tags:["pt"]}',
           'execute store result score y pt run data get entity @e[type=minecraft:marker,tag=pt,limit=1] Pos[1]',
           'execute positioned over world_surface run summon minecraft:marker ~ ~ ~ {Tags:["pt","ws"]}',
           'execute store result score ws pt run data get entity @e[type=minecraft:marker,tag=ws,limit=1] Pos[1]',
           'execute positioned over motion_blocking_no_leaves run function packtest:top',
           'execute positioned over motion_blocking_no_leaves if block ~ ~ ~ minecraft:snow run say SNOWLAYER',
           'execute positioned over motion_blocking_no_leaves run function packtest:biome',
           'kill @e[type=minecraft:marker,tag=pt]'])

def region_fn(name, cx0, cz0, cx1, cz1, dim=None):
    """packtest:count_<name> says "PREGEN <name> done" once every chunk of the region is loaded"""
    n = (cx1 - cx0 + 1) * (cz1 - cz0 + 1)
    pre = f'execute in {dim} ' if dim else 'execute '
    fn('count_' + name, ['scoreboard players set n pt 0'] +
       [f'{pre}if loaded {cx * 16} 0 {cz * 16} run scoreboard players add n pt 1' for cx in range(cx0, cx1 + 1) for cz in range(cz0, cz1 + 1)] +
       [f'execute if score n pt matches {n}.. run say PREGEN {name} done {n}'])
    return n

# ------------------------------------------------------------------ console commands
def probe(lines, tag, x, z, expect_biome=None):
    lines += [f'say PROBE {tag} {x} {z}', f'execute positioned {x} 0 {z} run function packtest:col',
              'scoreboard players get y pt', 'scoreboard players get ws pt']
    if expect_biome:
        lines += [f'execute positioned {x} 0 {z} positioned over motion_blocking_no_leaves if biome ~ ~ ~ minecraft:{expect_biome} run say BIOMEOK {tag}']

def island_probes(sample=None):
    c = ['say SECTION islands']
    for k in sample or SAMPLE:
        i = I[k]; x, z, R = i['x'], i['z'], i['radius']
        half = int(R * 0.5); out = R + 40
        c += [f'forceload add {x} {z} {x + half} {z}', f'forceload add {x + out} {z}', f'forceload add {x} {z + R + 4}',
              f'#poll 90 execute if loaded {x} 0 {z} if loaded {x + half} 0 {z} if loaded {x + out} 0 {z} if loaded {x} 0 {z + R + 4} run say LOADED {k} ## LOADED {k}']
        probe(c, f'{k} centre', x, z, i['biome'])
        probe(c, f'{k} half', x + half, z, i['biome'])
        probe(c, f'{k} outside', x + out, z)
        probe(c, f'{k} rim', x, z + R + 4)   # outside the terrain, inside the biome footprint: nothing may generate here
        # the body: what is 12 blocks under the ground at the centre, and at the layout's bottom
        c += [f'say BODY {k}', f'execute positioned {x} 0 {z} positioned over motion_blocking_no_leaves positioned ~ ~-12 ~ run function packtest:at',
              f'execute positioned {x} {i["y_bottom"] - 40} {z} run function packtest:at',
              # at the island's own altitude (stacked tiers share a column): block and biome in the middle of the body
              f'say MID {k} {i["y_top"] - i["thickness"] // 3}', f'execute positioned {x} {i["y_top"] - i["thickness"] // 3} {z} run function packtest:at',
              f'execute positioned {x} {i["y_top"] - i["thickness"] // 3} {z} run function packtest:biome',
              f'execute if biome {x} {i["y_top"] + 3} {z} minecraft:{i["biome"]} run say TOPBIOMEOK {k}',
              'forceload remove all']   # per island: 1,500 force-loaded chunks of this height do not fit in a 5 GB heap
    return c

def void_probes():
    c = ['say SECTION void']
    for n, (x, z) in enumerate(void_points()):
        c += [f'forceload add {x} {z}', f'#poll 120 execute if loaded {x} 0 {z} run say LOADED void{n} ## LOADED void{n}']
        probe(c, f'void{n} void', x, z)
        c += ['forceload remove all']
    return c

def limits():
    """build limits: blocks can be placed at the lowest and highest layer, not beyond"""
    x, z = 3900, 3900
    return ['say SECTION limits', f'forceload add {x} {z}', f'#poll 120 execute if loaded {x} 0 {z} run say LOADED limits ## LOADED limits',
            f'setblock {x} {MIN_Y} {z} minecraft:gold_block', f'execute if block {x} {MIN_Y} {z} minecraft:gold_block run say LIMIT bottom-ok {MIN_Y}',
            f'setblock {x} {TOP_Y} {z} minecraft:gold_block', f'execute if block {x} {TOP_Y} {z} minecraft:gold_block run say LIMIT top-ok {TOP_Y}',
            f'setblock {x} {MIN_Y - 1} {z} minecraft:gold_block', f'setblock {x} {TOP_Y + 1} {z} minecraft:gold_block',
            f'forceload remove {x} {z}']

def pregen(name, cx0, cz0, cx1, cz1, wait=900, after=()):
    """time to generate a region (forceload returns when the chunks are there), heap in use with it loaded, then drop it"""
    n = region_fn(name, cx0, cz0, cx1, cz1)
    return ['forceload remove all', '#sleep 20', f'#heap before-{name}', f'say PREGEN {name} start {n}', f'#prof {name} 12', f'#time PREGEN-{name}-{n}-chunks',
            f'forceload add {cx0 * 16} {cz0 * 16} {cx1 * 16} {cz1 * 16}',
            f'#poll {wait} function packtest:count_{name} ## PREGEN {name} done', '#time', f'#heap with-{name}', 'tick query'] + list(after) + ['forceload remove all']

REG_LAND = (20, -8, 35, 7)       # 16x16 chunks inside the spawn island (600 blocks of rock under them)
p = I['P1']; REG_TIER = (p['x'] // 16 - 4, p['z'] // 16 - 4, p['x'] // 16 + 3, p['z'] // 16 + 3)   # 8x8 chunks through three stacked tiers
v = void_points()[0]; REG_VOID = (v[0] // 16 - 8, v[1] // 16 - 8, v[0] // 16 + 7, v[1] // 16 + 7)

HEAD = ['say SECTION start', 'scoreboard objectives add pt dummy', 'gamerule max_block_modifications 100000000', 'gamerule respawn_radius 0', 'tick query']
ANIMALS = ['cow', 'sheep', 'pig', 'chicken', 'horse', 'rabbit', 'wolf', 'fox', 'llama', 'goat', 'frog', 'parrot', 'panda', 'camel', 'armadillo',
           'polar_bear', 'donkey', 'mooshroom', 'turtle', 'ocelot', 'cat']
def animals():
    return ['say SECTION animals'] + [x for a in ANIMALS for x in (f'say COUNT {a}', f'execute if entity @e[type=minecraft:{a}]')]

# structure -> a block that tells it from the terrain; None: the generator switches it off, /locate must find nothing
STRUCTS = [('the_isles:stronghold', 'minecraft:end_portal_frame'), ('minecraft:village_plains', '#minecraft:beds'), ('minecraft:trial_chambers', 'minecraft:tuff_bricks'),
           ('minecraft:ruined_portal', 'minecraft:obsidian'), ('minecraft:pillager_outpost', 'minecraft:dark_oak_planks'), ('minecraft:desert_pyramid', 'minecraft:chiseled_sandstone'),
           ('minecraft:shipwreck', '#minecraft:planks'), ('minecraft:ocean_ruin_warm', 'minecraft:cut_sandstone'), ('minecraft:ocean_ruin_cold', 'minecraft:stone_bricks'),
           ('minecraft:buried_treasure', 'minecraft:chest'), ('minecraft:igloo', 'minecraft:furnace'), ('minecraft:jungle_pyramid', 'minecraft:mossy_cobblestone'),
           ('minecraft:swamp_hut', 'minecraft:spruce_planks'), ('minecraft:trail_ruins', 'minecraft:suspicious_gravel'), ('minecraft:village_desert', '#minecraft:beds'),
           ('minecraft:ruined_portal_mountain', 'minecraft:obsidian'), ('minecraft:ruined_portal_ocean', 'minecraft:obsidian'),
           ('minecraft:stronghold', None), ('minecraft:mineshaft', None), ('minecraft:mineshaft_mesa', None), ('minecraft:monument', None), ('minecraft:mansion', None),
           ('minecraft:ancient_city', None)]
SEVERAL = {'the_isles:stronghold', 'minecraft:village_plains', 'minecraft:trial_chambers', 'minecraft:ruined_portal', 'minecraft:shipwreck'}
def structures():
    """/locate every Overworld structure (the common ones from three places), then look at what stands there: the ground of that
    column, the structure's blocks in the 5x5 chunks around it from 130 blocks below to 70 above that ground ("near"), in the rest of
    those columns from the bottom of the world to the top ("elsewhere": for a structure on a basin rim or a stacked tier that can be
    its own lower part), and how many of all of them lie in the lowest 200 layers ("floor", must be 0)."""
    c = ['say SECTION structures']
    origins = [('spawn', 0, 0), ('K1', I['K1']['x'], I['K1']['z']), ('T1', I['T1']['x'], I['T1']['z'])]
    for s, block in STRUCTS:
        for tag, ox, oz in (origins if s in SEVERAL else origins[:1]):
            k = f'{s.split(":")[1]}/{tag}' if s != 'the_isles:stronghold' else f'isles-stronghold/{tag}'   # ("@s" in a say command is a selector)
            c += [f'say LOCATE {k}', f'#time LOCATE-{k}', f'execute positioned {ox} 0 {oz} run locate structure {s}',
                  '#wait 180 ## is at \\[|Could not find|could not find|ERROR|Unknown|There is no structure', '#time', '#loc']
            if block is None: continue
            c += ['forceload add {X0} {Z0} {X1} {Z1}', '#poll 240 execute if loaded {X0} 0 {Z0} if loaded {X1} 0 {Z1} if loaded {LX} 0 {LZ} run say LOADED loc ## LOADED loc',
                  f'say PROBE ={k} structure {{LX}} {{LZ}}', 'execute positioned {LX} 0 {LZ} run function packtest:col', 'scoreboard players get y pt', 'scoreboard players get ws pt',
                  f'say SCAN {k} near {block}',
                  f'execute positioned {{LX}} 0 {{LZ}} positioned over motion_blocking_no_leaves run fill {{X0}} ~-130 {{Z0}} {{X1}} ~70 {{Z1}} minecraft:structure_void replace {block}',
                  f'say SCAN {k} elsewhere {block}', f'fill {{X0}} {MIN_Y} {{Z0}} {{X1}} {TOP_Y} {{Z1}} minecraft:structure_void replace {block}',
                  f'say SCAN {k} floor {block}', f'fill {{X0}} {MIN_Y} {{Z0}} {{X1}} {MIN_Y + 200} {{Z1}} minecraft:lime_wool replace minecraft:structure_void']
            if s == 'the_isles:stronghold':   # how deep the room is: the frames stand 28 blocks under the ground of their column
                c += [f'say SCAN {k} y-of-the-frames minecraft:structure_void'] + [
                    f'execute positioned {{LX}} 0 {{LZ}} positioned over motion_blocking_no_leaves run fill ~-40 ~{-10 * n - 10} ~-30 ~30 ~{-10 * n - 1} ~30 minecraft:end_portal_frame[eye=false] replace minecraft:structure_void'
                    for n in range(6)]
            c += ['forceload remove all']
    # what the old generator left on the world floor under the spawn island (stronghold at 176 1504, mineshaft at -48 -144)
    for tag, x, z, blocks in (('floor-under-old-stronghold', 176, 1504, ['minecraft:stone_bricks', 'minecraft:iron_bars']), ('floor-under-old-mineshaft', -48, -144, ['minecraft:oak_planks', 'minecraft:rail'])):
        x0, z0 = x // 16 * 16 - 64, z // 16 * 16 - 64
        c += [f'forceload add {x0} {z0} {x0 + 143} {z0 + 143}', f'#poll 240 execute if loaded {x0} 0 {z0} if loaded {x0 + 143} 0 {z0 + 143} run say LOADED {tag} ## LOADED {tag}']
        for b in blocks: c += [f'say SCAN {tag} y{MIN_Y}..{MIN_Y + 160} {b}', f'fill {x0} {MIN_Y} {z0} {x0 + 143} {MIN_Y + 160} {z0 + 143} minecraft:structure_void replace {b}']
        c += ['forceload remove all']
    # icebergs and ice spikes: packed ice under the frozen ocean island M5 at the bottom of the world, and under the ice spikes island e3 below its bottom
    m5, e3 = I['M5'], I['e3']
    c += [f'forceload add {m5["x"] - 40} {m5["z"] - 40} {m5["x"] + 40} {m5["z"] + 40}']
    for b in ('packed_ice', 'blue_ice', 'snow_block', 'ice'):
        c += [f'say SCAN M5-world-bottom-64 minecraft:{b}', f'fill {m5["x"] - 40} {MIN_Y} {m5["z"] - 40} {m5["x"] + 40} {MIN_Y + 64} {m5["z"] + 40} minecraft:structure_void replace minecraft:{b}',
              f'fill {m5["x"] - 40} {MIN_Y} {m5["z"] - 40} {m5["x"] + 40} {MIN_Y + 64} {m5["z"] + 40} minecraft:{b} replace minecraft:structure_void']
    c += ['forceload remove all', f'forceload add {e3["x"] - 60} {e3["z"] - 60} {e3["x"] + 60} {e3["z"] + 60}',
          f'say SCAN e3-below-the-island-y50..{e3["y_bottom"] - 30} minecraft:packed_ice',
          f'fill {e3["x"] - 60} 50 {e3["z"] - 60} {e3["x"] + 60} {e3["y_bottom"] - 30} {e3["z"] + 60} minecraft:structure_void replace minecraft:packed_ice',
          f'fill {e3["x"] - 60} 50 {e3["z"] - 60} {e3["x"] + 60} {e3["y_bottom"] - 30} {e3["z"] + 60} minecraft:packed_ice replace minecraft:structure_void',
          f'say SCAN e3-on-the-island minecraft:packed_ice',
          f'fill {e3["x"] - 60} {e3["y_bottom"] - 29} {e3["z"] - 60} {e3["x"] + 60} {e3["y_top"] + 60} {e3["z"] + 60} minecraft:structure_void replace minecraft:packed_ice',
          f'fill {e3["x"] - 60} {e3["y_bottom"] - 29} {e3["z"] - 60} {e3["x"] + 60} {e3["y_top"] + 60} {e3["z"] + 60} minecraft:packed_ice replace minecraft:structure_void',
          'forceload remove all']
    for b in ['minecraft:jagged_peaks', 'minecraft:mushroom_fields', 'the_isles:void']:
        c += [f'say LOCATE biome {b}', f'#time LOCATE-biome-{b.split(":")[1]}', f'locate biome {b}', '#wait 120 ## is at \\[|Could not find|could not find|ERROR', '#time']
    return c

def anomalies():
    """things earlier runs turned up: sand at y -15 over I1 (warm ocean basin, top y -300)"""
    c = ['say SECTION anomalies', 'forceload add -1273 3356 -1241 3388', 'say BODY I1-sand-column']
    c += [f'execute positioned -1257 {y} 3372 run function packtest:at' for y in (-14, -16, -20, -40, -80, -150, -250, -330, -366)]
    for b in ['sand', 'sandstone', 'water', 'stone', 'gravel', 'suspicious_sand', 'chest', 'oak_planks', 'spruce_planks', 'dark_oak_planks', 'prismarine', 'cut_sandstone']:
        c += [f'say SCAN I1-above-the-basin minecraft:{b}', f'fill -1289 -290 3340 -1226 100 3403 minecraft:structure_void replace minecraft:{b}',
              f'fill -1289 -290 3340 -1226 100 3403 minecraft:{b} replace minecraft:structure_void']
    return c + ['forceload remove all']

def dims():
    c = ['say SECTION dims']
    for d, blocks in (('the_nether', ['netherrack', 'bedrock', 'lava']), ('the_end', ['end_stone', 'obsidian', 'bedrock'])):
        c += [f'execute in minecraft:{d} run forceload add -16 -16 31 31',
              f'#poll 900 execute in minecraft:{d} if loaded 0 0 0 if loaded 31 0 31 if loaded -16 0 -16 run say LOADED {d} ## LOADED {d}']
        for b in blocks:
            # count by swapping to a marker block and back ("Successfully filled N block(s)")
            c += [f'say DIMCOUNT {d} {b}', f'execute in minecraft:{d} run fill -16 0 -16 31 127 31 minecraft:structure_void replace minecraft:{b}',
                  f'execute in minecraft:{d} run fill -16 0 -16 31 127 31 minecraft:{b} replace minecraft:structure_void']
        c += [f'execute in minecraft:{d} run forceload remove -16 -16 31 31']
    c += ['say COUNT ender_dragon', 'execute in minecraft:the_end run forceload add 0 0', '#sleep 5', 'execute if entity @e[type=minecraft:ender_dragon]',
          'execute in minecraft:the_end run forceload remove 0 0']
    return c

def churn():
    """tickets on the same chunks added and removed within seconds (what the first version of the island probes did); in the first runs a
    chunk worker died with "Parent chunk missing" and no chunk loaded any more. Run last, on both generators."""
    c = ['say SECTION churn']
    for k in range(6):
        x = -2000 - 40 * k
        c += [f'forceload add {x} 2000 {x + 64} 2000', f'forceload add {x + 200} 2000', '#sleep 4', f'forceload remove {x} 2000 {x + 64} 2000', f'forceload remove {x + 200} 2000']
    c += ['#sleep 5', 'forceload add 2000 2000', '#poll 120 execute if loaded 2000 0 2000 run say CHURN chunks-still-load ## CHURN chunks-still-load', 'forceload remove all']
    return c

# ---- biome packs (tools/providers.py): what stands on a spread of islands, one per kind of biome, and what is in the open under them
BIOME_SAMPLE = []
for b in ['desert', 'forest', 'badlands', 'warm_ocean', 'frozen_ocean', 'birch_forest', 'taiga', 'jungle', 'savanna', 'cherry_grove', 'swamp', 'mangrove_swamp']:
    c = [i for i in L['islands'] if i['biome'] == b and i['layer'] == 'main']
    if c: BIOME_SAMPLE.append(min(c, key=lambda i: abs(i['radius'] - 150))['id'])
VEG = ['#minecraft:logs', '#minecraft:leaves', '#minecraft:flowers', 'minecraft:short_grass', 'minecraft:tall_grass', 'minecraft:fern', 'minecraft:bush', 'minecraft:cactus',
       'minecraft:dead_bush', 'minecraft:leaf_litter', 'minecraft:moss_block', 'minecraft:moss_carpet', 'minecraft:cobblestone', 'minecraft:mossy_cobblestone',
       'minecraft:coarse_dirt', 'minecraft:podzol', 'minecraft:snow', 'minecraft:water', 'minecraft:lava', '#minecraft:coral_blocks', 'minecraft:sponge', 'minecraft:wet_sponge',
       'minecraft:bone_block', 'minecraft:magma_block', 'minecraft:spawner', 'minecraft:chest', 'minecraft:packed_ice', 'minecraft:ice', 'minecraft:granite', 'minecraft:calcite',
       'minecraft:tuff', '#minecraft:terracotta', 'minecraft:sandstone', 'minecraft:kelp_plant', 'minecraft:seagrass', 'minecraft:pumpkin', 'minecraft:sugar_cane']
UNDER = ['#minecraft:logs', '#minecraft:leaves', '#minecraft:base_stone_overworld', '#minecraft:dirt', '#minecraft:sand', '#minecraft:terracotta', '#minecraft:ice',
         'minecraft:water', 'minecraft:lava', 'minecraft:sandstone', '#minecraft:coral_blocks', 'minecraft:cobblestone', 'minecraft:mossy_cobblestone', 'minecraft:bone_block',
         'minecraft:packed_ice', 'minecraft:gravel', 'minecraft:deepslate', 'minecraft:tuff', 'minecraft:obsidian', 'minecraft:magma_block', 'minecraft:kelp_plant']
WIDE = ['minecraft:water', 'minecraft:lava', 'minecraft:vine', 'minecraft:cave_vines', 'minecraft:cave_vines_plant', 'minecraft:pointed_dripstone', '#minecraft:logs',
        '#minecraft:leaves', 'minecraft:mangrove_roots', 'minecraft:hanging_roots', 'minecraft:glow_lichen', '#minecraft:fences', 'minecraft:cobweb', 'minecraft:snow',
        'minecraft:powder_snow', 'minecraft:kelp_plant', 'minecraft:kelp', '#minecraft:base_stone_overworld', '#minecraft:dirt', '#minecraft:sand', 'minecraft:sandstone',
        '#minecraft:terracotta', 'minecraft:gravel', '#minecraft:ice']
def biome_scans():
    """96x96 columns around the centre of each island: blocks from the upper part of the body to 60 above the top, and (must be nothing)
    in a box 40 to 160 under the island's bottom. The counts replace the blocks (tags cannot be put back): run last."""
    c = ['say SECTION biomes']
    for k in BIOME_SAMPLE:
        i = I[k]; x0, z0 = i['x'] // 16 * 16 - 48, i['z'] // 16 * 16 - 48; x1, z1 = x0 + 95, z0 + 95
        lo, hi = i['y_top'] - int(min(0.5 * i['thickness'], 120)) - 10, i['y_top'] + 60
        c += [f'forceload add {x0} {z0} {x1} {z1}', f'#time BIOMEGEN-{k}-{i["biome"]}-36-chunks',
              f'#poll 300 execute if loaded {x0} 0 {z0} if loaded {x1} 0 {z1} if loaded {x0} 0 {z1} if loaded {x1} 0 {z0} if loaded {i["x"]} 0 {i["z"]} run say LOADED bio-{k} ## LOADED bio-{k}', '#time']
        probe(c, f'{k} bio', i['x'], i['z'], i['biome'])
        c += [f'say SCANBOX on-{k} {i["biome"]} y {lo}..{hi}, 96x96 columns']
        for b in VEG: c += [f'say SCAN on-{k} {b}', f'fill {x0} {lo} {z0} {x1} {hi} {z1} minecraft:structure_void replace {b}']
        c += [f'say SCANBOX under-{k} {i["biome"]} y {i["y_bottom"] - 160}..{i["y_bottom"] - 40} (in the open under the island)']
        for b in UNDER: c += [f'say SCAN under-{k} {b}', f'fill {x0} {i["y_bottom"] - 160} {z0} {x1} {i["y_bottom"] - 40} {z1} minecraft:structure_void replace {b}']
        c += ['forceload remove all']
    # under the whole footprint of the smaller ones, 40 to 200 blocks below the bottom: fluids and plants that hang or fall out of an
    # island, and everything that is not air (the volume minus the air blocks counted)
    for k in BIOME_SAMPLE:
        i = I[k]; R = i['radius'] + 12
        if i['radius'] > 170: continue
        x0, z0, x1, z1 = i['x'] - R, i['z'] - R, i['x'] + R, i['z'] + R; y0, y1 = i['y_bottom'] - 200, i['y_bottom'] - 40
        c += [f'forceload add {x0} {z0} {x1} {z1}',
              f'#poll 400 execute if loaded {x0} 0 {z0} if loaded {x1} 0 {z1} if loaded {x0} 0 {z1} if loaded {x1} 0 {z0} if loaded {i["x"]} 0 {i["z"]} run say LOADED wide-{k} ## LOADED wide-{k}',
              '#sleep 20', f'say SCANBOX below-{k} {i["biome"]} y {y0}..{y1}, whole footprint, volume {(x1 - x0 + 1) * (z1 - z0 + 1) * (y1 - y0 + 1)}']
        for b in WIDE + ['minecraft:air']: c += [f'say SCAN below-{k} {b}', f'fill {x0} {y0} {z0} {x1} {y1} {z1} minecraft:structure_void replace {b}']
        c += ['forceload remove all']
    return c

def write(name, lines):
    open(f'{OUT}/commands-{name}.txt', 'w').write('\n'.join(lines + [f'say SECTION end {name}']) + '\n')

# vanilla = Fabric API + The Isles only; baseline = the same server without The Isles (vanilla generator), timing only
QUICK_SAMPLE = ['S1', 'K1', 'I1', 'e1', 'M4', 'Pt3', 'C1']
write('vanilla', HEAD + (island_probes() if on('islands') else island_probes(QUICK_SAMPLE) if on('islands-few') else [])
      + (void_probes() if on('void') else []) + (limits() if on('limits') else [])
      + (structures() if on('structures') else [])
      + (pregen('land', *REG_LAND, after=animals()) + pregen('void', *REG_VOID) + pregen('tiers', *REG_TIER) if on('pregen') else [])
      + (anomalies() if on('anomalies') else []) + (dims() if on('dims') else [])
      + ['tick query'] + (churn() if on('churn') else []) + (biome_scans() if on('biomes') else []))
# perf: the same on every pack variant of packtest/perf.txt - generation time and heap of land, void and stacked tiers, with thread
# dumps while they generate, the tick times after, and a /locate that finds nothing
write('perf', HEAD + pregen('land', *REG_LAND) + pregen('void', *REG_VOID) + pregen('tiers', *REG_TIER)
      + ['say LOCATE mansion', '#time LOCATE-mansion', 'locate structure minecraft:mansion', '#wait 180 ## is at \\[|Could not find', '#time',
         'say LOCATE jungle_pyramid', '#time LOCATE-jungle_pyramid', 'locate structure minecraft:jungle_pyramid', '#wait 180 ## is at \\[|Could not find', '#time', 'tick query'])
write('speed', HEAD + pregen('land', *REG_LAND) + pregen('void', *REG_VOID))
write('baseline', HEAD + pregen('land', *REG_LAND) + ['tick query'] + churn())
json.dump({'sample': SAMPLE, 'void': void_points(), 'regions': {'land': REG_LAND, 'void': REG_VOID, 'tiers': REG_TIER}}, open(OUT + '/gen.json', 'w'))
print('sample islands:', ' '.join(SAMPLE))

# ------------------------------------------------------------------ pack phase: every mod + The Isles, real client
C, S, R = [], [], []      # console before the client joins, client script, console after the restart
def look(px, py, pz, tx, ty, tz):
    """tp command putting the player at p, looking at the centre of block t"""
    dx, dy, dz = tx + .5 - px, ty + .5 - (py + 1.62), tz + .5 - pz
    return f"cmd tp packtest {px} {py} {pz} {math.degrees(math.atan2(-dx, dz)):.1f} {-math.degrees(math.atan2(dy, math.hypot(dx, dz))):.1f}"

C += HEAD + ['gamerule immediate_respawn true', 'time set noon', 'gamerule advance_time false',
             'say SECTION spawn', 'forceload add -16 -16 16 16', 'summon minecraft:marker ~ ~ ~ {Tags:["wspawn"]}', 'say WORLDSPAWN',
             'data get entity @e[type=minecraft:marker,tag=wspawn,limit=1] Pos']
probe(C, 'spawn centre', 0, 0)
C += ['say SPAWNCOL', 'execute at @e[type=minecraft:marker,tag=wspawn,limit=1] run function packtest:col', 'scoreboard players get y pt']
# the vanilla phase probes every sampled island; here a spread of them is enough to see that the mods do not change the terrain
PACK_SAMPLE = ['S1', 'Sh4', 'P1', 'Pt3', 'Qt2', 'J1', 'Jt3', 'D1', 'K6', 'M4', 'T3', 'C4', 'e1', 'M1', 'I1', 'K5', 'R2', 'L3']
if on('probes'): C += island_probes([k for k in PACK_SAMPLE if k in SAMPLE]) + void_probes() + pregen('land', *REG_LAND, after=animals())

# ---- ores: what is inside the islands, by altitude (64x64 columns through the whole body)
ORES = ['minecraft:stone', 'minecraft:deepslate', 'minecraft:dirt', 'minecraft:gravel', 'minecraft:granite', 'minecraft:diorite', 'minecraft:andesite', 'minecraft:tuff',
        'minecraft:coal_ore', 'minecraft:iron_ore', 'minecraft:copper_ore', 'minecraft:gold_ore', 'minecraft:redstone_ore', 'minecraft:lapis_ore',
        'minecraft:diamond_ore', 'minecraft:emerald_ore', 'minecraft:deepslate_iron_ore', 'minecraft:deepslate_diamond_ore', 'minecraft:deepslate_redstone_ore',
        'create:zinc_ore', 'create:deepslate_zinc_ore', 'cgs:lead_ore', 'cgs:deepslate_lead_ore', 'createnuclear:uranium_ore',
        'createnuclear:deepslate_uranium_ore', 'create:scoria', 'create:limestone', 'minecraft:water', 'minecraft:lava']
SCAN_ISLANDS = ['S1', 'B1', 'C2', 'a1', 'h1', 'K2', 'F1', 'T1', 'M1']
def scan(lines, tag, pre, x0, y0, z0, x1, y1, z1, blocks):
    for b in blocks:
        lines += [f'say SCAN {tag} {b}', f'{pre}fill {x0} {y0} {z0} {x1} {y1} {z1} minecraft:structure_void replace {b}',
                  f'{pre}fill {x0} {y0} {z0} {x1} {y1} {z1} {b} replace minecraft:structure_void']
def ore_scans(islands, blocks):
    c = ['say SECTION ores']
    for k in islands:
        i = I[k]; x0, z0 = i['x'] // 16 * 16, i['z'] // 16 * 16
        c += [f'forceload add {x0} {z0} {x0 + 63} {z0 + 63}', f'#poll 240 execute if loaded {x0} 0 {z0} if loaded {x0 + 63} 0 {z0 + 63} run say LOADED scan-{k} ## LOADED scan-{k}',
              f'say SCANBOX {k} {i["biome"]} y {i["y_bottom"] - 20}..{i["y_top"] + 10}']
        scan(c, k, '', x0, i['y_bottom'] - 20, z0, x0 + 63, i['y_top'] + 10, z0 + 63, blocks)
        c += ['forceload remove all']
    return c
if on('ores'): C += ore_scans(SCAN_ISLANDS, ORES)
write('vanilla-ores', ore_scans(['S1', 'B1', 'a1', 'T1', 'S2'], [b for b in ORES if b.startswith('minecraft:')]))
N = 'execute in minecraft:the_nether run '
C += ['say SECTION nether ores', N + 'forceload add -16 -16 47 47', '#poll 240 ' + N + 'execute if loaded -16 0 -16 if loaded 47 0 47 run say LOADED nether ## LOADED nether']
scan(C, 'nether', N, -16, -16, -16, 47, 303, 47, ['minecraft:netherrack', 'cgs:sulfur_ore', 'minecraft:nether_quartz_ore', 'minecraft:nether_gold_ore', 'create:scoria', 'minecraft:bedrock'])
C += [N + 'forceload remove all']
# ---- oil (Create Diesel Generators): the amount per chunk, and whether anything in the world can serve as the deposit a pumpjack drills to
C += ['say SECTION oil']
for k in ['S1', 'C1', 'B1', 'C2', 'D1', 'K1', 'T1', 'F1', 'a1', 'K2']:
    i = I[k]
    for dx in (0, 48, 96):
        C += [f'say OIL {k} {i["biome"]} +{dx}', f'execute positioned {i["x"] + dx} {i["y_top"]} {i["z"]} run cdg oil get']
C += ['say OIL locate-from-spawn', 'cdg oil locate']
i = I['S1']
C += ['forceload add 0 0 63 63', '#poll 240 execute if loaded 0 0 0 if loaded 63 0 63 run say LOADED bedrock-scan ## LOADED bedrock-scan']
scan(C, 'S1-bedrock', '', 0, MIN_Y, 0, 63, 80, 63, ['minecraft:bedrock'])
C += ['forceload remove all']

# ---- the mods on an island: a platform 30 blocks above the rim of K1 (deep ocean basin, y 1250) and one above M4 (the lowest island, y -1350)
k1, k5, m4 = I['K1'], I['K5'], I['M4']
BX, BY, BZ = k1['x'] - 20, k1['y_top'] + 30, k1['z'] - 14
def P(dx, dy, dz): return f'{BX + dx} {BY + dy} {BZ + dz}'
C += ['say SECTION mods', f'forceload add {BX - 16} {BZ - 16} {BX + 79} {BZ + 47}',
      f'#poll 240 execute if loaded {BX - 16} 0 {BZ - 16} if loaded {BX + 79} 0 {BZ + 47} run say LOADED platform ## LOADED platform',
      f'fill {P(-4, -1, -4)} {P(60, -1, 30)} minecraft:smooth_stone', f'fill {P(-4, 0, -4)} {P(60, 12, 30)} minecraft:air',
      # Create: motor, shafts, cogwheels; press over a depot; bearing contraption
      f'setblock {P(0, 0, 0)} create:creative_motor[facing=east]{{ScrollValue:64}}', f'setblock {P(1, 0, 0)} create:shaft[axis=x]',
      f'setblock {P(2, 0, 0)} create:shaft[axis=x]', f'setblock {P(3, 0, 0)} create:cogwheel[axis=x]', f'setblock {P(3, 1, 0)} create:cogwheel[axis=x]',
      f'setblock {P(4, 1, 0)} create:shaft[axis=x]',
      f'setblock {P(0, 2, 4)} create:creative_motor[facing=east]{{ScrollValue:128}}', f'setblock {P(1, 2, 4)} create:shaft[axis=x]',
      f'setblock {P(2, 2, 4)} create:mechanical_press[facing=east]', f'setblock {P(2, 0, 4)} create:depot',
      f'summon minecraft:item {BX + 2.5} {BY + 1.3} {BZ + 4.5} {{Item:{{id:"minecraft:iron_ingot",count:1}}}}',
      f'setblock {P(0, 1, 8)} create:creative_motor[facing=east]{{ScrollValue:16}}', f'setblock {P(2, 1, 8)} minecraft:oak_planks',
      f'setblock {P(1, 1, 8)} create:mechanical_bearing[facing=east]']
# Diesel Generators: creative tank of diesel -> pump -> diesel engine between shafts (from that mod's smoke test)
def D(dx, dy, dz): return P(12 + dx, dy, dz)
C += [f'setblock {D(1, 1, 2)} create:fluid_pipe[east=true,waterlogged=false,south=false,north=false,west=false,up=true,down=false]',
      f'setblock {D(2, 1, 2)} create:fluid_pipe[east=true,waterlogged=false,south=false,north=false,west=true,up=false,down=false]',
      f'setblock {D(3, 1, 2)} create:mechanical_pump[waterlogged=false,facing=west]', f'setblock {D(3, 1, 3)} create:cogwheel[waterlogged=false,axis=x]',
      f'setblock {D(4, 1, 1)} create:creative_fluid_tank',
      f'setblock {D(4, 1, 2)} create:fluid_pipe[east=false,waterlogged=false,south=false,north=true,west=true,up=false,down=false]',
      f'setblock {D(4, 1, 3)} create:shaft[waterlogged=false,axis=x]', f'setblock {D(5, 1, 3)} create:creative_motor[facing=west]',
      f'setblock {D(1, 2, 0)} create:shaft[waterlogged=false,axis=z]', f'setblock {D(1, 2, 1)} create:shaft[waterlogged=false,axis=z]',
      f'setblock {D(1, 2, 2)} createdieselgenerators:diesel_engine[waterlogged=false,powered=false,facing=north]',
      f'setblock {D(1, 2, 3)} create:shaft[waterlogged=false,axis=z]', f'setblock {D(1, 2, 4)} create:shaft[waterlogged=false,axis=z]',
      f'data merge block {D(4, 1, 1)} {{Fluid:{{id:"createdieselgenerators:diesel",amount:81000}}}}']
# pumpjack: hole over a pipe that ends on what is under it (no bedrock anywhere in The Isles), and one over a bedrock block put there by hand
C += [f'setblock {D(1, 0, 10)} createdieselgenerators:pumpjack_hole', f'setblock {D(5, 1, 10)} createdieselgenerators:pumpjack_hole',
      f'setblock {D(5, 0, 10)} minecraft:bedrock']
# Create Nuclear: the 5x7x5 reactor of that mod's smoke test; the controller goes on last and assembles it
def Nn(dx, dy, dz): return P(24 + dx, dy, dz)
C += [f'fill {Nn(0, 0, 0)} {Nn(4, 6, 4)} createnuclear:reactor_casing']
for dx, dz, b in ((0, 2, 'frame'), (4, 2, 'frame'), (2, 0, 'frame'), (2, 4, 'frame'), (1, 1, 'cooler'), (1, 3, 'cooler'), (3, 1, 'cooler'), (3, 3, 'cooler'), (2, 2, 'core')):
    C += [f'fill {Nn(dx, 1, dz)} {Nn(dx, 5, dz)} createnuclear:reactor_{b}']
# (the controller is placed by the client script: the mod only assembles the reactor while a player is online)
C += [f'setblock {Nn(0, 3, 2)} createnuclear:reactor_input', f'setblock {Nn(4, 0, 2)} createnuclear:reactor_output',
      f'setblock {Nn(-2, 1, 2)} minecraft:stone', f'setblock {Nn(6, 1, 2)} minecraft:stone']
# guns: a target behind a wall
C += [f'fill {P(40, 0, 12)} {P(50, 4, 12)} minecraft:stone_bricks',
      f'summon minecraft:iron_golem {BX + 45.5} {BY} {BZ + 10.5} {{NoAI:1b,Tags:["target"],PersistenceRequired:1b}}']
# the same Create line 30 blocks above the lowest island
LX, LY, LZ = m4['x'], m4['y_top'] + 30, m4['z']
C += [f'forceload add {LX - 16} {LZ - 16} {LX + 31} {LZ + 31}', f'#poll 240 execute if loaded {LX - 16} 0 {LZ - 16} if loaded {LX + 31} 0 {LZ + 31} run say LOADED low ## LOADED low',
      f'fill {LX - 3} {LY - 1} {LZ - 3} {LX + 8} {LY - 1} {LZ + 8} minecraft:smooth_stone',
      f'setblock {LX} {LY} {LZ} create:creative_motor[facing=east]{{ScrollValue:64}}', f'setblock {LX + 1} {LY} {LZ} create:shaft[axis=x]',
      f'setblock {LX + 2} {LY} {LZ} create:cogwheel[axis=x]', f'setblock {LX} {LY + 1} {LZ + 4} create:creative_motor[facing=east]{{ScrollValue:16}}',
      f'setblock {LX + 2} {LY + 1} {LZ + 4} minecraft:oak_planks', f'setblock {LX + 1} {LY + 1} {LZ + 4} create:mechanical_bearing[facing=east]']
# hypertube from K5 (stony shore) across the void to K1: entrance, three accelerators, entrance, 30 blocks apart, laid by the client
TY, TZ = k1['y_top'] + 15, -1150
TX = [-3660, -3630, -3600, -3570, -3540]
C += [f'forceload add {TX[0] - 16} {TZ - 16} {TX[-1] + 16} {TZ + 16}',
      f'#poll 240 execute if loaded {TX[0] - 16} 0 {TZ - 16} if loaded {TX[-1] + 16} 0 {TZ + 16} run say LOADED tube ## LOADED tube',
      'say SECTION tube line: ground under the two ends, nothing under the middle']
probe(C, 'tube-K5 ground', TX[0], TZ); probe(C, 'tube-gap void', (TX[0] + TX[-1]) // 2 - 8, TZ); probe(C, 'tube-K1 ground', TX[-1], TZ)
C += [f'fill {TX[0] - 6} {TY - 1} {TZ - 1} {TX[-1] + 12} {TY - 1} {TZ + 2} minecraft:glass',
      f'setblock {TX[0]} {TY} {TZ} create_hypertube:hypertube_entrance[facing=east,locked=false]',
      f'setblock {TX[0]} {TY} {TZ + 1} create:cogwheel[axis=x]', f'setblock {TX[0] - 1} {TY} {TZ + 1} create:creative_motor[facing=east]{{ScrollValue:64}}',
      f'setblock {TX[-1]} {TY} {TZ} create_hypertube:hypertube_entrance[facing=west,locked=false]',
      f'setblock {TX[-1]} {TY} {TZ + 1} create:cogwheel[axis=x]', f'setblock {TX[-1] + 1} {TY} {TZ + 1} create:creative_motor[facing=west]{{ScrollValue:64}}',
      f'fill {TX[-1] + 10} {TY} {TZ - 1} {TX[-1] + 10} {TY + 3} {TZ + 2} minecraft:glass']
for x in TX[1:-1]:
    C += [f'setblock {x} {TY} {TZ} create_hypertube:hypertube_accelerator[facing=east]', f'setblock {x} {TY} {TZ + 1} create:cogwheel[axis=x]',
          f'setblock {x - 1} {TY} {TZ + 1} create:creative_motor[facing=east]{{ScrollValue:64}}']
# portals: one on the spawn island, one in the Nether under a void column of the Overworld
from build_nether import COORDINATE_SCALE
NSC = int(COORDINATE_SCALE)   # Overworld blocks per Nether block (1 in this pack, 8 in vanilla)
VX, VZ = void_points()[7]
C += ['forceload add 16 16 47 47', '#poll 240 execute if loaded 16 0 16 if loaded 47 0 47 run say LOADED portal ## LOADED portal',
      'fill 28 99 28 36 99 32 minecraft:smooth_stone', 'fill 28 100 28 36 106 32 minecraft:air', 'fill 30 100 30 33 104 30 minecraft:obsidian', 'fill 31 101 30 32 103 30 minecraft:air',
      'setblock 31 101 30 minecraft:fire', 'execute if block 31 101 30 minecraft:nether_portal run say PORTAL overworld-lit',
      # the Nether where that portal leads, generated now: the portal search generates it on the server thread otherwise (see README, Nether)
      N + f'forceload add {31 // NSC - 16} {30 // NSC - 16} {31 // NSC + 16} {30 // NSC + 16}',
      '#poll 600 ' + N + f'execute if loaded {31 // NSC - 16} 0 {30 // NSC - 16} if loaded {31 // NSC + 16} 0 {30 // NSC + 16} run say LOADED nether-spawn-portal ## LOADED nether-spawn-portal',
      N + f'forceload add {VX // NSC - 16} {VZ // NSC - 16} {VX // NSC + 16} {VZ // NSC + 16}',
      '#poll 240 ' + N + f'execute if loaded {VX // NSC} 0 {VZ // NSC} run say LOADED nether-portal ## LOADED nether-portal',
      N + f'fill {VX // NSC - 3} 69 {VZ // NSC - 3} {VX // NSC + 6} 69 {VZ // NSC + 3} minecraft:obsidian', N + f'fill {VX // NSC - 3} 70 {VZ // NSC - 3} {VX // NSC + 6} 76 {VZ // NSC + 3} minecraft:air',
      N + f'fill {VX // NSC} 70 {VZ // NSC} {VX // NSC + 3} 74 {VZ // NSC} minecraft:obsidian', N + f'fill {VX // NSC + 1} 71 {VZ // NSC} {VX // NSC + 2} 73 {VZ // NSC} minecraft:air',
      N + f'setblock {VX // NSC + 1} 71 {VZ // NSC} minecraft:fire', N + f'execute if block {VX // NSC + 1} 71 {VZ // NSC} minecraft:nether_portal run say PORTAL nether-lit']
C += ['tick sprint 200', '#sleep 8', 'say SECTION mods placed',
      'say CHECK create shaft speed', f'data get block {P(4, 1, 0)} Speed', 'say CHECK create press depot', f'data get block {P(2, 0, 4)}',
      f'execute if entity @e[type=create:stationary_contraption] run say CHECK contraptions-assembled', 'say CHECK contraption count',
      'execute if entity @e[type=create:stationary_contraption]',
      'say CHECK diesel engine shaft speed', f'data get block {D(1, 2, 0)} Speed', 'say CHECK diesel engine', f'data get block {D(1, 2, 2)}',
      'say CHECK pumpjack hole on a pipe-less island', f'data get block {D(1, 0, 10)}', 'say CHECK pumpjack hole on bedrock', f'data get block {D(5, 1, 10)}',
      'say CHECK low create shaft speed', f'data get block {LX + 1} {LY} {LZ} Speed', 'tick query', 'say SECTION end of server part']

# ---- client script (sections can be left out with packtest/quick)
def shots(n=1, wait=4): return ['sleep ' + str(wait), 'shot'] * n
S += ['cmd say SECTION client', 'cmd list', 'cmd say CHECK joined at', 'cmd data get entity packtest Pos', 'cmd execute at packtest run function packtest:col',
      'cmd scoreboard players get y pt', 'cmd data get entity packtest Dimension', 'sleep 20', 'shot', 'key F3', 'sleep 3', 'shot', 'key F3']
PASSIVE = ['cow', 'sheep', 'pig', 'chicken', 'horse', 'donkey', 'rabbit', 'wolf', 'fox', 'frog', 'untitledduckmod:duck', 'untitledduckmod:goose']
def count(tag, kinds): return [x for m in kinds for x in (f'cmd say COUNT {tag} {m}', f'cmd execute if entity @e[type={m}]')]
if on('spawn'):
    # animals that came with the terrain around the spawn point (the client's view distance)
    S += ['cmd say SECTION animals from generation'] + count('generated', PASSIVE)
    # respawn: killed on the island, then a fall out of the world
    S += ['cmd gamemode survival packtest', 'cmd kill packtest', 'sleep 8', 'cmd say CHECK respawned at', 'cmd data get entity packtest Pos',
          'cmd execute at packtest run function packtest:col', 'cmd scoreboard players get y pt', 'shot',
          'cmd tp packtest 1240 -1900 0', 'sleep 14', 'cmd say CHECK after the fall out of the world', 'cmd data get entity packtest Pos', 'cmd data get entity packtest Health', 'shot']
S += ['cmd time set noon', 'cmd gamerule advance_time false', 'cmd gamerule spawn_monsters false', 'cmd gamemode spectator packtest']
# views: top-down and from the side, of a spread of islands
VIEWS = ['S2', 'Pt3', 'C4', 'e3']
if on('views'):
    S += ['cmd say SECTION views']
    for k in VIEWS:
        i = I[k]; x, z, rad, top = i['x'], i['z'], i['radius'], i['y_top']
        S += [f'cmd say VIEW {k} {i["biome"]} top', f'cmd tp packtest {x} {top + max(70, min(190, int(rad * 1.3)))} {z} 180 90', 'sleep 45', 'shot',
              f'cmd say VIEW {k} side', f'cmd tp packtest {x} {top + 12} {z + rad + 70} 180 12', 'sleep 14', 'shot']
    S += ['cmd say VIEW I1 sand above the basin', 'cmd tp packtest -1257 20 3440 180 25', 'sleep 40', 'shot',
          'cmd say VIEW snow', f'cmd tp packtest {I["e3"]["x"]} {I["e3"]["y_top"] + 20} {I["e3"]["z"] + 60} 180 15', 'cmd weather rain', 'sleep 25', 'shot', 'cmd weather clear']
# biome packs: every sampled island from above, from a little above its ground, and from the side with what is under it
if on('biomeviews'):
    S += ['cmd say SECTION biome views']
    for k in BIOME_SAMPLE:
        i = I[k]; x, z, rad, top = i['x'], i['z'], i['radius'], i['y_top']
        g = top - (int(0.3 * i['thickness']) if i['kind'] == 'basin' else 0)   # ground level near the centre
        S += [f'cmd say VIEW biome {k} {i["biome"]} top, near, side', f'cmd tp packtest {x} {g + 75} {z} 180 90', 'sleep 40', 'shot',
              f'cmd tp packtest {x} {g + 22} {z + min(50, rad // 2)} 180 24', 'sleep 10', 'shot',
              f'cmd tp packtest {x} {top - i["thickness"] // 3} {z + rad + 80} 180 -4', 'sleep 18', 'shot']
# the look of the sky: on a low, a middle and a high island (standing on the rim, looking out over the void: level, down, up), in the open
# void at three heights, and at dusk and at night
if on('look'):
    S += ['cmd say SECTION look']
    for k in ['M4', 'S1', 'K6']:
        i = I[k]; x, z, rad, top = i['x'], i['z'], i['radius'], i['y_top']
        S += [f'cmd say VIEW look {k} y {top} side', f'cmd tp packtest {x} {top + 12} {z + rad + 70} 180 12', 'sleep 40', 'shot',
              f'cmd say VIEW look {k} level, down, up, outwards', f'cmd tp packtest {x} {top + 30} {z + int(rad * 0.6)} 0 0', 'sleep 25', 'shot',
              f'cmd tp packtest {x} {top + 30} {z + int(rad * 0.6)} 0 40', 'sleep 5', 'shot', f'cmd tp packtest {x} {top + 30} {z + int(rad * 0.6)} 0 -40', 'sleep 5', 'shot']
    S += ['cmd say VIEW void looking down and at the horizon, y 0 and y -1500', f'cmd tp packtest {VX} 0 {VZ} 0 0', 'sleep 20', 'shot', f'cmd tp packtest {VX} -1500 {VZ} 0 -30', 'sleep 8', 'shot',
          f'cmd tp packtest {VX} 1500 {VZ} 0 30', 'sleep 8', 'shot', f'cmd tp packtest {VX} -2000 {VZ} 0 0', 'sleep 8', 'shot',
          'cmd say VIEW look dusk and night on M4', f'cmd tp packtest {I["M4"]["x"]} {I["M4"]["y_top"] + 30} {I["M4"]["z"] + 40} 90 -10', 'cmd time set 12800', 'sleep 30', 'shot',
          'cmd time set midnight', 'sleep 8', 'shot', f'cmd tp packtest {I["M4"]["x"]} {I["M4"]["y_top"] + 30} {I["M4"]["z"] + 40} 90 30', 'sleep 5', 'shot', 'cmd time set noon']
# the mods
if on('modsclient'):
    S += ['cmd say SECTION mods client', 'cmd gamemode creative packtest', f'cmd tp packtest {BX + 3.5} {BY} {BZ - 3.5} 0 15', 'sleep 30', 'shot',
          f'cmd tp packtest {BX + 2.5} {BY + 1} {BZ + 12.5} 180 10', 'sleep 5', 'shot', f'cmd tp packtest {BX + 15.5} {BY} {BZ - 3.5} 0 10', 'sleep 5', 'shot',
          f'cmd tp packtest {BX + 20.5} {BY + 3} {BZ + 2.5} -90 15', 'sleep 5', 'shot',
          'cmd say CHECK create press result', f'cmd data get block {P(2, 0, 4)}', 'cmd say CHECK diesel engine shaft speed (client on)', f'cmd data get block {D(1, 2, 0)} Speed',
          'cmd say CHECK pumpjack hole on a pipe-less island (client on)', f'cmd data get block {D(1, 0, 10)}', 'cmd say CHECK pumpjack hole on bedrock (client on)', f'cmd data get block {D(5, 1, 10)}']
    # Create Nuclear: the controller goes on with the player there (as in the mod's own smoke test, .github/smoke-script.txt of the port).
    # Configuring the blueprint and loading rods needs the mod's GUIs; that part is covered by the mod's smoke test, not here.
    S += ['cmd say SECTION reactor', f'cmd tp packtest {BX + 30.5} {BY + 2} {BZ + 2.5} 90 0', 'sleep 6', f'cmd setblock {Nn(4, 3, 2)} createnuclear:reactor_controller', 'sleep 3',
          f'cmd execute if block {Nn(4, 3, 2)} createnuclear:reactor_controller[assembled=true] run say CHECK reactor-assembled', 'cmd say CHECK reactor controller',
          f'cmd data get block {Nn(4, 3, 2)}', 'cmd item replace entity packtest armor.head with create:goggles', 'sleep 3', 'shot',
          'cmd item replace entity packtest armor.head with minecraft:air']
if on('guns'):
    # gun: revolver, reload, three shots at the golem
    S += ['cmd say SECTION guns', f'cmd tp packtest {BX + 45.5} {BY} {BZ + 4.5} 0 2', 'cmd gamemode survival packtest', 'cmd item replace entity packtest armor.head with minecraft:air',
          'cmd item replace entity packtest hotbar.0 with cgs:revolver', 'cmd give packtest cgs:round_revolver 20', 'key 1', 'sleep 4', 'shot',
          'cmd say CHECK revolver before', 'cmd data get entity packtest SelectedItem', 'cmd data get entity @e[tag=target,limit=1] Health',
          'keydown r', 'sleep 0.4', 'keyup r', 'sleep 22', 'cmd say CHECK revolver reloaded', 'cmd data get entity packtest SelectedItem']
    for n in range(3): S += ['mdown 1', 'sleep 0.5', 'mup 1', 'sleep 0.3', 'shot', 'sleep 1.2']
    S += ['cmd say CHECK revolver fired', 'cmd data get entity packtest SelectedItem', 'cmd data get entity @e[tag=target,limit=1] Health', 'cmd gamemode creative packtest', 'cmd clear packtest']
if on('tube'):
    # hypertube: lay the four tubes by hand (use key = u), then ride
    S += ['cmd say SECTION tube', 'cmd gamemode creative packtest', 'cmd item replace entity packtest hotbar.0 with create_hypertube:hypertube 64', 'key 1']
    for a, b in zip(TX, TX[1:]):
        S += [f'cmd tp packtest {a + 3.5} {TY} {TZ + 0.5} 90 24', 'sleep 5', 'key u', 'sleep 1.5', f'cmd tp packtest {b - 2.5} {TY} {TZ + 0.5} -90 24', 'sleep 5', 'key u', 'sleep 2']
    S += ['shot', 'cmd say CHECK tube connections'] + [f'cmd data get block {x} {TY} {TZ} HypertubeConnections' for x in TX]
    S += ['cmd clear packtest', 'cmd gamemode spectator packtest', f'cmd tp packtest {(TX[0] + TX[-1]) // 2} {TY + 75} {TZ} 180 90', 'sleep 12', 'shot',
          f'cmd tp packtest {(TX[0] + TX[-1]) // 2} {TY + 12} {TZ + 85} 180 8', 'sleep 10', 'shot', 'cmd gamemode creative packtest',
          'cmd say CHECK tube ride start', f'cmd tp packtest {TX[0] - 0.5} {TY} {TZ + 0.5} -90 0', 'sleep 0.6', 'shot']
    for n in range(24): S += ['cmd data get entity packtest Pos', 'sleep 0.5']
    S += ['shot', 'cmd say CHECK tube ride end', 'cmd data get entity packtest Pos',
          # a villager through the same tube (entities other than players)
          f'cmd tp packtest {TX[2]} {TY + 4} {TZ + 6.5} 180 30', 'sleep 3', f'cmd summon minecraft:villager {TX[0] - 0.5} {TY} {TZ + 0.5} {{NoAI:1b,Tags:["rider"]}}', 'sleep 12',
          'cmd say CHECK villager ride end', 'cmd execute as @e[tag=rider] run data get entity @s Pos', 'cmd kill @e[tag=rider]']
# dimensions and portals
if on('portals'):
    S += ['cmd say SECTION portals', 'cmd gamemode creative packtest', 'cmd tp packtest 34.5 100 31.5 90 0', 'sleep 20', 'shot', 'cmd say CHECK before the portal', 'cmd data get entity packtest Dimension',
          'cmd tp packtest 31.5 101 30.5', 'sleep 14', 'cmd say CHECK through the overworld portal', 'cmd data get entity packtest Dimension', 'cmd data get entity packtest Pos', 'shot',
          'cmd execute as packtest at @s run tp @s ~3 ~ ~', 'sleep 16', 'cmd execute as packtest at @s run tp @s ~-3 ~ ~', 'sleep 14',
          'cmd say CHECK back through the nether side', 'cmd data get entity packtest Dimension', 'cmd data get entity packtest Pos', 'shot',
          f'cmd execute in minecraft:the_nether run tp packtest {VX // NSC + 5.5} 70 {VZ // NSC + 0.5} 90 0', 'sleep 20', 'shot',
          f'cmd execute in minecraft:the_nether run tp packtest {VX // NSC + 1.5} 71 {VZ // NSC + 0.5}', 'sleep 16',
          f'cmd say CHECK from a nether portal under the void column {VX} {VZ}', 'cmd data get entity packtest Dimension', 'cmd data get entity packtest Pos',
          'cmd execute at packtest run function packtest:top', 'cmd execute at packtest run function packtest:col', 'cmd scoreboard players get y pt', 'shot',
          'cmd gamemode spectator packtest', 'cmd execute as packtest at @s run tp @s ~12 ~8 ~12 135 25', 'sleep 6', 'shot',
          'cmd execute in minecraft:the_end run tp packtest 60 70 0 90 10', 'sleep 20', 'cmd say CHECK the end', 'cmd data get entity packtest Dimension', 'shot']
MOBS = ['zombie', 'skeleton', 'creeper', 'spider', 'enderman', 'witch', 'slime', 'zombie_villager', 'bat']
if on('mobs'):
    # monsters at night, in survival, on the spawn island
    # (the portal section before this one ends in the End: back to the spawn point first)
    S += ['cmd execute in minecraft:overworld run tp packtest 0.5 60 0.5 0 0', 'sleep 30', 'cmd gamerule spawn_monsters true',
          'cmd gamemode survival packtest', 'cmd effect give packtest minecraft:resistance infinite 255 true', 'cmd gamerule advance_time true', 'cmd time set midnight', 'sleep 90',
          'cmd say SECTION mobs'] + count('night', MOBS) + ['shot']
    S += ['cmd time set noon', 'cmd gamerule spawn_monsters false', 'cmd kill @e[type=#minecraft:undead]', 'cmd kill @e[type=minecraft:creeper]',
          'cmd kill @e[type=minecraft:spider]', 'cmd kill @e[type=minecraft:enderman]', 'cmd kill @e[type=minecraft:witch]', 'cmd kill @e[type=minecraft:item]']
    # animals that spawn later: everything generated is removed, then half a day passes at full speed (the game tries every 400 ticks)
    S += [f'cmd kill @e[type={m}]' for m in PASSIVE] + ['cmd kill @e[type=minecraft:item]', 'cmd kill @e[type=minecraft:experience_orb]', 'cmd say SECTION animals after the kill'] + count('killed', ['cow', 'pig', 'chicken'])
    S += ['cmd time set 0', 'cmd tick sprint 10000', 'sleep 150', 'cmd tick sprint stop', 'cmd say SECTION animals spawned later'] + count('later', PASSIVE)
    # a swamp, a forest and a snowy island: what generated there (ducks and geese of the duck mod live near water)
    for k in ['R1', 'f1', 'e1', 'D1']:
        i = I[k]
        S += [f'cmd execute in minecraft:overworld run tp packtest {i["x"]} {i["y_top"] + 40} {i["z"]}', 'sleep 45', f'cmd say SECTION animals on {k} {i["biome"]}'] + count(k, PASSIVE)
    S += ['cmd time set noon', 'cmd gamerule advance_time false', 'cmd weather rain', 'sleep 12', 'shot', 'cmd weather clear']
S += ['cmd execute in minecraft:overworld run tp packtest 0 90 0 0 20', 'sleep 20', 'cmd gamemode creative packtest', 'key F3', 'sleep 4', 'shot', 'key F3',
      'cmd say SECTION client end', 'cmd list', 'cmd tick query', 'sleep 3']

# ---- after the restart: everything is still there and still runs
R += ['say SECTION restart', 'forceload query', 'gamerule spawn_monsters false', '#sleep 15',
      'say CHECK create shaft speed', f'data get block {P(4, 1, 0)} Speed', 'say CHECK create press depot', f'data get block {P(2, 0, 4)}',
      'say CHECK contraption count', 'execute if entity @e[type=create:stationary_contraption]',
      'say CHECK diesel engine shaft speed', f'data get block {D(1, 2, 0)} Speed',
      f'execute if block {Nn(4, 3, 2)} createnuclear:reactor_controller[assembled=true] run say CHECK reactor-assembled', 'say CHECK reactor controller', f'data get block {Nn(4, 3, 2)}',
      'say CHECK low create shaft speed', f'data get block {LX + 1} {LY} {LZ} Speed',
      'say CHECK tube connections'] + [f'data get block {x} {TY} {TZ} HypertubeConnections' for x in TX] + [
      f'summon minecraft:villager {TX[0] - 0.5} {TY} {TZ + 0.5} {{NoAI:1b,Tags:["rider"]}}', '#sleep 12', 'say CHECK villager ride end',
      'execute as @e[tag=rider] run data get entity @s Pos', 'execute if block 31 101 30 minecraft:nether_portal run say PORTAL overworld-lit',
      'say WORLDSPAWN', 'data get entity @e[type=minecraft:marker,tag=wspawn,limit=1] Pos', 'tick query']
write('pack', C); write('pack-restart', R)
open(OUT + '/script-pack.txt', 'w').write('\n'.join(S) + '\n')
print(len(C), 'pack commands,', len(S), 'script lines,', len(R), 'restart commands; shots:', S.count('shot'),
      'script sleep:', round(sum(float(l.split()[1]) for l in S if l.startswith('sleep '))), 's')

# bisect-*: fresh worlds for narrowing a generation failure down (phase "bisect")
if os.path.exists(ROOT + '/packtest/bisect.txt'):
    for n, line in enumerate(open(ROOT + '/packtest/bisect.txt').read().split('\n')):
        ids = line.split()
        if ids: write(f'bisect-{n}', HEAD + island_probes(ids))
