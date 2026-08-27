@echo off
rem One-shot first publish. Requires: gh auth login  (browser sign-in, interactive).
rem Everything here is idempotent enough to re-run if a step fails partway.
setlocal
cd /d "%~dp0.."

gh auth status >nul 2>&1 || (
  echo Not authenticated. Run:  gh auth login
  exit /b 1
)

python tools\version.py --check || exit /b 1
for /f %%v in ('python tools\version.py') do set "VER=%%v"

echo == renaming ScreenTuner.exe to ScreenTuner ==
gh repo rename ScreenTuner --repo NachoSC/ScreenTuner.exe --yes 2>nul || echo    (already renamed, continuing)

echo == pushing main ==
git remote get-url origin >nul 2>&1 || git remote add origin https://github.com/NachoSC/ScreenTuner.git
git push -u origin main || exit /b 1

echo == pushing tag v%VER% ==
git push origin "v%VER%" || exit /b 1

echo == creating the release ==
gh release create "v%VER%" ^
  "dist\installer\ScreenTuner-%VER%-setup.exe" ^
  "dist\installer\ScreenTuner-%VER%-portable.zip" ^
  --title "ScreenTuner %VER%" --notes-file RELEASE-NOTES.md || exit /b 1

echo == setting the description and topics ==
gh repo edit NachoSC/ScreenTuner ^
  --description "Hotkey-switchable display profiles for Windows: NVIDIA digital vibrance, plus gamma, contrast and brightness on any GPU. Per-monitor, with live preview." ^
  --add-topic windows --add-topic nvidia --add-topic digital-vibrance --add-topic vibrance ^
  --add-topic gamma --add-topic color-management --add-topic monitor --add-topic gaming ^
  --add-topic tray-application --add-topic nvapi --add-topic python --add-topic ctypes

echo.
echo Done: https://github.com/NachoSC/ScreenTuner
