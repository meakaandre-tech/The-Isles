#!/usr/bin/env python3
"""The cave world inside the spawn island: Dwarfhollow ("Cavernous World", by kanokarob) fitted into island S1.

Called by tools/build_pack.py when the pack is in vendor/ (see tools/providers.py; it may not be redistributed, so this
only ever goes into build/). Dwarfhollow replaces the whole Overworld with one cave world, y -64..320: solid rock
riddled with caverns (a Nether-like 3D noise), a rock floor and a rock ceiling, 15 biomes placed by depth - highlands
above y 183, midlands down to y -9, seas below (sea level -6). Here it is the inside of one island:

  * Height. No scaling: a Dwarfhollow height y is world height y + SHIFT, so its top (320) lies at y -11, 65 to 75 blocks
    under the island's surface, and its floor (-64) at y -395. The island is 600 thick only near its centre and its
    underside is irregular; where it ends higher, the lower part of the cave world is simply not there (the seas only
    exist in the deepest parts). SHIFT puts Dwarfhollow's sea level on a height an aquifer of the game can have.
  * Shell. Caves are only carved ROOF blocks under the island's surface, FLOOR above its underside and SIDE in from its
    rim (zone()); over the last 12 blocks towards those limits the carving fades out. Everything outside is the island
    as before, so nothing opens to the void.
  * Biomes. Inside that zone the biome source gets Dwarfhollow's own parameter list (its 48 entries, unchanged) and its
    climate functions; outside, the islands' biome code as before (router()).
  * Features. Its configured/placed features are converted to the 26.3 formats (tools/convert81.py) with their heights
    moved by SHIFT. "count_on_every_layer" walks down the whole column for every layer (2,000 blocks of void under the
    island, 73 features): replaced by random heights inside the cave world and a short search for the floor.
  * Surface. Its surface rule (grass, mycelium, mud, sand, ice ... by biome) runs for its biomes only.
  * Entrances. The sinkholes of layout/islands.json are shafts from the surface into the cave world; "spiral_ledge" ones
    have a ramp winding down the wall.
Left out: its dimension and dimension type (the Overworld stays The Isles'), its noise settings, and its functions,
predicates and entity tag (they only move the world spawn and respawning players under its bedrock ceiling).
"""
import copy, json, math
import convert81

NSD = "dwho"
SHIFT = -331            # world y = Dwarfhollow y + SHIFT: its sea level -6 -> -337 = 40 * -9 + 23, a height aquifers can have
DH_MIN, DH_TOP = -64, 320
ROOF, FLOOR, SIDE = 56, 32, 28
FADE = 12.0
LAYER_TRIES = 12        # attempts per unit of a count_on_every_layer count
SINK_BOTTOM = {"spiral_ledge": -150, "water_landing": -120, "sheer_drop": -110}   # where a shaft ends (the cave world's highlands)
RAMP_PITCH, RAMP_WIDTH, RAMP_THICK, SECTORS = 36, 8, 12, 12

def base_amplitude(amps):
    """NormalNoise.computeParityBaseAmplitude of 26.3: the base_amplitude with which a noise equals the 1.21 noise of the
    same amplitudes (the old normalisation by the span of non-zero octaves over the new one by estimated deviation)"""
    a = [m * 0.5 ** k for k, m in enumerate(amps) if m]
    idx = [k for k, m in enumerate(amps) if m]
    new = (sum(abs(x) for x in a) / 3) / (0.2702247831245211 * math.sqrt(2) * math.sqrt(sum(x * x for x in a)))
    old = (1 / 6) / (0.1 * (1 + 1 / (idx[-1] - idx[0] + 1)))
    return old / new

class Caves:
    def __init__(self, bp, pack, layout, islands, island_id="S1"):
        self.bp, self.pack, self.layout = bp, pack, layout
        self.island = next(i for i in islands if i["id"] == island_id)
        self.lo, self.hi = DH_MIN + SHIFT, DH_TOP + SHIFT
        self.biomes = sorted(n.split("/")[-1][:-5] for n in pack.files if n.startswith(f"data/{NSD}/worldgen/biome/"))
        self.log = []

    # ------------------------------------------------------------------------------------------------ terrain
    def noises(self):
        bp = self.bp
        for n in ("rocks", "ridge", "erosion", "continentalness"):
            d = self.pack.json(f"data/{NSD}/worldgen/noise/{n}.json")
            bp.write(f"data/{bp.NS}/worldgen/noise/cave_{n}.json", {"amplitude_modifiers": d["amplitudes"], "base_amplitude": base_amplitude(d["amplitudes"]),
                                                                    "base_octave": d["firstOctave"], "octave_count": len(d["amplitudes"])})
        def flat2d(noise, scale):
            return bp.flat(bp.mc("noise", noise=bp.ref(noise), shift_x="minecraft:shift_x", shift_z="minecraft:shift_z", xz_scale=scale, y_scale=0.0))
        bp.write(f"data/{bp.NS}/worldgen/density_function/cave/continents.json", flat2d("cave_continentalness", 0.65))
        bp.write(f"data/{bp.NS}/worldgen/density_function/cave/erosion.json", flat2d("cave_erosion", 0.25))
    def zone(self):
        """flat fields of the island: top and bottom of the zone the cave world may occupy and the distance in from the side
        shell; cave/inner: how many blocks a point lies inside that zone (negative outside)"""
        bp, i = self.bp, self.island
        inside, surface, bottom, edge = bp.island_fields(i)     # (writes the island's files again, unchanged)
        w = lambda name, f: bp.write(f"data/{bp.NS}/worldgen/density_function/cave/{name}.json", f)
        w("top", bp.flat(bp.sub(surface, ROOF)))
        w("bottom", bp.flat(bp.add(bottom, FLOOR)))
        # edge is (distance from the rim) / 12 inside the footprint
        w("side", bp.flat(bp.add(bp.mul(inside, bp.sub(bp.mul(edge, 12.0), SIDE)), bp.mul(bp.sub(inside, 1), 1000.0))))
        T, B, S = (bp.ref(f"cave/{k}") for k in ("top", "bottom", "side"))
        w("inner", bp.dmin(bp.dmin(bp.sub(bp.dmin(T, self.hi + 24), bp.Y), bp.sub(bp.Y, B)), S))
    def density(self):
        """Dwarfhollow's final density before its squeeze (dwho:base_3d_noise with its top and bottom slides), at world heights"""
        bp = self.bp; n = lambda noise, xz, y: bp.mc("noise", noise=bp.ref(noise), xz_scale=float(xz), y_scale=float(y))
        base = bp.add(bp.add(bp.add(bp.add(bp.add(n("cave_rocks", 2, 7), bp.mul(-0.925, bp.ref("cave/erosion"))),
                                           bp.mul(0.325, n("cave_ridge", 7, 16))), 0.235), bp.mul(0.725, bp.ref("cave/continents"))), n("cave_rocks", 5, 21))
        grad = lambda y0, v0, y1, v1: bp.clamp(bp.mc("gradient", axis="y", from_coordinate=y0 + SHIFT, to_coordinate=y1 + SHIFT, from_value=float(v0), to_value=float(v1)),
                                               min(v0, v1), max(v0, v1))
        a = bp.add(0.9375, bp.mul(grad(306, 1, 320, 0), bp.add(-0.9375, base)))
        return bp.add(2.5, bp.mul(grad(-64, -0.06, -28, 1), bp.add(-2.5, a)))
    def sinkholes(self):
        """-> [(shaft, ramp or None)]: shaft > 0 inside a hole (to be cut out), ramp > 0 where a spiral ledge is solid"""
        bp, out = self.bp, []
        X, Z = bp.ref("x"), bp.ref("z")
        for s in self.layout.get("sinkholes", []):
            if math.hypot(s["x"] - self.island["x"], s["z"] - self.island["z"]) > self.island["radius"] - s["radius"] - SIDE: continue
            k, r = s["id"].lower(), s["radius"]
            yb = SINK_BOTTOM.get(s.get("type"), -110)
            dist = bp.mc("distance_to_point", metric="euclidean", point=[s["x"], 0, s["z"]])
            # in: blocks inside the wall (ragged by a few blocks), flat
            bp.write(f"data/{bp.NS}/worldgen/density_function/sinkhole/{k}_in.json", bp.flat(bp.sub(bp.add(r, bp.mul(3.0, bp.EDGE)), dist)))
            inn = bp.ref(f"sinkhole/{k}_in")
            shaft = bp.dmin(bp.dmin(bp.mul(inn, 1 / 6), bp.mul(bp.sub(bp.Y, yb), 1 / 8)), bp.mul(bp.sub(self.island["y_top"] + 40, bp.Y), 1 / 8))
            ramp = None
            if s.get("type") == "spiral_ledge":
                # A ramp winding down the wall, one turn per RAMP_PITCH blocks. The angle is not available as a density
                # function: the circle is cut into SECTORS sectors and inside each the angle is taken as linear along the chord.
                rr = r - RAMP_WIDTH / 2; terms = []
                dx, dz = bp.sub(X, s["x"]), bp.sub(Z, s["z"])
                for q in range(SECTORS):
                    a0, a1 = 2 * math.pi * q / SECTORS, 2 * math.pi * (q + 1) / SECTORS; am = (a0 + a1) / 2
                    line = lambda a, sign: bp.mul(sign, bp.add(bp.mul(-math.sin(a), dx), bp.mul(math.cos(a), dz)))   # > 0 on the far side of the ray at angle a
                    mask = bp.clamp(bp.dmin(bp.add(bp.mul(line(a0, 1.0), 1000.0), 1.0), bp.mul(line(a1, -1.0), 1000.0)), 0, 1)   # a0 <= angle < a1
                    along = bp.add(bp.mul(bp.add(bp.mul(-math.sin(am), dx), bp.mul(math.cos(am), dz)), 1 / (2 * rr * math.sin(math.pi / SECTORS))), 0.5)
                    terms.append(bp.mul(mask, bp.mul(RAMP_PITCH / SECTORS, bp.add(q, bp.clamp(along, 0, 1)))))
                bp.write(f"data/{bp.NS}/worldgen/density_function/sinkhole/{k}_turn.json", bp.flat(bp.tree(bp.add, terms)))   # 0..RAMP_PITCH around the hole
                top = self.island["y_top"]
                w = bp.add(bp.sub(bp.Y, top), bp.ref(f"sinkhole/{k}_turn"))     # the ramp's surface is where this is a multiple of the pitch
                turns = range(-((top - yb) // RAMP_PITCH) - 2, 3)
                u = bp.mc("interval_select", input=w, thresholds=[float(t * RAMP_PITCH) for t in turns][1:], functions=[bp.sub(w, float(t * RAMP_PITCH)) for t in turns])
                slab = bp.dmin(bp.sub(u, RAMP_PITCH - RAMP_THICK), bp.sub(RAMP_PITCH, u))
                ring = bp.dmin(bp.add(inn, 4.0), bp.sub(RAMP_WIDTH, inn))
                ramp = bp.dmin(bp.dmin(bp.mul(slab, 1 / 4), bp.mul(ring, 1 / 3)), bp.dmin(bp.mul(bp.sub(bp.Y, yb + 6), 1 / 8), bp.mul(bp.sub(top - 4, bp.Y), 1 / 8)))
            out.append((shaft, ramp)); self.log.append(f"sinkhole {s['id']} ({s.get('type')}): radius {r}, down to y {yb}" + (", spiral ramp" if ramp else ""))
        return out
    def carve(self, terrain):
        """the world's density with the cave world cut into the island and the sinkholes cut through its roof"""
        bp = self.bp
        self.noises(); self.zone()
        m = bp.clamp(bp.mul(bp.ref("cave/inner"), 1 / FADE), 0, 1)
        cave = bp.add(bp.clamp(self.density(), -2.0, 2.5), bp.mul(3.2, bp.sub(1, m)))   # >= 1.2 (no effect) outside the zone
        out = bp.dmin(terrain, cave)
        for shaft, ramp in self.sinkholes():
            out = bp.dmin(out, bp.clamp(bp.mul(shaft, -1.0), -1, 1))
            if ramp is not None: out = bp.dmax(out, bp.clamp(ramp, -1, 1))
        return out

    # ------------------------------------------------------------------------------------------------ biomes
    ISLAND_DEPTH = -1.9     # the "depth" climate parameter outside the cave world; Dwarfhollow's own runs from -0.3 to 1.1
    def router(self, router):
        """the climate functions: Dwarfhollow's inside the zone, the islands' biome code (temperature) outside"""
        bp = self.bp
        inner = bp.ref("cave/inner")
        depth = bp.clamp(bp.mc("gradient", axis="y", from_coordinate=self.lo, to_coordinate=self.hi, from_value=1.1, to_value=-0.3), -0.3, 1.1)
        router.update(continents=bp.ref("cave/continents"), erosion=bp.ref("cave/erosion"), ridges="minecraft:overworld/ridges",
                      vegetation=bp.flat("minecraft:overworld/vegetation"),
                      temperature=bp.choice(inner, 0, 100000, bp.flat("minecraft:overworld/temperature"), router["temperature"]),
                      depth=bp.choice(inner, 0, 100000, depth, self.ISLAND_DEPTH))
    def island_point(self, point):
        """an island biome's parameters: any climate, outside the cave world"""
        wide = [-2, 2]
        point.update(humidity=wide, continentalness=wide, erosion=wide, weirdness=wide, depth=self.ISLAND_DEPTH)
        return point
    def entries(self):
        return self.pack.json("data/minecraft/dimension/overworld.json")["generator"]["biome_source"]["biomes"]

    # ------------------------------------------------------------------------------------------------ files
    def every_layer(self, count):
        """instead of count_on_every_layer: random heights in the cave world, then down to the next floor"""
        mc = self.bp.mc
        free = mc("any_of", predicates=[mc("matching_block_tag", tag="minecraft:air"), mc("matching_blocks", blocks=["minecraft:water", "minecraft:lava"])])
        return [mc("count", count=count), mc("count", count=LAYER_TRIES), mc("in_square"),
                mc("height_range", height=mc("uniform", min_inclusive={"absolute": self.lo + 8}, max_inclusive={"absolute": self.hi - 8})),
                mc("environment_scan", direction_of_search="down", max_steps=32, allowed_search_condition=free, target_condition=mc("solid")),
                mc("offset", x=0, y=1, z=0)]
    def files(self):
        """features, biomes and tags of the pack in the 26.3 formats"""
        bp, f = self.bp, self.pack.files
        def reg(kind):
            pre = f"data/{NSD}/worldgen/{kind}/"
            return {f"{NSD}:" + n[len(pre):-5]: json.loads(b) for n, b in f.items() if n.startswith(pre) and n.endswith(".json")}
        conv = convert81.Converter(reg("configured_feature"), reg("placed_feature"), shift=SHIFT, old_min=DH_MIN, old_top=DH_TOP - 1, every_layer=self.every_layer)
        feats, placed = conv.features()
        for kind, d in (("feature", feats), ("placed_feature", placed)):
            for k, v in d.items(): bp.write(f"data/{NSD}/worldgen/{kind}/{k.split(':')[1]}.json", fix_types(v))
        for b in self.biomes:
            bp.write(f"data/{NSD}/worldgen/biome/{b}.json", convert81.biome(self.pack.json(f"data/{NSD}/worldgen/biome/{b}.json")))
        n = 0
        for rel, data in f.items():   # its block and biome tags (the function tags and the entity tag belong to what is left out)
            if rel.startswith((f"data/{NSD}/tags/block/", f"data/{NSD}/tags/worldgen/", "data/minecraft/tags/worldgen/biome/")):
                bp.write(rel, json.loads(data)); n += 1
        self.conv = conv
        self.log.append(f"dwarfhollow ({self.pack.path.name}): {len(feats)} features, {len(placed)} placed features, {len(self.biomes)} biomes, {n} tags converted; "
                        + ", ".join(f"{v} x {k}" for k, v in conv.notes.items()))
    def surface_rule(self):
        """Dwarfhollow's surface rule for its biomes (its bedrock floor and roof are left out)"""
        rule = self.pack.json(f"data/{NSD}/worldgen/noise_settings/dwarfhollow.json")["surface_rule"]
        conv = convert81.Converter({}, {}, shift=SHIFT, old_min=DH_MIN, old_top=DH_TOP - 1)
        seq = [e for e in rule["sequence"] if "bedrock" not in json.dumps(e.get("then_run", {}).get("result_state", ""))]
        self.bp.write(f"data/{self.bp.NS}/worldgen/material_rule/cave_world.json", {"type": "minecraft:sequence", "sequence": conv.rule(seq)})
        return {"type": "minecraft:condition", "if_true": {"type": "minecraft:biome", "biome_is": [f"{NSD}:{b}" for b in self.biomes]},
                "then_run": self.bp.ref("cave_world")}

def fix_types(o):
    """feature types that changed between 1.21.5 and 26.3 beyond what convert81 does"""
    if isinstance(o, list): return [fix_types(v) for v in o]
    if not isinstance(o, dict): return o
    o = {k: fix_types(v) for k, v in o.items()}
    if o.get("type") == "minecraft:pointed_dripstone" and "chance_of_taller_dripstone" in o:
        return {"type": "minecraft:speleothem", "base_block": "minecraft:dripstone_block", "pointed_block": "minecraft:pointed_dripstone",
                "replaceable_blocks": "#minecraft:dripstone_replaceable_blocks"}
    if o.get("type") == "minecraft:sculk_patch":
        o.pop("catalyst_chance", None); o.pop("extra_rare_growths", None)
    return o
