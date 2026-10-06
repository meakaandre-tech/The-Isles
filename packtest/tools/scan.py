#!/usr/bin/env python3
"""Reads the saved world of a pack test (region files) and reports what console commands cannot say: where exactly blocks
are, and what stands around them.

  scan.py <world dir> <repository root> [server log]

1. Sea basins. The terrain section replaces every water block under a basin's floor and outside its rim by structure_void
   (that is how it counts them). Here each of those blocks is listed with its position, the zone it lies in, the island
   it belongs to and the blocks around it.
2. Structures in the basins (every start saved in a basin's chunks): where each piece stands relative to the water level
   and to the floor under it - submerged, floating, on the water, past the rim - and how deep a treasure chest is buried.

Lines starting with "FAIL " go into the verdict (packtest/tools/report.py)."""
import collections, glob, gzip, json, math, os, struct, sys, zlib

# ------------------------------------------------------------------------------------------------ NBT, region files
def read_nbt(data):
    pos = 0
    def payload(t):
        nonlocal pos
        if t == 1: v = data[pos]; pos += 1; return v - 256 if v > 127 else v
        if t == 2: v = struct.unpack_from('>h', data, pos)[0]; pos += 2; return v
        if t == 3: v = struct.unpack_from('>i', data, pos)[0]; pos += 4; return v
        if t == 4: v = struct.unpack_from('>q', data, pos)[0]; pos += 8; return v
        if t == 5: v = struct.unpack_from('>f', data, pos)[0]; pos += 4; return v
        if t == 6: v = struct.unpack_from('>d', data, pos)[0]; pos += 8; return v
        if t == 7: n = struct.unpack_from('>i', data, pos)[0]; pos += 4; v = data[pos:pos + n]; pos += n; return v
        if t == 8: n = struct.unpack_from('>H', data, pos)[0]; pos += 2; v = data[pos:pos + n].decode('utf-8', 'replace'); pos += n; return v
        if t == 9:
            et = data[pos]; n = struct.unpack_from('>i', data, pos + 1)[0]; pos += 5
            return [payload(et) for _ in range(n)]
        if t == 10:
            d = {}
            while True:
                et = data[pos]; pos += 1
                if et == 0: return d
                n = struct.unpack_from('>H', data, pos)[0]; pos += 2; k = data[pos:pos + n].decode('utf-8', 'replace'); pos += n
                d[k] = payload(et)
        if t == 11: n = struct.unpack_from('>i', data, pos)[0]; pos += 4; v = list(struct.unpack_from(f'>{n}i', data, pos)); pos += 4 * n; return v
        if t == 12: n = struct.unpack_from('>i', data, pos)[0]; pos += 4; v = struct.unpack_from(f'>{n}Q', data, pos); pos += 8 * n; return v
        raise ValueError(f'NBT tag {t}')
    t = data[0]; n = struct.unpack_from('>H', data, 1)[0]; pos = 3 + n
    return payload(t)

def ci(d, *names):
    """a compound's entry by name, whatever its case (the key names changed between versions)"""
    if not isinstance(d, dict): return None
    for n in names:
        if n in d: return d[n]
    low = {k.lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in low: return low[n.lower()]
    return None

class World:
    def __init__(self, world):
        dirs = [d for d in glob.glob(world + '/**/region', recursive=True) if 'the_nether' not in d and 'the_end' not in d and 'DIM' not in d]
        self.dir = dirs[0] if dirs else None
        self.raw_cache, self.chunks, self.files = {}, {}, {}
    def raw(self, cx, cz):
        """the decompressed NBT bytes of a chunk, None when it is not saved"""
        key = (cx >> 5, cz >> 5)
        if key not in self.files:
            if len(self.files) > 6: self.files.clear()
            p = f'{self.dir}/r.{key[0]}.{key[1]}.mca'
            self.files[key] = open(p, 'rb').read() if self.dir and os.path.exists(p) and os.path.getsize(p) >= 8192 else None
        f = self.files[key]
        if f is None: return None
        n = (cx & 31) + 32 * (cz & 31)
        off = struct.unpack_from('>I', f, 4 * n)[0]
        sector, count = off >> 8, off & 255
        if sector == 0: return None
        length, comp = struct.unpack_from('>IB', f, sector * 4096)
        body = f[sector * 4096 + 5: sector * 4096 + 4 + length]
        if comp & 128:   # the chunk is in its own file
            p = f'{self.dir}/c.{cx}.{cz}.mcc'
            if not os.path.exists(p): return None
            body = open(p, 'rb').read(); comp &= 127
        if comp == 1: return gzip.decompress(body)
        if comp == 2: return zlib.decompress(body)
        if comp == 3: return body
        raise ValueError(f'chunk compression {comp} (lz4?) is not read here')
    def chunk(self, cx, cz):
        if (cx, cz) not in self.chunks:
            if len(self.chunks) > 600: self.chunks.clear()
            r = self.raw(cx, cz)
            self.chunks[(cx, cz)] = Chunk(read_nbt(r)) if r is not None else None
        return self.chunks[(cx, cz)]
    def block(self, x, y, z):
        c = self.chunk(x >> 4, z >> 4)
        return c.block(x & 15, y, z & 15) if c else None

class Chunk:
    def __init__(self, nbt):
        self.nbt = nbt; self.sections = {}; self.decoded = {}
        for s in ci(nbt, 'sections') or []:
            y = ci(s, 'Y')
            if y is not None: self.sections[y] = s
    def palette(self, sy):
        s = self.sections.get(sy)
        bs = ci(s, 'block_states') if s else None
        return [ci(p, 'Name', 'id') for p in (ci(bs, 'palette') or [])] if bs else []
    def section(self, sy):
        """(palette names, palette properties, 4096 palette indices or None for a section of one block)"""
        if sy not in self.decoded:
            s = self.sections.get(sy); bs = ci(s, 'block_states') if s else None
            if not bs: self.decoded[sy] = (['minecraft:air'], [None], None)
            else:
                pal = ci(bs, 'palette') or []; names = [ci(p, 'Name', 'id') for p in pal]; props = [ci(p, 'Properties', 'properties') for p in pal]
                data = ci(bs, 'data')
                if not data or len(pal) == 1: self.decoded[sy] = (names, props, None)
                else:
                    bits = max(4, (len(pal) - 1).bit_length()); per = 64 // bits; mask = (1 << bits) - 1; idx = []
                    for v in data:
                        for k in range(per): idx.append((v >> (k * bits)) & mask)
                    self.decoded[sy] = (names, props, idx[:4096])
        return self.decoded[sy]
    def block(self, x, y, z, with_props=False):
        names, props, idx = self.section(y >> 4)
        k = idx[((y & 15) << 8) | (z << 4) | x] if idx else 0
        if k >= len(names): return 'minecraft:air'
        return (names[k], props[k]) if with_props else names[k]
    def find(self, wanted, y0, y1):
        """positions (x, y, z in the chunk's own x/z) of the blocks named in wanted, between y0 and y1"""
        out = []
        for sy in sorted(self.sections):
            if sy * 16 + 15 < y0 or sy * 16 > y1: continue
            if not any(n in wanted for n in self.palette(sy)): continue
            names, props, idx = self.section(sy)
            if idx is None:
                if names[0] in wanted: out += [(x, sy * 16 + y, z, names[0]) for y in range(16) for z in range(16) for x in range(16) if y0 <= sy * 16 + y <= y1]
                continue
            hit = {k for k, n in enumerate(names) if n in wanted}
            for p, k in enumerate(idx):
                if k in hit:
                    y = sy * 16 + (p >> 8)
                    if y0 <= y <= y1: out.append((p & 15, y, (p >> 4) & 15, names[k]))
        return out

# ------------------------------------------------------------------------------------------------ the report
def short(n): return (n or '?').replace('minecraft:', '')
SOFT = {'minecraft:air', 'minecraft:cave_air', 'minecraft:water', 'minecraft:structure_void', 'minecraft:kelp', 'minecraft:kelp_plant', 'minecraft:seagrass',
        'minecraft:tall_seagrass', 'minecraft:ice', 'minecraft:snow', 'minecraft:bubble_column', None}
def main(world, root, log=None):
    sys.path.insert(0, root + '/tools')
    import build_pack as bp, build_terrain as bt
    L = json.load(open(root + '/layout/islands.json')); islands = L['islands']
    basins = [i for i in islands if i['kind'] == 'basin']
    W = World(world)
    print(f'region files: {W.dir} ({len(glob.glob(W.dir + "/*.mca")) if W.dir else 0} files)')
    if not W.dir: print('FAIL scan: no region folder in the world'); return
    def owner(x, y, z, but=None):
        for j in islands:
            if j is not but and math.hypot(x - j['x'], z - j['z']) <= j['radius'] + bp.PAD and j['y_bottom'] - 12 <= y <= j['y_top'] + 60: return j
    shown_keys = False
    marked = collections.defaultdict(list); starts = []
    n_chunks = n_void = 0
    for i in basins:
        R = i['radius']; s = bt.basin_shape(i); w, d = s['water'], s['depth']
        for cx in range((i['x'] - R - 24) >> 4, ((i['x'] + R + 24) >> 4) + 1):
            for cz in range((i['z'] - R - 24) >> 4, ((i['z'] + R + 24) >> 4) + 1):
                raw = W.raw(cx, cz)
                if raw is None: continue
                n_chunks += 1
                has_void = b'structure_void' in raw; has_start = b'Children' in raw or b'children' in raw
                if not has_void and not has_start: continue
                c = W.chunk(cx, cz)
                if not shown_keys:
                    shown_keys = True
                    sec = next((s_ for s_ in (ci(c.nbt, 'sections') or []) if ci(ci(s_, 'block_states'), 'data')), None)
                    print('chunk keys:', sorted(c.nbt), '| section keys:', sorted(sec) if sec else None, '| palette entry:', (ci(ci(sec, 'block_states'), 'palette') or [None])[0] if sec else None)
                if has_void:
                    n_void += 1
                    # (only under the floor or past the rim: the sea-life scan marks the whole floor of six seas)
                    far = math.hypot(min(abs(cx * 16 - i['x']), abs(cx * 16 + 15 - i['x'])), min(abs(cz * 16 - i['z']), abs(cz * 16 + 15 - i['z']))) > R - 24
                    for x, y, z, name in c.find({'minecraft:structure_void'}, i['y_bottom'] - 230, w + 60 if far else w - d - 15):
                        if y < w - d - 14 or math.hypot(cx * 16 + x - i['x'], cz * 16 + z - i['z']) > R: marked[i['id']].append((cx * 16 + x, y, cz * 16 + z))
                if has_start:
                    st = ci(ci(c.nbt, 'structures'), 'starts') or {}
                    for sid, sv in st.items():
                        ch = ci(sv, 'Children')
                        if ch: starts.append((i, sid, sv, cx, cz))
    sys.stdout.flush()
    print(f'{n_chunks} saved chunks in the squares of {len(basins)} basins, {n_void} with marked blocks, {len(starts)} structure starts')

    # ---- 1. water under and outside the basins (marked by the terrain section's fills)
    print('\n== water under the floor and outside the rim of the sea basins (blocks the fills of the terrain section marked) ==')
    for i in basins:
        R = i['radius']; s = bt.basin_shape(i); w, d = s['water'], s['depth']
        zones = collections.defaultdict(list)
        for x, y, z in set(marked[i['id']]):
            r = math.hypot(x - i['x'], z - i['z']); o = owner(x, y, z, but=i)
            if o: zone = f'on {o["id"]}'
            elif y < w - d - 14: zone = 'under' if r <= R + bp.PAD else 'under, past the rim'
            elif r > R: zone = 'outside the rim'
            else: continue
            zones[zone].append((x, y, z))
        bad = {k: v for k, v in zones.items() if k.startswith(('under', 'outside'))}
        if not bad: continue
        print(f'{i["id"]} {i["biome"]} centre {i["x"]} {i["z"]} radius {R} top {i["y_top"]} water {w} designed floor {w - d} bottom {i["y_bottom"]}: ' + ', '.join(f'{len(v)} {k}' for k, v in sorted(zones.items())))
        for k, v in sorted(bad.items()):
            v.sort(); xs, ys, zs = zip(*v)
            print(f'  {k}: x {min(xs)}..{max(xs)} y {min(ys)}..{max(ys)} z {min(zs)}..{max(zs)}; by height: ' + ' '.join(f'{y}:{n}' for y, n in sorted(collections.Counter(ys).items())))
            # clusters (blocks within 3 of each other)
            left = set(v); clusters = []
            while left:
                seed = left.pop(); grp = [seed]; todo = [seed]
                while todo:
                    a = todo.pop()
                    near = [b for b in left if abs(a[0] - b[0]) <= 3 and abs(a[1] - b[1]) <= 3 and abs(a[2] - b[2]) <= 3]
                    for b in near: left.discard(b); grp.append(b); todo.append(b)
                clusters.append(sorted(grp))
            for grp in sorted(clusters, key=len, reverse=True)[:8]:
                xs, ys, zs = zip(*grp); cx_, cy_, cz_ = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2, (min(zs) + max(zs)) // 2
                r = math.hypot(cx_ - i['x'], cz_ - i['z'])
                around = collections.Counter(W.block(x, y, z) for x in range(min(xs) - 5, max(xs) + 6) for y in range(min(ys) - 5, max(ys) + 6) for z in range(min(zs) - 5, max(zs) + 6))
                col = [short(W.block(cx_, y, cz_)) for y in range(max(ys) + 12, min(ys) - 13, -1)]
                runs = []
                for b in col:
                    if runs and runs[-1][0] == b: runs[-1][1] += 1
                    else: runs.append([b, 1])
                print(f'    {len(grp)} blocks x {min(xs)}..{max(xs)} y {min(ys)}..{max(ys)} z {min(zs)}..{max(zs)}, {r:.0f} from the centre ({r / R:.2f} R), {w - max(ys)} under the water level, {max(ys) - i["y_bottom"]} over the listed bottom')
                print('      around (5 blocks): ' + ', '.join(f'{short(b)} {n}' for b, n in around.most_common(14)))
                print(f'      column at {cx_} {cz_} from y {max(ys) + 12} down: ' + ' '.join(f'{b}x{n}' for b, n in runs))
                print('      first blocks: ' + ' '.join(f'{x},{y},{z}' for x, y, z in grp[:6]))

    # ---- 2. structures in the basins
    sys.stdout.flush()
    print('\n== structures that start in the chunks of a sea basin ==')
    print(f'{"structure":<26}{"basin":>6}{"at":>20}{"r/R":>6}{"y":>14}{"water":>7}{"floor":>7}{"under":>8}{"over":>6}{"gap med/max":>12}{"void":>6}  note')
    seen = set(); summary = collections.defaultdict(list)
    for i, sid, sv, cx, cz in starts:
        boxes = [ci(c_, 'BB') for c_ in ci(sv, 'Children') if ci(c_, 'BB')]
        if not boxes: continue
        x0, y0, z0 = (min(b[k] for b in boxes) for k in range(3)); x1, y1, z1 = (max(b[k] for b in boxes) for k in range(3, 6))
        key = (sid, x0, y0, z0)
        if key in seen: continue
        seen.add(key)
        mx, mz = (x0 + x1) // 2, (z0 + z1) // 2
        i = min(basins, key=lambda b: math.hypot(mx - b['x'], mz - b['z']) / b['radius'])   # (squares of neighbouring basins overlap)
        R = i['radius']; s = bt.basin_shape(i); w, d = s['water'], s['depth']; r = math.hypot(mx - i['x'], mz - i['z'])
        if r > R + 40: continue
        # the structure's own blocks: what is in its box that is neither water, air nor the ground's kind; the ground under it
        gaps, voids, tops, kinds = [], 0, [], collections.Counter()
        for x in range(x0, x1 + 1, max(1, (x1 - x0) // 12)):
            for z in range(z0, z1 + 1, max(1, (z1 - z0) // 12)):
                col = [W.block(x, y, z) for y in range(y1 + 2, y0 - 26, -1)]   # from 2 over the box down to 25 under it
                body = [k for k, b in enumerate(col[2:2 + y1 - y0 + 1]) if b not in SOFT]
                for b in col[2:2 + y1 - y0 + 1]: kinds[b] += 1
                if not body: continue
                low = 2 + body[-1]     # the lowest block in the box's height in this column (structure or ground)
                g = 0
                while low + 1 + g < len(col) and col[low + 1 + g] in SOFT: g += 1
                if low + 1 + g >= len(col): voids += 1
                elif low == 2 + y1 - y0: gaps.append(g)     # (the column's lowest block is the box's bottom layer: what is under it)
                else: gaps.append(0)
                tops.append(y1 - body[0])
        top = max(tops) if tops else y1
        chests = [(x, y, z) for ccx in range(x0 >> 4, (x1 >> 4) + 1) for ccz in range(z0 >> 4, (z1 >> 4) + 1) if W.chunk(ccx, ccz)
                  for x, y, z, n in W.chunk(ccx, ccz).find({'minecraft:chest'}, y0 - 2, y1 + 2) for x, z in [(ccx * 16 + x, ccz * 16 + z)] if x0 - 1 <= x <= x1 + 1 and z0 - 1 <= z <= z1 + 1]
        note = []
        for x, y, z in chests[:3]:
            above = [W.block(x, yy, z) for yy in range(y + 1, y + 14)]
            cover = next((k for k, b in enumerate(above) if b in SOFT), len(above))
            note.append(f'chest {x} {y} {z}: {cover} blocks of {short(above[0]) if cover else "nothing"} over it, {w - y} under the water level' if y <= w else f'chest {x} {y} {z}: {y - w} over the water level, {cover} blocks over it')
        gaps.sort()
        where = 'sea' if r <= R * (1 - s['e0']) else 'ring' if r <= R else 'past the rim'
        g_med, g_max = (gaps[len(gaps) // 2], gaps[-1]) if gaps else ('-', '-')
        flags = []
        if top > w and where == 'sea': flags.append(f'{top - w} above the water')
        if gaps and g_med > 2: flags.append('floats')
        if voids: flags.append(f'{voids} columns with nothing under them')
        print(f'{short(sid):<26}{i["id"]:>6}{f"{mx} {mz}":>20}{r / R:>6.2f}{f"{y0}..{y1}":>14}{w:>7}{w - d:>7}{w - y0:>8}{max(0, top - w):>6}{f"{g_med}/{g_max}":>12}{voids:>6}  {where}'
              + ('; ' + ', '.join(flags) if flags else '') + ('; ' + '; '.join(note) if note else '')
              + '; blocks: ' + ', '.join(f'{short(b)} {n}' for b, n in kinds.most_common(7)))
        summary[short(sid)].append((where, top - w, g_med if gaps else None, voids, w - y1))
    print()
    for sid, v in sorted(summary.items()):
        sea = [e for e in v if e[0] == 'sea']
        print(f'{sid}: {len(v)} ({len(sea)} in a sea, {sum(1 for e in v if e[0] == "ring")} on a ring, {sum(1 for e in v if e[0] == "past the rim")} past the rim); in a sea: '
              f'{sum(1 for e in sea if e[1] <= 0)} wholly under water, {sum(1 for e in sea if e[1] > 0)} reach above it, '
              f'{sum(1 for e in sea if e[2] is not None and e[2] > 2)} float (more than 2 blocks of water or air under the middle column), {sum(1 for e in v if e[3])} with columns over nothing')

def selftest():
    """a region file written here and read back: palette indices of 5 bits, a section of one block, a structure start"""
    import tempfile
    def tag(t, name, payload): b = name.encode(); return bytes([t]) + struct.pack('>H', len(b)) + b + payload
    def s8(v): b = v.encode(); return struct.pack('>H', len(b)) + b
    pal = ['minecraft:stone', 'minecraft:air', 'minecraft:water', 'minecraft:structure_void'] + [f'minecraft:b{k}' for k in range(14)]   # 18 entries: 5 bits
    idx = [0] * 4096; idx[(3 << 8) | (5 << 4) | 7] = 3; idx[(15 << 8) | (15 << 4) | 15] = 2; idx[1] = 17
    longs = []
    for k in range(0, 4096, 12):
        v = 0
        for n, e in enumerate(idx[k:k + 12]): v |= e << (5 * n)
        longs.append(v)
    palette = b''.join(tag(8, 'Name', s8(n)) + b'\0' for n in pal)
    bs = tag(9, 'palette', bytes([10]) + struct.pack('>i', len(pal)) + palette) + tag(12, 'data', struct.pack('>i', len(longs)) + b''.join(struct.pack('>Q', v) for v in longs)) + b'\0'
    sec = tag(1, 'Y', struct.pack('>b', -3)) + tag(10, 'block_states', bs) + b'\0'
    sec2 = tag(1, 'Y', struct.pack('>b', 4)) + tag(10, 'block_states', tag(9, 'palette', bytes([10]) + struct.pack('>i', 1) + tag(8, 'Name', s8('minecraft:water')) + b'\0') + b'\0') + b'\0'
    root = tag(10, '', tag(9, 'sections', bytes([10]) + struct.pack('>i', 2) + sec + sec2) + tag(3, 'xPos', struct.pack('>i', -1)) + b'\0')
    body = zlib.compress(root)
    d = tempfile.mkdtemp(); os.makedirs(d + '/dimensions/minecraft/overworld/region')
    head = bytearray(8192); n = (31) + 32 * (2 & 31); head[4 * n:4 * n + 4] = struct.pack('>I', (2 << 8) | 1)
    open(d + '/dimensions/minecraft/overworld/region/r.-1.0.mca', 'wb').write(bytes(head) + struct.pack('>IB', len(body) + 1, 2) + body + b'\0' * 4096)
    W = World(d); c = W.chunk(-1, 2)
    assert c.block(7, -48 + 3, 5) == 'minecraft:structure_void' and c.block(15, -33, 15) == 'minecraft:water' and c.block(1, -48, 0) == 'minecraft:b13' and c.block(0, -48, 0) == 'minecraft:stone'
    assert c.block(3, 70, 3) == 'minecraft:water' and c.block(3, 200, 3) == 'minecraft:air'
    assert c.find({'minecraft:structure_void'}, -100, 100) == [(7, -45, 5, 'minecraft:structure_void')] and W.block(-16 + 7, -45, 32 + 5) == 'minecraft:structure_void'
    assert len(c.find({'minecraft:water'}, 64, 79)) == 4096 and W.raw(0, 0) is None
    print('selftest ok')

if __name__ == '__main__':
    if sys.argv[1:] == ['selftest']: selftest()
    else: main(*sys.argv[1:4])
