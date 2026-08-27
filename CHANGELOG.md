# Changelog

Notable changes per release. Format follows [Keep a Changelog](https://keepachangelog.com),
versioning follows [Semantic Versioning](https://semver.org).

Since this is an end-user application rather than a library, "breaking" means something
that changes behaviour you had configured — a default hotkey moving, a `profiles.json`
key being renamed — not an API change.

<!-- next -->


## 1.0.0 - 2026-08-28

First public release.

### Added

- Digital vibrance through NVIDIA's NVAPI, plus gamma, contrast and brightness through
  the GDI gamma ramp, which works on any GPU
- Named profiles switched by global hotkeys; pressing an active profile's hotkey again
  returns to neutral
- Per-monitor overrides within a single profile, matched by vendor, position, index or
  EDID rather than the `\\.\DISPLAYn` adapter names Windows renumbers over time
- Settings window: live preview while dragging, hotkey capture with conflict warnings,
  a transfer-curve graph drawn from the lookup table that actually reaches the driver,
  and a vibrance colour preview
- Watchdog that reapplies the active profile when a fullscreen game takes the gamma ramp
  or the driver resets vibrance on a display-mode switch
- Tray menu with profile list, vibrance nudges, run-at-login and tray-pin toggles, and a
  "Copy diagnostics for a bug report" item
- `--diagnostics`: a report for issue threads containing hardware and settings but no
  username, home path, machine name, or profile contents
- `--install` / `--uninstall`, an Inno Setup wizard, and winget manifests — all sharing
  one implementation so they cannot drift
- Restores the display on exit, including per-monitor differences

### Notes

- Defaults are `Ctrl+Shift+…` rather than `Ctrl+Alt+…`. Windows implements AltGr as
  Ctrl+Alt, so on Spanish, German and most non-US layouts a `Ctrl+Alt` binding fires
  while you are simply typing — `AltGr+2` types `@` on a Spanish layout. If you bind
  `Ctrl+Alt` anyway, AltGr presses are detected and ignored.
- Built with PyInstaller `--onedir`. `--onefile` unpacked 25 MB into `%TEMP%` on every
  launch, cost ~0.5 s of startup, tripped antivirus heuristics, and leaked the folder
  whenever the process was killed rather than closed.
- The binary is not code-signed, so SmartScreen warns on first run.
