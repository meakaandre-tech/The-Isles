#!/usr/bin/env python3
"""The Nether part of the pack test report (called by report.py): reads server-nether.log and server-nether-base.log."""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT + '/tools')
import build_nether as BN

def messages(path):
    if not os.path.exists(path): return []
    return [re.sub(r'^\[[^\]]*\] \[[^\]]*\]: (\[Not Secure\] \[Server\] |System chat: )?', '', l) for l in open(path, errors='replace').read().split('\n')]
def scans(msg):
    tag, res = None, {}
    for m in msg:
        if m.startswith('SCAN '): tag = m[5:]
        elif tag and (m.startswith('Successfully filled') or m.startswith('No blocks were filled') or 'Unknown block' in m or "Can't find element" in m):
            n = int(re.search(r'(\d+) block', m).group(1)) if m.startswith('Succ') else (0 if m.startswith('No') else None)
            res.setdefault(tag, n); tag = None
    rows = {}
    for t, n in res.items():
        a, b = t.rsplit(' ', 1); rows.setdefault(a, {})[b.split(':')[1]] = n
    return rows
def table(rows, keys, w=16):
    bl = []
    for k in keys:
        for b in rows.get(k, {}):
            if b not in bl: bl.append(b)
    print('   ' + 'box'.ljust(w) + ' '.join(b[:9].rjust(9) for b in bl))
    for k in keys:
        if k in rows: print('   ' + k.ljust(w) + ' '.join(('' if rows[k].get(b) is None else str(rows[k][b])).rjust(9) for b in bl))

def perf(D, fails):
    """the perf variants of nether-phase.sh: times, heap, block counts of two layers, where the threads were"""
    import glob
    run = open(f'{D}/run.txt', errors='replace').read().split('\n') if os.path.exists(f'{D}/run.txt') else []
    lines = [l for l in run if ' NPERF ' in l]
    if not lines: return
    print('\n================ nether, perf variants (packtest/nether-perf.txt; one fresh world each) ================')
    print('   seconds for 64 chunks / for 9 chunks elsewhere afterwards, heap before -> with the chunks loaded')
    for l in lines: print('  ', l)
    names, rows = [], {}
    for f in sorted(glob.glob(f'{D}/server-nperf*-*.log')):
        n = os.path.basename(f)[7:-4]
        for k, v in scans(messages(f)).items(): rows[f'{n} {k}'] = v
    if rows:
        print('-- blocks of two layers in a 64x64 box, per variant (same layers and seed: the same counts)')
        table(rows, sorted(rows), 34)
    for f in sorted(glob.glob(f'{D}/nperf*-stacks.txt')):
        print(f'-- where the time goes, {os.path.basename(f)[:-11]}')
        for l in open(f).read().split('\n')[:22]:
            if l.startswith('--- top'): break
            print('   ' + l)

def report(D, fails, notes):
    perf(D, fails)
    msg = messages(f'{D}/server-nether.log')
    if not msg: return
    name = 'nether'
    print('\n================ nether (The Isles, every mod when the phases say nethermods) ================')
    print('layers (bottom..top, lava surface): ' + '  '.join(f'{l["k"]}: {l["bottom"]}..{l["top"] - 1} lava {l["lava"]}' for l in BN.LAYERS))
    if not any(m.startswith('SECTION end nether') for m in msg): fails.append(f'{name}: the console commands did not run to the end')
    run = [l for l in open(f'{D}/run.txt', errors='replace').read().split('\n')] if os.path.exists(f'{D}/run.txt') else []
    for l in run:
        if 'NGEN' in l or 'ngen' in l: print('  ', l)
    # columns
    col, cols = None, {}
    for m in msg:
        if m.startswith('NCOL '): col = m[5:]; cols[col] = []
        elif m.startswith('NC ') and col: y, c = m.split()[1:]; cols[col].append((int(y), int(c)))
    for k, v in cols.items():
        print(f'-- column {k}: per layer blocks of air, lava runs (top..bottom), bedrock, solid at the layer top / bottom')
        for l in reversed(BN.LAYERS):
            runs = []
            for i, (y, c) in enumerate(v):
                y2 = v[i + 1][0] + 1 if i + 1 < len(v) else BN.MIN_Y
                lo, hi = max(y2, l['bottom']), min(y, l['top'] - 1)
                if hi >= lo: runs.append((hi, lo, c))
            if not runs: continue
            air = sum(h - lo + 1 for h, lo, c in runs if c == 0); bed = sum(h - lo + 1 for h, lo, c in runs if c == 2)
            lava = [f'{h}..{lo}' for h, lo, c in runs if c == 1]
            top = runs[0][0] - runs[0][1] + 1 if runs[0][2] == 3 else 0; bot = runs[-1][0] - runs[-1][1] + 1 if runs[-1][2] == 3 else 0
            print(f'   layer {l["k"]:2d}: air {air:3d}  lava {" ".join(lava) or "-":<24} bedrock {bed}  solid top {top} bottom {bot}')
            if bed and 0 < l['k'] < len(BN.LAYERS) - 1: fails.append(f'{name}: bedrock inside layer {l["k"]} in column {k}')
    rows = scans(msg)
    lay = [f'layer{l["k"]}' for l in BN.LAYERS]
    if any(k in rows for k in lay):
        print('-- blocks per layer in a 64x64 box (vanilla: the vanilla Nether, same box, y 0..127)')
        base = scans(messages(f'{D}/server-nether-base.log'))
        if 'vanilla' in base: rows['vanilla'] = base['vanilla']
        table(rows, lay + ['bottom-pad', 'vanilla'])
        for l in BN.LAYERS:
            r = rows.get(f'layer{l["k"]}', {})
            if r.get('bedrock') and l['k'] < len(BN.LAYERS) - 1: fails.append(f'{name}: {r["bedrock"]} bedrock in layer {l["k"]}')
            for b in ('lava', 'nether_quartz_ore', 'nether_gold_ore', 'ancient_debris'):
                if r and not r.get(b): fails.append(f'{name}: no {b} in layer {l["k"]}')
            if r.get('sulfur_ore'): fails.append(f'{name}: {r["sulfur_ore"]} sulfur ore in layer {l["k"]} (it is switched off)')
        if not rows.get('bottom-pad', {}).get('bedrock'): fails.append(f'{name}: no bedrock at the bottom')
        print('-- air in the 16 blocks around each layer boundary, 128x128 (of 262144): ' + ' '.join(str(rows[k].get('air')) for k in rows if k.startswith('separator')))
        print('-- structures: marker blocks per layer around the located start')
        for k in rows:
            m = re.match(r'(.*)-layer(\d+)$', k)
            if m and list(rows[k].values())[0]: print(f'   {m.group(1):<16} layer {m.group(2):>2}: {list(rows[k].values())[0]} {list(rows[k])[0]}')
    cur, out, seen = None, [], {}
    for m in msg:
        if re.match(r'(COUNT|PORTALTEST|CHECK|VIEW|LOCATE|TICK) ', m): cur = m; seen[cur] = []; continue
        if cur and (m.startswith('Test passed') or 'has the following entity data' in m or re.match(r'(UNDER|AT|NBIOME|PORTAL) ', m) or 'is at [' in m or 'Could not find' in m or 'Percentiles' in m):
            seen[cur].append(re.sub(r'.*has the following entity data: ', '', m))
    frz = [l for l in open(f'{D}/server-nether.log', errors='replace').read().split('\n')]
    a = next((n for n, l in enumerate(frz) if 'FREEZE start' in l), None)
    if a is not None:
        print('-- portal into Nether that does not exist yet (server thread; the pings are sent half a second apart)')
        for l in frz[a:a + 60]:
            if 'FREEZE' in l or "Can't keep up" in l or 'lost connection' in l or 'CHECK through the overworld-fresh' in l: print('   ' + l[:150])
    print('-- mobs, portals, structures found, tick times')
    for k, v in seen.items():
        if v and not k.startswith('VIEW'): print(f'   {k:<52} {" | ".join(v)[:200]}')
    for tag in ('overworld-low', 'overworld-high'):
        v = seen.get(f'CHECK through the {tag} portal')
        if v is not None and not any('the_nether' in x for x in v): fails.append(f'{name}: the {tag} portal did not lead to the Nether: {" | ".join(v)[:120]}')
        if v and not any(x.startswith('UNDER solid') or x.startswith('UNDER obsidian') for x in v): fails.append(f'{name}: no solid ground behind the {tag} portal')
    for tag in [k for k in seen if k.startswith('CHECK through the nether-')]:
        if not any('overworld' in x for x in seen[tag]): fails.append(f'{name}: {tag[6:]}: did not lead to the Overworld: {" | ".join(seen[tag])[:120]}')
    if any('lost connection' in m for m in msg) and not any(m.startswith('SECTION end client') for m in msg): fails.append(f'{name}: the client lost its connection before the end of the script')
    done = next((n for n, m in enumerate(msg) if m.startswith('Done (')), None)
    if done is None: fails.append(f'{name}: the server did not start'); return
    bad = [m for m in msg[:done] if re.search(r'Registry loading errors|Failed to parse', m)] + [m for m in msg[done:] if re.search(r'Exception|PACKTEST delayed crash', m)]
    if bad: fails.append(f'{name}: {len(bad)} error lines in the server log, first: {bad[0][:140]}')
