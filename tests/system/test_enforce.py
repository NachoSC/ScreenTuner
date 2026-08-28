"""Simulate a fullscreen game stealing the gamma ramp / resetting vibrance."""
import ctypes as C, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp

u = C.WinDLL("user32", use_last_error=True)
fails = []
def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

nv = sp.NvApi(); gc = sp.GammaController()
def state():
    return ({n: nv.get_level(h) for h, n in nv.displays},
            {a: gc._read(a)[0][128] for a in gc.adapters})

base_v, base_r = state()
print("before:", base_v, base_r)

EXE = os.path.join(ROOT, "dist", "ScreenTuner", "ScreenTuner.exe")
LOG = os.path.join(ROOT, "dist", "ScreenTuner", "screentuner.log")
if os.path.exists(LOG): os.remove(LOG)
proc = subprocess.Popen([EXE])
for _ in range(40):
    time.sleep(0.5)
    if os.path.exists(LOG) and "Running." in open(LOG, encoding="utf-8").read(): break
log = open(LOG, encoding="utf-8").read()
check("keep-applied armed at startup", "keep-applied:" in log)

hwnd = sp.find_running_instance()
print("\n=== apply the tarkov profile (ctrl+2 -> vibrance 75, gamma 2.4) ===")
cfg_path = os.path.join(os.path.dirname(EXE), "profiles.json")
prof = [p["name"] for p in sp.load_config(cfg_path)["profiles"]]
idx = prof.index("tarkov")
u.PostMessageW(hwnd, 0x0111, 1000 + idx, 0)     # WM_COMMAND -> that profile
time.sleep(2.0)
applied_v, applied_r = state()
print("applied:", applied_v, applied_r)
check("profile applied", applied_r != base_r)

print("\n=== now impersonate the game: stomp the gamma ramp + reset vibrance ===")
gc.apply(1.0, 50, 50)                            # what a game's own gamma does
if nv.ok: nv.set_level(50)                       # what a driver mode-switch does
stomped_v, stomped_r = state()
print("stomped:", stomped_v, stomped_r)
check("stomp actually changed things", stomped_r != applied_r)

print("\n=== wait for the watchdog ===")
# Only the monitors this profile actually targets should come back. A profile may
# legitimately skip a screen, and the watchdog must respect that rather than
# stamping the profile onto monitors the user excluded.
cfg = sp.load_config(cfg_path)
targeted = {m.adapter for m, _ in
            sp.resolve_profile(cfg["profiles"][idx], sp.discover_monitors())}
print("  profile targets:", sorted(targeted))
regained = None
for i in range(16):
    time.sleep(0.5)
    now_v, now_r = state()
    if all(now_r[a] == applied_r[a] and now_v[a] == applied_v[a] for a in targeted):
        regained = (i + 1) * 0.5
        break
print("recovered after:", regained, "seconds")
check("gamma ramp taken back on every targeted monitor", regained is not None)
check("vibrance taken back on every targeted monitor",
      all(state()[0][a] == applied_v[a] for a in targeted))

print("\n=== and it logged why ===")
log = open(LOG, encoding="utf-8").read()
check("logged the reapply", "something overwrote us" in log)
for line in log.splitlines():
    if "overwrote" in line: print("   ", line.strip())

print("\n=== quit + restore ===")
u.PostMessageW(hwnd, 0x0111, 902, 0)             # CMD_EXIT
try: proc.wait(timeout=15)
except subprocess.TimeoutExpired: proc.kill()
time.sleep(1.0)
end_v, end_r = state()
print("after quit:", end_v, end_r)
check("display restored on exit", end_r == base_r)
nv.unload()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
