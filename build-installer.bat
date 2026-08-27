@echo off
rem Builds dist\installer\ScreenTuner-<version>-setup.exe
rem Requires Inno Setup 6:  winget install JRSoftware.InnoSetup
setlocal
cd /d "%~dp0"

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

echo Compiling installer with "%ISCC%"
"%ISCC%" /Q "installer\ScreenTuner.iss" || exit /b 1

echo Packing the portable zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\ScreenTuner\*' -DestinationPath 'dist\installer\ScreenTuner-1.0.0-portable.zip' -Force" || exit /b 1

echo.
for %%F in ("dist\installer\*") do echo Done: %%~fF  (%%~zF bytes)
