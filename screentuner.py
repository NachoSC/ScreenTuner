"""
ScreenTuner - hotkey-driven digital vibrance / gamma / contrast / brightness for Windows.

Digital vibrance goes through NVIDIA's NVAPI (same knob as the NVIDIA Control Panel).
Gamma / contrast / brightness go through the GDI gamma ramp, which works on any GPU.

Run it, leave it running, hit a hotkey to switch profiles instantly.
Edit profiles.json to taste; Ctrl+Alt+R reloads it without restarting.
"""

import argparse
import atexit
import ctypes as C
import json
import os
import sys
import time
import traceback
from ctypes import wintypes as W

APP_NAME = "ScreenTuner"
FROZEN = getattr(sys, "frozen", False)

# Frozen: everything user-facing lives beside the .exe, never in PyInstaller's
# temp extraction dir (which __file__ points at and which is deleted on exit).
BASE_DIR = (os.path.dirname(os.path.abspath(sys.executable)) if FROZEN
            else os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(BASE_DIR, "profiles.json")


def resource_path(name):
    """Read-only files we ship (the icon): bundled dir first, then next to us."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        p = os.path.join(bundle, name)
        if os.path.exists(p):
            return p
    return os.path.join(BASE_DIR, name)


def app_launch_args(*extra):
    """How to start another copy of ourselves, script or frozen."""
    if FROZEN:
        return [sys.executable, *extra]
    return [pythonw_exe(), os.path.abspath(__file__), *extra]


def attach_console():
    """Built windowed, but invoked from a terminal - write back to that terminal."""
    if not FROZEN or sys.stdout is not None:
        return
    try:
        if not kernel32.AttachConsole(-1):      # ATTACH_PARENT_PROCESS
            kernel32.AllocConsole()
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    except Exception:
        pass
    if sys.stdout is None:      # last resort, so argparse can't die on None.write
        try:
            sys.stdout = sys.stderr = open(os.path.join(BASE_DIR, "screentuner.log"),
                                           "a", encoding="utf-8", buffering=1)
        except Exception:
            pass

user32 = C.WinDLL("user32", use_last_error=True)
gdi32 = C.WinDLL("gdi32", use_last_error=True)
shell32 = C.WinDLL("shell32", use_last_error=True)
kernel32 = C.WinDLL("kernel32", use_last_error=True)

# ctypes defaults every restype to C int, which truncates 64-bit handles.
kernel32.GetModuleHandleW.restype = W.HMODULE
gdi32.CreateDCW.restype = W.HDC
gdi32.CreateDCW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, C.c_void_p]
gdi32.DeleteDC.argtypes = [W.HDC]
gdi32.GetDeviceGammaRamp.argtypes = [W.HDC, C.c_void_p]
gdi32.SetDeviceGammaRamp.argtypes = [W.HDC, C.c_void_p]
user32.CreateWindowExW.restype = W.HWND
user32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                                   C.c_int, C.c_int, C.c_int, C.c_int,
                                   W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
user32.PostMessageW.argtypes = [W.HWND, C.c_uint, W.WPARAM, W.LPARAM]
user32.SetForegroundWindow.argtypes = [W.HWND]
user32.FindWindowW.restype = W.HWND
user32.FindWindowW.argtypes = [W.LPCWSTR, W.LPCWSTR]
user32.ShowWindow.argtypes = [W.HWND, C.c_int]
user32.LoadIconW.restype = W.HICON
user32.LoadIconW.argtypes = [W.HINSTANCE, W.LPCWSTR]
user32.LoadImageW.restype = W.HANDLE
user32.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, C.c_uint,
                              C.c_int, C.c_int, C.c_uint]
user32.CreatePopupMenu.restype = W.HMENU
user32.DefWindowProcW.restype = C.c_longlong
user32.DefWindowProcW.argtypes = [W.HWND, C.c_uint, W.WPARAM, W.LPARAM]
user32.TrackPopupMenu.restype = C.c_int
user32.TrackPopupMenu.argtypes = [W.HMENU, C.c_uint, C.c_int, C.c_int,
                                  C.c_int, W.HWND, C.c_void_p]
user32.AppendMenuW.argtypes = [W.HMENU, C.c_uint, C.c_size_t, W.LPCWSTR]
user32.RegisterHotKey.argtypes = [W.HWND, C.c_int, C.c_uint, C.c_uint]
user32.UnregisterHotKey.argtypes = [W.HWND, C.c_int]

MAKEINTRESOURCE = lambda i: C.cast(C.c_void_p(i), W.LPCWSTR)  # noqa: E731


LOG_FILE = os.path.join(BASE_DIR, "screentuner.log")


def log(msg):
    """Console when there is one; a log file when running windowless under pythonw."""
    if sys.stdout is not None:
        try:
            print(msg, flush=True)
            return
        except Exception:
            pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------
# NVAPI - digital vibrance
# --------------------------------------------------------------------------

NVAPI_IDS = {
    "Initialize": 0x0150E828,
    "Unload": 0xD22BDD7E,
    "GetErrorMessage": 0x6C2D048C,
    "EnumNvidiaDisplayHandle": 0x9ABDD40D,
    "GetAssociatedNvidiaDisplayName": 0x22A78B05,
    "GetDVCInfoEx": 0x0E45002D,
    "SetDVCLevelEx": 0x4A82C2B1,
}


class DVC_INFO_EX(C.Structure):
    _fields_ = [
        ("version", C.c_uint32),
        ("currentLevel", C.c_int32),
        ("minLevel", C.c_int32),
        ("maxLevel", C.c_int32),
        ("defaultLevel", C.c_int32),
    ]


def _nv_version(struct, ver=1):
    return C.sizeof(struct) | (ver << 16)


class NvApi:
    """Thin ctypes binding over the handful of NVAPI calls we need."""

    def __init__(self):
        self.ok = False
        self.displays = []          # list of (handle, name)
        self.min = 0
        self.max = 100
        self.default = 50
        self._fns = {}
        self._qi = None          # stays None if the DLL is missing (non-NVIDIA machine)
        try:
            self._dll = C.WinDLL("nvapi64.dll" if C.sizeof(C.c_void_p) == 8 else "nvapi.dll")
        except OSError:
            log("[vibrance] NVAPI not available - vibrance disabled (gamma still works).")
            return

        qi = self._dll.nvapi_QueryInterface
        qi.restype = C.c_void_p
        qi.argtypes = [C.c_uint32]
        self._qi = qi

        if self._call("Initialize", C.c_int32) != 0:
            log("[vibrance] NvAPI_Initialize failed - vibrance disabled.")
            return

        self._enumerate()
        self.ok = bool(self.displays)
        if not self.ok:
            log("[vibrance] No NVIDIA-driven displays found - vibrance disabled.")

    def _fn(self, name, restype, *argtypes):
        key = (name, argtypes)
        if key not in self._fns:
            ptr = self._qi(NVAPI_IDS[name])
            if not ptr:
                return None
            self._fns[key] = C.WINFUNCTYPE(restype, *argtypes)(ptr)
        return self._fns[key]

    def _call(self, name, restype, *args):
        argtypes = tuple(type(a) if not isinstance(a, int) else C.c_uint32 for a in args)
        fn = self._fn(name, restype, *argtypes)
        if fn is None:
            return -1
        return fn(*args)

    def _enumerate(self):
        enum = self._fn("EnumNvidiaDisplayHandle", C.c_int32, C.c_uint32, C.POINTER(C.c_void_p))
        get_name = self._fn("GetAssociatedNvidiaDisplayName", C.c_int32, C.c_void_p, C.c_char_p)
        i = 0
        while True:
            h = C.c_void_p()
            if enum(i, C.byref(h)) != 0:
                break
            buf = C.create_string_buffer(64)
            name = buf.value.decode(errors="replace") if get_name(h, buf) == 0 else f"display{i}"
            self.displays.append((h, name))
            i += 1
        if self.displays:
            info = self.get_info(self.displays[0][0])
            if info:
                self.min, self.max, self.default = info[1], info[2], info[3]

    def get_info(self, handle):
        fn = self._fn("GetDVCInfoEx", C.c_int32, C.c_void_p, C.c_uint32, C.POINTER(DVC_INFO_EX))
        if fn is None:
            return None
        info = DVC_INFO_EX(version=_nv_version(DVC_INFO_EX))
        if fn(handle, 0, C.byref(info)) != 0:
            return None
        return (info.currentLevel, info.minLevel, info.maxLevel, info.defaultLevel)

    def get_level(self, handle=None):
        if not self.ok:
            return None
        info = self.get_info(handle or self.displays[0][0])
        return info[0] if info else None

    def get_all_levels(self):
        return {name: self.get_level(h) for h, name in self.displays}

    def _set_one(self, handle, level):
        if not self._qi:
            return False
        fn = self._fn("SetDVCLevelEx", C.c_int32, C.c_void_p, C.c_uint32, C.POINTER(DVC_INFO_EX))
        if fn is None:
            return False
        level = max(self.min, min(self.max, int(round(level))))
        info = DVC_INFO_EX(version=_nv_version(DVC_INFO_EX), currentLevel=level)
        return fn(handle, 0, C.byref(info)) == 0

    def set_level(self, level, only=None):
        """Set vibrance (min..max, 50 = neutral). `only` filters by display name."""
        if not self.ok:
            return False
        done = False
        for handle, name in self.displays:
            if only and name not in only:
                continue
            done |= self._set_one(handle, level)
        return done

    def handle_for(self, adapter):
        """NVAPI reports the same \\\\.\\DISPLAYn names as GDI, so that's the join key."""
        for handle, name in self.displays:
            if name.lower() == str(adapter).lower():
                return handle
        return None

    def set_for(self, adapter, level):
        handle = self.handle_for(adapter)
        return self._set_one(handle, level) if handle is not None else False

    def snapshot(self):
        """Per-display current levels, so we can restore monitors independently."""
        return [(h, self.get_level(h)) for h, _ in self.displays] if self.ok else []

    def restore(self, snap):
        for handle, level in snap:
            if level is not None:
                self._set_one(handle, level)

    def unload(self):
        # After this the function pointers are dead, so make every later call a no-op.
        if getattr(self, "_qi", None):
            try:
                self._call("Unload", C.c_int32)
            except Exception:
                pass
        self.ok = False
        self._qi = None
        self._fns.clear()
        self.displays = []


# --------------------------------------------------------------------------
# GDI gamma ramp - gamma / contrast / brightness
# --------------------------------------------------------------------------

class DISPLAY_DEVICEW(C.Structure):
    _fields_ = [
        ("cb", W.DWORD),
        ("DeviceName", W.WCHAR * 32),
        ("DeviceString", W.WCHAR * 128),
        ("StateFlags", W.DWORD),
        ("DeviceID", W.WCHAR * 128),
        ("DeviceKey", W.WCHAR * 128),
    ]


class DEVMODEW(C.Structure):
    _fields_ = [("dmDeviceName", W.WCHAR * 32), ("dmSpecVersion", W.WORD),
                ("dmDriverVersion", W.WORD), ("dmSize", W.WORD),
                ("dmDriverExtra", W.WORD), ("dmFields", W.DWORD),
                ("dmPositionX", C.c_long), ("dmPositionY", C.c_long),
                ("dmDisplayOrientation", W.DWORD), ("dmDisplayFixedOutput", W.DWORD),
                ("dmColor", C.c_short), ("dmDuplex", C.c_short),
                ("dmYResolution", C.c_short), ("dmTTOption", C.c_short),
                ("dmCollate", C.c_short), ("dmFormName", W.WCHAR * 32),
                ("dmLogPixels", W.WORD), ("dmBitsPerPel", W.DWORD),
                ("dmPelsWidth", W.DWORD), ("dmPelsHeight", W.DWORD),
                ("dmDisplayFlags", W.DWORD), ("dmDisplayFrequency", W.DWORD),
                ("dmICMMethod", W.DWORD), ("dmICMIntent", W.DWORD),
                ("dmMediaType", W.DWORD), ("dmDitherType", W.DWORD),
                ("dmReserved1", W.DWORD), ("dmReserved2", W.DWORD),
                ("dmPanningWidth", W.DWORD), ("dmPanningHeight", W.DWORD)]


DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004
ENUM_CURRENT_SETTINGS = -1
RAMP = W.WORD * 256 * 3

# PnP vendor codes from the EDID, so "DELA123" can be shown (and matched) as "Dell".
PNP_VENDORS = {
    "AOC": "AOC", "BNQ": "BenQ", "BNR": "BenQ", "ACR": "Acer", "ACI": "Asus",
    "AUS": "Asus", "DEL": "Dell", "SAM": "Samsung", "SEC": "Samsung",
    "GSM": "LG", "LGD": "LG", "GBT": "Gigabyte", "MSI": "MSI", "HWP": "HP",
    "HPN": "HP", "LEN": "Lenovo", "VSC": "ViewSonic", "PHL": "Philips",
    "NEC": "NEC", "SNY": "Sony", "APP": "Apple", "IVM": "Iiyama",
    "HSD": "Hansol", "CMN": "ChiMei", "AUO": "AUO", "SHP": "Sharp",
}


class Monitor:
    """One desktop monitor, with every handle we might want to address it by."""

    def __init__(self, index, adapter, gpu, edid, is_primary, dm):
        self.index = index                  # 1-based, enumeration order
        self.adapter = adapter              # \\.\DISPLAY1 - the NVAPI/GDI join key
        self.gpu = gpu
        self.edid = edid                    # e.g. DELA123
        self.is_primary = is_primary
        self.width = dm.dmPelsWidth if dm else 0
        self.height = dm.dmPelsHeight if dm else 0
        self.refresh = dm.dmDisplayFrequency if dm else 0
        self.x = dm.dmPositionX if dm else 0
        self.y = dm.dmPositionY if dm else 0
        self.vendor = PNP_VENDORS.get(edid[:3].upper(), edid[:3].upper()) if edid else ""

    @property
    def label(self):
        bits = [self.vendor or self.adapter]
        if self.width:
            bits.append(f"{self.width}x{self.height}@{self.refresh}Hz")
        if self.is_primary:
            bits.append("primary")
        return " ".join(bits)

    def matches(self, key):
        """Accepts the adapter name, EDID id, vendor, index, or primary/secondary."""
        k = str(key).strip().lower()
        if not k:
            return False
        if k in ("all", "*"):
            return True
        if k == self.adapter.lower() or k == str(self.index):
            return True
        if k == "primary":
            return self.is_primary
        if k in ("secondary", "second"):
            return not self.is_primary
        if self.edid and (k == self.edid.lower() or k in self.edid.lower()):
            return True
        if self.vendor and k == self.vendor.lower():
            return True
        return False


def discover_monitors():
    mons = []
    i = 0
    while True:
        d = DISPLAY_DEVICEW()
        d.cb = C.sizeof(d)
        if not user32.EnumDisplayDevicesW(None, i, C.byref(d), 0):
            break
        if d.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            mon = DISPLAY_DEVICEW()
            mon.cb = C.sizeof(mon)
            edid = ""
            if user32.EnumDisplayDevicesW(d.DeviceName, 0, C.byref(mon), 0):
                # MONITOR\DELA123\{guid}\0001  ->  DELA123
                parts = mon.DeviceID.split("\\")
                if len(parts) > 1:
                    edid = parts[1]
            dm = DEVMODEW()
            dm.dmSize = C.sizeof(dm)
            if not user32.EnumDisplaySettingsW(d.DeviceName, ENUM_CURRENT_SETTINGS, C.byref(dm)):
                dm = None
            mons.append(Monitor(len(mons) + 1, d.DeviceName, d.DeviceString, edid,
                                bool(d.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE), dm))
        i += 1
    return mons


def resolve_monitors(monitors, key):
    """A profile key -> the monitors it addresses. Unknown keys match nothing."""
    if key is None:
        return list(monitors)
    keys = key if isinstance(key, (list, tuple)) else [key]
    out = []
    for m in monitors:
        if any(m.matches(k) for k in keys) and m not in out:
            out.append(m)
    return out


class GammaController:
    def __init__(self):
        self.baseline = {}      # device name -> saved ramp
        self.refresh()

    def refresh(self):
        """(Re)discover adapters, keeping any baseline we already captured."""
        self.adapters = [m.adapter for m in discover_monitors()]
        for name in self.adapters:
            if name not in self.baseline:
                ramp = self._read(name)
                if ramp is not None:
                    self.baseline[name] = ramp

    def _dc(self, name):
        return gdi32.CreateDCW("DISPLAY", name, None, None)

    def _read(self, name):
        hdc = self._dc(name)
        if not hdc:
            return None
        try:
            ramp = RAMP()
            return ramp if gdi32.GetDeviceGammaRamp(hdc, C.byref(ramp)) else None
        finally:
            gdi32.DeleteDC(hdc)

    def _write(self, name, ramp):
        hdc = self._dc(name)
        if not hdc:
            return False
        try:
            return bool(gdi32.SetDeviceGammaRamp(hdc, C.byref(ramp)))
        finally:
            gdi32.DeleteDC(hdc)

    @staticmethod
    def build_ramp(gamma, contrast, brightness):
        """gamma: 0.30-2.80 (1.0 neutral). contrast/brightness: 0-100 (50 neutral).
        Each may be a scalar or a 3-list for [R, G, B]."""
        def triple(v):
            return list(v) if isinstance(v, (list, tuple)) else [v, v, v]

        g, c, b = triple(gamma), triple(contrast), triple(brightness)
        ramp = RAMP()
        for ch in range(3):
            gv = max(0.30, min(2.80, float(g[ch])))
            scale = 1.0 + (float(c[ch]) - 50.0) / 50.0        # 0 .. 2
            offset = (float(b[ch]) - 50.0) / 50.0 * 0.5       # -0.5 .. +0.5
            for i in range(256):
                v = i / 255.0
                v = (v - 0.5) * scale + 0.5 + offset
                v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
                v = v ** (1.0 / gv)
                ramp[ch][i] = int(v * 65535.0 + 0.5) & 0xFFFF
        return ramp

    def apply(self, gamma, contrast, brightness, only=None):
        """Same values on every adapter (or the subset named in `only`)."""
        targets = [n for n in self.adapters if not only or n in only]
        return self.apply_map({n: (gamma, contrast, brightness) for n in targets})

    def apply_map(self, per_adapter):
        """{adapter name: (gamma, contrast, brightness)} - each monitor its own ramp."""
        if not per_adapter:
            return True
        ok = False
        cache = {}
        for name, values in per_adapter.items():
            key = repr(values)
            if key not in cache:
                cache[key] = self.build_ramp(*values)
            ok |= self._write(name, cache[key])
        if not ok:
            log("  ! Windows rejected the gamma ramp (values too extreme?). "
                "Try 'python screentuner.py --enable-full-gamma-range' as admin.")
        return ok

    def restore_baseline(self):
        for name, ramp in self.baseline.items():
            self._write(name, ramp)


# --------------------------------------------------------------------------
# Hotkey parsing
# --------------------------------------------------------------------------

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
MODIFIERS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
             "shift": MOD_SHIFT, "win": MOD_WIN, "super": MOD_WIN}

VK_NAMES = {
    "space": 0x20, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "enter": 0x0D,
    "return": 0x0D, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "pgdn": 0x22, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "capslock": 0x14, "printscreen": 0x2C,
    "scrolllock": 0x91, "pause": 0x13,
    "add": 0x6B, "subtract": 0x6D, "multiply": 0x6A, "divide": 0x6F,
    "decimal": 0x6E, "numlock": 0x90,
    ";": 0xBA, "=": 0xBB, "plus": 0xBB, ",": 0xBC, "-": 0xBD, "minus": 0xBD,
    ".": 0xBE, "/": 0xBF, "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}


VK_LMENU, VK_RMENU = 0xA4, 0xA5
_ALTGR_LAYOUT = None


def layout_has_altgr():
    """True if the current keyboard layout produces characters with AltGr.

    Windows implements AltGr as Ctrl+Alt, so on these layouts a Ctrl+Alt hotkey
    fires while the user is simply typing. On a Spanish layout AltGr+2 types
    '@', which would otherwise trigger a Ctrl+Alt+2 hotkey.

    VkKeyScanEx reports the modifiers a character needs in its high byte:
    bit 1 = Ctrl, bit 2 = Alt. Both set together means AltGr."""
    global _ALTGR_LAYOUT
    if _ALTGR_LAYOUT is not None:
        return _ALTGR_LAYOUT
    try:
        user32.GetKeyboardLayout.restype = W.HKL
        user32.VkKeyScanExW.restype = C.c_short
        user32.VkKeyScanExW.argtypes = [W.WCHAR, W.HKL]
        hkl = user32.GetKeyboardLayout(0)
        _ALTGR_LAYOUT = any(
            (user32.VkKeyScanExW(chr(cp), hkl) != -1
             and (user32.VkKeyScanExW(chr(cp), hkl) >> 8) & 0x06 == 0x06)
            for cp in list(range(33, 127)) + list(range(160, 256)))
    except Exception:
        _ALTGR_LAYOUT = False
    return _ALTGR_LAYOUT


def altgr_conflicts(hotkeys):
    """Which of these hotkey strings would fire when the user types with AltGr."""
    out = []
    for label, spec in hotkeys:
        parsed = parse_hotkey(spec)
        if parsed and (parsed[0] & MOD_CONTROL) and (parsed[0] & MOD_ALT):
            out.append((label, spec))
    return out


def altgr_is_down():
    """AltGr is the right Alt plus a synthetic left Ctrl. A genuine Ctrl+Alt
    chord uses the left Alt, so the two are distinguishable once the keys are
    down - even though RegisterHotKey cannot separate them at registration."""
    right = user32.GetAsyncKeyState(VK_RMENU) & 0x8000
    left = user32.GetAsyncKeyState(VK_LMENU) & 0x8000
    return bool(right and not left)


def parse_hotkey(spec):
    """'ctrl+alt+1' -> (modifiers, vk). Returns None if unparseable."""
    if not spec:
        return None
    mods = 0
    key = None
    for part in str(spec).lower().replace(" ", "").split("+"):
        if not part:
            key = "+"          # a literal '+' between separators
            continue
        if part in MODIFIERS:
            mods |= MODIFIERS[part]
        else:
            key = part
    if key is None:
        return None
    if key == "+":
        vk = 0xBB
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key.startswith("numpad") and key[6:].isdigit():
        vk = 0x60 + int(key[6:])
    elif key in VK_NAMES:
        vk = VK_NAMES[key]
    else:
        return None
    return (mods | MOD_NOREPEAT, vk)


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

DEFAULT_PROFILES = {
    "settings": {
        "restore_on_exit": True,
        "toggle_back": True,
        "reapply_on_display_change": True,
        "notify": True,
        "pin_tray_icon": False,
        "enforce_profile": True,
        "enforce_interval_ms": 2000,
        "vibrance_step": 5
    },
    "hotkeys": {
        "neutral": "ctrl+shift+0",
        "cycle": "ctrl+shift+v",
        "vibrance_up": "ctrl+shift+=",
        "vibrance_down": "ctrl+shift+-",
        "reload": "ctrl+shift+f5",
        "quit": "ctrl+shift+q"
    },
    "profiles": [
        {"name": "Neutral", "hotkey": "ctrl+shift+1",
         "vibrance": 50, "gamma": 1.00, "contrast": 50, "brightness": 50},
        {"name": "Competitive FPS", "hotkey": "ctrl+shift+2",
         "vibrance": 80, "gamma": 1.10, "contrast": 55, "brightness": 54},
        {"name": "Vivid", "hotkey": "ctrl+shift+3",
         "vibrance": 100, "gamma": 1.00, "contrast": 56, "brightness": 50},
        {"name": "Movie", "hotkey": "ctrl+shift+4",
         "vibrance": 62, "gamma": 0.95, "contrast": 52, "brightness": 48},
        {"name": "Night / dark room", "hotkey": "ctrl+shift+5",
         "vibrance": 55, "gamma": 1.25, "contrast": 46, "brightness": 43},
        {"name": "Focus (dim the second screen)", "hotkey": "ctrl+shift+6",
         "vibrance": 55, "gamma": 1.00, "contrast": 50, "brightness": 50,
         "monitors": {
             "secondary": {"vibrance": 42, "brightness": 38, "contrast": 46}
         }}
    ]
}


def load_config(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PROFILES, f, indent=2)
        log(f"Created default config: {path}")
        return json.loads(json.dumps(DEFAULT_PROFILES))
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("settings", {})
    for k, v in DEFAULT_PROFILES["settings"].items():
        cfg["settings"].setdefault(k, v)
    cfg.setdefault("hotkeys", {})
    cfg.setdefault("profiles", [])
    return cfg


def profile_value(prof, key, default):
    v = prof.get(key, default)
    return default if v is None else v


# --------------------------------------------------------------------------
# Run-at-login + talking to an already-running instance
# --------------------------------------------------------------------------

WINDOW_CLASS = "ScreenTunerHiddenWindow"
SETTINGS_TITLE = "ScreenTuner - Settings"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "ScreenTuner"


def pythonw_exe():
    """The windowless interpreter beside the current one, so no console flashes."""
    exe = sys.executable or "python.exe"
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def startup_command():
    if FROZEN:
        return f'"{sys.executable}"'
    return f'"{pythonw_exe()}" "{os.path.abspath(__file__)}"'


# --------------------------------------------------------------------------
# Install / uninstall - one implementation; the wizard and winget both call it
# --------------------------------------------------------------------------

VERSION = "1.0.0"
REPO_URL = "https://github.com/NachoSC/ScreenTuner"
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", BASE_DIR),
                           "Programs", "ScreenTuner")
UNINSTALL_KEY = (r"Software\Microsoft\Windows\CurrentVersion"
                 r"\Uninstall\ScreenTuner")


def _start_menu_dir():
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                        "Start Menu", "Programs")


def _make_shortcut(link, target, description=""):
    """IShellLink through PowerShell - avoids hand-rolling COM for one .lnk."""
    import subprocess

    def q(value):
        """A PowerShell single-quoted literal; ' is escaped by doubling it."""
        return "'" + str(value).replace("'", "''") + "'"

    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({q(link)});"
          f"$s.TargetPath={q(target)};"
          f"$s.WorkingDirectory={q(os.path.dirname(target))};"
          f"$s.Description={q(description)};"
          f"$s.IconLocation={q(target + ',0')};"
          f"$s.Save()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                        "-Command", ps], check=True, capture_output=True,
                       timeout=30)
        return True
    except Exception as e:
        log(f"  ! could not create shortcut: {e}")
        return False


def cmd_install(target_dir=None, startup=True):
    """Copy ourselves somewhere permanent and register properly with Windows.

    Per-user throughout: no admin needed, and nothing is written outside
    HKCU and %LOCALAPPDATA%."""
    import shutil
    import winreg
    if not FROZEN:
        print("--install works on the built ScreenTuner.exe, not the .py source.")
        return 1

    dest_dir = os.path.abspath(target_dir or INSTALL_DIR)
    dest = os.path.join(dest_dir, "ScreenTuner.exe")
    src = os.path.abspath(sys.executable)
    src_dir = os.path.dirname(src)
    os.makedirs(dest_dir, exist_ok=True)

    if os.path.normcase(src_dir) != os.path.normcase(dest_dir):
        # This is a --onedir build: the exe is useless without the runtime
        # files beside it, so the whole tree moves, not just the .exe.
        # Runtime state is left behind so a reinstall keeps existing profiles.
        skip = shutil.ignore_patterns("profiles.json", "screentuner.log",
                                      "backups")
        for _ in range(10):
            try:
                shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True,
                                ignore=skip)
                break
            except PermissionError:
                time.sleep(0.5)          # an older copy may still be exiting
        else:
            print(f"Could not write to {dest_dir} - is ScreenTuner still running?")
            return 1
    if not os.path.exists(dest):
        print(f"Install incomplete: {dest} missing")
        return 1
    n = sum(len(f) for _, _, f in os.walk(dest_dir))
    print(f"Installed to {dest_dir} ({n} files)")

    link = os.path.join(_start_menu_dir(), "ScreenTuner.lnk")
    if _make_shortcut(link, dest, "Hotkey display profiles"):
        print(f"Start Menu shortcut created")

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
        for name, value in (("DisplayName", "ScreenTuner"),
                            ("DisplayVersion", VERSION),
                            ("Publisher", "ScreenTuner"),
                            ("DisplayIcon", dest),
                            ("InstallLocation", dest_dir),
                            ("UninstallString", f'"{dest}" --uninstall'),
                            ("QuietUninstallString",
                             f'"{dest}" --uninstall --quiet'),
                            ("URLInfoAbout", REPO_URL)):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD,
                          max(1, os.path.getsize(dest) // 1024))
    print("Listed in Installed apps")

    if startup:
        set_startup_path(f'"{dest}"')
        print("Runs at login")
    return 0


def set_startup_path(command):
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, command)


def cmd_uninstall(quiet=False, keep_settings=None):
    """Remove every trace: files, shortcut, run-at-login, the tray-pin flag and
    the Installed-apps entry. Deleting the folder by hand leaves those behind."""
    import subprocess
    import winreg

    if keep_settings is None:
        keep_settings = False if quiet else _ask_keep_settings()

    hwnd = find_running_instance()
    if hwnd:
        user32.PostMessageW(hwnd, WM_DESTROY, 0, 0)
        for _ in range(20):
            time.sleep(0.25)
            if not find_running_instance():
                break

    promote_tray_icon(False)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_VALUE)
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    link = os.path.join(_start_menu_dir(), "ScreenTuner.lnk")
    if os.path.exists(link):
        try:
            os.remove(link)
        except OSError:
            pass

    install_dir = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else None
    if install_dir and not keep_settings:
        for leftover in ("profiles.json", "screentuner.log"):
            f = os.path.join(install_dir, leftover)
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

    print("ScreenTuner removed." + ("" if keep_settings else " Settings deleted."))
    if install_dir and FROZEN:
        _schedule_folder_delete(install_dir)
    return 0


def _schedule_folder_delete(folder):
    """Delete a folder we are currently running from, after we exit.

    A running exe cannot remove itself, and in a --onedir build the Python
    runtime DLLs beside it stay locked briefly afterwards. This runs from a
    throwaway .bat rather than `cmd /c "..."`: a batch file avoids cmd's
    quoting rules, and its working directory is %TEMP%, because Windows will
    not delete a directory that is any running process's current directory.
    """
    import subprocess
    import tempfile
    temp = tempfile.gettempdir()
    bat = os.path.join(temp, "screentuner-cleanup.bat")
    try:
        with open(bat, "w", encoding="ascii", newline="\r\n") as f:
            f.write("@echo off\n")
            f.write("for /l %%i in (1,1,30) do (\n")
            f.write("  ping 127.0.0.1 -n 2 >nul\n")
            f.write(f'  rmdir /s /q "{folder}" 2>nul\n')
            f.write(f'  if not exist "{folder}" goto done\n')
            f.write(")\n")
            f.write(":done\n")
            f.write('start "" /b cmd /c del "%~f0"\n')
        subprocess.Popen(["cmd", "/c", bat], cwd=temp,
                         creationflags=0x00000008)      # DETACHED_PROCESS
        return True
    except Exception as e:
        log(f"  ! could not schedule cleanup of {folder}: {e}")
        return False


def cmd_cleanup():
    """Remove only what the app registered with Windows - no files touched.

    The Inno installer owns the files and the Installed-apps entry; it calls this
    on uninstall so the two never disagree about who removes what."""
    import winreg
    hwnd = find_running_instance()
    if hwnd:
        user32.PostMessageW(hwnd, WM_DESTROY, 0, 0)
        for _ in range(20):
            time.sleep(0.25)
            if not find_running_instance():
                break
    promote_tray_icon(False)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_VALUE)
    except OSError:
        pass
    print("ScreenTuner registrations removed.")
    return 0


def _scrub(text):
    """Strip the reporter's identity out of any path before it is shared."""
    for var in ("USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP"):
        val = os.environ.get(var)
        if val:
            text = text.replace(val, f"%{var}%")
    user = os.environ.get("USERNAME")
    if user:
        text = text.replace(user, "<user>")
    return text


def build_diagnostics(config_path=None):
    """A report someone can paste into a bug report without leaking who they are.

    Deliberately excludes: username, home directory, machine name, and the
    contents of profiles.json (profile *names* only - people put all sorts in
    those). Paths are reduced to environment-variable form."""
    import platform
    lines = []
    add = lines.append

    add(f"ScreenTuner {VERSION}")
    add(f"frozen: {FROZEN}   python: {platform.python_version()}")
    add(f"windows: {platform.platform()}")
    add(f"install: {'yes' if os.path.exists(os.path.join(INSTALL_DIR, 'ScreenTuner.exe')) else 'portable/source'}")
    add(f"run at login: {'yes' if startup_enabled() else 'no'}")
    add(f"tray icon pinned: {'yes' if tray_icon_pinned() else 'no'}")
    add("")

    nv = NvApi()
    add(f"NVAPI: {'available' if nv.ok else 'NOT available - vibrance disabled'}")
    if nv.ok:
        add(f"  vibrance range {nv.min}-{nv.max}, neutral {nv.default}, "
            f"{len(nv.displays)} NVIDIA display(s)")
    add("")

    add("monitors:")
    for m in discover_monitors():
        vib = nv.get_level(nv.handle_for(m.adapter)) if nv.ok else None
        add(f"  [{m.index}] {m.vendor or '?'} {m.edid or '?'} "
            f"{m.width}x{m.height}@{m.refresh}Hz "
            f"{'primary' if m.is_primary else 'secondary'} "
            f"vibrance={vib if vib is not None else 'n/a'} gpu={m.gpu}")
    add("")

    try:
        cfg = load_config(config_path or DEFAULT_CONFIG)
        st = cfg.get("settings", {})
        add(f"settings: {json.dumps(st, sort_keys=True)}")
        add(f"profiles ({len(cfg.get('profiles', []))}): "
            + ", ".join(p.get("name", "?") for p in cfg.get("profiles", [])))
    except Exception as e:
        add(f"config: could not read ({e})")
    add("")

    add("recent log:")
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            tail = f.read().splitlines()[-40:]
        add("\n".join("  " + t for t in tail) if tail else "  (empty)")
    except OSError:
        add("  (no log file yet)")

    nv.unload()
    return _scrub("\n".join(lines))


def cmd_diagnostics():
    report = build_diagnostics()
    out = os.path.join(BASE_DIR, "screentuner-diagnostics.txt")
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write(report)
    except OSError:
        out = None
    print(report)
    if out:
        print(f"\nSaved to {out}")
        print("Attach that file to your bug report. It contains no username, "
              "home path or machine name.")
    return 0


def copy_diagnostics_to_clipboard():
    """Tray-menu path: put the report on the clipboard and say so."""
    import subprocess
    report = build_diagnostics()
    try:
        subprocess.run(["clip"], input=report.encode("utf-16-le"),
                       check=True, creationflags=0x08000000)
        return True
    except Exception as e:
        log(f"  ! clipboard failed: {e}")
        return False


def _ask_keep_settings():
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        keep = messagebox.askyesno(
            "ScreenTuner",
            "Keep your profiles.json?\n\n"
            "Yes - leave your profiles on disk\n"
            "No  - remove everything")
        r.destroy()
        return keep
    except Exception:
        return False


def startup_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, RUN_VALUE)[0]
    except (FileNotFoundError, OSError):
        return None


def set_startup(enable):
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_VALUE)
            except FileNotFoundError:
                pass
    return bool(enable)


def find_running_instance():
    user32.FindWindowW.restype = W.HWND
    user32.FindWindowW.argtypes = [W.LPCWSTR, W.LPCWSTR]
    return user32.FindWindowW(WINDOW_CLASS, None)


def signal_reload():
    """Ask a running instance to re-read profiles.json. True if one was listening."""
    hwnd = find_running_instance()
    if not hwnd:
        return False
    user32.PostMessageW(hwnd, WM_RELOAD_REQUEST, 0, 0)
    return True


def signal_show_settings():
    """Launching a second copy should surface the first one, not duplicate it."""
    hwnd = find_running_instance()
    if not hwnd:
        return False
    user32.PostMessageW(hwnd, WM_SHOW_SETTINGS, 0, 0)
    return True


def promote_tray_icon(promote=True):
    """Windows 11 hides new tray icons in the overflow flyout. Each icon gets a key
    under NotifyIconSettings keyed by its executable; IsPromoted=1 pins it to the
    taskbar itself, 0 puts it back in the overflow. The key only exists once the icon
    has been shown at least once.

    Off by default - rearranging someone's taskbar uninvited is not our call."""
    import winreg
    want = 1 if promote else 0
    exe = os.path.normcase(os.path.abspath(
        sys.executable if FROZEN else pythonw_exe()))
    root = r"Control Panel\NotifyIconSettings"
    pinned = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root) as base:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(base, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(base, name, 0,
                                        winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                        try:
                            path = winreg.QueryValueEx(k, "ExecutablePath")[0]
                        except FileNotFoundError:
                            continue
                        if os.path.normcase(os.path.abspath(path)) != exe:
                            continue
                        try:
                            if winreg.QueryValueEx(k, "IsPromoted")[0] == want:
                                pinned += 1
                                continue
                        except FileNotFoundError:
                            pass
                        winreg.SetValueEx(k, "IsPromoted", 0, winreg.REG_DWORD, want)
                        pinned += 1
                except OSError:
                    continue
    except OSError:
        return 0
    return pinned


def tray_icon_pinned():
    """True if our icon is currently pinned to the taskbar rather than the overflow."""
    import winreg
    exe = os.path.normcase(os.path.abspath(
        sys.executable if FROZEN else pythonw_exe()))
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Control Panel\NotifyIconSettings") as base:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(base, i)
                except OSError:
                    return False
                i += 1
                try:
                    with winreg.OpenKey(base, name) as k:
                        path = winreg.QueryValueEx(k, "ExecutablePath")[0]
                        if os.path.normcase(os.path.abspath(path)) != exe:
                            continue
                        return winreg.QueryValueEx(k, "IsPromoted")[0] == 1
                except (OSError, FileNotFoundError):
                    continue
    except OSError:
        return False


SETTING_KEYS = ("vibrance", "gamma", "contrast", "brightness")


def resolve_profile(profile, monitors):
    """Expand a profile into [(Monitor, settings)] - one entry per monitor it touches.

    Top-level values are the defaults; a `monitors` block overrides them per screen.
    A value of None means "leave that knob alone"; an override of false or
    {"skip": true} drops the monitor from the profile entirely.
    """
    base = {k: profile.get(k) for k in SETTING_KEYS}
    overrides = profile.get("monitors") or {}
    plan = []
    for m in monitors:
        settings = dict(base)
        for key, ov in overrides.items():
            if not m.matches(key):
                continue
            if ov is False or (isinstance(ov, dict) and ov.get("skip")):
                settings = None
            elif isinstance(ov, dict):
                settings.update({k: v for k, v in ov.items() if k in SETTING_KEYS})
            break
        if settings is not None:
            plan.append((m, settings))
    return plan


def apply_plan(plan, nv, gamma):
    gamma_map = {}
    for m, s in plan:
        if s["vibrance"] is not None:
            nv.set_for(m.adapter, s["vibrance"])
        # A gamma ramp is one curve, so any of the three implies writing all three.
        if any(s[k] is not None for k in ("gamma", "contrast", "brightness")):
            gamma_map[m.adapter] = (
                1.0 if s["gamma"] is None else s["gamma"],
                50 if s["contrast"] is None else s["contrast"],
                50 if s["brightness"] is None else s["brightness"])
    gamma.apply_map(gamma_map)


def fmt(v):
    return "-" if v is None else str(v)


def summarise_plan(plan):
    if not plan:
        return "no monitors targeted"
    if len({repr(s) for _, s in plan}) == 1:
        s = plan[0][1]
        return (f"vibrance {fmt(s['vibrance'])} · gamma {fmt(s['gamma'])} · "
                f"contrast {fmt(s['contrast'])} · brightness {fmt(s['brightness'])}")
    return " | ".join(f"{m.vendor or m.adapter}: vib {fmt(s['vibrance'])}, "
                      f"gam {fmt(s['gamma'])}" for m, s in plan)


# --------------------------------------------------------------------------
# Tray icon + message loop
# --------------------------------------------------------------------------

WM_DESTROY, WM_COMMAND, WM_HOTKEY = 0x0002, 0x0111, 0x0312
WM_DISPLAYCHANGE, WM_ENDSESSION = 0x007E, 0x0016
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_RELOAD_REQUEST = WM_APP + 2      # posted by the settings window after a save
WM_SHOW_SETTINGS = WM_APP + 3       # posted when the user launches a second copy
SW_RESTORE = 9
WM_TIMER = 0x0113
TIMER_ENFORCE = 1            # periodic "is our profile still applied?" check
TIMER_REFOCUS = 2            # one-shot, fires just after a foreground change
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
WINEVENTPROC = C.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND,
                             C.c_long, C.c_long, W.DWORD, W.DWORD)
user32.SetTimer.restype = C.c_size_t
user32.SetTimer.argtypes = [W.HWND, C.c_size_t, W.UINT, C.c_void_p]
user32.KillTimer.argtypes = [W.HWND, C.c_size_t]
user32.SetWinEventHook.restype = W.HANDLE
user32.SetWinEventHook.argtypes = [W.DWORD, W.DWORD, W.HMODULE, WINEVENTPROC,
                                   W.DWORD, W.DWORD, W.DWORD]
user32.UnhookWinEvent.argtypes = [W.HANDLE]
WM_LBUTTONDBLCLK, WM_RBUTTONUP, WM_LBUTTONUP = 0x0203, 0x0205, 0x0202

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
SM_CXSMICON, SM_CYSMICON = 49, 50
MF_STRING, MF_SEPARATOR, MF_CHECKED = 0x0000, 0x0800, 0x0008
MF_DISABLED, MF_GRAYED, MF_POPUP = 0x0002, 0x0001, 0x0010

# Past this many profiles the rest go into a "More profiles" submenu, rather than
# letting Windows turn the popup into an auto-scrolling column.
MENU_PROFILE_LIMIT = 12
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100

WNDPROC = C.WINFUNCTYPE(C.c_longlong, W.HWND, C.c_uint, W.WPARAM, W.LPARAM)


def load_app_icon(size=None):
    """Our icon.ico at tray size, or 0 if it is missing."""
    path = resource_path("icon.ico")
    if not os.path.exists(path):
        return 0
    cx = size or user32.GetSystemMetrics(SM_CXSMICON)
    cy = size or user32.GetSystemMetrics(SM_CYSMICON)
    return user32.LoadImageW(None, path, IMAGE_ICON, cx, cy, LR_LOADFROMFILE) or 0


class WNDCLASSW(C.Structure):
    _fields_ = [("style", C.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", C.c_int),
                ("cbWndExtra", C.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH),
                ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR)]


class NOTIFYICONDATAW(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", C.c_uint),
                ("uFlags", C.c_uint), ("uCallbackMessage", C.c_uint), ("hIcon", W.HICON),
                ("szTip", W.WCHAR * 128), ("dwState", W.DWORD), ("dwStateMask", W.DWORD),
                ("szInfo", W.WCHAR * 256), ("uVersion", C.c_uint),
                ("szInfoTitle", W.WCHAR * 64), ("dwInfoFlags", W.DWORD),
                ("guidItem", C.c_byte * 16), ("hBalloonIcon", W.HICON)]


class POINT(C.Structure):
    _fields_ = [("x", C.c_long), ("y", C.c_long)]


class MSG(C.Structure):
    _fields_ = [("hwnd", W.HWND), ("message", C.c_uint), ("wParam", W.WPARAM),
                ("lParam", W.LPARAM), ("time", W.DWORD), ("pt", POINT)]


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

CMD_BASE = 1000
CMD_NEUTRAL = 900
CMD_RELOAD = 901
CMD_EXIT = 902
CMD_SETTINGS = 903
CMD_STARTUP = 904
CMD_PIN = 905
CMD_VIB_UP = 906
CMD_VIB_DOWN = 907
CMD_DIAG = 908

# Menu id -> the same named action the hotkeys use, so both routes stay in step.
MENU_ACTIONS = {
    CMD_NEUTRAL: "neutral",
    CMD_RELOAD: "reload",
    CMD_EXIT: "quit",
    CMD_SETTINGS: "settings",
    CMD_STARTUP: "startup",
    CMD_PIN: "pin",
    CMD_VIB_UP: "vibrance_up",
    CMD_VIB_DOWN: "vibrance_down",
    CMD_DIAG: "diagnostics",
}


class App:
    def __init__(self, config_path, use_tray=True):
        self.config_path = config_path
        self.use_tray = use_tray
        self.nv = NvApi()
        self.gamma = GammaController()
        self.current = None          # index of active profile, None = baseline
        self.hwnd = None
        self.nid = None
        self._hotkey_ids = {}
        self._next_id = 1
        self._shutdown_done = False
        self._warned_altgr = False
        self._expected_vib = {}      # adapter -> level the driver reported back
        self._expected_ramp = {}     # adapter -> ramp the driver reported back
        self._hook = None
        self._hook_proc = None
        self.baseline_vibrance = self.nv.snapshot()
        self.cfg = load_config(config_path)

    # ---- applying -------------------------------------------------------

    def apply_profile(self, idx, announce=True):
        profs = self.cfg["profiles"]
        if not (0 <= idx < len(profs)):
            return
        p = profs[idx]
        monitors = discover_monitors()
        plan = resolve_profile(p, monitors)
        apply_plan(plan, self.nv, self.gamma)
        self.current = idx
        self._record_expected(plan)

        if announce:
            log(f"-> {p['name']}")
            for m, s in plan:
                log(f"     {m.label:<28} vibrance {fmt(s['vibrance'])}  "
                    f"gamma {fmt(s['gamma'])}  contrast {fmt(s['contrast'])}  "
                    f"brightness {fmt(s['brightness'])}")
            self.notify(p["name"], summarise_plan(plan))
        self.update_tip()

    def apply_neutral(self, announce=True):
        if self.nv.ok:
            self.nv.set_level(self.nv.default)
        self.gamma.apply(1.0, 50, 50)
        self.current = None
        self._clear_expected()
        if announce:
            log("-> Neutral (driver defaults)")
            self.notify("Neutral", "Back to driver defaults")
        self.update_tip()

    def restore_baseline(self):
        self._clear_expected()
        self.nv.restore(self.baseline_vibrance)
        self.gamma.restore_baseline()
        self.current = None

    # ---- keeping the profile applied ------------------------------------

    def _record_expected(self, plan):
        """Remember what the driver reports *after* we apply, not what we asked
        for - Windows can clamp a ramp, and drift checks must not fight that."""
        self._clear_expected()
        if not self.cfg["settings"].get("enforce_profile", True):
            return
        for m, s in plan:
            if s["vibrance"] is not None and self.nv.ok:
                level = self.nv.get_level(self.nv.handle_for(m.adapter))
                if level is not None:
                    self._expected_vib[m.adapter] = level
            if any(s[k] is not None for k in ("gamma", "contrast", "brightness")):
                ramp = self.gamma._read(m.adapter)
                if ramp is not None:
                    self._expected_ramp[m.adapter] = bytes(ramp)

    def _clear_expected(self):
        self._expected_vib = {}
        self._expected_ramp = {}

    def _enforce(self):
        """A game in exclusive fullscreen owns the gamma ramp, and the driver can
        reset vibrance on a mode switch - so alt-tabbing loses the profile. Put it
        back when that happens. Never while the settings window is previewing, or
        the two would fight over every slider drag."""
        if self.current is None or not (self._expected_vib or self._expected_ramp):
            return
        if user32.FindWindowW(None, SETTINGS_TITLE):
            return
        fixed = []
        for adapter, level in self._expected_vib.items():
            handle = self.nv.handle_for(adapter)
            if handle is not None and self.nv.get_level(handle) != level:
                self.nv._set_one(handle, level)
                fixed.append(f"vibrance on {adapter}")
        for adapter, expected in self._expected_ramp.items():
            current = self.gamma._read(adapter)
            if current is not None and bytes(current) != expected:
                self.gamma._write(adapter, RAMP.from_buffer_copy(expected))
                fixed.append(f"gamma on {adapter}")
        if fixed:
            log(f"   something overwrote us - reapplied {', '.join(fixed)}")

    def _on_foreground(self, hook, event, hwnd, idobj, idchild, thread, ts):
        """Alt-tab. Re-check once the incoming app has had a moment to settle."""
        try:
            user32.SetTimer(self.hwnd, TIMER_REFOCUS, 600, None)
        except Exception:
            pass

    def cycle(self):
        profs = self.cfg["profiles"]
        if not profs:
            return
        nxt = 0 if self.current is None else (self.current + 1) % len(profs)
        self.apply_profile(nxt)

    def nudge_vibrance(self, delta):
        if not self.nv.ok:
            log("  ! No NVIDIA display - can't change vibrance.")
            return
        cur = self.nv.get_level()
        if cur is None:
            return
        new = max(self.nv.min, min(self.nv.max, cur + delta))
        self.nv.set_level(new)
        log(f"-> vibrance {new}")
        self.notify("Digital vibrance", f"{new} / {self.nv.max}")
        self.update_tip()

    # ---- hotkeys --------------------------------------------------------

    def register_hotkeys(self):
        self.unregister_hotkeys()
        actions = []
        for i, p in enumerate(self.cfg["profiles"]):
            if p.get("hotkey"):
                actions.append((p["hotkey"], ("profile", i), p["name"]))
        hk = self.cfg.get("hotkeys", {})
        for name in ("neutral", "cycle", "vibrance_up", "vibrance_down", "reload", "quit"):
            if hk.get(name):
                actions.append((hk[name], (name, None), name))

        for spec, action, label in actions:
            parsed = parse_hotkey(spec)
            if not parsed:
                log(f"  ! Unrecognised hotkey '{spec}' for {label}")
                continue
            mods, vk = parsed
            hid = self._next_id
            self._next_id += 1
            if user32.RegisterHotKey(self.hwnd, hid, mods, vk):
                self._hotkey_ids[hid] = (action, mods)
                log(f"  {spec:<18} {label}")
            else:
                err = C.get_last_error()
                log(f"  ! Could not register {spec} for {label} "
                    f"({'already taken by another app' if err == 1409 else f'error {err}'})")

    def unregister_hotkeys(self):
        for hid in list(self._hotkey_ids):
            user32.UnregisterHotKey(self.hwnd, hid)
        self._hotkey_ids.clear()
        self._next_id = 1

    # ---- actions --------------------------------------------------------
    # Hotkeys, tray menu items and the profile list all end up here. One table
    # each, so adding an action is one line rather than another branch.

    def _step(self):
        return int(self.cfg["settings"].get("vibrance_step", 5))

    def quit(self):
        user32.PostMessageW(self.hwnd, WM_DESTROY, 0, 0)

    def toggle_profile(self, idx):
        """A profile's own hotkey doubles as an on/off switch for it."""
        if self.cfg["settings"].get("toggle_back", True) and self.current == idx:
            self.apply_neutral()
        else:
            self.apply_profile(idx)

    def toggle_startup(self):
        on = not startup_enabled()
        set_startup(on)
        log(f"-> start with Windows: {'on' if on else 'off'}")
        self.notify(APP_NAME, f"Start with Windows: {'on' if on else 'off'}")

    def toggle_pin(self):
        on = not tray_icon_pinned()
        promote_tray_icon(on)
        self.cfg["settings"]["pin_tray_icon"] = on
        self.save_settings()
        log(f"-> pin icon to taskbar: {'on' if on else 'off'}")
        self.notify(APP_NAME,
                    ("Icon pinned to the taskbar." if on else
                     "Icon moved back to the ^ overflow.")
                    + " Takes effect next start.")

    def copy_diagnostics(self):
        if copy_diagnostics_to_clipboard():
            self.notify("Diagnostics copied",
                        "Paste it into your bug report. No username, home path "
                        "or machine name is included.")
        else:
            self.notify("Diagnostics", "Could not reach the clipboard - "
                                       "run ScreenTuner.exe --diagnostics instead.")

    def save_settings(self):
        """Persist a settings-only change without disturbing the profiles."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            on_disk.setdefault("settings", {}).update(self.cfg["settings"])
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(on_disk, f, indent=2)
        except Exception as e:
            log(f"  ! Could not save settings: {e}")

    @property
    def actions(self):
        return {
            "neutral": self.apply_neutral,
            "cycle": self.cycle,
            "vibrance_up": lambda: self.nudge_vibrance(self._step()),
            "vibrance_down": lambda: self.nudge_vibrance(-self._step()),
            "reload": self.reload,
            "quit": self.quit,
            "settings": self.open_settings,
            "startup": self.toggle_startup,
            "pin": self.toggle_pin,
            "diagnostics": self.copy_diagnostics,
        }

    def on_hotkey(self, hid):
        entry = self._hotkey_ids.get(hid)
        if not entry:
            return
        action, mods = entry

        # On an AltGr layout Windows reports AltGr as Ctrl+Alt, so this may be
        # someone typing '@' rather than asking for a profile. Suppress only
        # when the right Alt is down and the left is not: that is AltGr.
        if (mods & MOD_CONTROL) and (mods & MOD_ALT) and layout_has_altgr() \
                and altgr_is_down():
            if not self._warned_altgr:
                self._warned_altgr = True
                log("  ! Ignoring AltGr. Your keyboard layout types characters "
                    "with it, and Windows reports AltGr as Ctrl+Alt.")
                log("    Rebind to Ctrl+Shift+... in Settings to avoid the clash "
                    "entirely.")
            return

        kind, arg = action
        if kind == "profile":
            self.toggle_profile(arg)
        else:
            self.actions.get(kind, lambda: None)()

    def reload(self):
        try:
            self.cfg = load_config(self.config_path)
        except Exception as e:
            log(f"  ! Config error: {e}")
            self.notify("Config error", str(e))
            return
        self.current = None
        log("\nConfig reloaded. Hotkeys:")
        self.register_hotkeys()
        self.notify("Reloaded", f"{len(self.cfg['profiles'])} profiles")
        self.update_tip()

    # ---- tray -----------------------------------------------------------

    def create_window(self):
        self._wndproc = WNDPROC(self._on_message)
        cls = WNDCLASSW()
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = kernel32.GetModuleHandleW(None)
        cls.lpszClassName = WINDOW_CLASS
        if not user32.RegisterClassW(C.byref(cls)):
            raise OSError(f"RegisterClassW failed: {C.get_last_error()}")
        self._cls = cls
        self.hwnd = user32.CreateWindowExW(
            0, cls.lpszClassName, APP_NAME, 0, 0, 0, 0, 0, None, None, cls.hInstance, None)
        if not self.hwnd:
            raise OSError(f"CreateWindowExW failed: {C.get_last_error()}")

    def add_tray(self):
        if not self.use_tray:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = C.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = load_app_icon() or user32.LoadIconW(
            None, MAKEINTRESOURCE(IDI_APPLICATION))
        nid.szTip = APP_NAME
        self.nid = nid
        # Opt-in only: if you have not asked for it, we leave your taskbar alone and
        # the icon sits in the "^" overflow like any other.
        pin = self.cfg["settings"].get("pin_tray_icon", False)
        # Explorer reads IsPromoted when the icon is added, so set it first using the
        # entry a previous run left behind...
        if pin:
            promote_tray_icon()
        shell32.Shell_NotifyIconW(NIM_ADD, C.byref(nid))
        # ...and again afterwards, because on the very first run the registry entry
        # does not exist until the icon has been shown once.
        if pin and promote_tray_icon():
            log("  tray icon pinned to the taskbar")
        elif not pin:
            log("  tray icon is in the \"^\" overflow (Options tab can pin it)")

    def update_tip(self):
        if not self.nid:
            return
        name = self.cfg["profiles"][self.current]["name"] if self.current is not None else "Neutral"
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self.nid.szTip = f"{APP_NAME} - {name}"[:127]
        shell32.Shell_NotifyIconW(NIM_MODIFY, C.byref(self.nid))

    def notify(self, title, text):
        if not self.nid or not self.cfg["settings"].get("notify", True):
            return
        self.nid.uFlags = NIF_INFO | NIF_ICON
        self.nid.szInfoTitle = title[:63]
        self.nid.szInfo = text[:255]
        self.nid.dwInfoFlags = 0
        shell32.Shell_NotifyIconW(NIM_MODIFY, C.byref(self.nid))

    def remove_tray(self):
        if self.nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, C.byref(self.nid))
            self.nid = None

    @property
    def active_name(self):
        return (self.cfg["profiles"][self.current]["name"]
                if self.current is not None else "Neutral")

    def _profile_item(self, i):
        p = self.cfg["profiles"][i]
        label = p["name"] + (f"\t{p['hotkey']}" if p.get("hotkey") else "")
        return ("item", CMD_BASE + i, label, i == self.current, True)

    def _menu_items(self):
        """Menu tree: ("item", id, label, checked, enabled),
        ("submenu", label, [children]), or None for a separator."""
        hk = self.cfg.get("hotkeys", {})

        def acc(action, text):
            return text + (f"\t{hk[action]}" if hk.get(action) else "")

        def item(cmd, label, checked=False, enabled=True):
            return ("item", cmd, label, checked, enabled)

        items = [item(0, f"{APP_NAME}  -  {self.active_name}", enabled=False), None]

        limit = int(self.cfg["settings"].get("menu_profile_limit", MENU_PROFILE_LIMIT))
        count = len(self.cfg["profiles"])
        if count <= limit:
            items += [self._profile_item(i) for i in range(count)]
        else:
            # Keep the active profile visible even when it lives in the overflow.
            shown = list(range(limit - 1))
            if self.current is not None and self.current not in shown:
                shown[-1] = self.current
            items += [self._profile_item(i) for i in shown]
            rest = [self._profile_item(i) for i in range(count) if i not in shown]
            items.append(("submenu", f"More profiles  ({len(rest)})...", rest))

        items += [None, item(CMD_NEUTRAL, acc("neutral", "Back to driver defaults"))]
        if self.nv.ok:
            items += [
                item(CMD_VIB_UP, acc("vibrance_up", f"Vibrance +{self._step()}")),
                item(CMD_VIB_DOWN, acc("vibrance_down", f"Vibrance -{self._step()}"))]

        items += [
            None,
            item(CMD_SETTINGS, "Settings..."),
            item(CMD_RELOAD, acc("reload", "Reload profiles.json")),
            item(CMD_DIAG, "Copy diagnostics for a bug report"),
            None,
            item(CMD_STARTUP, "Start with Windows", checked=bool(startup_enabled())),
            item(CMD_PIN, "Pin icon to taskbar", checked=tray_icon_pinned()),
            None,
            item(CMD_EXIT, acc("quit", "Exit")),
        ]
        return items

    def _build_menu(self, items):
        """Turn the item tree into an HMENU. DestroyMenu on the root frees submenus."""
        menu = user32.CreatePopupMenu()
        for entry in items:
            if entry is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            elif entry[0] == "submenu":
                _, label, children = entry
                sub = self._build_menu(children)
                user32.AppendMenuW(menu, MF_POPUP | MF_STRING, sub, label)
            else:
                _, cmd, label, checked, enabled = entry
                flags = MF_STRING | (MF_CHECKED if checked else 0)
                if not enabled:
                    flags |= MF_DISABLED | MF_GRAYED
                user32.AppendMenuW(menu, flags, cmd, label)
        return menu

    def show_menu(self):
        menu = self._build_menu(self._menu_items())
        pt = POINT()
        user32.GetCursorPos(C.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        if cmd:
            self.on_command(cmd)

    def open_settings(self):
        """Run the settings window as its own process - tkinter needs its own loop."""
        import subprocess
        existing = user32.FindWindowW(None, SETTINGS_TITLE)
        if existing:                      # already open - raise it, don't duplicate
            user32.ShowWindow(existing, SW_RESTORE)
            user32.SetForegroundWindow(existing)
            return
        try:
            subprocess.Popen(app_launch_args("--gui", "--config", self.config_path),
                             close_fds=True)
        except Exception as e:
            log(f"  ! Could not open settings: {e}")

    def on_command(self, cmd):
        if cmd >= CMD_BASE:
            self.apply_profile(cmd - CMD_BASE)
            return
        self.actions.get(MENU_ACTIONS.get(cmd), lambda: None)()

    # ---- message loop ---------------------------------------------------

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_HOTKEY:
            self.on_hotkey(wparam)
            return 0
        if msg == WM_TRAY:
            # Left button opens the settings window, right button the menu.
            # Neither one changes the display: switching profiles is for the
            # hotkeys and for picking an entry out of the menu.
            low = lparam & 0xFFFF
            if low in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self.open_settings()
            elif low == WM_RBUTTONUP:
                self.show_menu()
            return 0
        if msg == WM_COMMAND:
            self.on_command(wparam & 0xFFFF)
            return 0
        if msg == WM_TIMER:
            if wparam == TIMER_REFOCUS:
                user32.KillTimer(self.hwnd, TIMER_REFOCUS)
            self._enforce()
            return 0
        if msg == WM_RELOAD_REQUEST:
            self.reload()
            return 0
        if msg == WM_SHOW_SETTINGS:
            self.open_settings()
            return 0
        if msg == WM_DISPLAYCHANGE:
            if self.cfg["settings"].get("reapply_on_display_change", True):
                self.gamma.refresh()
                if self.current is not None:
                    self.apply_profile(self.current, announce=False)
            return 0
        if msg in (WM_DESTROY, WM_ENDSESSION):
            self.shutdown()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def shutdown(self):
        if self._shutdown_done:      # WM_DESTROY and atexit both land here
            return
        self._shutdown_done = True
        if self._hook:
            user32.UnhookWinEvent(self._hook)
            self._hook = None
        if self.hwnd:
            user32.KillTimer(self.hwnd, TIMER_ENFORCE)
            user32.KillTimer(self.hwnd, TIMER_REFOCUS)
        self.unregister_hotkeys()
        self.remove_tray()
        if self.cfg["settings"].get("restore_on_exit", True):
            self.restore_baseline()
        self.nv.unload()

    def run(self):
        self.create_window()
        self.add_tray()
        atexit.register(self.shutdown)

        log(f"{APP_NAME}")
        log(f"  config   : {self.config_path}")
        for m in discover_monitors():
            vib = self.nv.get_level(self.nv.handle_for(m.adapter)) if self.nv.ok else None
            log(f"  monitor  : [{m.index}] {m.label:<28} {m.adapter}"
                + (f"  vibrance {vib}" if vib is not None else ""))
        if self.nv.ok:
            log(f"  vibrance : NVAPI on {len(self.nv.displays)} display(s), "
                f"range {self.nv.min}-{self.nv.max} (neutral {self.nv.default}), "
                f"currently {', '.join(str(l) for _, l in self.baseline_vibrance)}")

        st = self.cfg["settings"]
        if st.get("enforce_profile", True):
            every = max(500, int(st.get("enforce_interval_ms", 2000)))
            user32.SetTimer(self.hwnd, TIMER_ENFORCE, every, None)
            self._hook_proc = WINEVENTPROC(self._on_foreground)
            self._hook = user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None,
                self._hook_proc, 0, 0,
                WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)
            log(f"  keep-applied: every {every} ms, and on every alt-tab")
        log("\nHotkeys:")
        self.register_hotkeys()

        if layout_has_altgr():
            pairs = [(p.get("name", "?"), p["hotkey"])
                     for p in self.cfg["profiles"] if p.get("hotkey")]
            pairs += [(k, v) for k, v in self.cfg.get("hotkeys", {}).items() if v]
            clashes = altgr_conflicts(pairs)
            if clashes:
                log(f"\n  ! Your keyboard layout has AltGr, and Windows reports "
                    f"AltGr as Ctrl+Alt, so {len(clashes)} binding(s) would fire "
                    f"while you type:")
                for label, spec in clashes:
                    log(f"      {spec:<18} {label}")
                log("    They are suppressed when AltGr is the key actually held, "
                    "but Ctrl+Shift+... is a cleaner fix.")
        quit_key = self.cfg.get("hotkeys", {}).get("quit") or "the tray menu"
        log(f"\nRunning. Tray icon: left-click opens Settings, right-click "
            f"the menu. Quit with {quit_key}.\n")
        self.notify(f"{APP_NAME} is running",
                    "It lives in the tray - left-click for Settings, "
                    "right-click for the profile menu.")

        msg = MSG()
        try:
            while True:
                r = user32.GetMessageW(C.byref(msg), None, 0, 0)
                if r == 0 or r == -1:
                    break
                user32.TranslateMessage(C.byref(msg))
                user32.DispatchMessageW(C.byref(msg))
        except KeyboardInterrupt:
            self.shutdown()
        log("Stopped, display settings restored.")


# --------------------------------------------------------------------------
# One-shot / info commands
# --------------------------------------------------------------------------

def cmd_list(cfg):
    nv = NvApi()
    monitors = discover_monitors()
    print("\nMonitors (a profile can target any of these names):")
    for m in monitors:
        vib = nv.get_level(nv.handle_for(m.adapter)) if nv.ok else None
        print(f"  [{m.index}] {m.vendor or '?':<10} {m.width}x{m.height}@{m.refresh}Hz"
              f"  {'primary' if m.is_primary else 'secondary':<10}"
              f"  vibrance={vib if vib is not None else 'n/a'}")
        print(f"       match by: {m.index}  |  \"{m.vendor}\"  |  \"{m.edid}\"  |  "
              f"\"{'primary' if m.is_primary else 'secondary'}\"  |  "
              f"\"{m.adapter}\"")
    if nv.ok:
        print(f"\nVibrance range {nv.min}-{nv.max}, neutral {nv.default}.")
    print("\nProfiles:")
    for p in cfg["profiles"]:
        print(f"  {p.get('hotkey', ''):<14} {p['name']}")
        for m, s in resolve_profile(p, monitors):
            print(f"       {m.vendor or m.adapter:<10} vibrance={fmt(s['vibrance'])} "
                  f"gamma={fmt(s['gamma'])} contrast={fmt(s['contrast'])} "
                  f"brightness={fmt(s['brightness'])}")
    print()
    nv.unload()


def cmd_apply(cfg, name):
    matches = [p for p in cfg["profiles"] if p["name"].lower() == name.lower()]
    if not matches:
        matches = [p for p in cfg["profiles"] if name.lower() in p["name"].lower()]
    if not matches:
        print(f"No profile matching '{name}'. Known: "
              + ", ".join(p["name"] for p in cfg["profiles"]))
        return 1
    p = matches[0]
    nv = NvApi()
    plan = resolve_profile(p, discover_monitors())
    apply_plan(plan, nv, GammaController())
    print(f"Applied '{p['name']}':")
    for m, s in plan:
        print(f"  {m.label:<28} vibrance={fmt(s['vibrance'])} gamma={fmt(s['gamma'])} "
              f"contrast={fmt(s['contrast'])} brightness={fmt(s['brightness'])}")
    nv.unload()
    return 0


def cmd_reset():
    nv = NvApi()
    if nv.ok:
        nv.set_level(nv.default)
    GammaController().apply(1.0, 50, 50)
    nv.unload()
    print("Reset to neutral.")


def cmd_enable_full_gamma_range():
    import winreg
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ICM", 0,
            winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "GdiIcmGammaRange", 0, winreg.REG_DWORD, 256)
        winreg.CloseKey(key)
        print("GdiIcmGammaRange set to 256. Reboot (or sign out) for it to take effect.")
        print("This lifts Windows' clamp on extreme gamma/contrast ramps.")
    except PermissionError:
        print("Needs an elevated prompt. Re-run this in an Administrator terminal:")
        print(f'  python "{os.path.abspath(__file__)}" --enable-full-gamma-range')
        return 1
    return 0


# Arguments that produce console output. Everything else (--config, --no-tray,
# --gui) is a tray-mode modifier and must not conjure a console window.
CONSOLE_ARGS = {
    "-h", "--help", "--list", "--apply", "--reset", "--startup", "--diagnostics",
    "--install", "--uninstall", "--cleanup", "--pin-tray",
    "--enable-full-gamma-range",
}


def main():
    if any(a.split("=", 1)[0] in CONSOLE_ARGS for a in sys.argv[1:]):
        attach_console()

    ap = argparse.ArgumentParser(
        prog="screentuner",
        description="Hotkey-driven digital vibrance / gamma / contrast / brightness.")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="path to profiles.json")
    ap.add_argument("--list", action="store_true", help="show displays, current vibrance, profiles")
    ap.add_argument("--apply", metavar="NAME", help="apply a profile once and exit")
    ap.add_argument("--reset", action="store_true", help="reset to neutral and exit")
    ap.add_argument("--gui", action="store_true", help="open the settings window")
    ap.add_argument("--startup", choices=["on", "off", "toggle", "status"],
                    help="run ScreenTuner automatically at login")
    ap.add_argument("--no-tray", action="store_true", help="run without a tray icon")
    ap.add_argument("--install", nargs="?", const="", metavar="DIR",
                    help="install to %LOCALAPPDATA% (or DIR), with Start Menu entry")
    ap.add_argument("--uninstall", action="store_true",
                    help="remove ScreenTuner and everything it registered")
    ap.add_argument("--cleanup", action="store_true",
                    help="remove only the registry entries (used by the installer)")
    ap.add_argument("--diagnostics", action="store_true",
                    help="print a scrubbed report to attach to a bug report")
    ap.add_argument("--quiet", action="store_true",
                    help="with --uninstall: no prompts")
    ap.add_argument("--no-startup", action="store_true",
                    help="with --install: do not run at login")
    ap.add_argument("--pin-tray", action="store_true",
                    help="pin the tray icon to the taskbar instead of the overflow")
    ap.add_argument("--enable-full-gamma-range", action="store_true",
                    help="registry tweak lifting Windows' gamma clamp (needs admin)")
    args = ap.parse_args()

    if args.enable_full_gamma_range:
        return cmd_enable_full_gamma_range()

    if args.install is not None:
        return cmd_install(args.install or None, startup=not args.no_startup)

    if args.uninstall:
        return cmd_uninstall(quiet=args.quiet)

    if args.cleanup:
        return cmd_cleanup()

    if args.diagnostics:
        return cmd_diagnostics()

    if args.pin_tray:
        n = promote_tray_icon()
        print(f"Pinned {n} tray icon entr{'y' if n == 1 else 'ies'} to the taskbar."
              if n else
              "No tray icon entry found yet - start the app once, then run this again.")
        return 0

    if args.startup:
        current = startup_enabled()
        if args.startup == "status":
            print(f"Start at login: {'ON  -> ' + current if current else 'off'}")
            return 0
        want = {"on": True, "off": False, "toggle": not current}[args.startup]
        set_startup(want)
        print(f"Start at login: {'ON  -> ' + startup_command() if want else 'off'}")
        return 0

    cfg = load_config(args.config)
    if args.gui:
        if not FROZEN:
            sys.path.insert(0, BASE_DIR)
        import configui
        # Pass this module in, so the GUI shares our already-loaded state
        # instead of importing a second copy of it under a different name.
        return configui.run(args.config, sys.modules[__name__])
    if args.list:
        cmd_list(cfg)
        return 0
    if args.reset:
        cmd_reset()
        return 0
    if args.apply:
        return cmd_apply(cfg, args.apply)

    # A second copy would fail to register every hotkey and report them all as
    # "taken by another app" - which would be us. Instead of exiting silently
    # (looks like nothing happened when you double-click), show the first one's
    # settings window: that is what a tray app with no main window should do.
    if signal_show_settings():
        attach_console()
        log("ScreenTuner is already running - opening its settings window.")
        return 0

    App(args.config, use_tray=not args.no_tray).run()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
