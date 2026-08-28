"""Left-click must open the menu, not change the profile."""
import ctypes as C
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp

u = C.WinDLL("user32", use_last_error=True)
u.FindWindowW.restype = C.c_void_p
u.SetCursorPos.argtypes = [C.c_int, C.c_int]

WM_LBUTTONUP, WM_RBUTTONUP, WM_LBUTTONDBLCLK = 0x0202, 0x0205, 0x0203
WM_CANCELMODE = 0x001F

fails = []


def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


def levels(nv):
    return {n: nv.get_level(h) for h, n in nv.displays}


def menu_open():
    return bool(u.FindWindowW("#32768", None))


def dismiss(hwnd):
    u.PostMessageW(hwnd, WM_CANCELMODE, 0, 0)
    for _ in range(6):
        time.sleep(0.25)
        if not menu_open():
            return True
        m = u.FindWindowW("#32768", None)
        if m:
            u.PostMessageW(C.c_void_p(m), 0x0010, 0, 0)   # WM_CLOSE
    return not menu_open()


hwnd = sp.find_running_instance()
if not hwnd:
    print("app not running")
    sys.exit(1)

nv = sp.NvApi()
before = levels(nv)
print("vibrance before:", before)
check("no menu open to begin with", not menu_open())

def settings_open():
    return bool(u.FindWindowW(None, sp.SETTINGS_TITLE))


def close_settings():
    for _ in range(10):
        w = u.FindWindowW(None, sp.SETTINGS_TITLE)
        if not w:
            return True
        u.PostMessageW(C.c_void_p(w), 0x0010, 0, 0)      # WM_CLOSE
        time.sleep(0.4)
    return not settings_open()


for name, click in (("left-click", WM_LBUTTONUP),
                    ("double-click", WM_LBUTTONDBLCLK)):
    print(f"\n=== {name} -> settings window ===")
    check("no settings window beforehand", close_settings())
    u.PostMessageW(hwnd, sp.WM_TRAY, 1, click)
    for _ in range(24):
        time.sleep(0.5)
        if settings_open():
            break
    check(f"{name} opened the settings window", settings_open())
    check(f"{name} did NOT open the tray menu", not menu_open())
    check(f"{name} did not change the display", levels(nv) == before)
    check("settings window closed again", close_settings())

print("\n=== left-click twice must not open two windows ===")
u.PostMessageW(hwnd, sp.WM_TRAY, 1, WM_LBUTTONUP)
time.sleep(6)
u.PostMessageW(hwnd, sp.WM_TRAY, 1, WM_LBUTTONUP)
time.sleep(3)
n = 0


def count_settings(h, _):
    global n
    buf = C.create_unicode_buffer(256)
    u.GetWindowTextW(h, buf, 256)
    if buf.value == sp.SETTINGS_TITLE:
        n += 1
    return True


u.EnumWindows(C.WINFUNCTYPE(C.c_bool, C.c_void_p, C.c_void_p)(count_settings), None)
check(f"exactly one settings window (found {n})", n == 1)
check("closed", close_settings())

for name, click in (("right-click", WM_RBUTTONUP),):
    print(f"\n=== {name} -> tray menu ===")
    u.SetCursorPos(900, 500)
    time.sleep(0.2)
    u.PostMessageW(hwnd, sp.WM_TRAY, 1, click)
    time.sleep(1.2)
    check(f"{name} opens the menu", menu_open())
    check(f"{name} did not change the display", levels(nv) == before)
    check(f"{name} menu dismissed cleanly", dismiss(hwnd))

print("\n=== profile switching still works from the menu ===")
sp.user32.PostMessageW(hwnd, 0x0111, 1000 + 2, 0)     # WM_COMMAND -> profile index 2
time.sleep(1.2)
after = levels(nv)
print("   ", after)
check("menu command applied profile 3 (Vivid, vibrance 100)",
      all(v == 100 for v in after.values()))

sp.user32.PostMessageW(hwnd, 0x0111, 900, 0)          # CMD_NEUTRAL
time.sleep(1.0)
print("    back to neutral:", levels(nv))

nv.unload()
print("\nleftover menus:", menu_open())
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
