#!/usr/bin/env python3
"""usage: stacks.py <concatenated jstack output> -> where the running worker threads are (counts of the top Minecraft frames)"""
import re, sys, collections
top, phase, n = collections.Counter(), collections.Counter(), 0
for block in open(sys.argv[1]).read().split('\n\n'):
    lines = block.strip().split('\n')
    if not lines or not lines[0].startswith('"') or 'java.lang.Thread.State: RUNNABLE' not in block: continue
    name = lines[0].split('"')[1]
    if not re.match(r'Worker-|Server thread|c2me', name, re.I): continue
    frames = [l.strip()[3:].split('(')[0] for l in lines if l.strip().startswith('at ')]
    mc = [f for f in frames if f.startswith('net.minecraft')]
    if not mc: continue
    n += 1
    top[' < '.join(f.replace('net.minecraft.world.level.', '').replace('levelgen.', '') for f in mc[:3])] += 1
    for f in mc:
        m = re.search(r'(NoiseBasedChunkGenerator\.(\w+)|ChunkStatusTasks\.(\w+)|ThreadedLevelLightEngine|LightEngine|placement\.\w+|carver\.\w+|SurfaceSystem|Aquifer\$NoiseBasedAquifer\.\w+)', f)
        if m: phase[m.group(1)] += 1
print(n, 'running samples')
print('--- frames anywhere in the stack'); [print(f'{c:5d} {k}') for k, c in phase.most_common(40)]
print('--- top frames'); [print(f'{c:5d} {k}') for k, c in top.most_common(40)]
