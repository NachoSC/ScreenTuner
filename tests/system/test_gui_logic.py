"""Drive the settings window's model without a human clicking."""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp
import configui

configui.sp = sp

SRC = os.path.join(ROOT, "profiles.json")
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_profiles.json")
shutil.copy(SRC, TMP)

fails = []


def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


w = configui.ConfigWindow(TMP)
w.withdraw()
w.preview.set(False)          # don't repaint the real screen during the test
w.update()

mon_keys = [w.monitor_key(m) for m in w.monitors]
print("monitor keys:", mon_keys)
second = mon_keys[1]

print("\n=== 1. custom settings for one monitor ===")
w._select(1)                                   # Competitive FPS
w.scope.set(second)
w._load_profile()
w.mode.set("custom")
w._on_mode()
w.s_vib.set(37)
w.s_bri.set(41)
w._on_slider()
w._save()
saved = json.load(open(TMP, encoding="utf-8"))["profiles"][1]
print("  ->", json.dumps(saved))
check("monitors block written", second in saved.get("monitors", {}))
check("per-monitor vibrance 37", saved["monitors"][second]["vibrance"] == 37)
check("per-monitor brightness 41", saved["monitors"][second]["brightness"] == 41)
check("top-level vibrance untouched (80)", saved["vibrance"] == 80)

print("\n=== 2. switch that monitor to 'leave alone' ===")
w.mode.set("skip")
w._on_mode()
w._save()
saved = json.load(open(TMP, encoding="utf-8"))["profiles"][1]
check("skip written", saved["monitors"][second] == {"skip": True})
plan = sp.resolve_profile(saved, w.monitors)
check("resolve drops that monitor", len(plan) == len(w.monitors) - 1)

print("\n=== 3. back to 'same as all monitors' ===")
w.mode.set("same")
w._on_mode()
w._save()
saved = json.load(open(TMP, encoding="utf-8"))["profiles"][1]
check("monitors block removed", "monitors" not in saved)
check("both monitors targeted again",
      len(sp.resolve_profile(saved, w.monitors)) == len(w.monitors))

print("\n=== 4. unchecking a group drops those keys ===")
w.scope.set(configui.ALL)
w._load_profile()
w.vib_on.set(False)
w._on_toggle()
w._save()
saved = json.load(open(TMP, encoding="utf-8"))["profiles"][1]
print("  ->", json.dumps(saved))
check("vibrance key gone", "vibrance" not in saved)
check("gamma keys still there", "gamma" in saved and "contrast" in saved)
res = sp.resolve_profile(saved, w.monitors)[0][1]
check("resolves to vibrance=None (leave alone)", res["vibrance"] is None)

print("\n=== 5. ramp group off drops all three ===")
w.ramp_on.set(False)
w._on_toggle()
w._save()
saved = json.load(open(TMP, encoding="utf-8"))["profiles"][1]
check("gamma/contrast/brightness all gone",
      not any(k in saved for k in ("gamma", "contrast", "brightness")))

print("\n=== 6. add / rename / delete ===")
before = len(w.cfg["profiles"])
w._add()
w.name_var.set("Test Profile")
w._on_name()
w._save()
saved = json.load(open(TMP, encoding="utf-8"))
check("profile added", len(saved["profiles"]) == before + 1)
check("name saved", saved["profiles"][-1]["name"] == "Test Profile")
check("hotkey conflict check runs", w._check_hotkey() is None)

print("\n=== 7. settings + global hotkeys survive a save ===")
w.opt_vars["notify"].set(False)
w.global_hk["cycle"].set("ctrl+alt+shift+c")
w._save()
saved = json.load(open(TMP, encoding="utf-8"))
check("notify=False saved", saved["settings"]["notify"] is False)
check("global hotkey saved", saved["hotkeys"]["cycle"] == "ctrl+alt+shift+c")
check("reloadable by the app", sp.load_config(TMP)["settings"]["notify"] is False)

w.dirty = False
w._close()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
