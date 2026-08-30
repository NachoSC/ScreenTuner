# Changelog

Notable changes per release. Format follows [Keep a Changelog](https://keepachangelog.com),
versioning follows [Semantic Versioning](https://semver.org).

Since this is an end-user application rather than a library, "breaking" means something
that changes behaviour you had configured — a default hotkey moving, a `profiles.json`
key being renamed — not an API change.

<!-- next -->

## Unreleased

### Added

- **Update notifications.** ScreenTuner checks GitHub once a day for a newer release and
  shows a tray notification when it finds one. Clicking it, or the new tray menu entry,
  offers to install it: the official installer is downloaded, its SHA-256 verified
  against the digest GitHub reports, then run silently, and the app reopens with your
  profiles intact. Portable copies are pointed at the download page instead, since they
  cannot replace themselves while running.
- `check_for_updates` setting, on by default, with a checkbox in Settings — Options.
  The check is an unauthenticated GET to the public releases API and sends nothing about
  you or your machine.

### Fixed

- Running from source used `src/profiles.json` and could not find `icon.ico`, because
  moving the sources into `src/` also moved what the app treated as its base directory.
  Both live in the repo root, which is where a source run now looks again. Installed and
  portable copies were never affected.

- The install and wizard system tests uninstalled ScreenTuner and never put it back, so
  running the suite removed the app from the machine it was run on. Both now snapshot the
  existing install — files, `profiles.json` and run-at-login — and restore it
  afterwards, reinstalling through the wizard if that is how it was installed. Affects
  contributors running the tests, not users.

## 1.0.1 - 2026-08-28

A bug fix and the test suite. Nothing you have configured changes.

### Fixed

- A hotkey consisting only of whitespace, such as `"hotkey": " "` in a hand-edited
  `profiles.json`, was parsed as the `+` key and registered globally - so pressing `+`
  anywhere switched profiles. It is now rejected like any other empty value.

### Added

- A test suite under `tests/`, split by what a machine can answer rather than by test
  size. `tests/unit/` needs nothing but Windows - no GPU, no build, no install - and
  covers the gamma ramp maths, hotkey parsing, monitor matching, profile resolution,
  config loading, and the privacy scrubbing on `--diagnostics`. `tests/system/` holds the
  hardware tests, which need real displays and, for vibrance, an NVIDIA card.
- `tests\run.bat` runs either layer, or both.

### Changed

- Contributors are asked to use [Conventional Commits](https://www.conventionalcommits.org),
  since the commit type is what decides the next version number.

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
