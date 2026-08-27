@echo off
rem Builds dist\ScreenTuner\ScreenTuner.exe
rem --onedir, not --onefile: onefile unpacks ~25 MB into %TEMP% on every launch,
rem which costs half a second of startup, trips antivirus heuristics, and leaves
rem the folder behind whenever the process is killed rather than closed.
setlocal
cd /d "%~dp0"

if not exist ".build\venv\Scripts\python.exe" (
  echo Creating build environment...
  python -m venv ".build\venv" || goto :fail
  ".build\venv\Scripts\python.exe" -m pip install --upgrade pip --quiet || goto :fail
  ".build\venv\Scripts\python.exe" -m pip install pyinstaller --quiet || goto :fail
)

echo Generating icon...
python make_icon.py || goto :fail

echo Building...
".build\venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean ^
  --onedir --windowed ^
  --name ScreenTuner ^
  --icon "%~dp0icon.ico" ^
  --add-data "%~dp0icon.ico;." ^
  --hidden-import configui ^
  --distpath dist --workpath ".build\work" --specpath ".build" ^
  screentuner.py || goto :fail

echo.
echo Done: %~dp0dist\ScreenTuner\ScreenTuner.exe
echo Run it with --install to put it in %%LOCALAPPDATA%%\Programs\ScreenTuner.
goto :eof

:fail
echo.
echo BUILD FAILED
exit /b 1
