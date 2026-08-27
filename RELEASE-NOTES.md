First public release.

**What it does** — digital vibrance, gamma, contrast and brightness as named profiles you
switch with a hotkey, without leaving a game. Vibrance goes through NVIDIA's NVAPI; gamma,
contrast and brightness go through the GDI gamma ramp and work on any GPU.

**Highlights**

- Per-monitor overrides inside a single profile, matched by vendor, position, index or
  EDID rather than the adapter names Windows renumbers
- Settings window with live preview, a real transfer-curve graph drawn from the lookup
  table that actually reaches the driver, and a vibrance colour preview
- A watchdog that reapplies your profile when a fullscreen game takes the gamma ramp, or
  the driver resets vibrance on a display-mode switch
- Defaults are `Ctrl+Shift+…`: Windows reports AltGr as Ctrl+Alt, so `Ctrl+Alt` bindings
  fire while typing on Spanish, German and most non-US layouts. If you do bind Ctrl+Alt,
  AltGr presses are detected and ignored
- Per-user install, no admin prompt. `--uninstall` removes every registry entry it made

**Install** — run the setup exe, or `winget install NachoSC.ScreenTuner`, or unzip the
portable build anywhere.

**Note on SmartScreen** — the binary is not code-signed, so Windows will warn on first
run. Click *More info → Run anyway*. The source is here and `build.bat` reproduces it.

**Requires** Windows 10/11 64-bit. Vibrance needs an NVIDIA GPU; everything else works on
AMD and Intel. AMD saturation via ADL is on the roadmap — testers welcome.
