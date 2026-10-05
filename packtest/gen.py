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
I = {i['id']: i for i in L['islands']}
MIN_Y, TOP_Y = L['min_y'], L['min_y'] + L['height'] - 1

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

def island_probes():
    c = ['say SECTION islands']
    for k in SAMPLE:
        i = I[k]; x, z, R = i['x'], i['z'], i['radius']
        half = int(R * 0.5); out = R + 40
        c += [f'forceload add {x} {z} {x + half} {z}', f'forceload add {x + out} {z}',
              f'#poll 240 execute if loaded {x} 0 {z} if loaded {x + half} 0 {z} if loaded {x + out} 0 {z} run say LOADED {k} ## LOADED {k}']
        probe(c, f'{k} centre', x, z, i['biome'])
        probe(c, f'{k} half', x + half, z, i['biome'])
        probe(c, f'{k} outside', x + out, z)
        # the body: what is 12 blocks under the ground at the centre, and at the layout's bottom
        c += [f'say BODY {k}', f'execute positioned {x} 0 {z} positioned over motion_blocking_no_leaves positioned ~ ~-12 ~ run function packtest:at',
              f'execute positioned {x} {i["y_bottom"] - 40} {z} run function packtest:at',
              # at the island's own altitude (stacked tiers share a column): block and biome in the middle of the body
              f'say MID {k} {i["y_top"] - i["thickness"] // 3}', f'execute positioned {x} {i["y_top"] - i["thickness"] // 3} {z} run function packtest:at',
              f'execute positioned {x} {i["y_top"] - i["thickness"] // 3} {z} run function packtest:biome',
              f'execute if biome {x} {i["y_top"] + 3} {z} minecraft:{i["biome"]} run say TOPBIOMEOK {k}',
              ]
    # tickets are dropped once, at the end: removing and re-adding tickets on neighbouring chunks within seconds is what the "churn" section does
    return c + ['forceload remove all']

def void_probes():
    c = ['say SECTION void']
    for n, (x, z) in enumerate(void_points()):
        c += [f'forceload add {x} {z}', f'#poll 120 execute if loaded {x} 0 {z} run say LOADED void{n} ## LOADED void{n}']
        probe(c, f'void{n} void', x, z)
    return c + ['forceload remove all']

def limits():
    """build limits: blocks can be placed at the lowest and highest layer, not beyond"""
    x, z = 3900, 3900
    return ['say SECTION limits', f'forceload add {x} {z}', f'#poll 120 execute if loaded {x} 0 {z} run say LOADED limits ## LOADED limits',
            f'setblock {x} {MIN_Y} {z} minecraft:gold_block', f'execute if block {x} {MIN_Y} {z} minecraft:gold_block run say LIMIT bottom-ok {MIN_Y}',
            f'setblock {x} {TOP_Y} {z} minecraft:gold_block', f'execute if block {x} {TOP_Y} {z} minecraft:gold_block run say LIMIT top-ok {TOP_Y}',
            f'setblock {x} {MIN_Y - 1} {z} minecraft:gold_block', f'setblock {x} {TOP_Y + 1} {z} minecraft:gold_block',
            f'forceload remove {x} {z}']

def pregen(name, cx0, cz0, cx1, cz1, wait=900):
    n = region_fn(name, cx0, cz0, cx1, cz1)
    return [f'say PREGEN {name} start {n}', f'forceload add {cx0 * 16} {cz0 * 16} {cx1 * 16} {cz1 * 16}',
            f'#poll {wait} function packtest:count_{name} ## PREGEN {name} done', 'tick query']

REG_LAND = (20, -8, 35, 7)       # 16x16 chunks inside the spawn island (600 blocks of rock under them)
p = I['P1']; REG_TIER = (p['x'] // 16 - 4, p['z'] // 16 - 4, p['x'] // 16 + 3, p['z'] // 16 + 3)   # 8x8 chunks through three stacked tiers
v = void_points()[0]; REG_VOID = (v[0] // 16 - 8, v[1] // 16 - 8, v[0] // 16 + 7, v[1] // 16 + 7)

HEAD = ['say SECTION start', 'scoreboard objectives add pt dummy', 'gamerule max_block_modifications 100000000', 'gamerule respawn_radius 0', 'tick query']
ANIMALS = ['cow', 'sheep', 'pig', 'chicken', 'horse', 'rabbit', 'wolf', 'fox', 'llama', 'goat', 'frog', 'parrot', 'panda', 'camel', 'armadillo',
           'polar_bear', 'donkey', 'mooshroom', 'turtle', 'ocelot', 'cat']
def animals():
    return ['say SECTION animals'] + [x for a in ANIMALS for x in (f'say COUNT {a}', f'execute if entity @e[type=minecraft:{a}]')]

def structures():
    c = ['say SECTION structures']
    for s in ['minecraft:village_plains', 'minecraft:stronghold', 'minecraft:mineshaft', 'minecraft:pillager_outpost', 'minecraft:trial_chambers',
              'minecraft:ancient_city', 'minecraft:ruined_portal', 'minecraft:desert_pyramid', 'minecraft:shipwreck']:
        c += [f'say LOCATE {s}', f'locate structure {s}', '#wait 120 ## is at \\[|Could not find|could not find|ERROR']
    for b in ['minecraft:jagged_peaks', 'minecraft:mushroom_fields', 'the_isles:void']:
        c += [f'say LOCATE biome {b}', f'locate biome {b}', '#wait 120 ## is at \\[|Could not find|could not find|ERROR']
    return c

def dims():
    c = ['say SECTION dims']
    for d, blocks in (('the_nether', ['netherrack', 'bedrock', 'lava']), ('the_end', ['end_stone', 'obsidian', 'bedrock'])):
        c += [f'execute in minecraft:{d} run forceload add -16 -16 31 31',
              f'#poll 240 execute in minecraft:{d} if loaded 0 0 0 if loaded 31 0 31 if loaded -16 0 -16 run say LOADED {d} ## LOADED {d}']
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

def write(name, lines):
    open(f'{OUT}/commands-{name}.txt', 'w').write('\n'.join(lines + [f'say SECTION end {name}']) + '\n')

# vanilla = Fabric API + The Isles only; baseline = the same server without The Isles (vanilla generator), timing only
write('vanilla', HEAD + island_probes() + void_probes() + limits() + pregen('land', *REG_LAND) + animals() + pregen('void', *REG_VOID)
      + pregen('tiers', *REG_TIER) + dims() + structures() + ['tick query'] + churn())
write('baseline', HEAD + pregen('land', *REG_LAND) + ['tick query'] + churn())
json.dump({'sample': SAMPLE, 'void': void_points(), 'regions': {'land': REG_LAND, 'void': REG_VOID, 'tiers': REG_TIER}}, open(OUT + '/gen.json', 'w'))
print('sample islands:', ' '.join(SAMPLE))
