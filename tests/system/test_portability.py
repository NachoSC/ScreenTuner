"""Would this run on someone else's machine? Simulate the hardware we don't have."""
import ctypes as C
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp

fails = []


def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


print("=== 1. machine with NO NVIDIA GPU (nvapi64.dll missing) ===")
real_windll = C.WinDLL


class FakeWinDLL:
    def __call__(self, name, *a, **k):
        if "nvapi" in name.lower():
            raise OSError("simulated: no NVIDIA driver on this machine")
        return real_windll(name, *a, **k)


sp.C.WinDLL = FakeWinDLL()
try:
    nv = sp.NvApi()
    check("NvApi degrades instead of crashing", nv.ok is False)
    check("reports no displays", nv.displays == [])
    check("set_level is a safe no-op", nv.set_level(80) is False)
    check("set_for is a safe no-op", nv.set_for("\\\\.\\DISPLAY1", 80) is False)
    check("snapshot/restore safe", nv.snapshot() == [] or nv.restore(nv.snapshot()) is None)
    check("get_level safe", nv.get_level() is None)

    gamma = sp.GammaController()
    mons = sp.discover_monitors()
    prof = {"name": "x", "vibrance": 90, "gamma": 1.2, "contrast": 55, "brightness": 52}
    plan = sp.resolve_profile(prof, mons)
    base = {a: gamma._read(a) for a in gamma.adapters}
    sp.apply_plan(plan, nv, gamma)          # must not raise
    changed = any(gamma._read(a)[0][128] != base[a][0][128] for a in gamma.adapters)
    check("gamma/contrast/brightness still applied without NVIDIA", changed)
    for a, r in base.items():
        gamma._write(a, r)
    nv.unload()
    check("unload safe with no DLL", True)
finally:
    sp.C.WinDLL = real_windll

print("\n=== 2. monitor discovery is runtime, not baked in ===")
mons = sp.discover_monitors()
print("   discovered:", [(m.index, m.vendor, m.edid, f"{m.width}x{m.height}",
                          "primary" if m.is_primary else "secondary") for m in mons])
check("found monitors dynamically", len(mons) >= 1)
check("each has an EDID id", all(m.edid for m in mons))
check("exactly one primary", sum(1 for m in mons if m.is_primary) == 1)


class FakeMon:
    """Stand-ins for hardware this machine doesn't have."""
    def __init__(self, i, vendor, edid, primary):
        self.index, self.vendor, self.edid = i, vendor, edid
        self.is_primary = primary
        self.adapter = f"\\\\.\\DISPLAY{i}"
        self.width = self.height = self.refresh = self.x = self.y = 0
    matches = sp.Monitor.matches
    label = "fake"


print("\n=== 3. a profile naming monitors this machine doesn't have ===")
prof = {"name": "x", "vibrance": 60, "gamma": 1.0, "contrast": 50, "brightness": 50,
        "monitors": {"Dell": {"vibrance": 20}, "Samsung": {"skip": True}}}
plan = sp.resolve_profile(prof, mons)
check("no crash on unknown monitor names", len(plan) == len(mons))
check("unmatched overrides ignored, base values used",
      all(s["vibrance"] == 60 for _, s in plan))

print("\n=== 4. a single-monitor laptop ===")
one = [FakeMon(1, "LG", "LGD1234", True)]
prof = {"name": "x", "vibrance": 70, "monitors": {"secondary": {"vibrance": 30}}}
plan = sp.resolve_profile(prof, one)
check("single monitor still targeted", len(plan) == 1)
check("'secondary' matches nothing, base used", plan[0][1]["vibrance"] == 70)

print("\n=== 5. a four-monitor setup, mixed vendors ===")
four = [FakeMon(1, "Dell", "DEL4141", True), FakeMon(2, "LG", "GSM7777", False),
        FakeMon(3, "AOC", "AOCB403", False), FakeMon(4, "Dell", "DELAAAA", False)]
prof = {"name": "x", "vibrance": 50,
        "monitors": {"primary": {"vibrance": 85}, "AOC": {"skip": True},
                     "2": {"vibrance": 10}}}
plan = sp.resolve_profile(prof, four)
got = {m.vendor + str(m.index): s["vibrance"] for m, s in plan}
print("   ->", got)
check("primary override", got.get("Dell1") == 85)
check("index override", got.get("LG2") == 10)
check("skip honoured", "AOC3" not in got)
check("duplicate vendor falls through to base", got.get("Dell4") == 50)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
