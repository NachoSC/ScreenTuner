**ScreenTuner can now tell you when there is a new version, and install it for you.**

This is the last update you will have to install by hand. Versions before this one have no
way of knowing a release exists, so 1.0.x will not notify you about 1.1.0 — from here on
it will.

**How it works**

- Once a day, ScreenTuner asks GitHub whether there is a newer release.
- If there is, you get a tray notification. Click it, or the new **Update to x.y.z…**
  entry in the tray menu, and it asks whether to install.
- Say yes and it downloads the official installer, checks its SHA-256 against the digest
  GitHub reports for that exact file, runs it silently, and reopens. **Your profiles and
  settings are kept.**

Nothing interrupts you. No dialog ever appears on its own — this is an app you leave
running inside a game, so the notification is the only unprompted thing, and it goes away
by itself. Every dialog is reached from a click.

**Turning it off** — Settings → Options → *"Check GitHub for new versions"*, or
`"check_for_updates": false` in `profiles.json`. The check is an unauthenticated GET to
the public releases API: nothing about you or your machine is sent, and the app still has
no telemetry of any kind.

**A portable copy** cannot replace itself while it is running, so it opens the download
page instead.

**Also fixed**

- Running from a source checkout looked for `profiles.json` and `icon.ico` in the wrong
  place after the sources moved into `src/`. Installed and portable copies were never
  affected.

**Upgrading** — run the setup exe over your existing install, or
`winget upgrade NachoSC.ScreenTuner`. Settings and profiles are preserved.

**Note on SmartScreen** — the binary is not code-signed, so Windows will warn on first
run. Click *More info → Run anyway*. Verifying the download proves it arrived intact, not
that the release is trustworthy; that needs code signing, which is on the roadmap.

**Requires** Windows 10/11 64-bit. Vibrance needs an NVIDIA GPU; gamma, contrast and
brightness work on any GPU. AMD and Intel saturation is the next roadmap item — testers
welcome.

Full detail in [CHANGELOG.md](https://github.com/NachoSC/ScreenTuner/blob/main/CHANGELOG.md).
