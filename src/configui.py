"""Settings window for ScreenTuner.

Runs as its own process (tkinter needs its own event loop, the tray app already has a
Win32 one). Sliders preview live on the real screen; Save writes profiles.json and pokes
the running tray app to reload.
"""

import ctypes as C
import json
import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

sp = None       # the screentuner module, injected by run()


# --------------------------------------------------------------------------
# Look and feel
# --------------------------------------------------------------------------

LIGHT = dict(bg="#f4f5f7", panel="#ffffff", text="#1b1d21", subtle="#6b7280",
             accent="#2f6fed", border="#d4d9e0", trough="#e2e6ec",
             sel="#e8f0fe", danger="#c0392b",
             button="#ffffff", button_active="#eef2f8", indicator="#ffffff")
DARK = dict(bg="#1e1f22", panel="#26282c", text="#e6e8ec", subtle="#9aa0a8",
            accent="#5b9bff", border="#3a3d43", trough="#15161a",
            sel="#2f3a4d", danger="#e06c5f",
            button="#33363b", button_active="#3d4147", indicator="#15161a")


def as_scalar(value, default):
    """Config allows [r, g, b]; these sliders are single values.
    Returns (value_for_the_slider, was_per_channel)."""
    if value is None:
        return default, False
    if isinstance(value, (list, tuple)):
        nums = [float(x) for x in value]
        return (round(sum(nums) / len(nums), 2), True) if nums else (default, True)
    return value, False


def windows_dark_mode():
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        with k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def set_dark_titlebar(root, dark):
    """Win11 dark title bar - purely cosmetic, ignore any failure."""
    try:
        root.update_idletasks()
        hwnd = C.windll.user32.GetParent(root.winfo_id())
        val = C.c_int(1 if dark else 0)
        for attr in (20, 19):       # 20 on current Win10/11, 19 on older builds
            if C.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, C.byref(val), C.sizeof(val)) == 0:
                break
    except Exception:
        pass


def build_style(root, P):
    style = ttk.Style(root)
    style.theme_use("clam")
    f = ("Segoe UI", 10)
    fb = ("Segoe UI Semibold", 10)

    root.configure(bg=P["bg"])
    # No global focuscolor: clam paints it as a ring around the Scale groove.
    style.configure(".", background=P["bg"], foreground=P["text"], font=f,
                    borderwidth=0)
    style.configure("TFrame", background=P["bg"])
    style.configure("Panel.TFrame", background=P["panel"], relief="flat")
    style.configure("TLabel", background=P["bg"], foreground=P["text"], font=f)
    style.configure("Panel.TLabel", background=P["panel"], foreground=P["text"])
    style.configure("Subtle.TLabel", background=P["bg"], foreground=P["subtle"],
                    font=("Segoe UI", 9))
    style.configure("PanelSubtle.TLabel", background=P["panel"], foreground=P["subtle"],
                    font=("Segoe UI", 9))
    style.configure("Head.TLabel", background=P["bg"], foreground=P["text"], font=fb)
    style.configure("PanelHead.TLabel", background=P["panel"], foreground=P["text"], font=fb)
    style.configure("Title.TLabel", background=P["bg"], foreground=P["text"],
                    font=("Segoe UI Semibold", 13))

    style.configure("TButton", background=P["button"], foreground=P["text"],
                    bordercolor=P["border"], borderwidth=1, padding=(12, 6),
                    relief="solid", font=f,
                    lightcolor=P["button"], darkcolor=P["button"])
    style.map("TButton",
              background=[("pressed", P["button_active"]),
                          ("active", P["button_active"])],
              lightcolor=[("active", P["button_active"])],
              darkcolor=[("active", P["button_active"])],
              bordercolor=[("active", P["accent"])])
    style.configure("Accent.TButton", background=P["accent"], foreground="#ffffff",
                    bordercolor=P["accent"], padding=(16, 7), font=fb)
    style.map("Accent.TButton",
              background=[("pressed", P["accent"]), ("active", P["accent"]),
                          ("disabled", P["border"])],
              foreground=[("disabled", P["subtle"])])
    style.configure("Mini.TButton", padding=(6, 2), font=("Segoe UI", 9))

    # Segmented buttons: borrow Toolbutton's layout so no radio dot is drawn at all.
    try:
        style.layout("Seg.TRadiobutton", style.layout("Toolbutton"))
    except tk.TclError:
        pass
    style.configure("Seg.TRadiobutton", background=P["button"], foreground=P["subtle"],
                    bordercolor=P["border"], borderwidth=1, relief="solid",
                    lightcolor=P["button"], darkcolor=P["button"],
                    padding=(14, 7), font=f, anchor="center")
    style.map("Seg.TRadiobutton",
              background=[("selected", P["accent"]), ("active", P["button_active"])],
              lightcolor=[("selected", P["accent"])],
              darkcolor=[("selected", P["accent"])],
              bordercolor=[("selected", P["accent"])],
              foreground=[("selected", "#ffffff"), ("active", P["text"])])

    style.configure("TEntry", fieldbackground=P["panel"], foreground=P["text"],
                    bordercolor=P["border"], insertcolor=P["text"],
                    borderwidth=1, padding=6)
    style.map("TEntry", bordercolor=[("focus", P["accent"])])
    style.configure("TSpinbox", fieldbackground=P["panel"], foreground=P["text"],
                    bordercolor=P["border"], arrowcolor=P["text"],
                    borderwidth=1, padding=4)

    style.configure("TNotebook", background=P["bg"], borderwidth=0,
                    bordercolor=P["border"], lightcolor=P["bg"], darkcolor=P["bg"],
                    tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=P["bg"], foreground=P["subtle"],
                    bordercolor=P["bg"], lightcolor=P["bg"], darkcolor=P["bg"],
                    padding=(20, 9), borderwidth=0, font=f)
    style.map("TNotebook.Tab",
              background=[("selected", P["panel"]), ("active", P["bg"])],
              lightcolor=[("selected", P["panel"])],
              darkcolor=[("selected", P["panel"])],
              foreground=[("selected", P["text"]), ("active", P["text"])],
              expand=[("selected", (0, 0, 0, 0))])

    for s in ("TScale", "Horizontal.TScale", "Panel.Horizontal.TScale"):
        # light/dark/border all match the trough: the slider keeps its accent fill
        # but loses clam's default bright bevel around the groove.
        style.configure(s, background=P["accent"], troughcolor=P["trough"],
                        bordercolor=P["trough"], lightcolor=P["trough"],
                        darkcolor=P["trough"], focuscolor=P["trough"],
                        borderwidth=0, gripcount=0,
                        sliderlength=20, sliderthickness=16)
        style.map(s,
                  background=[("disabled", P["border"]), ("active", P["accent"])],
                  lightcolor=[("disabled", P["border"])],
                  darkcolor=[("disabled", P["border"])],
                  troughcolor=[("disabled", P["trough"])])
    style.configure("TSeparator", background=P["border"])
    return style


# Classic tk check/radio buttons: ttk's clam indicators are near-invisible in dark
# mode, and these let us colour the box directly.
def make_check(parent, P, text, var, command, panel=True, font=("Segoe UI", 10)):
    bg = P["panel"] if panel else P["bg"]
    return tk.Checkbutton(
        parent, text=text, variable=var, command=command or (lambda: None), font=font,
        bg=bg, fg=P["text"], activebackground=bg, activeforeground=P["text"],
        selectcolor=P["indicator"], disabledforeground=P["subtle"],
        highlightthickness=0, bd=0, anchor="w", padx=2, cursor="hand2")


def make_radio(parent, P, text, value, var, command, panel=True):
    bg = P["panel"] if panel else P["bg"]
    return tk.Radiobutton(
        parent, text=text, value=value, variable=var, command=command,
        font=("Segoe UI", 10), bg=bg, fg=P["text"], activebackground=bg,
        activeforeground=P["text"], selectcolor=P["indicator"],
        disabledforeground=P["subtle"], highlightthickness=0, bd=0,
        anchor="w", padx=2, cursor="hand2")


# --------------------------------------------------------------------------
# Small composite widgets
# --------------------------------------------------------------------------

class SliderRow(ttk.Frame):
    """Label + slider + numeric box + reset, on a panel background."""

    def __init__(self, parent, P, label, lo, hi, neutral, resolution, on_change):
        super().__init__(parent, style="Panel.TFrame")
        self.P, self.lo, self.hi = P, lo, hi
        self.neutral, self.resolution = neutral, resolution
        self.on_change = on_change
        self._mute = False

        ttk.Label(self, text=label, style="Panel.TLabel", width=12).pack(side="left")
        self.var = tk.DoubleVar(value=neutral)
        self.scale = ttk.Scale(self, from_=lo, to=hi, orient="horizontal",
                               variable=self.var, style="Panel.Horizontal.TScale",
                               command=self._slid)
        self.scale.pack(side="left", fill="x", expand=True, padx=(4, 10))

        self.entry = ttk.Entry(self, width=6, justify="center")
        self.entry.pack(side="left")
        self.entry.bind("<Return>", self._typed)
        self.entry.bind("<FocusOut>", self._typed)

        self.reset_btn = ttk.Button(self, text="reset", style="Mini.TButton",
                                    width=6, command=self.reset)
        self.reset_btn.pack(side="left", padx=(8, 0))
        self._refresh_entry()

    def _round(self, v):
        return round(round(float(v) / self.resolution) * self.resolution,
                     2 if self.resolution < 1 else 0)

    def _refresh_entry(self):
        v = self._round(self.var.get())
        txt = f"{v:.2f}" if self.resolution < 1 else f"{int(v)}"
        self.entry.delete(0, "end")
        self.entry.insert(0, txt)

    def _slid(self, _=None):
        if self._mute:
            return
        self._refresh_entry()
        self.on_change()

    def _typed(self, _=None):
        try:
            v = max(self.lo, min(self.hi, float(self.entry.get())))
        except ValueError:
            v = self.var.get()
        self.set(v)
        self.on_change()

    def reset(self):
        self.set(self.neutral)
        self.on_change()

    def get(self):
        return self._round(self.var.get())

    def set(self, v, silent=True):
        self._mute = silent
        self.var.set(float(v))
        self._mute = False
        self._refresh_entry()

    def set_enabled(self, on):
        state = "normal" if on else "disabled"
        self.scale.state(["!disabled"] if on else ["disabled"])
        self.entry.state(["!disabled"] if on else ["disabled"])
        self.reset_btn.state(["!disabled"] if on else ["disabled"])


class VibrancePreview(tk.Canvas):
    """Swatches showing roughly what a vibrance level does to colour.

    NVIDIA's DVC maths is not published, so this is an HLS saturation scale
    standing in for it - the direction and rough strength are right, the exact
    shade is not. Greys stay grey either way, which is the useful part to see.
    """

    ROW = 21
    GAP = 3

    # (hue, saturation, lightness): a hue sweep, then a skin tone - the first
    # thing to look wrong when over-saturated - and a grey, which must not move.
    BASE = ([(h / 12.0, 0.50, 0.52) for h in range(12)]
            + [(0.06, 0.45, 0.68), (0.0, 0.00, 0.55)])

    def __init__(self, parent, P, width=380):
        self.P = P
        self.w = width
        super().__init__(parent, width=width, height=self.ROW * 2 + self.GAP + 2,
                         bg=P["panel"], highlightthickness=0, bd=0)

    @staticmethod
    def _swatch(hue, light, sat, factor):
        import colorsys
        r, g, b = colorsys.hls_to_rgb(hue, light, max(0.0, min(1.0, sat * factor)))
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    def render(self, level, enabled=True):
        self.delete("all")
        factor = (level / 50.0) if enabled else 1.0
        n = len(self.BASE)
        cw = self.w / n
        for i, (hue, sat, light) in enumerate(self.BASE):
            x0, x1 = i * cw, (i + 1) * cw - 1
            self.create_rectangle(x0, 0, x1, self.ROW,
                                  fill=self._swatch(hue, light, sat, 1.0), outline="")
            self.create_rectangle(x0, self.ROW + self.GAP, x1,
                                  self.ROW * 2 + self.GAP,
                                  fill=self._swatch(hue, light, sat, factor),
                                  outline="")


class CurveGraph(tk.Canvas):
    """The transfer curve: input level in, what the GPU sends out.

    Drawn straight from GammaController.build_ramp - the same lookup table that
    gets written to the driver - so this is the real curve, not an impression
    of one. The dashed diagonal is "no change"; the strip underneath is the
    resulting black-to-white ramp.
    """

    PAD = 8
    STRIP = 18
    CHANNEL_COLOURS = ("#e0605f", "#54bd77", "#5b9bff")

    def __init__(self, parent, P, size=224):
        self.P = P
        self.size = size
        super().__init__(parent, width=size, height=size + self.STRIP + 8,
                         bg=P["panel"], highlightthickness=1, bd=0,
                         highlightbackground=P["border"])

    def render(self, gamma, contrast, brightness, enabled=True):
        self.delete("all")
        P, s, pad = self.P, self.size, self.PAD
        x0, y0, x1, y1 = pad, pad, s - pad, s - pad
        w, h = x1 - x0, y1 - y0

        for k in range(1, 4):
            gx, gy = x0 + w * k / 4, y0 + h * k / 4
            self.create_line(gx, y0, gx, y1, fill=P["border"])
            self.create_line(x0, gy, x1, gy, fill=P["border"])
        self.create_rectangle(x0, y0, x1, y1, outline=P["border"])
        self.create_line(x0, y1, x1, y0, fill=P["subtle"], dash=(3, 3))

        try:
            ramp = sp.GammaController.build_ramp(gamma, contrast, brightness)
        except Exception:
            return
        chans = [[ramp[c][i] for i in range(256)] for c in range(3)]

        def points(vals):
            pts = []
            for i in range(0, 256, 3):
                pts += [x0 + w * i / 255.0, y1 - h * vals[i] / 65535.0]
            pts += [x1, y1 - h * vals[255] / 65535.0]
            return pts

        if not enabled:
            self.create_text(s / 2, s / 2, text="not modified",
                             fill=P["subtle"], font=("Segoe UI", 9))
        elif chans[0] == chans[1] == chans[2]:
            self.create_line(*points(chans[0]), fill=P["accent"], width=2,
                             smooth=True, capstyle="round")
        else:
            for c, colour in enumerate(self.CHANNEL_COLOURS):
                self.create_line(*points(chans[c]), fill=colour, width=2,
                                 smooth=True, capstyle="round")

        sy0 = y1 + 6
        sy1 = sy0 + self.STRIP
        steps = 72
        for k in range(steps):
            i = int(k * 255 / (steps - 1))
            if enabled:
                r, g, b = (chans[c][i] >> 8 for c in range(3))
            else:
                r = g = b = i
            self.create_rectangle(x0 + w * k / steps, sy0,
                                  x0 + w * (k + 1) / steps + 1, sy1,
                                  fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
        self.create_rectangle(x0, sy0, x1, sy1, outline=P["border"])


KEYSYM_MAP = {
    "space": "space", "minus": "-", "equal": "=", "plus": "=", "bracketleft": "[",
    "bracketright": "]", "semicolon": ";", "apostrophe": "'", "comma": ",",
    "period": ".", "slash": "/", "backslash": "\\", "grave": "`",
    "Prior": "pgup", "Next": "pgdn", "Home": "home", "End": "end",
    "Insert": "insert", "Delete": "delete", "Up": "up", "Down": "down",
    "Left": "left", "Right": "right", "Return": "enter", "BackSpace": "backspace",
    "Tab": "tab", "KP_Add": "add", "KP_Subtract": "subtract",
    "KP_Multiply": "multiply", "KP_Divide": "divide",
}
DEAD_KEYSYMS = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                "Win_L", "Win_R", "Super_L", "Super_R", "Caps_Lock"}


class HotkeyButton(ttk.Button):
    """Click, then press the combination you want."""

    def __init__(self, parent, P, on_change, width=20):
        super().__init__(parent, width=width, command=self._start)
        self.P, self.on_change = P, on_change
        self.value = None
        self._capturing = False
        self._binds = []
        self._render()

    def _render(self):
        self.configure(text=self.value if self.value else "(none)")

    def set(self, value):
        self.value = value or None
        self._render()

    def _start(self):
        if self._capturing:
            return
        self._capturing = True
        self.configure(text="press keys...  (Esc clears)")
        top = self.winfo_toplevel()
        self._binds = [top.bind("<KeyPress>", self._key, add="+")]
        self.focus_set()

    def _stop(self):
        top = self.winfo_toplevel()
        for b in self._binds:
            top.unbind("<KeyPress>", b)
        self._binds = []
        self._capturing = False
        self._render()

    def _key(self, event):
        if event.keysym in DEAD_KEYSYMS:
            return "break"
        if event.keysym == "Escape":
            self.value = None
            self._stop()
            self.on_change()
            return "break"

        mods = []
        if event.state & 0x0004:
            mods.append("ctrl")
        if event.state & 0x20000 or event.state & 0x0008:
            mods.append("alt")
        if event.state & 0x0001:
            mods.append("shift")

        ks = event.keysym
        if ks in KEYSYM_MAP:
            key = KEYSYM_MAP[ks]
        elif len(ks) == 1 and ks.isalnum():
            key = ks.lower()
        elif ks.startswith("F") and ks[1:].isdigit():
            key = ks.lower()
        elif ks.startswith("KP_") and ks[3:].isdigit():
            key = "numpad" + ks[3:]
        else:
            key = ks.lower()

        if not mods:
            self.configure(text="need Ctrl / Alt / Shift...")
            return "break"

        self.value = "+".join(mods + [key])
        self._stop()
        self.on_change()
        return "break"


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------

ALL = "\x00all"


class ConfigWindow(tk.Tk):
    def __init__(self, config_path):
        super().__init__()
        self.config_path = config_path
        self.dark = windows_dark_mode()
        self.P = DARK if self.dark else LIGHT
        P = self.P

        self.title(sp.SETTINGS_TITLE)
        self.geometry("1240x820")
        self.minsize(1120, 740)
        build_style(self, P)
        set_dark_titlebar(self, self.dark)
        try:
            self.iconbitmap(sp.resource_path("icon.ico"))
        except Exception:
            pass
        try:
            tkfont.nametofont("TkDefaultFont").configure(family="Segoe UI", size=10)
        except Exception:
            pass

        self.cfg = sp.load_config(config_path)
        self.monitors = sp.discover_monitors()
        self.nv = sp.NvApi()
        self.gamma = sp.GammaController()
        self.entry_vibrance = self.nv.snapshot()
        self.entry_ramps = {a: self.gamma._read(a) for a in self.gamma.adapters}

        self.dirty = False
        self.current = None
        self.scope = tk.StringVar(value=ALL)
        self.preview = tk.BooleanVar(value=True)
        self._loading = False

        self._build()
        self._refresh_profile_list()
        if self.cfg["profiles"]:
            self._select(0)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ---- keys -----------------------------------------------------------

    def monitor_key(self, m):
        vendors = [x.vendor for x in self.monitors]
        if m.vendor and vendors.count(m.vendor) == 1:
            return m.vendor
        return m.edid or m.adapter

    # ---- layout ---------------------------------------------------------

    def _build(self):
        P = self.P
        outer = ttk.Frame(self, padding=(16, 14, 16, 12))
        outer.pack(fill="both", expand=True)

        head = ttk.Frame(outer)
        head.pack(fill="x", pady=(0, 12))
        ttk.Label(head, text="ScreenTuner", style="Title.TLabel").pack(side="left")
        self.status = ttk.Label(head, text="", style="Subtle.TLabel")
        self.status.pack(side="right")

        # Pack the action bar FIRST against the bottom edge, so a tall profile
        # pane can never push Save off the window.
        bar = ttk.Frame(outer, padding=(0, 12, 0, 0))
        bar.pack(side="bottom", fill="x")
        make_check(bar, P, "Live preview while editing", self.preview,
                   None, panel=False).pack(side="left")
        ttk.Button(bar, text="Close", command=self._close).pack(side="right")
        self.save_btn = ttk.Button(bar, text="Save", style="Accent.TButton",
                                   command=self._save)
        self.save_btn.pack(side="right", padx=(0, 8))

        nb = ttk.Notebook(outer)
        nb.enable_traversal()          # Ctrl+Tab between Profiles and Options
        nb.pack(side="top", fill="both", expand=True)
        tab_p = ttk.Frame(nb, style="Panel.TFrame", padding=14)
        tab_o = ttk.Frame(nb, style="Panel.TFrame", padding=18)
        nb.add(tab_p, text="  Profiles  ")
        nb.add(tab_o, text="  Options  ")
        self._build_profiles(tab_p)
        self._build_options(tab_o)

    def _build_profiles(self, root):
        P = self.P
        left = ttk.Frame(root, style="Panel.TFrame")
        left.pack(side="left", fill="y", padx=(0, 16))

        ttk.Label(left, text="PROFILES", style="PanelSubtle.TLabel").pack(anchor="w")
        self.listbox = tk.Listbox(
            left, width=26, activestyle="none", highlightthickness=1, bd=0,
            bg=P["panel"], fg=P["text"], selectbackground=P["accent"],
            selectforeground="#ffffff", highlightbackground=P["border"],
            highlightcolor=P["border"], font=("Segoe UI", 10))
        self.listbox.pack(fill="y", expand=True, pady=(6, 8))
        self.listbox.bind("<<ListboxSelect>>", self._on_list_select)

        tb = ttk.Frame(left, style="Panel.TFrame")
        tb.pack(fill="x")
        for txt, cmd, w in (("+", self._add, 3), ("Copy", self._duplicate, 6),
                            ("Delete", self._delete, 7), ("^", self._up, 3),
                            ("v", self._down, 3)):
            ttk.Button(tb, text=txt, width=w, style="Mini.TButton",
                       command=cmd).pack(side="left", padx=(0, 4))

        right = ttk.Frame(root, style="Panel.TFrame")
        right.pack(side="left", fill="both", expand=True)

        row = ttk.Frame(right, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 4))
        ttk.Label(row, text="Name", style="Panel.TLabel", width=12).pack(side="left")
        self.name_var = tk.StringVar()
        e = ttk.Entry(row, textvariable=self.name_var)
        e.pack(side="left", fill="x", expand=True)
        self.name_var.trace_add("write", lambda *_: self._on_name())

        row = ttk.Frame(right, style="Panel.TFrame")
        row.pack(fill="x", pady=(8, 14))
        ttk.Label(row, text="Hotkey", style="Panel.TLabel", width=12).pack(side="left")
        self.hotkey_btn = HotkeyButton(row, P, self._on_hotkey)
        self.hotkey_btn.pack(side="left")
        self.hotkey_note = ttk.Label(row, text="", style="PanelSubtle.TLabel")
        self.hotkey_note.pack(side="left", padx=(10, 0))

        ttk.Separator(right).pack(fill="x", pady=(0, 12))

        ttk.Label(right, text="APPLIES TO", style="PanelSubtle.TLabel").pack(anchor="w")
        seg = ttk.Frame(right, style="Panel.TFrame")
        seg.pack(anchor="w", pady=(6, 12))
        ttk.Radiobutton(seg, text="All monitors", value=ALL, variable=self.scope,
                        style="Seg.TRadiobutton", command=self._on_scope).pack(side="left")
        for m in self.monitors:
            ttk.Radiobutton(seg, text=f"{m.vendor or m.adapter}  {m.width}x{m.height}",
                            value=self.monitor_key(m), variable=self.scope,
                            style="Seg.TRadiobutton",
                            command=self._on_scope).pack(side="left", padx=(6, 0))

        self.mode = tk.StringVar(value="same")
        self.mode_frame = ttk.Frame(right, style="Panel.TFrame")
        self.mode_frame.pack(fill="x", pady=(0, 10))
        for txt, val in (("Same as all monitors", "same"),
                         ("Custom for this monitor", "custom"),
                         ("Leave this monitor alone", "skip")):
            make_radio(self.mode_frame, P, txt, val, self.mode,
                       self._on_mode).pack(anchor="w", pady=1)

        self.vib_on = tk.BooleanVar(value=True)
        self.ramp_on = tk.BooleanVar(value=True)

        cols = ttk.Frame(right, style="Panel.TFrame")
        cols.pack(fill="both", expand=True, pady=(6, 0))
        sliders = ttk.Frame(cols, style="Panel.TFrame")
        sliders.pack(side="left", fill="both", expand=True)

        box = ttk.Frame(sliders, style="Panel.TFrame")
        box.pack(fill="x")
        make_check(box, P, "Digital vibrance", self.vib_on, self._on_toggle,
                   font=("Segoe UI Semibold", 10)).pack(anchor="w")
        self.s_vib = SliderRow(box, P, "Vibrance", 0, 100, 50, 1, self._on_slider)
        self.s_vib.pack(fill="x", pady=(4, 2), padx=(18, 0))
        self.vib_preview = VibrancePreview(box, P)
        self.vib_preview.pack(anchor="w", padx=(18, 0), pady=(4, 2))
        ttk.Label(box, wraplength=440, justify="left", style="PanelSubtle.TLabel",
                  text="50 is neutral, same scale as the NVIDIA Control Panel. "
                       "Top row is neutral, bottom row is this setting "
                       "(approximate - greys never shift).").pack(anchor="w",
                                                                  padx=(18, 0))

        ttk.Separator(sliders).pack(fill="x", pady=12)

        box2 = ttk.Frame(sliders, style="Panel.TFrame")
        box2.pack(fill="x")
        make_check(box2, P, "Gamma ramp", self.ramp_on, self._on_toggle,
                   font=("Segoe UI Semibold", 10)).pack(anchor="w")
        self.s_gam = SliderRow(box2, P, "Gamma", 0.30, 2.80, 1.00, 0.05, self._on_slider)
        self.s_con = SliderRow(box2, P, "Contrast", 0, 100, 50, 1, self._on_slider)
        self.s_bri = SliderRow(box2, P, "Brightness", 0, 100, 50, 1, self._on_slider)
        for s in (self.s_gam, self.s_con, self.s_bri):
            s.pack(fill="x", pady=2, padx=(18, 0))
        ttk.Label(box2, text="These three share one lookup table, so they switch on "
                            "and off together.",
                  style="PanelSubtle.TLabel").pack(anchor="w", padx=(18, 0), pady=(2, 0))
        self.channel_note = ttk.Label(box2, text="", style="PanelSubtle.TLabel",
                                      wraplength=380, justify="left")
        self.channel_note.pack(anchor="w", padx=(18, 0), pady=(4, 0))

        graph = ttk.Frame(cols, style="Panel.TFrame")
        graph.pack(side="left", padx=(20, 0), anchor="n")
        ttk.Label(graph, text="RESULTING CURVE",
                  style="PanelSubtle.TLabel").pack(anchor="w", pady=(0, 6))
        self.curve = CurveGraph(graph, P)
        self.curve.pack(anchor="w")
        ttk.Label(graph, wraplength=224, justify="left", style="PanelSubtle.TLabel",
                  text="Across: input level. Up: what the GPU sends to the "
                       "monitor. Dashed = no change.\n"
                       "Vibrance is not shown - it mixes channels rather than "
                       "bending a curve.").pack(anchor="w", pady=(8, 0))

    def _build_options(self, root):
        P = self.P
        ttk.Label(root, text="STARTUP", style="PanelSubtle.TLabel").pack(anchor="w")
        self.startup_var = tk.BooleanVar(value=bool(sp.startup_enabled()))
        make_check(root, P, "Start ScreenTuner automatically when I sign in",
                   self.startup_var, self._on_startup).pack(anchor="w", pady=(6, 2))
        self.startup_note = ttk.Label(root, text="", style="PanelSubtle.TLabel")
        self.startup_note.pack(anchor="w", padx=(22, 0))
        self._refresh_startup_note()

        ttk.Separator(root).pack(fill="x", pady=16)
        ttk.Label(root, text="BEHAVIOUR", style="PanelSubtle.TLabel").pack(anchor="w")
        s = self.cfg["settings"]
        self.opt_vars = {}
        for key, label in (
                ("restore_on_exit", "Put my display back the way it was when the app quits"),
                ("toggle_back", "Pressing an active profile's hotkey again returns to neutral"),
                ("reapply_on_display_change",
                 "Re-apply after a resolution change or monitor hotplug"),
                ("notify", "Show a tray notification on each switch"),
                ("pin_tray_icon",
                 "Pin the tray icon to the taskbar instead of the overflow menu")):
            v = tk.BooleanVar(value=bool(s.get(key, True)))
            self.opt_vars[key] = v
            make_check(root, P, label, v, self._mark_dirty).pack(anchor="w", pady=2)

        row = ttk.Frame(root, style="Panel.TFrame")
        row.pack(anchor="w", pady=(10, 0))
        ttk.Label(row, text="Vibrance step for the +/- hotkeys",
                  style="Panel.TLabel").pack(side="left", padx=(0, 10))
        self.step_var = tk.StringVar(value=str(s.get("vibrance_step", 5)))
        ttk.Spinbox(row, from_=1, to=25, width=5, textvariable=self.step_var,
                    command=self._mark_dirty).pack(side="left")

        ttk.Separator(root).pack(fill="x", pady=16)
        ttk.Label(root, text="GLOBAL HOTKEYS", style="PanelSubtle.TLabel").pack(anchor="w")
        grid = ttk.Frame(root, style="Panel.TFrame")
        grid.pack(anchor="w", pady=(8, 0))
        self.global_hk = {}
        for i, (key, label) in enumerate((
                ("neutral", "Back to driver defaults"),
                ("cycle", "Cycle to next profile"),
                ("vibrance_up", "Vibrance up"),
                ("vibrance_down", "Vibrance down"),
                ("reload", "Reload profiles.json"),
                ("quit", "Quit"))):
            ttk.Label(grid, text=label, style="Panel.TLabel", width=30).grid(
                row=i, column=0, sticky="w", pady=3)
            b = HotkeyButton(grid, P, self._mark_dirty, width=22)
            b.set(self.cfg.get("hotkeys", {}).get(key))
            b.grid(row=i, column=1, sticky="w", pady=3)
            self.global_hk[key] = b

    # ---- profile list ---------------------------------------------------

    def _refresh_profile_list(self):
        sel = self.listbox.curselection()
        self.listbox.delete(0, "end")
        for p in self.cfg["profiles"]:
            hk = p.get("hotkey")
            self.listbox.insert("end", f" {p.get('name', 'Untitled')}"
                                       + (f"   ({hk})" if hk else ""))
        if sel:
            self.listbox.selection_set(min(sel[0], self.listbox.size() - 1))

    def _select(self, idx):
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.current = idx
        self._load_profile()

    def _on_list_select(self, _=None):
        sel = self.listbox.curselection()
        if sel and sel[0] != self.current:
            self.current = sel[0]
            self.scope.set(ALL)
            self._load_profile()
            self._apply_preview()

    @property
    def profile(self):
        if self.current is None or not (0 <= self.current < len(self.cfg["profiles"])):
            return None
        return self.cfg["profiles"][self.current]

    # ---- loading / storing the edited scope ------------------------------

    def _scope_dict(self, create=False):
        """The dict the sliders currently edit: the profile itself, or a monitor entry."""
        p = self.profile
        if p is None:
            return None
        if self.scope.get() == ALL:
            return p
        mons = p.setdefault("monitors", {}) if create else p.get("monitors") or {}
        key = self.scope.get()
        if key not in mons and create:
            mons[key] = {}
        return mons.get(key)

    def _load_profile(self):
        p = self.profile
        if p is None:
            return
        self._loading = True
        self.name_var.set(p.get("name", ""))
        self.hotkey_btn.set(p.get("hotkey"))
        self._check_hotkey()

        is_all = self.scope.get() == ALL
        for w in self.mode_frame.winfo_children():
            w.configure(state="normal" if not is_all else "disabled")

        d = self._scope_dict()
        if is_all:
            self.mode.set("same")
        elif d is None:
            self.mode.set("same")
        elif d.get("skip"):
            self.mode.set("skip")
        else:
            self.mode.set("custom")

        src = p if is_all else (d if self.mode.get() == "custom" else p)
        vib, l1 = as_scalar(src.get("vibrance"), 50)
        gam, l2 = as_scalar(src.get("gamma"), 1.0)
        con, l3 = as_scalar(src.get("contrast"), 50)
        bri, l4 = as_scalar(src.get("brightness"), 50)
        self.vib_on.set(src.get("vibrance") is not None)
        self.ramp_on.set(any(src.get(k) is not None
                             for k in ("gamma", "contrast", "brightness")))
        self.s_vib.set(vib)
        self.s_gam.set(gam)
        self.s_con.set(con)
        self.s_bri.set(bri)
        self.channel_note.configure(text=(
            "This profile sets separate R/G/B values. The sliders show their average, "
            "and saving from here replaces them with one value per control."
            if any((l1, l2, l3, l4)) else ""))
        self._sync_enabled()
        self._refresh_curve()
        self._loading = False

    def _refresh_curve(self):
        if getattr(self, "curve", None) is None:
            return
        self.curve.render(self.s_gam.get(), self.s_con.get(), self.s_bri.get(),
                          enabled=self.ramp_on.get())
        self.vib_preview.render(self.s_vib.get(), enabled=self.vib_on.get())

    def _sync_enabled(self):
        editable = self.scope.get() == ALL or self.mode.get() == "custom"
        self.s_vib.set_enabled(editable and self.vib_on.get())
        for s in (self.s_gam, self.s_con, self.s_bri):
            s.set_enabled(editable and self.ramp_on.get())

    def _store(self):
        """Write the visible slider state back into the profile dict."""
        if self._loading:
            return
        p = self.profile
        if p is None:
            return
        is_all = self.scope.get() == ALL

        if not is_all:
            mons = p.setdefault("monitors", {})
            key = self.scope.get()
            if self.mode.get() == "same":
                mons.pop(key, None)
                if not mons:
                    p.pop("monitors", None)
                return
            if self.mode.get() == "skip":
                mons[key] = {"skip": True}
                return

        target = self._scope_dict(create=True)
        target.pop("skip", None)
        target["vibrance"] = self.s_vib.get() if self.vib_on.get() else None
        if self.ramp_on.get():
            target["gamma"] = self.s_gam.get()
            target["contrast"] = self.s_con.get()
            target["brightness"] = self.s_bri.get()
        else:
            for k in ("gamma", "contrast", "brightness"):
                target[k] = None
        for k in list(target):
            if target[k] is None:
                target.pop(k)

    # ---- events ---------------------------------------------------------

    def _mark_dirty(self, *_):
        self.dirty = True
        self.status.configure(text="unsaved changes")

    def _on_name(self):
        if self._loading or self.profile is None:
            return
        self.profile["name"] = self.name_var.get()
        self._refresh_profile_list()
        self._mark_dirty()

    def _on_hotkey(self):
        if self.profile is None:
            return
        self.profile["hotkey"] = self.hotkey_btn.value
        self._check_hotkey()
        self._refresh_profile_list()
        self._mark_dirty()

    def _check_hotkey(self):
        spec = self.hotkey_btn.value
        if not spec:
            self.hotkey_note.configure(text="")
            return
        parsed = sp.parse_hotkey(spec)
        if not parsed:
            self.hotkey_note.configure(text="not a valid combination",
                                       foreground=self.P["danger"])
            return
        clashes = [p["name"] for i, p in enumerate(self.cfg["profiles"])
                   if i != self.current and p.get("hotkey") == spec]
        clashes += [k for k, b in getattr(self, "global_hk", {}).items()
                    if b.value == spec]
        if clashes:
            self.hotkey_note.configure(text=f"also used by: {clashes[0]}",
                                       foreground=self.P["danger"])
        elif sp.altgr_conflicts([(spec, spec)]) and sp.layout_has_altgr():
            # Windows reports AltGr as Ctrl+Alt, so on these layouts a Ctrl+Alt
            # binding fires while the user is just typing.
            self.hotkey_note.configure(
                text="AltGr types this on your layout - prefer Ctrl+Shift",
                foreground=self.P["danger"])
        else:
            self.hotkey_note.configure(text="", foreground=self.P["subtle"])

    def _on_scope(self):
        self._load_profile()

    def _on_mode(self):
        self._store()
        self._load_profile()
        self._mark_dirty()
        self._apply_preview()

    def _on_toggle(self):
        self._sync_enabled()
        self._store()
        self._mark_dirty()
        self._refresh_curve()
        self._apply_preview()

    def _on_slider(self):
        self._store()
        self._mark_dirty()
        self._refresh_curve()
        self._apply_preview()

    def _on_startup(self):
        try:
            sp.set_startup(self.startup_var.get())
        except Exception as e:
            messagebox.showerror(sp.APP_NAME, f"Could not change startup:\n{e}")
            self.startup_var.set(bool(sp.startup_enabled()))
        self._refresh_startup_note()

    def _refresh_startup_note(self):
        cur = sp.startup_enabled()
        self.startup_note.configure(
            text=cur if cur else "Not currently registered to start at login.")

    # ---- preview --------------------------------------------------------

    def _apply_preview(self):
        if not self.preview.get() or self.profile is None:
            return
        try:
            plan = sp.resolve_profile(self.profile, self.monitors)
            sp.apply_plan(plan, self.nv, self.gamma)
        except Exception as e:
            self.status.configure(text=f"preview failed: {e}")

    def _restore_entry_state(self):
        self.nv.restore(self.entry_vibrance)
        for adapter, ramp in self.entry_ramps.items():
            if ramp is not None:
                self.gamma._write(adapter, ramp)

    # ---- list editing ---------------------------------------------------

    def _add(self):
        self.cfg["profiles"].append(
            {"name": "New profile", "hotkey": None, "vibrance": 50,
             "gamma": 1.0, "contrast": 50, "brightness": 50})
        self._refresh_profile_list()
        self._select(len(self.cfg["profiles"]) - 1)
        self._mark_dirty()

    def _duplicate(self):
        if self.profile is None:
            return
        copy = json.loads(json.dumps(self.profile))
        copy["name"] += " copy"
        copy["hotkey"] = None
        self.cfg["profiles"].insert(self.current + 1, copy)
        self._refresh_profile_list()
        self._select(self.current + 1)
        self._mark_dirty()

    def _delete(self):
        if self.profile is None:
            return
        if not messagebox.askyesno(sp.APP_NAME,
                                   f"Delete '{self.profile.get('name')}'?",
                                   parent=self):
            return
        del self.cfg["profiles"][self.current]
        self._refresh_profile_list()
        if self.cfg["profiles"]:
            self._select(min(self.current, len(self.cfg["profiles"]) - 1))
        else:
            self.current = None
        self._mark_dirty()

    def _move(self, delta):
        i = self.current
        j = i + delta
        if i is None or not (0 <= j < len(self.cfg["profiles"])):
            return
        ps = self.cfg["profiles"]
        ps[i], ps[j] = ps[j], ps[i]
        self._refresh_profile_list()
        self._select(j)
        self._mark_dirty()

    def _up(self):
        self._move(-1)

    def _down(self):
        self._move(1)

    # ---- save / close ---------------------------------------------------

    def _collect(self):
        s = self.cfg.setdefault("settings", {})
        for k, v in self.opt_vars.items():
            s[k] = bool(v.get())
        try:
            s["vibrance_step"] = max(1, min(25, int(self.step_var.get())))
        except ValueError:
            pass
        self.cfg["hotkeys"] = {k: b.value for k, b in self.global_hk.items() if b.value}

    def _save(self):
        self._store()
        self._collect()
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2)
        except Exception as e:
            messagebox.showerror(sp.APP_NAME, f"Could not save:\n{e}", parent=self)
            return
        self.dirty = False
        delivered = sp.signal_reload()
        self.status.configure(
            text="saved - tray app reloaded" if delivered else "saved")

    def _close(self):
        if self.dirty:
            answer = messagebox.askyesnocancel(
                sp.APP_NAME, "Save your changes before closing?", parent=self)
            if answer is None:
                return
            if answer:
                self._save()
        self._restore_entry_state()
        self.nv.unload()
        self.destroy()


def run(config_path, module=None):
    global sp
    if module is not None:
        sp = module
    else:
        import screentuner as _sp
        sp = _sp
    try:
        C.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            C.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    ConfigWindow(os.path.abspath(config_path)).mainloop()
    return 0
