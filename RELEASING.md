# Releasing

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

`VERSION` in `screentuner.py` is the single source of truth. Everything else derives
from it or is updated by the tool - never edit versions by hand.

```powershell
python toolsersion.py                 # what is the current version
python toolsersion.py --check         # verify every file agrees
python toolsersion.py --set 1.1.0     # bump everywhere, add a CHANGELOG stub
python toolsersion.py --tag           # annotated git tag, refuses if inconsistent
```

`--set` updates `screentuner.py`, all three winget manifests, the `winget\<version>\`
folder name, the release URLs inside those manifests, and adds a CHANGELOG heading. The
installer reads the version at compile time via `/DAppVersion`, so there is nothing to
change in the `.iss`.

`build-installer.bat` runs `--check` first and refuses to build if anything disagrees.
