#!/usr/bin/env python3
"""usage: stacks.py <concatenated jstack output> -> where the running worker threads are.

Every RUNNABLE sample of a worker / the server thread is counted once, in the first group below that has a frame in
its stack (so the percentages add up to 100), then the top frames."""
import re, sys, collections
GROUPS = [   # name, regex over the frames of a sample (innermost first)
    ('terrain: 3D noise', r'synth\.|NoiseFunction|OldBlendedNoise'),
    ('terrain: aquifer', r'Aquifer'),
    ('terrain: other density functions', r'densityfunction\.'),
    ('surface rule', r'material\.|NoiseBasedChunkGenerator\.buildSurface'),
    ('carvers', r'carver\.|generateCarvers|applyCarvingMask'),
    ('terrain: fill (blocks into sections)', r'NoiseBasedChunkGenerator\.(doFill|buildTerrain|lambda\$buildTerrain)|ChunkStatusTasks\.buildTerrain'),
    ('features', r'ChunkStatusTasks\.generateFeatures|applyBiomeDecoration|placement\.|feature\.'),
    ('structures', r'generateStructureStarts|generateStructureReferences|structure\.'),
    ('biomes', r'ChunkStatusTasks\.generateBiomes|fillBiomesFromNoise|createBiomes'),
    ('light', r'LightEngine|lighting\.'),
    ('heightmaps', r'Heightmap'),
    ('spawn at generation', r'spawnOriginalMobs|generateSpawn'),
    ('saving / loading chunks', r'SerializableChunkData|chunk\.storage|\.nbt\.|RegionFile|IOWorker'),
    ('full chunk (entities, block entities, POI)', r'ChunkStatusTasks\.full|LevelChunk|PoiManager|protoChunkToFullChunk'),
    ('waiting', r'waitForTasks|managedBlock|LockSupport|\.park'),
    ('commands (fill / scans of the test)', r'commands\.'),
    ('tick', r'MinecraftServer\.tick|ServerLevel\.tick'),
]
top, group, feat, n = collections.Counter(), collections.Counter(), collections.Counter(), 0
for block in open(sys.argv[1], errors='replace').read().split('\n\n'):
    lines = block.strip().split('\n')
    if not lines or not lines[0].startswith('"') or 'java.lang.Thread.State: RUNNABLE' not in block: continue
    name = lines[0].split('"')[1]
    if not re.match(r'Worker-|Server thread|c2me', name, re.I): continue
    frames = [l.strip()[3:].split('(')[0] for l in lines if l.strip().startswith('at ')]
    mc = [f for f in frames if f.startswith('net.minecraft') or f.startswith('com.ishland')]
    if not mc: continue
    if re.search(GROUPS[-3][1], mc[0]): continue   # the server thread waiting for the chunks it asked for
    g = next((gn for gn, rx in GROUPS if any(re.search(rx, f) for f in mc)), 'other')
    if g == 'waiting': continue
    n += 1; group[g] += 1
    if g == 'features':
        f = next((x for x in mc if re.search(r'feature\.\w+\.place$', x)), None) or next((x for x in mc if 'placement.' in x), 'other')
        feat[f.split('levelgen.')[-1]] += 1
    top[' < '.join(f.replace('net.minecraft.world.level.', '').replace('levelgen.', '') for f in mc[:3])] += 1
print(n, 'running samples (worker and server threads, waiting ones left out)')
print('--- share of the samples'); [print(f'{100 * c / max(n, 1):5.1f}% {c:5d} {k}') for k, c in group.most_common()]
if feat: print('--- features'); [print(f'{100 * c / max(n, 1):5.1f}% {c:5d} {k}') for k, c in feat.most_common(14)]
print('--- top frames'); [print(f'{c:5d} {k}') for k, c in top.most_common(30)]
