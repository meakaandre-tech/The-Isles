#!/usr/bin/env python3
"""Turns the logs of a pack test into a report: report.py <dir with the logs>  (also writes <dir>/verdict.txt)"""
import json, math, os, re, sys
D = sys.argv[1]
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L = json.load(open(ROOT + '/layout/islands.json'))
I = {i['id']: i for i in L['islands']}
MIN_Y = L['min_y']
sys.path.insert(0, ROOT + '/tools')
try:
    from build_pack import RELIEF, DEFAULT_RELIEF
except Exception:
    RELIEF, DEFAULT_RELIEF = {}, 18
fails, notes = [], []

def lines(name):
    p = f'{D}/{name}'
    return open(p, errors='replace').read().split('\n') if os.path.exists(p) else []
def msg(l):
    m = re.match(r'^\[[\d:]+\] \[([^\]]*)\]: (.*)$', l)
    return (m.group(1), re.sub(r'^(\[Not Secure\] )?\[Server\] |^System chat: ', '', m.group(2))) if m else ('', l)

NOISE = re.compile(r'Ambiguity between arguments|is missing mods\.toml|Mod .* uses the version|experimental|Server Watchdog|Can\'t keep up|'
                   r'moved too quickly|make no attempt to authenticate|While this makes the game possible|To change this, set "online-mode"|sun.misc.Unsafe|Unknown or incomplete command|authlib|\*\*\*\* |Reference map|@Mixin target .* was not found')
def problems(name):
    out = []
    for l in lines(name):
        if re.search(r'/(ERROR|WARN|FATAL)\]|Exception|^\s+at |Caused by', l) and not NOISE.search(l): out.append(l[:260])
    return out

def covering(x, z, frac=1.0):
    return [i for i in L['islands'] if math.hypot(x - i['x'], z - i['z']) < i['radius'] * frac]
def top_range(i):
    amp = 0 if i['kind'] == 'basin' else min(RELIEF.get(i['biome'], DEFAULT_RELIEF), 0.5 * i['thickness'])
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
        if m.startswith(start + ' '): cur = m[len(start) + 1:]; res[cur] = []; continue
        if re.match(r'(SECTION|PROBE|BODY|MID|COUNT|LOCATE|DIMCOUNT|SCAN|LOADED|PREGEN|CHECK) ', m) or m.startswith('say '): cur = None
        elif cur is not None and t.startswith('Server thread') and not m.startswith(('Running function', 'Executed ', 'Marked ', 'Unmarked ')): res[cur].append(m)
    return res

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
            if p['kind'] in ('void', 'outside') and not cov:
                exp = f'void {MIN_Y}'
                if y != MIN_Y: verdict = 'FAIL not empty'
                elif b != 'the_isles:void': verdict = 'FAIL biome'
            elif y is None: verdict = 'FAIL no answer'
            else:
                ranges = [(i, top_range(i)) for i in cov]
                hit = [i for i, (lo, hi) in ranges if lo <= y <= hi]
                want = max(core, key=lambda i: i['y_top']) if core else None
                exp = (f"{want['id']} {want['y_top']}" if want else 'rim ' + '/'.join(i['id'] for i in cov))
                if y == MIN_Y and core: verdict = 'FAIL no ground'
                elif not hit and core: verdict = f'FAIL height (allowed {",".join("%d..%d" % r for _, r in ranges)})'
                elif hit and b != 'minecraft:' + hit[0]['biome'] and b not in ['minecraft:' + i['biome'] for i in cov]: verdict = f"FAIL biome (want {hit[0]['biome']})"
            if verdict != 'ok': fails.append(f"{name}: probe {p['tag']} {p['kind']}: {verdict}")
            print(f"{p['tag']:<16}{p['x']:>6}{p['z']:>6}{str(y):>8}{str(p.get('ws')):>7}  {exp:<16}{b:<30}{p.get('top', '?'):<14} {verdict}")
    for start in ('BODY', 'MID', 'COUNT', 'LOCATE', 'DIMCOUNT', 'SCAN'):
        d = parse_tagged(log, start)
        if d:
            print(f'\n-- {start}')
            for k, v in d.items(): print(f'   {k:<34} {" | ".join(x[:110] for x in v[:6])}')
    print('\n-- other')
    for l in ls:
        t, m = msg(l)
        if re.match(r'(LIMIT|TOPBIOMEOK|PREGEN|CHECK|SECTION) ', m) or re.search(r'Average time per tick|P50|P95|P99|Target tick rate|Sample: ', m): print('   ', l[:11], m[:200])
    if isles:
        want = {i for i in json.load(open(f'{D}/gen.json'))['sample']} if os.path.exists(f'{D}/gen.json') else set()
        ok = {msg(l)[1].split()[1] for l in ls if msg(l)[1].startswith('TOPBIOMEOK ')}
        if want and want - ok:
            fails.append(f'{name}: biome above the island is not the layout biome on {sorted(want - ok)}')
        for lim in ('bottom-ok', 'top-ok'):
            if not any('LIMIT ' + lim in l for l in ls): fails.append(f'{name}: build limit {lim} missing')

for l in lines('run.txt'):
    if l.startswith('['): print(l)
for l in lines('build.txt'): print('build:', l)
server_report('vanilla'); server_report('baseline', False)
for n in range(20): server_report(f'bisect-{n}')
server_report('pack')
for extra in ('report-pack.txt',):
    for l in lines(extra): print(l)
print('\n================ verdict ================')
print('PASS' if not fails else 'FAIL')
for f in fails: print('  -', f)
open(f'{D}/verdict.txt', 'w').write(('PASS' if not fails else 'FAIL') + '\n' + ''.join(f'- {f}\n' for f in fails[:30]))
