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

## Commit messages

This repo uses [Conventional Commits](https://www.conventionalcommits.org). The point is
not tidiness for its own sake: the type is what decides the next version number, and the
subject lines are what the release notes get written from.

```
<type>(<scope>): <subject>

<body - why, not what>

<footers>
```

**Type**, and what it means for the version:

| Type | Meaning | Version effect |
| --- | --- | --- |
| `feat` | A new capability a user can notice | minor - `1.x.0` |
| `fix` | A bug fix | patch - `1.0.x` |
| `perf` | Faster or lighter, same behaviour | patch |
| `refactor` | Restructuring with no behaviour change | none |
| `test` | Tests only | none |
| `docs` | Documentation only | none |
| `build` | Build scripts, installer, packaging | none, unless users must reinstall |
| `chore` | Everything else - version bumps, housekeeping | none |

Breaking changes take a `!` before the colon **and** a `BREAKING CHANGE:` footer
explaining what a user has to do:

```
feat(hotkeys)!: move the defaults off Ctrl+Alt

BREAKING CHANGE: existing profiles.json files keep their own bindings, but the
shipped defaults change, so a fresh install behaves differently from an upgrade.
```

Remember that "breaking" here means breaking *someone's setup* - a default hotkey moving,
a `profiles.json` key being renamed - not an API change. See [RELEASING.md](RELEASING.md).

**Scope** is optional but appreciated. The ones in use: `nvapi`, `gamma`, `hotkeys`,
`tray`, `settings`, `installer`, `winget`, `tests`, `docs`.

**Subject**: imperative mood ("add", not "added" or "adds"), lower case, no full stop,
under about 72 characters. It should complete the sentence *"this commit will…"*.

**Body**: the *why*. The diff already shows the what. If a Windows quirk forced the
approach, this is where it gets recorded - that is how the awkward parts of this codebase
stay explicable a year later.

Real examples from this repo:

```
fix(hotkeys): reject a hotkey that is only whitespace

" " stripped to "", split into one empty part, and hit the branch meaning a
literal '+' between separators - so it registered an unmodified global '+'
hotkey and typing + anywhere switched profiles.

test(unit): add a mutation-tested unit layer under tests/unit
docs(readme): explain why the build is --onedir
build(installer): pass the version through from screentuner.py
```

One logical change per commit. If the subject needs an "and", it is probably two commits.

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
tests
un.bat unit      :: pure logic - no GPU, no build, about a second
tests
un.bat system    :: real hardware, asks before it starts
```

The split is by what a machine can answer, not by test size: `tests/unit/` runs anywhere
Windows runs, `tests/system/` needs a real display and, for vibrance, an NVIDIA card.
See [tests/README.md](tests/README.md).

**Please run `tests
un.bat unit` before submitting** - it is fast and it covers profile
resolution, hotkey parsing, config handling and the gamma maths.

If you have no NVIDIA card, that is the whole of what you can run, and that is fine. Say
so in the PR rather than skipping quietly. There is no CI yet; several system tests take
over the display and send keystrokes, so they will never run on a hosted runner, but the
unit layer could and should.

## Reporting bugs

Include your Windows version, GPU, whether the affected monitor has HDR on, and the
contents of `screentuner.log` (next to the exe). For display issues, `--list` output is
almost always the fastest way to see what's going on.
