import ctypes as C
import os
import subprocess
import sys
import time
from ctypes import wintypes as W

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp

T = os.path.join(ROOT, "dist", "ScreenTuner")
EXE = os.path.join(T, "ScreenTuner.exe")
LOG = os.path.join(T, "screentuner.log")

user32 = C.WinDLL("user32", use_last_error=True)
VK_CONTROL, VK_SHIFT = 0x11, 0x10
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", C.POINTER(C.c_ulong))]


class INPUT(C.Structure):
    class _U(C.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", C.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", W.DWORD), ("u", _U)]


def key(vk, up=False):
    i = INPUT(type=1)
    i.ki = KEYBDINPUT(wVk=vk, dwFlags=KEYEVENTF_KEYUP if up else 0)
    user32.SendInput(1, C.byref(i), C.sizeof(INPUT))


def combo(vk):
    # Defaults moved to Ctrl+Shift: on AltGr layouts Windows reports AltGr as
    # Ctrl+Alt, so Ctrl+Alt bindings fire while the user is simply typing.
    key(VK_CONTROL); key(VK_SHIFT); key(vk)
    time.sleep(0.05)
    key(vk, True); key(VK_SHIFT, True); key(VK_CONTROL, True)


def levels():
    nv = sp.NvApi()
    out = {n: nv.get_level(h) for h, n in nv.displays}
    nv.unload()
    return out


fails = []


def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


if os.path.exists(LOG):
    os.remove(LOG)
base = levels()
print("baseline vibrance:", base)

print("\n=== launching the exe (no arguments = tray mode) ===")
proc = subprocess.Popen([EXE], cwd=T)
for _ in range(40):
    time.sleep(0.5)
    if os.path.exists(LOG) and "Running." in open(LOG, encoding="utf-8").read():
        break
log = open(LOG, encoding="utf-8").read()
check("started and registered hotkeys", "Running." in log)
check("found both monitors", log.count("monitor  :") == 2)
check("NVAPI active in the frozen build", "NVAPI on 2 display(s)" in log)
check("no hotkey registration failures", "! Could not register" not in log)

print("\n=== hotkey: ctrl+shift+3 (Vivid, vibrance 100) ===")
time.sleep(0.6)
combo(ord("3"))
time.sleep(1.2)
after = levels()
print("  ", after)
check("vibrance driven to 100 by the exe", all(v == 100 for v in after.values()))

print("\n=== hotkey: ctrl+shift+6 (per-monitor profile) ===")
combo(ord("6"))
time.sleep(1.2)
after = levels()
print("  ", after)
check("per-monitor split works in the exe (55 / 42)",
      sorted(after.values()) == [42, 55])

print("\n=== quit with ctrl+shift+q ===")
combo(ord("Q"))
try:
    proc.wait(timeout=15)
    check("exited cleanly", proc.returncode == 0)
except subprocess.TimeoutExpired:
    proc.kill()
    check("exited cleanly", False)

time.sleep(1.0)
restored = levels()
print("  restored:", restored)
check("display restored on exit", restored == base)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
