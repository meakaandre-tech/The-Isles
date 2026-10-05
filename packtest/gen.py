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

# ------------------------------------------------------------------ pack phase: every mod + The Isles, real client
C, S, R = [], [], []      # console before the client joins, client script, console after the restart
def look(px, py, pz, tx, ty, tz):
    """tp command putting the player at p, looking at the centre of block t"""
    dx, dy, dz = tx + .5 - px, ty + .5 - (py + 1.62), tz + .5 - pz
    return f"cmd tp packtest {px} {py} {pz} {math.degrees(math.atan2(-dx, dz)):.1f} {-math.degrees(math.atan2(dy, math.hypot(dx, dz))):.1f}"

C += HEAD + ['gamerule immediate_respawn true', 'time set noon', 'gamerule advance_time false',
             'say SECTION spawn', 'summon minecraft:marker ~ ~ ~ {Tags:["wspawn"]}', 'say WORLDSPAWN', 'data get entity @e[type=minecraft:marker,tag=wspawn,limit=1] Pos']
probe(C, 'spawn centre', 0, 0)
C += island_probes() + void_probes() + pregen('land', *REG_LAND)

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
C += ['say SECTION ores']
for k in SCAN_ISLANDS:
    i = I[k]; x0, z0 = i['x'] // 16 * 16, i['z'] // 16 * 16
    C += [f'forceload add {x0} {z0} {x0 + 63} {z0 + 63}', f'#poll 240 execute if loaded {x0} 0 {z0} if loaded {x0 + 63} 0 {z0 + 63} run say LOADED scan-{k} ## LOADED scan-{k}',
          f'say SCANBOX {k} {i["biome"]} y {i["y_bottom"] - 20}..{i["y_top"] + 10}']
    scan(C, k, '', x0, i['y_bottom'] - 20, z0, x0 + 63, i['y_top'] + 10, z0 + 63, ORES)
    C += ['forceload remove all']
N = 'execute in minecraft:the_nether run '
C += ['say SECTION nether ores', N + 'forceload add -16 -16 47 47', '#poll 240 ' + N + 'execute if loaded -16 0 -16 if loaded 47 0 47 run say LOADED nether ## LOADED nether']
scan(C, 'nether', N, -16, 0, -16, 47, 127, 47, ['minecraft:netherrack', 'cgs:sulfur_ore', 'minecraft:nether_quartz_ore', 'minecraft:nether_gold_ore', 'create:scoria', 'minecraft:bedrock'])
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
C += [f'setblock {Nn(0, 3, 2)} createnuclear:reactor_input', f'setblock {Nn(4, 0, 2)} createnuclear:reactor_output',
      f'setblock {Nn(4, 3, 2)} createnuclear:reactor_controller']
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
      f'fill {TX[0] - 6} {TY - 1} {TZ - 1} {TX[-1] + 12} {TY - 1} {TZ + 2} minecraft:glass',
      f'setblock {TX[0]} {TY} {TZ} create_hypertube:hypertube_entrance[facing=east,locked=false]',
      f'setblock {TX[0]} {TY} {TZ + 1} create:cogwheel[axis=x]', f'setblock {TX[0] - 1} {TY} {TZ + 1} create:creative_motor[facing=east]{{ScrollValue:64}}',
      f'setblock {TX[-1]} {TY} {TZ} create_hypertube:hypertube_entrance[facing=west,locked=false]',
      f'setblock {TX[-1]} {TY} {TZ + 1} create:cogwheel[axis=x]', f'setblock {TX[-1] + 1} {TY} {TZ + 1} create:creative_motor[facing=west]{{ScrollValue:64}}',
      f'fill {TX[-1] + 10} {TY} {TZ - 1} {TX[-1] + 10} {TY + 3} {TZ + 2} minecraft:glass']
for x in TX[1:-1]:
    C += [f'setblock {x} {TY} {TZ} create_hypertube:hypertube_accelerator[facing=east]', f'setblock {x} {TY} {TZ + 1} create:cogwheel[axis=x]',
          f'setblock {x - 1} {TY} {TZ + 1} create:creative_motor[facing=east]{{ScrollValue:64}}']
probe(C, 'tube-K5 ground', TX[0], TZ); probe(C, 'tube-gap void', (TX[0] + TX[-1]) // 2 - 8, TZ); probe(C, 'tube-K1 ground', TX[-1], TZ)
# portals: one on the spawn island, one in the Nether under a void column of the Overworld
VX, VZ = void_points()[7]
C += ['forceload add 16 16 47 47', '#poll 240 execute if loaded 16 0 16 if loaded 47 0 47 run say LOADED portal ## LOADED portal',
      'fill 28 99 28 36 99 32 minecraft:smooth_stone', 'fill 28 100 28 36 106 32 minecraft:air', 'fill 30 100 30 33 104 30 minecraft:obsidian', 'fill 31 101 30 32 103 30 minecraft:air',
      'setblock 31 101 30 minecraft:fire', 'execute if block 31 101 30 minecraft:nether_portal run say PORTAL overworld-lit',
      N + f'forceload add {VX // 8 - 16} {VZ // 8 - 16} {VX // 8 + 16} {VZ // 8 + 16}',
      '#poll 240 ' + N + f'execute if loaded {VX // 8} 0 {VZ // 8} run say LOADED nether-portal ## LOADED nether-portal',
      N + f'fill {VX // 8 - 3} 69 {VZ // 8 - 3} {VX // 8 + 6} 69 {VZ // 8 + 3} minecraft:obsidian', N + f'fill {VX // 8 - 3} 70 {VZ // 8 - 3} {VX // 8 + 6} 76 {VZ // 8 + 3} minecraft:air',
      N + f'fill {VX // 8} 70 {VZ // 8} {VX // 8 + 3} 74 {VZ // 8} minecraft:obsidian', N + f'fill {VX // 8 + 1} 71 {VZ // 8} {VX // 8 + 2} 73 {VZ // 8} minecraft:air',
      N + f'setblock {VX // 8 + 1} 71 {VZ // 8} minecraft:fire', N + f'execute if block {VX // 8 + 1} 71 {VZ // 8} minecraft:nether_portal run say PORTAL nether-lit']
C += ['tick sprint 200', '#sleep 8', 'say SECTION mods placed',
      'say CHECK create shaft speed', f'data get block {P(4, 1, 0)} Speed', 'say CHECK create press depot', f'data get block {P(2, 0, 4)}',
      f'execute if entity @e[type=create:stationary_contraption] run say CHECK contraptions-assembled', 'say CHECK contraption count',
      'execute if entity @e[type=create:stationary_contraption]',
      'say CHECK diesel engine shaft speed', f'data get block {D(1, 2, 0)} Speed', 'say CHECK diesel engine', f'data get block {D(1, 2, 2)}',
      'say CHECK pumpjack hole on a pipe-less island', f'data get block {D(1, 0, 10)}', 'say CHECK pumpjack hole on bedrock', f'data get block {D(5, 1, 10)}',
      f'execute if block {Nn(4, 3, 2)} createnuclear:reactor_controller[assembled=true] run say CHECK reactor-assembled',
      'say CHECK reactor controller', f'data get block {Nn(4, 3, 2)}',
      'say CHECK low create shaft speed', f'data get block {LX + 1} {LY} {LZ} Speed', 'tick query', 'say SECTION end of server part']

# ---- client script
def shots(n=1, wait=4): return ['sleep ' + str(wait), 'shot'] * n
S += ['cmd say SECTION client', 'cmd list', 'cmd say CHECK joined at', 'cmd data get entity packtest Pos', 'cmd execute at packtest run function packtest:col',
      'cmd scoreboard players get y pt', 'cmd data get entity packtest Dimension', 'sleep 20', 'shot', 'key F3', 'sleep 3', 'shot', 'key F3',
      # respawn: killed on the island, then a fall out of the world
      'cmd gamemode survival packtest', 'cmd kill packtest', 'sleep 8', 'cmd say CHECK respawned at', 'cmd data get entity packtest Pos',
      'cmd execute at packtest run function packtest:col', 'cmd scoreboard players get y pt', 'shot',
      'cmd tp packtest 1240 -1900 0', 'sleep 14', 'cmd say CHECK after the fall out of the world', 'cmd data get entity packtest Pos', 'cmd data get entity packtest Health', 'shot',
      # mob spawning at night, in survival, on the spawn island
      'cmd effect give packtest minecraft:resistance infinite 255 true', 'cmd gamerule advance_time true', 'cmd time set midnight', 'sleep 90']
MOBS = ['zombie', 'skeleton', 'creeper', 'spider', 'enderman', 'witch', 'slime', 'zombie_villager', 'cow', 'sheep', 'pig', 'chicken', 'horse', 'bat', 'untitledduckmod:duck', 'untitledduckmod:goose']
S += ['cmd say SECTION mobs'] + [x for m in MOBS for x in (f'cmd say COUNT {m}', f'cmd execute if entity @e[type={m}]')] + ['shot']
S += ['cmd time set noon', 'cmd gamerule advance_time false', 'cmd gamerule spawn_monsters false', 'cmd kill @e[type=#minecraft:undead]', 'cmd kill @e[type=minecraft:creeper]',
      'cmd kill @e[type=minecraft:spider]', 'cmd kill @e[type=minecraft:enderman]', 'cmd kill @e[type=minecraft:witch]', 'cmd kill @e[type=minecraft:item]',
      'cmd weather rain', 'sleep 12', 'shot', 'cmd weather clear', 'cmd gamemode spectator packtest']
# views: top-down and from the side, of a spread of islands
VIEWS = ['S2', 'S4', 'Sh4', 'Pt3', 'Qt3', 'D4', 'K6', 'M4', 'T3', 'C4', 'Jt3', 'M5', 'e3', 'R2', 'L5', 'K5']
S += ['cmd say SECTION views']
for k in VIEWS:
    i = I[k]; x, z, rad, top = i['x'], i['z'], i['radius'], i['y_top']
    S += [f'cmd say VIEW {k} {i["biome"]} top', f'cmd tp packtest {x} {top + max(70, min(190, int(rad * 1.3)))} {z} 180 90', 'sleep 40', 'shot',
          f'cmd say VIEW {k} side', f'cmd tp packtest {x} {top + 12} {z + rad + 70} 180 12', 'sleep 14', 'shot']
S += ['cmd say VIEW void looking down and at the horizon, y 0 and y -1500', f'cmd tp packtest {VX} 0 {VZ} 0 0', 'sleep 20', 'shot', f'cmd tp packtest {VX} -1500 {VZ} 0 -30', 'sleep 8', 'shot',
      f'cmd tp packtest {VX} 1500 {VZ} 0 30', 'sleep 8', 'shot',
      'cmd say VIEW snow', f'cmd tp packtest {I["e3"]["x"]} {I["e3"]["y_top"] + 20} {I["e3"]["z"] + 60} 180 15', 'cmd weather rain', 'sleep 25', 'shot', 'cmd weather clear']
# the mods
S += ['cmd say SECTION mods client', 'cmd gamemode creative packtest', f'cmd tp packtest {BX + 3.5} {BY} {BZ - 3.5} 0 15', 'sleep 30', 'shot',
      f'cmd tp packtest {BX + 2.5} {BY + 1} {BZ + 12.5} 180 10', 'sleep 5', 'shot', f'cmd tp packtest {BX + 15.5} {BY} {BZ - 3.5} 0 10', 'sleep 5', 'shot',
      f'cmd tp packtest {BX + 20.5} {BY + 3} {BZ + 2.5} -90 15', 'sleep 5', 'shot',
      'cmd item replace entity packtest armor.head with create:goggles', f'cmd tp packtest {BX + 26.5} {BY} {BZ - 4.5} 0 -10', 'sleep 5', 'shot',
      'cmd say CHECK create press result', f'cmd data get block {P(2, 0, 4)}', 'cmd say CHECK diesel engine shaft speed (client on)', f'cmd data get block {D(1, 2, 0)} Speed',
      'cmd say CHECK pumpjack hole on a pipe-less island (client on)', f'cmd data get block {D(1, 0, 10)}', 'cmd say CHECK pumpjack hole on bedrock (client on)', f'cmd data get block {D(5, 1, 10)}',
      # gun: revolver, reload, three shots at the golem
      'cmd say SECTION guns', f'cmd tp packtest {BX + 45.5} {BY} {BZ + 4.5} 0 2', 'cmd gamemode survival packtest', 'cmd item replace entity packtest armor.head with minecraft:air',
      'cmd item replace entity packtest hotbar.0 with cgs:revolver', 'cmd give packtest cgs:round_revolver 20', 'key 1', 'sleep 4', 'shot',
      'cmd say CHECK revolver before', 'cmd data get entity packtest SelectedItem', 'cmd data get entity @e[tag=target,limit=1] Health',
      'keydown r', 'sleep 0.4', 'keyup r', 'sleep 22', 'cmd say CHECK revolver reloaded', 'cmd data get entity packtest SelectedItem']
for n in range(3): S += ['mdown 1', 'sleep 0.5', 'mup 1', 'sleep 0.3', 'shot', 'sleep 1.2']
S += ['cmd say CHECK revolver fired', 'cmd data get entity packtest SelectedItem', 'cmd data get entity @e[tag=target,limit=1] Health', 'cmd gamemode creative packtest', 'cmd clear packtest']
# hypertube: lay the four tubes by hand (use key = u), then ride
S += ['cmd say SECTION tube', 'cmd item replace entity packtest hotbar.0 with create_hypertube:hypertube 64', 'key 1']
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
S += ['cmd say SECTION portals', 'cmd tp packtest 34.5 100 31.5 90 0', 'sleep 20', 'shot', 'cmd say CHECK before the portal', 'cmd data get entity packtest Dimension',
      'cmd tp packtest 31.5 101 30.5', 'sleep 14', 'cmd say CHECK through the overworld portal', 'cmd data get entity packtest Dimension', 'cmd data get entity packtest Pos', 'shot',
      'cmd execute as packtest at @s run tp @s ~3 ~ ~', 'sleep 16', 'cmd execute as packtest at @s run tp @s ~-3 ~ ~', 'sleep 14',
      'cmd say CHECK back through the nether side', 'cmd data get entity packtest Dimension', 'cmd data get entity packtest Pos', 'shot',
      f'cmd execute in minecraft:the_nether run tp packtest {VX // 8 + 5.5} 70 {VZ // 8 + 0.5} 90 0', 'sleep 20', 'shot',
      f'cmd execute in minecraft:the_nether run tp packtest {VX // 8 + 1.5} 71 {VZ // 8 + 0.5}', 'sleep 16',
      f'cmd say CHECK from a nether portal under the void column {VX} {VZ}', 'cmd data get entity packtest Dimension', 'cmd data get entity packtest Pos',
      'cmd execute at packtest run function packtest:top', 'cmd execute at packtest run function packtest:col', 'cmd scoreboard players get y pt', 'shot',
      'cmd gamemode spectator packtest', 'cmd execute as packtest at @s run tp @s ~12 ~8 ~12 135 25', 'sleep 6', 'shot',
      'cmd execute in minecraft:the_end run tp packtest 60 70 0 90 10', 'sleep 20', 'cmd say CHECK the end', 'cmd data get entity packtest Dimension', 'shot',
      'cmd execute in minecraft:overworld run tp packtest 0 90 0 0 20', 'sleep 20', 'cmd gamemode creative packtest', 'key F3', 'sleep 4', 'shot', 'key F3',
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
