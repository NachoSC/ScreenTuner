# Contributing to ScreenTuner

Pull requests are welcome. Bug reports and ideas are just as useful — open an issue.

## Before you start on something big

Open an issue first if the change is more than a fix. Saves you building something
that turns out not to fit.

## Contributor terms — please read

ScreenTuner is released under the [PolyForm Noncommercial License](LICENSE.md): free for
everyone to use noncommercially, with commercial rights reserved to the maintainer. For
that to hold together, contributions have to come in on terms that let the maintainer
keep offering the project under those terms — and change them later if needed.

**By opening a pull request you confirm that:**

1. The contribution is your own work, and you have the right to submit it.
2. You grant the maintainer a perpetual, worldwide, irrevocable, royalty-free licence to
   use, reproduce, modify, distribute and **sublicense or relicense** your contribution,
   including as part of a commercially licensed version of ScreenTuner.
3. You keep your own copyright. This is a licence, not an assignment — you can still do
   whatever you like with your own code elsewhere.

This is the same arrangement most source-available projects use. Without it, a single
merged PR would permanently block the project from ever being relicensed, because every
past contributor would have to be tracked down and asked.

If you would rather not grant that, please open an issue describing the change instead of
a PR, and it can be implemented independently.

## Getting set up

No dependencies beyond Python 3.10+ on Windows. The app is pure `ctypes`.

```
git clone https://github.com/NachoSC/ScreenTuner
cd ScreenTuner
python src\screentuner.py            # run from source, tray icon appears
python src\screentuner.py --list     # monitors, current vibrance, resolved profiles
python src\screentuner.py --gui      # settings window
```

To build the exe and the installer:

```
build.bat              -> dist\ScreenTuner\ScreenTuner.exe   (needs Python)
build-installer.bat    -> dist\installer\ScreenTuner-x.y.z-setup.exe  (needs Inno Setup 6)
```

## House style

The code is plain `ctypes` against Win32 and NVAPI, no wrappers. A few conventions that
are worth keeping:

- **Set `restype` and `argtypes` on every Win32 function you call.** ctypes defaults
  `restype` to C `int`, which silently truncates 64-bit handles. Several bugs in this
  project's history were exactly that.
- **Comment the *why*, not the *what*.** Especially for the Windows quirks — future you
  will not remember why the cleanup runs from a `.bat` in `%TEMP%`.
- **Test against the driver, not against your own code.** Apply a setting, read it back
  from the hardware, then restore. The existing tests all work that way.
- Keep it dependency-free. The zero-install story is a feature.

## Tests

```bat
testsun.bat unit      :: pure logic - no GPU, no build, about a second
testsun.bat system    :: real hardware, asks before it starts
```

The split is by what a machine can answer, not by test size: `tests/unit/` runs anywhere
Windows runs, `tests/system/` needs a real display and, for vibrance, an NVIDIA card.
See [tests/README.md](tests/README.md).

**Please run `testsun.bat unit` before submitting** - it is fast and it covers profile
resolution, hotkey parsing, config handling and the gamma maths.

If you have no NVIDIA card, that is the whole of what you can run, and that is fine. Say
so in the PR rather than skipping quietly. There is no CI yet; several system tests take
over the display and send keystrokes, so they will never run on a hosted runner, but the
unit layer could and should.

## Reporting bugs

Include your Windows version, GPU, whether the affected monitor has HDR on, and the
contents of `screentuner.log` (next to the exe). For display issues, `--list` output is
almost always the fastest way to see what's going on.
