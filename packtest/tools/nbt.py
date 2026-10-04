#!/usr/bin/env python3
"""Dumps a (gzipped) NBT file as indented text: nbt.py <file> [max-depth]"""
import gzip, struct, sys
data = open(sys.argv[1], 'rb').read()
if data[:2] == b'\x1f\x8b': data = gzip.decompress(data)
pos = 0
def rd(fmt):
    global pos
    n = struct.calcsize(fmt); v = struct.unpack_from(fmt, data, pos); pos += n; return v[0]
def string():
    global pos
    n = rd('>H'); s = data[pos:pos + n].decode('utf-8', 'replace'); pos += n; return s
def payload(t):
    global pos
    if t == 1: return rd('>b')
    if t == 2: return rd('>h')
    if t == 3: return rd('>i')
    if t == 4: return rd('>q')
    if t == 5: return rd('>f')
    if t == 6: return rd('>d')
    if t == 7: n = rd('>i'); pos += n; return f'<{n} bytes>'
    if t == 8: return string()
    if t == 9:
        et = rd('>b'); n = rd('>i'); return [payload(et) for _ in range(n)]
    if t == 10:
        d = {}
        while True:
            et = rd('>b')
            if et == 0: return d
            k = string(); d[k] = payload(et)
    if t == 11: n = rd('>i'); v = [rd('>i') for _ in range(n)]; return v if n <= 16 else f'<{n} ints>'
    if t == 12: n = rd('>i'); pos += 8 * n; return f'<{n} longs>'
    raise ValueError(t)
t = rd('>b'); string(); tree = payload(t)
maxd = int(sys.argv[2]) if len(sys.argv) > 2 else 6
def show(v, ind=0, d=0):
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, (dict, list)) and x and d < maxd and not (isinstance(x, list) and not isinstance(x[0], (dict, list))):
                print(' ' * ind + k + ':'); show(x, ind + 2, d + 1)
            else: print(' ' * ind + f'{k}: {str(x)[:300]}')
    elif isinstance(v, list):
        for n, x in enumerate(v[:40]):
            print(' ' * ind + f'- [{n}]'); show(x, ind + 2, d + 1)
    else: print(' ' * ind + str(v)[:300])
show(tree)
