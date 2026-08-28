import os
import sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp

nv = sp.NvApi()
gc = sp.GammaController()
mons = sp.discover_monitors()
snap = nv.snapshot()
base_ramp = {a: gc._read(a) for a in gc.adapters}


def state():
    out = {}
    for m in mons:
        out[m.vendor] = (nv.get_level(nv.handle_for(m.adapter)),
                         gc._read(m.adapter)[0][128])
    return out


print("baseline:", state())
fails = []


def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


print("\n=== 1. per-monitor overrides (Focus profile) ===")
prof = {"name": "Focus", "vibrance": 55, "gamma": 1.0, "contrast": 50, "brightness": 50,
        "monitors": {"secondary": {"vibrance": 42, "brightness": 38, "contrast": 46}}}
sp.apply_plan(sp.resolve_profile(prof, mons), nv, gc)
s = state()
print("  ", s)
check("AOC vibrance 55", s["AOC"][0] == 55)
check("BenQ vibrance 42", s["BenQ"][0] == 42)
check("gamma ramps differ between monitors", s["AOC"][1] != s["BenQ"][1])

print("\n=== 2. targeting by vendor name ===")
prof = {"name": "x", "vibrance": 60,
        "monitors": {"BenQ": {"vibrance": 90}, "AOC": {"vibrance": 20}}}
sp.apply_plan(sp.resolve_profile(prof, mons), nv, gc)
s = state()
print("  ", s)
check("AOC vibrance 20", s["AOC"][0] == 20)
check("BenQ vibrance 90", s["BenQ"][0] == 90)

print("\n=== 3. targeting by index + skip ===")
before = state()
prof = {"name": "x", "vibrance": 77, "monitors": {"2": {"skip": True}}}
sp.apply_plan(sp.resolve_profile(prof, mons), nv, gc)
s = state()
print("  ", s)
check("AOC changed to 77", s["AOC"][0] == 77)
check("BenQ untouched (still 90)", s["BenQ"][0] == before["BenQ"][0])

print("\n=== 4. omitted keys leave that knob alone ===")
before = state()
prof = {"name": "x", "vibrance": 33}          # no gamma/contrast/brightness at all
sp.apply_plan(sp.resolve_profile(prof, mons), nv, gc)
s = state()
print("  ", s)
check("vibrance applied to both", s["AOC"][0] == 33 and s["BenQ"][0] == 33)
check("gamma ramps untouched",
      s["AOC"][1] == before["AOC"][1] and s["BenQ"][1] == before["BenQ"][1])

print("\n=== 5. EDID id targeting ===")
prof = {"name": "x", "vibrance": 50, "monitors": {"BNQ7F33": {"vibrance": 66}}}
sp.apply_plan(sp.resolve_profile(prof, mons), nv, gc)
s = state()
print("  ", s)
check("BenQ matched by EDID -> 66", s["BenQ"][0] == 66)
check("AOC got the base 50", s["AOC"][0] == 50)

print("\n=== restore ===")
nv.restore(snap)
for a, r in base_ramp.items():
    gc._write(a, r)
s = state()
print("  ", s)
want = {n: l for (h, l), (_, n) in zip(snap, nv.displays)}
check("vibrance restored to whatever it was",
      all(s[m.vendor][0] == want[m.adapter] for m in mons))
check("gamma restored", all(s[m.vendor][1] == base_ramp[m.adapter][0][128] for m in mons))

nv.unload()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
