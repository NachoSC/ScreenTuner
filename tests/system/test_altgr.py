"""Real Ctrl+LeftAlt must fire; AltGr (Ctrl+RightAlt) must not."""
import ctypes as C
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes as W

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp

u = C.WinDLL("user32", use_last_error=True)
VK_LCONTROL, VK_LMENU, VK_RMENU = 0xA2, 0xA4, 0xA5
KEYUP = 0x0002
EXTENDED = 0x0001

fails = []


def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


class KBD(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", C.POINTER(C.c_ulong))]


class INP(C.Structure):
    class _U(C.Union):
        _fields_ = [("ki", KBD), ("pad", C.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", W.DWORD), ("u", _U)]


def key(vk, up=False, ext=False):
    i = INP(type=1)
    i.ki = KBD(wVk=vk, dwFlags=(KEYUP if up else 0) | (EXTENDED if ext else 0))
    u.SendInput(1, C.byref(i), C.sizeof(INP))


def chord(alt_vk, vk):
    """alt_vk = VK_LMENU for a real Ctrl+Alt, VK_RMENU to imitate AltGr."""
    key(VK_LCONTROL)
    key(alt_vk, ext=(alt_vk == VK_RMENU))
    key(vk)
    time.sleep(0.06)
    key(vk, True)
    key(alt_vk, True, ext=(alt_vk == VK_RMENU))
    key(VK_LCONTROL, True)


SC = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(SC, "altgr_test.json")
json.dump({"settings": {"notify": False, "enforce_profile": False},
           "hotkeys": {},
           "profiles": [{"name": "altgr-probe", "hotkey": "ctrl+alt+2",
                         "vibrance": 95}]}, open(CFG, "w"))

EXE = os.path.join(ROOT, "dist", "ScreenTuner", "ScreenTuner.exe")
LOG = os.path.join(os.path.dirname(EXE), "screentuner.log")
if os.path.exists(LOG):
    os.remove(LOG)

nv = sp.NvApi()
base = {n: nv.get_level(h) for h, n in nv.displays}
print("layout has AltGr:", sp.layout_has_altgr())
print("baseline vibrance:", base)

# Launch fully detached: with an inherited console the app logs to stdout
# rather than to screentuner.log, which is what the test reads.
subprocess.run(["powershell", "-NoProfile", "-Command",
                f"Start-Process '{EXE}' -ArgumentList '--config','{CFG}'"],
               capture_output=True)
proc = None
for _ in range(40):
    time.sleep(0.5)
    if os.path.exists(LOG) and "Running." in open(LOG, encoding="utf-8",
                                                  errors="replace").read():
        break
log = open(LOG, encoding="utf-8", errors="replace").read()
check("warns at startup that the binding clashes with AltGr",
      "AltGr" in log and "ctrl+alt+2" in log)

print("\n=== imitate AltGr (Ctrl + RIGHT Alt + 2) - must be IGNORED ===")
chord(VK_RMENU, ord("2"))
time.sleep(1.5)
after = {n: nv.get_level(h) for h, n in nv.displays}
print("  vibrance:", after)
check("AltGr did NOT switch the profile", after == base)
log = open(LOG, encoding="utf-8", errors="replace").read()
check("logged that it ignored AltGr", "Ignoring AltGr" in log)

print("\n=== real Ctrl + LEFT Alt + 2 - must APPLY ===")
chord(VK_LMENU, ord("2"))
time.sleep(1.5)
after = {n: nv.get_level(h) for h, n in nv.displays}
print("  vibrance:", after)
check("genuine Ctrl+Alt still works", all(v == 95 for v in after.values()))

u.PostMessageW(sp.find_running_instance(), 0x0111, 902, 0)
time.sleep(3)
time.sleep(1)
for h, n in nv.displays:
    nv._set_one(h, base[n])
nv.unload()
os.remove(CFG)
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
