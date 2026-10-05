#!/usr/bin/env python3
"""Third-party packs The Isles can take biomes (and the cave world) from: "providers".

  python3 tools/providers.py fetch     download the providers that have a public URL into vendor/ (sha256 checked)
  python3 tools/providers.py list      what is in vendor/, and which vanilla biomes each provider ships for 26.3

layout/providers.json lists them (page, licence, file name pattern, URL and sha256 of the tested version). The packs
themselves are never committed: vendor/ is ignored by git, and what tools/build_pack.py makes from them goes to build/
(ignored as well). None of them allows redistribution, see README.md.

A provider is a zip (or an unpacked folder) in vendor/ whose name matches the manifest's "file" pattern; of several
matches the last by name wins, so a newer version only has to be dropped in.
"""
import fnmatch, hashlib, json, sys, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
FORMAT = 121   # data pack format of Minecraft 26.3

def manifest():
    return json.loads((ROOT / "layout" / "providers.json").read_text())["providers"]

def _major(v):   # pack formats are written as 81, [121, 0] or {"min_inclusive": ..}
    return v[0] if isinstance(v, list) else v
def _range(e):
    """(min, max) of a pack.mcmeta "pack" section or overlay entry"""
    lo, hi = e.get("min_format"), e.get("max_format")
    f = e.get("formats", e.get("supported_formats"))
    if isinstance(f, dict): f = [f["min_inclusive"], f["max_inclusive"]]
    if isinstance(f, int): f = [f, f]
    if lo is None: lo = f[0] if f else e.get("pack_format")
    if hi is None: hi = f[1] if f else e.get("pack_format")
    return _major(lo), _major(hi)

class Pack:
    """The files of a data pack as Minecraft 26.3 sees them: {"data/<ns>/...": bytes}, overlays applied."""
    def __init__(self, pid, meta, path):
        self.id, self.meta, self.path = pid, meta, path
        raw = {}
        if path.is_dir():
            for f in path.rglob("*"):
                if f.is_file(): raw[f.relative_to(path).as_posix()] = f.read_bytes()
        else:
            with zipfile.ZipFile(path) as z:
                for n in z.namelist():
                    if not n.endswith("/"): raw[n] = z.read(n)
        tops = [n for n in raw if n.endswith("pack.mcmeta")]
        top = min(tops, key=len)[:-len("pack.mcmeta")]   # a zip may hold the pack in one folder
        raw = {n[len(top):]: b for n, b in raw.items() if n.startswith(top)}
        mcmeta = json.loads(raw["pack.mcmeta"])
        lo, hi = _range(mcmeta["pack"])
        self.supports = lo <= FORMAT <= hi
        self.format = (lo, hi)
        self.overlays = [e["directory"] for e in mcmeta.get("overlays", {}).get("entries", [])
                         if _range(e)[0] <= FORMAT <= _range(e)[1]]
        self.files = {n: b for n, b in raw.items() if n.startswith("data/")}
        for d in self.overlays:   # later entries win
            self.files.update({n[len(d) + 1:]: b for n, b in raw.items() if n.startswith(d + "/data/")})
        self.sha256 = None if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest()
        self.tested = self.sha256 is not None and self.sha256 == meta.get("sha256")
    def json(self, rel):
        return json.loads(self.files[rel]) if rel in self.files else None
    def biomes(self):
        """the vanilla biomes this pack replaces"""
        pre = "data/minecraft/worldgen/biome/"
        return sorted(n[len(pre):-5] for n in self.files if n.startswith(pre) and n.endswith(".json") and "/" not in n[len(pre):])
    def namespaces(self):
        return sorted({n.split("/")[1] for n in self.files})

def find(pid, meta):
    if not VENDOR.is_dir(): return None
    hit = sorted(p for p in VENDOR.iterdir() if fnmatch.fnmatch(p.name.lower(), meta["file"].lower()))
    return hit[-1] if hit else None

def load(only=None):
    """{id: Pack} of the providers present in vendor/ (ISLES_PROVIDERS=none: nothing; =a,b: only those)"""
    out = {}
    for pid, meta in manifest().items():
        if only is not None and pid not in only: continue
        p = find(pid, meta)
        if p: out[pid] = Pack(pid, meta, p)
    return out

def fetch():
    VENDOR.mkdir(exist_ok=True)
    ok = True
    for pid, meta in manifest().items():
        if find(pid, meta): print(f"{pid}: {find(pid, meta).name} is there"); continue
        if not meta.get("url"):
            print(f"{pid}: no public download ({meta['page']}); put your copy ({meta['file']}) into vendor/"); continue
        name = meta["url"].rsplit("/", 1)[1].replace("%20", "_")
        req = urllib.request.Request(meta["url"], headers={"User-Agent": "the-isles-build (github.com/meakaandre-tech/The-Isles)"})
        data = urllib.request.urlopen(req, timeout=60).read()
        sha = hashlib.sha256(data).hexdigest()
        if meta.get("sha256") and sha != meta["sha256"]:
            print(f"{pid}: sha256 of the download is {sha}, the manifest says {meta['sha256']}: not saved"); ok = False; continue
        (VENDOR / name).write_bytes(data); print(f"{pid}: {name} ({len(data)} bytes)")
    return ok

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "fetch": sys.exit(0 if fetch() else 1)
    for pid, p in load().items():
        print(f"{pid}: {p.path.name}, pack format {p.format[0]}..{p.format[1]}" + ("" if p.supports else f" (NOT made for {FORMAT})")
              + ("" if p.tested else ", not the tested version") + f", overlays {p.overlays or 'none'}, namespaces {p.namespaces()}")
        print(f"  {len(p.biomes())} vanilla biomes: {' '.join(p.biomes())}")
