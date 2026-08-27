# Releasing

## When to cut a release

Not every commit is a release. But **every release is a full one** — GitHub release,
installer, portable zip and patch notes. Shipping a "release" people cannot install
means nothing, and `winget upgrade` users would be stranded on it.

| Bump | When | Example |
| --- | --- | --- |
| **Patch** `1.0.x` | Bug fixes only. Nothing you had configured behaves differently | `--config` popping a stray console window |
| **Minor** `1.x.0` | New features. Existing `profiles.json` keeps working untouched | Per-app profiles; AMD support |
| **Major** `x.0.0` | Something you configured now behaves differently | Moving the default hotkeys off `Ctrl+Alt` |

"Breaking" here means breaking a *user's setup*, not an API: a default hotkey moving, a
`profiles.json` key being renamed, a profile resolving differently than before.

**Patch notes for every release, including patches.** A patch release is exactly when
someone asks "what changed, and does it fix my problem?" The CHANGELOG entry is cheap;
a confused user filing a duplicate issue is not.

**One exception, for winget only.** Each winget submission is a PR into
`microsoft/winget-pkgs` with review latency, so batching several trivial patches into one
manifest update is reasonable. Publish the GitHub release immediately regardless — winget
lagging by a patch is fine, users having no download is not.

If a release fixes something that makes the app misbehave for a whole class of user — the
AltGr clash did, for every non-US keyboard layout — ship it as its own release
immediately rather than holding it for company.

Steps that need your GitHub credentials, in order. `gh` is installed; authenticate once
with `gh auth login` (browser flow) and the rest are one-liners.

## 1. Rename the repository (once)

The repo was created as `ScreenTuner.exe`. Every URL in this project assumes
`ScreenTuner`, so rename it before the first push:

```powershell
gh repo rename ScreenTuner --repo NachoSC/ScreenTuner.exe
```

Or on the web: **Settings → General → Repository name**.

## 2. First push

```powershell
git remote add origin https://github.com/NachoSC/ScreenTuner.git
git push -u origin main
```

Then set the About text and topics (see README's description section).

## 3. Cut a release

```powershell
.\build-installer.bat                 # always rebuild: it also rebuilds the app
git tag v1.0.0
git push origin v1.0.0
gh release create v1.0.0 `
    "dist\installer\ScreenTuner-1.0.0-setup.exe" `
    "dist\installer\ScreenTuner-1.0.0-portable.zip" `
    --title "ScreenTuner 1.0.0" --notes-file RELEASE-NOTES.md
```

## 4. Refresh the winget hash, then submit

The manifest pins the installer's SHA256, so **rebuilding invalidates it**. Recompute
against the exact file you uploaded:

```powershell
(Get-FileHash .\dist\installer\ScreenTuner-1.0.0-setup.exe -Algorithm SHA256).Hash
```

Paste it into `winget\1.0.0\NachoSC.ScreenTuner.installer.yaml`, then:

```powershell
winget validate --manifest .\winget\1.0.0
winget install --manifest .\winget\1.0.0     # test it locally first
```

Then open a PR to [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) with
the three files under `manifests/n/NachoSC/ScreenTuner/1.0.0/`.

## Version bumps

`VERSION` in `src/screentuner.py` is the single source of truth. Everything else derives
from it or is updated by the tool - never edit versions by hand.

```powershell
python toolsersion.py                 # what is the current version
python toolsersion.py --check         # verify every file agrees
python toolsersion.py --set 1.1.0     # bump everywhere, add a CHANGELOG stub
python toolsersion.py --tag           # annotated git tag, refuses if inconsistent
```

`--set` updates `src/screentuner.py`, all three winget manifests, the `winget\<version>\`
folder name, the release URLs inside those manifests, and adds a CHANGELOG heading. The
installer reads the version at compile time via `/DAppVersion`, so there is nothing to
change in the `.iss`.

`build-installer.bat` runs `--check` first and refuses to build if anything disagrees.
