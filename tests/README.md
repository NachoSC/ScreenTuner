# Tests

Two layers, split by one question: **can someone other than the author run this?**

| | `unit/` | `system/` |
| --- | --- | --- |
| Needs an NVIDIA GPU | no | yes, for the vibrance parts |
| Needs a build in `dist/` | no | five of them do |
| Touches your display | no | yes |
| Runtime | under a second | a few minutes |
| Safe on a work machine | yes | it installs and uninstalls software |

Both layers need **Windows** — the app is `ctypes` against Win32, so even the pure
functions live in a module that loads `user32` on import. Nothing else is required:
no pip install, no test framework, no configuration. `unit/` uses `unittest` from the
standard library because the app itself has zero dependencies and the tests should not
be the thing that breaks that.

## Running them

```bat
tests\run.bat unit      :: pure logic, safe anywhere
tests\run.bat system    :: real hardware, asks first
tests\run.bat           :: both
tests\run.bat -y        :: both, no prompt
```

Anything non-zero from `run.bat` means something failed. You can also run any single
file directly — `python tests\unit\test_ramp.py -v`.

## `unit/` — logic, on fabricated hardware

`fakes.py` provides stand-in monitors, so a four-screen mixed-vendor desk and a
single-panel laptop are both testable from one machine. They borrow the real
`Monitor.matches`, so what is being tested is the shipping logic, not a copy of it.

- **`test_ramp.py`** — `build_ramp`, the 256-entry lookup table that reaches the driver.
  The highest-traffic pure function in the app, and the settings window's curve graph is
  drawn from the same call, so a change here desynchronises the picture from the pixels.
  Checks neutral is genuinely a no-op, that the curve never decreases, that each knob
  moves the image the direction its label claims, and that hand-edited nonsense clamps
  rather than producing garbage.
- **`test_privacy.py`** — `_scrub` and the `--diagnostics` report. The only function here
  whose failure hurts a *user* rather than annoying them: it fails by putting someone's
  real name into a public issue thread, where it cannot be taken back.
- **`test_hotkeys.py`** — `parse_hotkey` and the AltGr conflict check. Windows implements
  AltGr as Ctrl+Alt, so on most non-US layouts a Ctrl+Alt binding fires while you type.
  Includes a check that the shipped defaults are all clear of it.
- **`test_profiles.py`** — monitor matching and profile expansion, including profiles
  that name hardware the machine does not have, which is what happens whenever people
  share settings.
- **`test_updater.py`** — update checking, with the network injected. Pins what the
  updater *refuses*: drafts and pre-releases, a download URL outside this repo, a
  missing or malformed digest, and a file whose hash does not match (which must be
  deleted rather than left somewhere it could later be run). This is the only code
  in the app that downloads and executes something, so those rules are asserted
  rather than assumed.
- **`test_config.py`** — reading `profiles.json`, filling in keys added by later
  versions, and refusing to quietly overwrite a corrupt file.

## `system/` — the parts only real hardware can answer

These apply settings, read them back **from the driver**, and restore. They are the
reason the app works; they just cannot run anywhere but a real desktop.

| File | What it proves |
| --- | --- |
| `test_portability.py` | Degrades cleanly with no NVIDIA driver present; discovery is runtime, not baked in |
| `test_menu.py` | The tray menu tree, including the overflow submenu, without displaying it |
| `test_gui_logic.py` | The settings window's model, driven without a human clicking |
| `test_permonitor.py` | Per-monitor overrides reach the right screen and restore exactly |
| `test_exe.py` | The built exe registers hotkeys and responds to them |
| `test_enforce.py` | The watchdog takes the gamma ramp back after a fullscreen game steals it |
| `test_click.py` | Left-click opens Settings, right-click opens the menu |
| `test_altgr.py` | Real Ctrl+Alt fires; AltGr does not |
| `test_install.py` | `--install` then `--uninstall` leaves no files or registry entries |
| `test_wizard.py` | The same, through the Inno installer, silently |

They are unavoidably order-dependent and share the display, so `run.bat` runs them in
sequence — cheapest first, the two that install software last.

### They put your install back

`test_install.py` and `test_wizard.py` drive the **real** per-user install — the actual
`%LOCALAPPDATA%\Programs\ScreenTuner`, Run key and uninstall entry — because a copy
installed somewhere else would not prove the thing under test works. They finish by
uninstalling, which once removed the app from the developer's own machine with no
explanation: it simply vanished, and took a diagnosis to trace back to a test run.

So both bracket themselves with `_install_state.py`. It records whether an install was
present, how it got there, its `profiles.json` and the run-at-login value, and puts all of
it back afterwards — reinstalling through the wizard if that is how it was installed, so
the uninstaller does not silently disappear. This runs whether the test passed, failed or
raised, and a failed restore is itself a test failure.

If `dist\` is empty there is nothing to reinstall from, so the tests say so loudly rather
than leaving you to find out later.

## If you are contributing without an NVIDIA card

Run `tests\run.bat unit`. It covers profile resolution, hotkey parsing, config handling
and the gamma maths — which is most of what a change is likely to break — and it does not
care what GPU you have. Say in the PR that the system layer was not run; that is expected,
not a problem.
