#!/usr/bin/env python3
"""Nether probes of the pack test: python3 packtest/gen_nether.py <out-dir> (after gen.py, which creates the probe pack).

Writes commands-nether.txt (server console, The Isles), commands-nether-base.txt (same server without the pack: the
vanilla Nether as reference), script-nether.txt (client script) and adds functions to the probe data pack.
"""
import json, math, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1]
sys.path.insert(0, ROOT + '/tools')
import build_nether as BN
LAY = BN.LAYERS
ISL = {i['id']: i for i in json.load(open(ROOT + '/layout/islands.json'))['islands']}
F = OUT + '/probes/data/packtest/function'
os.makedirs(F, exist_ok=True)
def fn(name, lines): open(f'{F}/{name}.mcfunction', 'w').write('\n'.join(lines) + '\n')
N = 'execute in minecraft:the_nether run '
MIN_Y, TOP_Y = BN.MIN_Y, BN.TOP - 1

# packtest:ncol - run at the top of a column: says every change of block class on the way down (0 air, 1 lava, 2 bedrock, 3 other)
fn('ncol', ['scoreboard players set y pt %d' % TOP_Y, 'scoreboard players set prev pt -1', 'function packtest:nscan', 'say NCOLEND'])
fn('nscan', ['scoreboard players set c pt 3', 'execute if block ~ ~ ~ #minecraft:air run scoreboard players set c pt 0',
             'execute if block ~ ~ ~ minecraft:lava run scoreboard players set c pt 1',
             'execute if block ~ ~ ~ minecraft:bedrock run scoreboard players set c pt 2',
             'execute unless score c pt = prev pt run function packtest:nchange', 'scoreboard players operation prev pt = c pt',
             'scoreboard players remove y pt 1', f'execute if score y pt matches {MIN_Y}.. positioned ~ ~-1 ~ run function packtest:nscan'])
fn('nchange', ['execute store result storage packtest:n y int 1 run scoreboard players get y pt',
               'execute store result storage packtest:n c int 1 run scoreboard players get c pt', 'function packtest:nsay with storage packtest:n'])
fn('nsay', ['$say NC $(y) $(c)'])
NB = ['nether_wastes', 'soul_sand_valley', 'crimson_forest', 'warped_forest', 'basalt_deltas']
fn('nbiome', [f'execute if biome ~ ~ ~ minecraft:{b} run say NBIOME {b}' for b in NB])
FEET = ['obsidian', 'netherrack', 'lava', 'air', 'grass_block', 'stone', 'soul_sand', 'soul_soil', 'basalt', 'blackstone', 'crimson_nylium', 'warped_nylium', 'nether_portal', 'sand', 'snow_block', 'gravel']
fn('nfeet', [f'execute if block ~ ~-1 ~ minecraft:{b} run say UNDER {b}' for b in FEET] + [f'execute if block ~ ~ ~ minecraft:{b} run say AT {b}' for b in FEET]
   + ['execute if block ~ ~-1 ~ #minecraft:air run say UNDER #air', 'execute unless block ~ ~-1 ~ #minecraft:air unless block ~ ~-1 ~ minecraft:lava run say UNDER solid'])

BLOCKS = ['minecraft:netherrack', 'minecraft:lava', 'minecraft:bedrock', 'minecraft:nether_quartz_ore', 'minecraft:nether_gold_ore', 'minecraft:ancient_debris',
          'minecraft:glowstone', 'minecraft:soul_sand', 'minecraft:soul_soil', 'minecraft:basalt', 'minecraft:blackstone', 'minecraft:magma_block',
          'minecraft:gravel', 'minecraft:crimson_nylium', 'minecraft:warped_nylium', 'cgs:sulfur_ore']
def scan(c, tag, x0, y0, z0, x1, y1, z1, blocks, pre=N):
    for b in blocks:
        c += [f'say SCAN {tag} {b}', f'{pre}fill {x0} {y0} {z0} {x1} {y1} {z1} minecraft:structure_void replace {b}',
              f'{pre}fill {x0} {y0} {z0} {x1} {y1} {z1} {"minecraft:air" if b.startswith("#") else b} replace minecraft:structure_void']
HEAD = ['say SECTION start', 'scoreboard objectives add pt dummy', 'gamerule max_block_modifications 100000000',
        'gamerule max_command_sequence_length 10000000', 'gamerule maxCommandChainLength 10000000', 'tick query']
MOBS = ['strider', 'piglin', 'zombified_piglin', 'ghast', 'magma_cube', 'hoglin', 'enderman', 'skeleton', 'blaze', 'wither_skeleton']
def mobs(tag): return [x for m in MOBS for x in (f'say COUNT {tag} {m}', f'execute if entity @e[type=minecraft:{m}]')]
def gen(n=127):
    return ['say SECTION gen', '#sleep 10', '#heap before-ngen', '#time NGEN-64-chunks', N + f'forceload add 0 0 {n} {n}',
            '#poll 2400 ' + N + f'execute if loaded 0 0 0 if loaded {n} 0 {n} run say LOADED ngen ## LOADED ngen', '#time', '#heap with-ngen',
            'tick query', '#sleep 45', 'say TICK after-45s', 'tick query'] + mobs('gen')

C = HEAD + gen()
C += ['say SECTION columns']
COLS = [(8, 8), (72, 40), (120, 120), (40, 100)]
for x, z in COLS:
    C += [f'say NCOL {x} {z}', N + f'execute positioned {x} {TOP_Y} {z} run function packtest:ncol', '#wait 120 ## NCOLEND']
    for l in LAY: C += [f'say NBIOMEAT {x} {z} layer {l["k"]}', N + f'execute positioned {x} {l["lava"] + 40} {z} run function packtest:nbiome']
C += ['say SECTION layers']
for l in LAY:
    scan(C, f'layer{l["k"]}', 0, l['bottom'], 0, 63, l['top'] - 1, 63, BLOCKS)
    if l['k'] > 0: scan(C, f'separator{l["k"] - 1}-{l["k"]}', 0, l['bottom'] - 4, 0, 127, l['bottom'] + 11, 127, ['#minecraft:air'])
scan(C, 'bottom-pad', 0, MIN_Y, 0, 63, LAY[0]['bottom'] - 1, 63, ['minecraft:bedrock', 'minecraft:netherrack', 'minecraft:lava', '#minecraft:air'])
C += [N + 'forceload remove all', 'say SECTION structures']
def structure(tag, s, ox, oz, block):
    c = [f'say LOCATE {tag}', 'fill 0 0 0 0 0 0 minecraft:air replace minecraft:structure_void',
         N + f'execute positioned {ox} 0 {oz} run locate structure {s}', '#wait 180 ## is at \\[|Could not find', '#loc', N + 'forceload add {X0} {Z0} {X1} {Z1}',
         '#sleep 2']
    for l in LAY:
        c += [f'say SCAN {tag}-layer{l["k"]} {block}', N + f'fill {{X0}} {l["bottom"]} {{Z0}} {{X1}} {l["top"] - 1} {{Z1}} minecraft:structure_void replace {block}',
              N + f'fill {{X0}} {l["bottom"]} {{Z0}} {{X1}} {l["top"] - 1} {{Z1}} {block} replace minecraft:structure_void']
    return c + [N + 'forceload remove all']
C += structure('fortress', 'minecraft:fortress', 0, 0, 'minecraft:nether_bricks')
for n, (ox, oz) in enumerate([(0, 0), (1500, 1500), (-2000, 800)]): C += structure(f'bastion{n}', 'minecraft:bastion_remnant', ox, oz, 'minecraft:polished_blackstone_bricks')
C += structure('ruined-portal', 'minecraft:ruined_portal_nether', 0, 0, 'minecraft:obsidian')
C += structure('fossil', 'minecraft:nether_fossil', 0, 0, 'minecraft:bone_block')
C += ['tick query']
open(OUT + '/commands-nether.txt', 'w').write('\n'.join(C + ['say SECTION end nether']) + '\n')

B = HEAD + gen() + ['say SECTION layers']
scan(B, 'vanilla', 0, 0, 0, 63, 127, 63, BLOCKS)
B += [N + 'forceload remove all', 'tick query']
open(OUT + '/commands-nether-base.txt', 'w').write('\n'.join(B + ['say SECTION end nether-base']) + '\n')

# ------------------------------------------------------------------ client
S = ['cmd say SECTION client', 'cmd gamemode creative packtest', 'cmd time set noon']
def frame(pre, at):   # a lit portal: frame in the x/y plane, the lower left portal block at the position
    return [f'cmd {pre}{at}fill ~-1 ~-1 ~ ~2 ~3 ~ minecraft:obsidian', f'cmd {pre}{at}fill ~ ~ ~ ~1 ~2 ~ minecraft:air', f'cmd {pre}{at}setblock ~ ~ ~ minecraft:fire',
            f'cmd {pre}{at}execute if block ~ ~ ~ minecraft:nether_portal run say PORTAL lit']
def where(tag): return [f'cmd say CHECK {tag}', 'cmd data get entity packtest Dimension', 'cmd data get entity packtest Pos', 'cmd execute at packtest run function packtest:nfeet',
                        'cmd execute at packtest run function packtest:nbiome']
# views and mobs in two layers: a platform in the cavern, 45 blocks above the lava
for k, (px, pz) in ((6, (72, 40)), (9, (72, 40))):
    l = LAY[k]; y = l['lava'] + 45
    S += [f'cmd say SECTION layer {k}', f'cmd {N}forceload add {px} {pz}', 'sleep 3', f'cmd {N}fill {px - 2} {y - 1} {pz - 2} {px + 2} {y - 1} {pz + 2} minecraft:glass',
          f'cmd {N}fill {px - 2} {y} {pz - 2} {px + 2} {y + 3} {pz + 2} minecraft:air', f'cmd {N}tp packtest {px + .5} {y} {pz + .5} 0 10', 'sleep 75']
    for yaw, pitch in ((0, 10), (90, 25), (180, -20), (270, 40), (0, 89)): S += [f'cmd say VIEW layer{k} yaw {yaw} pitch {pitch}', f'cmd {N}tp packtest {px + .5} {y} {pz + .5} {yaw} {pitch}', 'sleep 9', 'shot']
    S += ['cmd gamemode survival packtest', 'cmd effect give packtest minecraft:resistance infinite 255 true', 'cmd effect give packtest minecraft:fire_resistance infinite 255 true',
          'cmd kill @e[type=!minecraft:player]', 'sleep 120'] + [f'cmd {x}' for x in mobs(f'layer{k}-120s')] + ['cmd tick query', 'shot',
          'sleep 120'] + [f'cmd {x}' for x in mobs(f'layer{k}-240s')] + ['cmd gamemode creative packtest', f'cmd {N}forceload remove all']
# portals from the Overworld: the lowest and the highest island
S += ['cmd say SECTION portals']
lo, hi = min(ISL.values(), key=lambda i: i['y_top']), max(ISL.values(), key=lambda i: i['y_top'])
for tag, i in (('low', lo), ('high', hi)):
    x, z = i['x'], i['z']
    S += [f'cmd say PORTALTEST overworld-{tag} island {i["id"]} top {i["y_top"]}', f'cmd forceload add {x} {z}', f'cmd tp packtest {x} {i["y_top"] + 30} {z}', 'sleep 25',
          f'cmd execute positioned {x} 0 {z} positioned over motion_blocking run summon minecraft:marker ~ ~ ~ {{Tags:["pf{tag}"]}}',
          f'cmd data get entity @e[type=minecraft:marker,tag=pf{tag},limit=1] Pos']
    S += frame('', f'execute at @e[type=minecraft:marker,tag=pf{tag},limit=1] run ')
    S += [f'cmd execute at @e[type=minecraft:marker,tag=pf{tag},limit=1] run tp packtest ~0.5 ~ ~0.5', 'sleep 40'] + where(f'through the overworld-{tag} portal') + ['shot',
          'cmd execute at packtest run tp packtest ~3 ~ ~3', 'sleep 2', 'cmd forceload remove all']
# portals from the Nether: layer 2 under the spawn island, layer 9 under a void column
for tag, k, x, z in (('layer2-under-S1', 2, 300, 300), ('layer9-void', 9, 2000, -1000)):
    y = LAY[k]['lava'] + 40
    S += [f'cmd say PORTALTEST nether-{tag} at {x} {y} {z}', f'cmd {N}tp packtest {x + .5} {y} {z + 2.5}', 'sleep 30',
          f'cmd {N}fill {x - 3} {y - 1} {z - 3} {x + 4} {y - 1} {z + 3} minecraft:netherrack', f'cmd {N}fill {x - 3} {y} {z - 3} {x + 4} {y + 4} {z + 3} minecraft:air']
    S += frame(N, f'execute positioned {x} {y} {z} run ')
    S += [f'cmd {N}tp packtest {x + .5} {y} {z + .5}', 'sleep 40'] + where(f'through the nether-{tag} portal') + ['shot', 'cmd execute at packtest run tp packtest ~3 ~ ~3', 'sleep 2']
S += ['cmd tick query', 'cmd say SECTION end client']
open(OUT + '/script-nether.txt', 'w').write('\n'.join(S) + '\n')
