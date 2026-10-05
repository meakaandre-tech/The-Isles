#!/usr/bin/env python3
"""Turns the logs of a pack test into a report: report.py <dir with the logs>  (also writes <dir>/verdict.txt)"""
import json, math, os, re, sys
D = sys.argv[1]
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L = json.load(open(ROOT + '/layout/islands.json'))
I = {i['id']: i for i in L['islands']}
MIN_Y = L['min_y']
sys.path.insert(0, ROOT + '/tools')
from build_pack import RELIEF, DEFAULT_RELIEF, pack_biome
for i in L['islands']: i['layout_biome'] = i['biome']; i['biome'] = pack_biome(i)
fails, notes = [], []

def lines(name):
    p = f'{D}/{name}'
    return open(p, errors='replace').read().split('\n') if os.path.exists(p) else []
def msg(l):
    m = re.match(r'^\[[\d:]+\] \[([^\]]*)\]: (.*)$', l)
    return (m.group(1), re.sub(r'^(\[Not Secure\] )?\[Server\] |^System chat: ', '', m.group(2))) if m else ('', l)

NOISE = re.compile(r'Ambiguity between arguments|is missing mods\.toml|Mod .* uses the version|experimental|Server Watchdog|Can\'t keep up|'
                   r'moved too quickly|Error loading class: |config/create/server\.json|\[STDERR\]: \s+at |Failed to read config file|packtest:biome|the_isles:void|make no attempt to authenticate|While this makes the game possible|To change this, set "online-mode"|sun.misc.Unsafe|Unknown or incomplete command|authlib|\*\*\*\* |Reference map|@Mixin target .* was not found')
def problems(name):
    out = []
    for l in lines(name):
        if re.search(r'/(ERROR|WARN|FATAL)\]|Exception|^\s+at |Caused by', l) and not NOISE.search(l): out.append(l[:260])
    return out

def covering(x, z, frac=1.0):
    return [i for i in L['islands'] if math.hypot(x - i['x'], z - i['z']) < i['radius'] * frac]
def top_range(i):
    amp = 0 if i['kind'] == 'basin' else min(RELIEF.get(i['layout_biome'], DEFAULT_RELIEF), 0.5 * i['thickness'])
    lo = i['y_top'] - amp - min(10, 0.1 * i['thickness']) - (0.3 * i['thickness'] if i['kind'] == 'basin' else 0) - 10
    return lo, i['y_top'] + 40   # trees and structures may stand on top

def parse_probes(name):
    """-> list of dicts {tag, kind, x, z, y, ws, top, biome, biomeok}"""
    res, cur = [], None
    for l in lines(name):
        t, m = msg(l)
        g = re.match(r'PROBE (\S+) (\S+) (-?\d+) (-?\d+)', m)
        if g:
            cur = {'tag': g.group(1), 'kind': g.group(2), 'x': int(g.group(3)), 'z': int(g.group(4))}; res.append(cur); continue
        if cur is None: continue
        if m.startswith('TOP ') and 'top' not in cur: cur['top'] = m[4:]
        elif m.startswith('BIOME ') and 'biome' not in cur: cur['biome'] = m[6:]
        elif m.startswith('BIOMEOK '): cur['biomeok'] = True
        elif m == 'SNOWLAYER': cur['snow'] = True
        else:
            g = re.match(r'(y|ws) has (-?\d+) \[pt\]', m)
            if g and g.group(1) not in cur: cur[g.group(1)] = int(g.group(2))
        if m.startswith(('BODY', 'SECTION', 'LOADED')): cur = None
    return res

def parse_tagged(name, start):
    """say <start> <key...> followed by answer lines -> {key: [answers]}"""
    res, cur = {}, None
    for l in lines(name):
        t, m = msg(l)
        if m.startswith(start + ' ') or m == start:
            cur = m[len(start) + 1:] or start
            while cur in res: cur += "'"
            res[cur] = []; continue
        if re.match(r'(SECTION|PROBE|BODY|MID|COUNT|LOCATE|DIMCOUNT|SCAN|SCANBOX|OIL|VIEW|LOADED|PREGEN|CHECK|WORLDSPAWN)( |$)', m) or m.startswith('say '): cur = None
        elif cur is not None and t.startswith('Server thread') and not m.startswith(('Running function', 'Executed ', 'Marked ', 'Unmarked ')): res[cur].append(m)
    return res

def filled(v):
    """blocks changed by the fill commands answered in v (None: no answer)"""
    n, seen = 0, False
    for x in v:
        m = re.search(r'filled (\d+) block', x)
        if m: n += int(m.group(1)); seen = True
        elif 'No blocks' in x: seen = True
    return n if seen else None

def structure_table(name, log, probes, scans):
    """/locate results with what stands there: ground of the column, the structure's blocks near the ground and anywhere else in the columns"""
    loc = parse_tagged(log, 'LOCATE')
    rows = [k for k in loc if '/' in k]
    if not rows: return
    took = {m.group(1): m.group(2) for l in lines('run.txt') for m in [re.search(r'TIME LOCATE-(\S+) ([\d.]+) s', l)] if m} if name == 'vanilla' else {}
    pr = {p['tag'][1:]: p for p in probes if p['kind'] == 'structure'}
    print(f'\n-- structures ({name}): /locate, the ground there, the structure\'s marker blocks from 130 below to 70 above that ground (5x5 chunks), in the rest of those columns, and of all of them in the lowest 200 layers of the world')
    print(f'   {"structure/from":<34}{"found at":>16}{"island":>8}{"ground":>8}{"near":>7}{"elsewhere":>10}{"floor":>7}{"locate s":>9}  verdict')
    for k in rows:
        ans = ' | '.join(loc[k]); m = re.search(r'is at \[(-?\d+), [^,]+, (-?\d+)\]', ans)
        off = k.split('/')[0] in ('stronghold', 'mineshaft', 'mineshaft_mesa', 'monument', 'mansion', 'ancient_city')
        if not m:
            verdict = 'off, as generated' if off and 'ould not find' in ans else 'not found' if 'ould not find' in ans else 'NO ANSWER: ' + ans[:60]
            if 'NO ANSWER' in verdict or k.startswith('isles-stronghold'): fails.append(f'{name}: structure {k}: {verdict}')
            print(f'   {k:<34}{"-":>16}{"":>8}{"":>8}{"":>7}{"":>10}{"":>7}{took.get(k, ""):>9}  {verdict}'); continue
        x, z = int(m.group(1)), int(m.group(2)); p = pr.get(k, {}); y = p.get('y')
        cov = covering(x, z)
        def cnt(kind):
            q = [q for q in scans if q.startswith(f'{k} {kind} ')]
            return filled(scans[q[0]]) if q else None
        near, else_, floor = cnt('near'), cnt('elsewhere'), cnt('floor')
        verdict = 'ok'
        if off: verdict = 'FAIL: the generator switches this off'
        elif y is None: verdict = 'no probe'
        elif floor: verdict = f'ON THE WORLD FLOOR: {floor} blocks'
        elif y == MIN_Y: verdict = 'starts over the void (nothing built)' if not near and not else_ else 'starts over the void'
        elif not near and not else_: verdict = 'ok (none of its marker blocks there)'
        elif else_: verdict = 'ok (reaches more than 130 below / 70 above the ground at its start)'
        # the pack's own stronghold must be right; the others are findings (rims), listed, not fatal
        if 'FAIL' in verdict or (k.startswith('isles-stronghold') and not verdict.startswith('ok')): fails.append(f'{name}: structure {k} at {x} {z}: {verdict}')
        elif 'FLOOR' in verdict: notes.append(f'{name}: structure {k} at {x} {z}: {verdict}')
        isl = max(cov, key=lambda i: i['y_top'])['id'] if cov else '-'
        print(f'   {k:<34}{f"{x} {z}":>16}{isl:>8}{str(y):>8}{str(near):>7}{str(else_):>10}{str(floor):>7}{took.get(k, ""):>9}  {verdict}')
    for k, v in scans.items():
        if 'y-of-the-frames' in k or k.startswith('floor-under'): print(f'   {k}: {" | ".join(x[:60] for x in v)}')
        if k.startswith('floor-under') and filled(v): fails.append(f'{name}: {k}: {filled(v)} blocks on the world floor')

def phase_times():
    """run.txt -> {phase: [(label, value)]} for the TIME and HEAP lines"""
    res, cur = {}, None
    for l in lines('run.txt'):
        m = re.search(r'\] (\S+): server start', l)
        if m: cur = m.group(1); res.setdefault(cur, [])
        m = re.search(r'\] TIME (\S+) ([\d.]+) s', l)
        if m and cur: res[cur].append((m.group(1), float(m.group(2))))
        m = re.search(r'\] HEAP (\S+) used (\d+)K', l)
        if m and cur: res[cur].append(('heap ' + m.group(1), round(int(m.group(2)) / 1024)))
    return res

def perf_report():
    """the perf phase: one row per pack variant; and where the chunk workers spend their time (thread dumps while generating)"""
    t = phase_times(); names = [n for n in t if n.startswith('perf-')]
    if names:
        cols = ['PREGEN-land-256-chunks', 'PREGEN-void-256-chunks', 'PREGEN-tiers-64-chunks', 'LOCATE-mansion', 'LOCATE-jungle_pyramid', 'heap with-land', 'heap with-void', 'heap before-land']
        print('\n================ perf: pack variants (seconds; heap in MB after a full collection) ================')
        print(f'   {"variant":<22}' + ''.join(f'{c.replace("PREGEN-", "").replace("-chunks", "")[:14]:>15}' for c in cols) + '   tick P50/P95/P99 after land')
        for n in names:
            d = dict(t[n]); pc = [m.group(1) for l in lines(f'server-{n}.log') for m in [re.search(r'Percentiles: (.*?)\. Sample', l)] if m]
            print(f'   {n[5:]:<22}' + ''.join(f'{str(d.get(c, "-")):>15}' for c in cols) + '   ' + (pc[1] if len(pc) > 1 else '-'))
    for f in sorted(os.listdir(D)):
        if not (f.startswith('prof-') and f.endswith('.txt')): continue
        from collections import Counter
        top, mid, n = Counter(), Counter(), 0
        for block in open(f'{D}/{f}', errors='replace').read().split('\n\n'):
            ls = block.split('\n')
            if not ls or not re.match(r'"(Worker-Main|Server thread)', ls[0]): continue
            fr = [x.strip()[3:].split('(')[0] for x in ls if x.strip().startswith('at ')]
            if not fr or 'RUNNABLE' not in block or fr[0].startswith(('jdk.internal.misc.Unsafe.park', 'java.lang.Thread.sleep')): continue
            n += 1; top[fr[0]] += 1
            mc_ = [x for x in fr if x.startswith('net.minecraft.')]
            if mc_: mid[mc_[0]] += 1
            for x in fr:
                if re.search(r'ChunkStatusTasks\.|NoiseBasedChunkGenerator\.(doFill|buildSurface|applyCarvers|createStructures|createReferences|applyBiomeDecoration|fillFromNoise|createBiomes|populateBiomes|doCreateBiomes)|LightEngine|ThreadedLevelLightEngine\.|StructureCheck|findNearestMapStructure', x): mid['STEP ' + x] += 1; break
        if n:
            print(f'\n-- {f}: {n} running worker/server thread samples; innermost game frame, and the generation step it belongs to')
            for k, v in mid.most_common(14): print(f'   {v:>4} {100 * v // n:>3}%  {k[-110:]}')

def server_report(name, isles=True):
    log = f'server-{name}.log'; ls = lines(log)
    if not ls: return
    print(f'\n================ {name} ================')
    done = [l for l in ls if 'Done (' in l]
    print('boot:', done[0].split(']: ')[-1] if done else 'NO "Done" - the server did not start')
    if not done: fails.append(f'{name}: server did not start')
    pr = problems(log)
    print(f'ERROR/WARN lines: {len(pr)}')
    for l in pr[:60]: print('   ', l)
    if any('/ERROR]' in l or 'Exception' in l for l in pr): fails.append(f'{name}: {sum(1 for l in pr if "/ERROR]" in l or "Exception" in l)} error lines in the server log')
    probes = parse_probes(log)
    if isles and probes:
        print(f'\n{"probe":<16}{"x":>6}{"z":>6}{"ground":>8}{"surf":>7}  {"expected":<16}{"biome":<30}{"top":<14} verdict')
        for p in probes:
            y, b = p.get('y'), p.get('biome', '?')
            cov = covering(p['x'], p['z']); core = covering(p['x'], p['z'], 0.7)
            verdict, exp = 'ok', ''
            if y is None: verdict = 'FAIL no answer'
            elif p['kind'] in ('void', 'outside', 'rim') and not cov:
                exp = f'void {MIN_Y}'
                own = I.get(p['tag'])   # the rim point is 4 blocks outside the radius: the rag noise can still put a block there
                if y != MIN_Y and p['kind'] == 'rim' and own and own['y_bottom'] - 40 <= y <= own['y_top'] + 40: verdict = 'ok (ragged rim)'
                elif y != MIN_Y: verdict = 'FAIL not empty'
                elif b != 'the_isles:void' and p['kind'] != 'rim': verdict = 'FAIL biome'   # the biome footprint is 8 blocks wider than the radius
            elif p['kind'] == 'structure' and not cov: verdict = 'IN THE VOID' if y == MIN_Y else 'outside every island footprint, on something'
            else:
                ranges = [(i, top_range(i)) for i in cov]
                hit = [i for i, (lo, hi) in ranges if lo <= y <= hi]
                want = max(core, key=lambda i: i['y_top']) if core else None
                exp = (f"{want['id']} {want['y_top']}" if want else 'rim ' + '/'.join(i['id'] for i in cov))
                if p['kind'] == 'structure': verdict = 'in an island' if y > MIN_Y else 'IN THE VOID'
                elif y == MIN_Y and core and p['kind'] == 'half' and core[0]['radius'] < 100: verdict = 'ok (hole in a small ragged island)'
                elif y == MIN_Y and core: verdict = 'FAIL no ground'
                elif not hit and core: verdict = f'FAIL height (allowed {",".join("%d..%d" % r for _, r in ranges)})'
                elif hit and b != 'minecraft:' + hit[0]['biome'] and b not in ['minecraft:' + i['biome'] for i in cov]: verdict = f"FAIL biome (want {hit[0]['biome']})"
            if 'FAIL' in verdict: fails.append(f"{name}: probe {p['tag']} {p['kind']}: {verdict}")
            print(f"{p['tag']:<16}{p['x']:>6}{p['z']:>6}{str(y):>8}{str(p.get('ws')):>7}  {exp:<16}{b:<30}{p.get('top', '?') + (' +snow' if p.get('snow') else ''):<14} {verdict}")
        # snow cover by biome: only the biomes that snow in the vanilla overworld may have it
        SNOWY = {'snowy_plains', 'ice_spikes', 'snowy_taiga', 'snowy_beach', 'grove', 'snowy_slopes', 'jagged_peaks', 'frozen_peaks', 'frozen_ocean', 'deep_frozen_ocean'}
        snow = {}
        for p in probes:
            if p.get('y', MIN_Y) > MIN_Y and p.get('biome', '').startswith('minecraft:'):
                k = p['biome'][10:]; snow.setdefault(k, [0, 0]); snow[k][0] += 1; snow[k][1] += 1 if p.get('snow') else 0
        wrong = sorted(k for k, (n, sn) in snow.items() if sn and k not in SNOWY)
        bare = sorted(k for k, (n, sn) in snow.items() if not sn and k in SNOWY - {'frozen_ocean', 'deep_frozen_ocean', 'jagged_peaks', 'frozen_peaks', 'snowy_slopes', 'grove'})
        if bare: fails.append(f'{name}: no snow layer at all in {", ".join(bare)}')
        print(f"\nsnow layer on the ground: {sum(v[1] for v in snow.values())} of {sum(v[0] for v in snow.values())} probes; "
              f"in biomes that do not snow in vanilla: {', '.join(f'{k} {snow[k][1]}/{snow[k][0]}' for k in wrong) or 'none'}")
        if wrong: fails.append(f'{name}: snow cover in {len(wrong)} biomes that rain in vanilla ({", ".join(wrong[:6])}...)')
    scans = parse_tagged(log, 'SCAN')
    if scans:   # blocks per island: "SCAN <island> <block>" followed by the fill answers
        table = {}
        for k, v in scans.items():
            if '/' in k.split(' ')[0]: continue   # structure scans: see structure_table
            isl, block = k.split(' ', 1)
            m = re.search(r'filled (\d+) block', v[0]) if v else None
            table.setdefault(isl, {})[block] = int(m.group(1)) if m else (0 if v and 'No blocks' in v[0] else None)
        boxes = {msg(l)[1].split()[1]: msg(l)[1] for l in ls if msg(l)[1].startswith('SCANBOX ')}
        print('\n-- blocks inside 64x64 columns (SCAN)')
        for isl, d in table.items():
            print(f'   {boxes.get(isl, isl)}')
            print('      ' + ', '.join(f'{b.split(":")[1]} {n}' for b, n in d.items() if n))
            print('      none of: ' + ' '.join(b.split(':')[1] for b, n in d.items() if n == 0))
            if any(n is None for n in d.values()): print('      no answer: ' + ' '.join(b for b, n in d.items() if n is None))
    structure_table(name, log, probes, scans)
    for start in ('BODY', 'MID', 'COUNT', 'LOCATE', 'DIMCOUNT', 'OIL', 'CHECK', 'WORLDSPAWN', 'VIEW'):
        d = parse_tagged(log, start)
        if d:
            print(f'\n-- {start}')
            for k, v in d.items(): print(f'   {k:<34} {" | ".join(x[:(420 if start == "CHECK" else 110)] for x in v[:(30 if start == "CHECK" else 6)])}')
    print('\n-- other')
    for l in ls:
        t, m = msg(l)
        if re.match(r'(LIMIT|PREGEN|PORTAL|CHURN|SECTION) ', m) or re.search(r'Average time per tick|P50|P95|P99|Target tick rate|Sample: ', m): print('   ', l[:11], m[:200])
    if isles:
        want = {p['tag'] for p in probes if p['kind'] == 'centre' and p['tag'] in I}   # the islands this phase probed
        ok = {msg(l)[1].split()[1] for l in ls if msg(l)[1].startswith('TOPBIOMEOK ')}
        if want and want - ok and name in ('vanilla', 'pack'):
            fails.append(f'{name}: biome above the island is not the layout biome on {sorted(want - ok)}')
        if name in ('pack', 'pack-restart') and any('SECTION reactor' in l or 'SECTION restart' in l for l in ls) and not any('CHECK reactor-assembled' in l for l in ls):
            fails.append(f'{name}: the Create Nuclear reactor is not assembled')
        for lim in ('bottom-ok', 'top-ok'):
            if name == 'vanilla' and not any('LIMIT ' + lim in l for l in ls): fails.append(f'{name}: build limit {lim} missing')

for l in lines('run.txt'):
    if l.startswith('[') and ' poll ok ' not in l: print(l)
for l in lines('build.txt'): print('build:', l)
server_report('vanilla'); server_report('baseline', False)
for n in range(20): server_report(f'bisect-{n}')
server_report('pack')
if os.path.exists(f'{D}/server2-pack.log'): os.replace(f'{D}/server2-pack.log', f'{D}/server-pack-restart.log')
server_report('pack-restart')
perf_report()
for extra in ('report-pack.txt',):
    for l in lines(extra): print(l)
# packtest/known.txt: regexes of failures that are known findings (reported, not fixed); they do not fail the run
known = [l.split('#')[0].strip() for l in open(ROOT + '/packtest/known.txt')] if os.path.exists(ROOT + '/packtest/known.txt') else []
known = [k for k in known if k]
accepted = [f for f in fails if any(re.search(k, f) for k in known)]
fails = [f for f in fails if f not in accepted]
print('\n================ verdict ================')
for f in accepted: print('  known:', f)
for f in notes: print('  note:', f)
print('PASS' if not fails else 'FAIL')
for f in fails: print('  -', f)
open(f'{D}/verdict.txt', 'w').write(('PASS' if not fails else 'FAIL') + '\n' + ''.join(f'- {f}\n' for f in fails[:30]))
