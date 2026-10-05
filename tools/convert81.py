#!/usr/bin/env python3
"""Converts worldgen files of a data pack made for Minecraft 1.21.5..26.2 (configured features, "Name"/"Properties" block
states) to the 26.3 formats. Used by tools/build_caves.py for Dwarfhollow (pack format 81).

What changed (read off the vanilla data of 26.2 and 26.3):
  * worldgen/configured_feature/x.json {"type", "config": {..}}  ->  worldgen/feature/x.json {"type", ..config fields}
  * block states {"Name", "Properties"} -> {"id", "properties"}
  * state providers: simple_state_provider -> the state itself; weighted_state_provider -> weighted;
    randomized_int_state_provider -> randomized_int; rule_based_state_provider -> rule_based; rotated_block_provider -> rotated
  * random_patch and flower are gone: a patch is a placed feature with count(tries) and a trapezoid offset in its
    placement, followed by the placement of what it scatters
  * placement random_offset {xz_spread, y_spread} -> offset {x, y, z}
  * forest_rock -> block_blob; trees: dirt_provider/force_dirt -> below_trunk_provider
  * biomes: sky/fog colours, music, mob spawns and the like moved from "effects"/"spawners" to "attributes"
"""
import copy, json

PROVIDERS = {"minecraft:weighted_state_provider": "minecraft:weighted", "minecraft:randomized_int_state_provider": "minecraft:randomized_int",
             "minecraft:rule_based_state_provider": "minecraft:rule_based", "minecraft:rotated_block_provider": "minecraft:rotated",
             "minecraft:noise_provider": "minecraft:noise", "minecraft:dual_noise_provider": "minecraft:dual_noise",
             "minecraft:noise_threshold_provider": "minecraft:noise_threshold"}
PATCHES = ("minecraft:random_patch", "minecraft:flower", "minecraft:no_bonemeal_flower")
FEATURE_TYPES = {"minecraft:forest_rock": "minecraft:block_blob"}

def ns(t): return t if ":" in t else "minecraft:" + t

class Converter:
    def __init__(self, configured, placed, shift=0, old_min=-64, old_top=319, every_layer=None):
        """configured, placed: {id: json} of the old pack; shift: added to every absolute height (anchors relative to the
        bottom or top of the old world become absolute first); every_layer(count) -> modifiers replacing count_on_every_layer"""
        self.configured, self.placed, self.shift, self.old_min, self.old_top = configured, placed, shift, old_min, old_top
        self.every_layer = every_layer
        self.notes = {}
    def note(self, k): self.notes[k] = self.notes.get(k, 0) + 1

    def state(self, s):
        out = {"id": s["Name"]}
        if s.get("Properties"): out["properties"] = dict(s["Properties"])
        return out
    def anchor(self, a):
        if "absolute" in a: y = a["absolute"]
        elif "above_bottom" in a: y = self.old_min + a["above_bottom"]
        else: y = self.old_top - a["below_top"]
        return {"absolute": y + self.shift}

    def any(self, o):
        """everything that is not a feature or a placed feature: states, providers, predicates, placers, modifiers"""
        if isinstance(o, list): return [self.any(v) for v in o]
        if not isinstance(o, dict): return o
        if "Name" in o and set(o) <= {"Name", "Properties"}: return self.state(o)
        if set(o) and set(o) <= {"absolute", "above_bottom", "below_top"} and len(o) == 1: return self.anchor(o)
        if "feature" in o and "placement" in o and isinstance(o["placement"], list): return self.placed_feature(o)
        t = ns(o["type"]) if isinstance(o.get("type"), str) else None
        if t and "config" in o and isinstance(o["config"], dict): return self.feature(o)
        if t == "minecraft:simple_state_provider": return self.any(o["state"])
        if t == "minecraft:random_offset":
            return {"type": "minecraft:offset", "x": self.any(o["xz_spread"]), "y": self.any(o["y_spread"]), "z": self.any(o["xz_spread"])}
        if t == "minecraft:count_on_every_layer" and self.every_layer: self.note("count_on_every_layer replaced"); return {"__many__": self.every_layer(o["count"])}
        out = {k: self.any(v) for k, v in o.items()}
        if t is None and "fallback" in o and "rules" in o: out = {"type": "minecraft:rule_based", **out}   # (disks had it without a type)
        if t in PROVIDERS: out["type"] = PROVIDERS[t]
        elif t: out["type"] = t
        return out
    def modifiers(self, pl):
        out = []
        for m in pl:
            c = self.any(m)
            out += c["__many__"] if "__many__" in c else [c]
        return out

    def feature(self, f):
        """a configured feature (inline or a file) -> a 26.3 feature"""
        t = ns(f["type"]); cfg = f.get("config", {})
        if t in PATCHES: raise ValueError("a patch has to be reached through a placed feature")
        out = {"type": FEATURE_TYPES.get(t, t)}
        out.update({k: self.any(v) for k, v in cfg.items()})
        if t == "minecraft:forest_rock": out.setdefault("can_place_on", {"type": "minecraft:solid"})
        if t == "minecraft:tree":
            out.pop("dirt_provider", None); out.pop("force_dirt", None)
            out.setdefault("below_trunk_provider", "minecraft:soil_beneath_tree")
        return out
    def is_patch(self, f):
        if isinstance(f, str): f = self.configured.get(f)
        return isinstance(f, dict) and ns(f.get("type", "")) in PATCHES
    def placed_feature(self, p):
        """a placed feature (inline or a file); patches are unfolded into the placement"""
        f, pl = p["feature"], list(p["placement"])
        for _ in range(8):
            if not self.is_patch(f): break
            cfg = (self.configured[f] if isinstance(f, str) else f)["config"]
            inner = cfg["feature"]
            if isinstance(inner, str): inner = self.placed[inner]
            xz, y = cfg.get("xz_spread", 7), cfg.get("y_spread", 3)
            tri = lambda r: {"type": "minecraft:trapezoid", "min": -r, "max": r, "plateau": 0} if r else 0
            pl.append({"type": "minecraft:count", "count": min(256, cfg.get("tries", 128))})
            while xz > 0 or y > 0:   # an offset reaches 16 blocks at most: wider spreads take several
                a, b = min(xz, 16), min(y, 16); xz -= a; y -= b
                pl.append({"type": "minecraft:offset", "x": tri(a), "y": tri(b), "z": tri(a)})
            pl += list(inner["placement"]); f = inner["feature"]; self.note("patch unfolded")
        return {"feature": f if isinstance(f, str) else self.feature(f), "placement": self.modifiers(pl)}

    def features(self):
        """-> ({id: feature}, {id: placed feature}) in the 26.3 formats"""
        feats = {k: self.feature(copy.deepcopy(v)) for k, v in self.configured.items() if not self.is_patch(v)}
        return feats, {k: self.placed_feature(copy.deepcopy(v)) for k, v in self.placed.items()}

    def rule(self, o):
        """a surface rule (noise settings of the old pack) -> a 26.3 material rule"""
        if isinstance(o, list): return [self.rule(v) for v in o]
        if not isinstance(o, dict): return o
        if "Name" in o and set(o) <= {"Name", "Properties"}:
            s = self.state(o); return s if "properties" in s else s["id"]
        if set(o) and set(o) <= {"absolute", "above_bottom", "below_top"} and len(o) == 1: return self.anchor(o)
        out = {k: self.rule(v) for k, v in o.items()}
        if isinstance(out.get("type"), str): out["type"] = ns(out["type"])
        return out

def colour(v): return v if isinstance(v, str) else "#%06x" % v
def biome(d):
    """a biome file of 1.21.5 -> 26.3 (features are left as they are)"""
    eff = dict(d.get("effects", {})); att = {}
    for old, new in (("sky_color", "minecraft:visual/sky_color"), ("fog_color", "minecraft:visual/fog_color"), ("water_fog_color", "minecraft:visual/water_fog_color")):
        if old in eff: att[new] = colour(eff.pop(old))
    music = eff.pop("music", None)
    if music:
        m = music[0]["data"] if isinstance(music, list) else music
        att["minecraft:audio/background_music"] = {"default": {k: m[k] for k in ("max_delay", "min_delay", "sound")}}
    for k in ("mood_sound", "music_volume", "additions_sound", "ambient_sound", "particle"): eff.pop(k, None)
    cats = ["ambient", "axolotls", "creature", "misc", "monster", "underground_water_creature", "water_ambient", "water_creature"]
    def spawn(s):
        lo, hi = s["minCount"], s["maxCount"]
        return {"type": s["type"], "weight": s["weight"], "count": lo if lo == hi else {"type": "minecraft:uniform", "min_inclusive": lo, "max_inclusive": hi}}
    att["minecraft:gameplay/natural_mob_spawns"] = {"spawn_costs": d.get("spawn_costs", {}),
        "spawns_by_category": {c: [spawn(s) for s in d.get("spawners", {}).get(c, [])] for c in cats}}
    if "creature_spawn_probability" in d: att["minecraft:gameplay/creature_world_gen_spawn_probability"] = d["creature_spawn_probability"]
    out = {"attributes": att, "carvers": d.get("carvers", []), "downfall": d["downfall"], "effects": eff, "features": d["features"],
           "has_precipitation": d["has_precipitation"], "temperature": d["temperature"]}
    if "temperature_modifier" in d: out["temperature_modifier"] = d["temperature_modifier"]
    return out
