A small bug fix, plus a test suite. **Nothing you have configured changes** — upgrading is
safe, and your `profiles.json` is untouched.

**Fixed**

- A hotkey consisting only of whitespace — `"hotkey": " "` in a hand-edited
  `profiles.json` — was parsed as the `+` key and registered globally, so pressing `+`
  anywhere switched profiles. It is now rejected like any other empty value.

**Added, for contributors**

- A test suite under `tests/`, split by what a machine can answer rather than by test
  size. `tests/unit/` needs nothing but Windows — no GPU, no build, no install — and
  covers the gamma ramp maths, hotkey parsing, monitor matching, profile resolution,
  config loading, and the privacy scrubbing on `--diagnostics`. `tests/system/` holds the
  hardware tests that need real displays and, for vibrance, an NVIDIA card.
- This matters for the AMD and Intel work on the roadmap: someone without an NVIDIA card
  can now run `tests\run.bat unit` and check they have not broken anything, which was
  previously impossible.

**Upgrading** — run the new setup exe over your existing install, or
`winget upgrade NachoSC.ScreenTuner`. Settings and profiles are preserved.

**Note on SmartScreen** — the binary is not code-signed, so Windows will warn on first
run. Click *More info → Run anyway*. The source is here and `build.bat` reproduces it.

**Requires** Windows 10/11 64-bit. Vibrance needs an NVIDIA GPU; gamma, contrast and
brightness work on any GPU. AMD saturation via ADL is on the roadmap — testers welcome.

Full detail in [CHANGELOG.md](https://github.com/NachoSC/ScreenTuner/blob/main/CHANGELOG.md).
