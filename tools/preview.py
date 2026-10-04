#!/usr/bin/env python3
"""Offline sanity check: evaluates the generated density functions with a stand-in noise and
draws a biome map plus vertical slices. Shapes are indicative only; the game's noise differs."""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DF = ROOT / "datapack/data/the_isles/worldgen/density_function"
NOISE = {"edge": (-7, 3), "relief": (-7, 4), "under": (-5, 3), "rag": (-5, 3)}
cache = {}
def load(name):
    if name not in cache: cache[name] = json.loads((DF / (name.split(":")[1] + ".json")).read_text())
    return cache[name]
def fake_noise(name, x, y, z, ys):
    octave, count = NOISE[name]; h = sum(map(ord, name)); out = np.zeros_like(x, dtype=float); amp = 1.0; tot = 0
    for o in range(count):
        f = 2.0 ** (octave + o) * 2 * np.pi
        out += amp * (np.sin(x * f + h + 1.7 * o) * np.cos(z * f * 1.13 + 0.6 * h) + (np.sin(y * ys * f * 1.31 + o) * np.cos((x + z) * f * 0.71 + h) if ys else 0))
        tot += amp * (2 if ys else 1); amp *= 0.5
    return out / tot
def ev(f, x, y, z):
    if isinstance(f, (int, float)): return np.full(x.shape, float(f))
    if isinstance(f, str):
        if f == "minecraft:y": return y.astype(float)
        return ev(load(f), x, y, z)
    t = f["type"].split(":")[1]; E = lambda k: ev(f[k], x, y, z)
    if t == "add": return E("left") + E("right")
    if t == "sub": return E("left") - E("right")
    if t == "mul": return E("left") * E("right")
    if t == "min": return np.minimum(E("left"), E("right"))
    if t == "max": return np.maximum(E("left"), E("right"))
    if t == "clamp": return np.clip(E("input"), f["min"], f["max"])
    if t == "sqrt": return np.sqrt(E("input"))
    if t == "cache": return E("input")
    if t == "gradient":
        c = {"x": x, "y": y, "z": z}[f["axis"]].astype(float); a, b = f["from_coordinate"], f["to_coordinate"]
        return f["from_value"] + (np.clip(c, a, b) - a) / (b - a) * (f["to_value"] - f["from_value"])
    if t == "slice":
        yy = y if f["axis"] != "y" else np.full(y.shape, f["coordinate"]); return ev(f["input"], x, yy, z)
    if t == "distance_to_point":
        px, py, pz = f["point"]; return np.sqrt((x - px) ** 2 + (y - py) ** 2 + (z - pz) ** 2)
    if t == "noise": return fake_noise(f["noise"].split(":")[1], x * f["xz_scale"], y, z * f["xz_scale"], f["y_scale"])
    if t == "range_choice":
        v = E("input"); m = (v >= f["min_inclusive"]) & (v < f["max_exclusive"]); out = np.empty(x.shape)
        if m.any(): out[m] = ev(f["when_in_range"], x[m], y[m], z[m])
        if (~m).any(): out[~m] = ev(f["when_out_of_range"], x[~m], y[~m], z[~m])
        return out
    if t == "interval_select":
        idx = np.searchsorted(np.array(f["thresholds"]), E("input"), side="right"); out = np.empty(x.shape)
        for k in np.unique(idx):
            m = idx == k; out[m] = ev(f["functions"][k], x[m], y[m], z[m])
        return out
    raise ValueError(t)

layout = json.loads((ROOT / "layout/islands.json").read_text())
dim = json.loads((ROOT / "datapack/data/minecraft/dimension/overworld.json").read_text())
codes = [(e["parameters"]["temperature"], e["biome"]) for e in dim["generator"]["biome_source"]["biomes"]]
fig, ax = plt.subplots(2, 2, figsize=(22, 17), facecolor="#10141c")
def style(a, t):
    a.set_title(t, color="white", fontsize=13); a.tick_params(colors="#9aa6bd"); a.set_facecolor("#1a2233")
# biome codes, top-down at y=64 and y=900
for a, yy in zip(ax[0], (64, 1000)):
    g = np.arange(-4000, 4001, 16); X, Z = np.meshgrid(g, g); B = ev("the_isles:biome_code", X.ravel(), np.full(X.size, yy), Z.ravel()).reshape(X.shape)
    a.imshow(np.where(B < -1.79, np.nan, B), extent=[-4000, 4000, 4000, -4000], cmap="turbo"); style(a, f"Biome code per column at y={yy} (dark = void biome)")
    # every island centre must resolve to its own biome
bad = 0
for i in layout["islands"]:
    if i["layer"] == "high": continue
    v = ev("the_isles:biome_code", np.array([i["x"]]), np.array([i["y_top"] - 5]), np.array([i["z"]]))[0]
    got = min(codes, key=lambda c: abs((c[0][0] + c[0][1]) / 2 - v))[1]
    if got != "minecraft:" + i["biome"]: bad += 1; print("biome mismatch", i["id"], i["biome"], got)
print("biome mismatches:", bad)
for a, (zc, x0, x1, y0, y1, t) in zip(ax[1], [(0, -1500, 1500, -700, 300, "Spawn island, slice at z=0"), (-3380, 2900, 3900, 200, 1500, "High Peaks stack, slice at z=-3380")]):
    xs = np.arange(x0, x1, 2); ys = np.arange(y0, y1, 2); X, Yy = np.meshgrid(xs, ys)
    D = ev("the_isles:terrain", X.ravel(), Yy.ravel(), np.full(X.size, zc)).reshape(X.shape)
    a.imshow(D > 0, extent=[x0, x1, y0, y1], origin="lower", cmap="Greens", vmin=-0.3, aspect="equal"); style(a, t)
    print(t, "solid fraction", round(float((D > 0).mean()), 3))
# every island must produce solid terrain at its centre
empty = 0
for i in layout["islands"]:
    ys = np.arange(i["y_bottom"] - 20, i["y_top"] + 20, 2.0)
    D = ev("the_isles:terrain", np.full(ys.shape, i["x"]), ys, np.full(ys.shape, i["z"]))
    if not (D > 0).any(): empty += 1; print("no terrain:", i["id"], i["radius"], i["thickness"])
print("islands with no terrain at centre:", empty)
fig.savefig(ROOT / "layout/preview-check.png", facecolor=fig.get_facecolor(), dpi=70)
