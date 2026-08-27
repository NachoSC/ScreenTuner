@echo off
rem Builds the installer and the portable zip into dist\installer\.
rem The version comes from screentuner.py via tools\version.py - never hardcode it.
rem Requires Inno Setup 6:  winget install JRSoftware.InnoSetup
setlocal
cd /d "%~dp0"

for /f %%v in ('python tools\version.py') do set "VER=%%v"
if not defined VER (
  echo Could not read the version from src\screentuner.py
  exit /b 1
)
echo Version %VER%

python tools\version.py --check >nul || (
  echo.
  echo Version numbers disagree across the repo:
  python tools\version.py --check
  exit /b 1
)

set "ISCC="
for %%P in (
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do if exist %%P set "ISCC=%%~P"

if not defined ISCC (
  echo Inno Setup 6 not found. Install it with:
  echo   winget install --id JRSoftware.InnoSetup
  exit /b 1
)

rem Always rebuild the app first. Reusing whatever happens to be in dist\ is how
rem you ship an installer wrapping last week's binary.
echo Building the app...
call "%~dp0build.bat" || exit /b 1

echo Compiling installer...
"%ISCC%" /Q "/DAppVersion=%VER%" "installer\ScreenTuner.iss" || exit /b 1

echo Packing the portable zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\ScreenTuner\*' -DestinationPath 'dist\installer\ScreenTuner-%VER%-portable.zip' -Force" || exit /b 1

echo.
for %%F in ("dist\installer\*") do echo Done: %%~fF  (%%~zF bytes)
