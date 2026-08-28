# Roadmap

No dates. Roughly in the order they'd be worth doing.

---

## 1. AMD and Intel saturation

**Status: planned. The biggest gap.**

Digital vibrance is NVIDIA-only today because it goes through NVAPI. Gamma, contrast and
brightness already work everywhere, since those use the GDI gamma ramp rather than a
vendor API.

Both other vendors expose an equivalent:

- **AMD** — the saturation slider in Radeon Software, via the AMD Display Library:
  `ADL_Display_Color_Set` with `ADL_DL_COLOR_SATURATION`, or the newer ADLX. This is
  well documented and the closest analogue to NVAPI's DVC.
- **Intel** — the Intel Graphics Control Library (IGCL) exposes colour controls, and
  Intel Graphics Command Center has a saturation slider, so the capability is there. The
  exact entry point still needs confirming against the SDK rather than assumed.

**Why it matters more than it looks:** on hybrid-graphics laptops the built-in panel is
usually wired to the integrated GPU, so NVAPI never enumerates it — the machine has an
NVIDIA chip and still cannot set vibrance on its own screen. APU desktops have the same
problem. Supporting the iGPU vendors fixes a class of machine, not just a brand.

**Shape of the work.** The app already degrades cleanly when NVAPI is absent, and
`NvApi.ok` is checked at every call site. The natural design is a small backend interface
— `available`, `range`, `get(monitor)`, `set(monitor, level)` — with NVAPI, ADL and IGCL
implementations, selected per monitor rather than per machine, since a mixed-GPU system
drives different screens from different adapters. `discover_monitors()` already records
which GPU drives each display, so the routing information exists.

**Blocker:** no AMD or Intel hardware to develop or test against. If you have either and
want to help, please open an issue — even just running `--diagnostics` and pasting the
output is useful groundwork.

---

## 2. Profiles that follow the running program

**Status: planned. Probably the most useful feature not yet built.**

Bind a profile to an executable, so launching the game applies it and quitting restores
what you had:

```jsonc
{
  "name": "Tarkov",
  "hotkey": "ctrl+shift+2",
  "vibrance": 75,
  "launch_with": ["EscapeFromTarkov.exe"]
}
```

Hotkeys keep working exactly as now — this adds a trigger, it does not replace one.

**Which profile wins when several match.** Follow the **foreground window**, not merely
what is running: a browser is always open, and two games could be running at once. The
profile whose executable owns the focused window wins; when focus moves to something
unmatched, revert to whatever was active before. That also handles alt-tabbing out of a
game and back.

**Most of the plumbing already exists.** The watchdog installs a
`SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` to reapply the profile after alt-tab, which is
exactly the signal this needs — the hook is already there, it just needs to carry
`GetWindowThreadProcessId` → executable name and consult a lookup table. No polling, no
injection, and nothing an anti-cheat would object to.

**Details worth getting right:**

- Precedence when a hotkey and a program rule disagree: an explicit hotkey press should
  win until focus changes, or switching manually inside a game would be undone within two
  seconds by the watchdog.
- Match on the executable name, not the window title, which is unstable and localised.
- Restore to the *previous* profile on exit, rather than to neutral.
- The settings window needs a way to pick the executable — ideally a list of currently
  running processes to choose from, rather than making people type a filename.

---

## 3. Code signing

**Status: wanted, cost is the obstacle.**

The binary is unsigned, so every user meets SmartScreen's *"Windows protected your PC"* on
first run. It is the single biggest friction in the install, and no packaging change fixes
it — a wizard makes it marginally worse, since unsigned installers draw more scrutiny than
plain executables.

An OV certificate runs a few hundred dollars a year and, since 2023, requires a hardware
token or cloud HSM. That is hard to justify for a free, donation-funded tool, but it is
what the donations would be for first.

---

## 4. Smaller things

- **Import/export profiles**, so people can share tuned settings for particular games.
- **Per-profile HDR awareness** — currently gamma silently has no effect on an HDR
  monitor. The app can detect this and say so rather than leaving people puzzled.
- **CI for the unit layer.** `tests/unit/` needs nothing but Windows and a Python, so it
  could run on every push against a hosted runner. `tests/system/` never will - it takes
  over the display and sends keystrokes - so the interesting question is how much more of
  the app can be pulled into the layer a machine can check unattended.
- **Nuitka build**, as an alternative to PyInstaller: smaller, faster to start, and fewer
  antivirus false positives. Worth measuring before committing to it.

---

## Not planned

- **Anything that injects into games.** The app calls display APIs and nothing else. That
  is precisely why anti-cheat has no reason to care about it, and it stays that way.
- **Per-application colour on non-focused windows.** Vibrance and gamma are display-wide
  in the hardware. Making one window look different is a compositor problem, not this
  app's.
- **Telemetry.** No.
