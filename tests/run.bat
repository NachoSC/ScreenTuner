@echo off
REM ---------------------------------------------------------------------------
REM  ScreenTuner test runner.
REM
REM    run.bat unit      pure logic - safe anywhere, no GPU, no build, ~1 second
REM    run.bat system    drives real hardware - see the warning below
REM    run.bat           unit, then system
REM
REM  Add  -y  to skip the confirmation prompt before the system tests.
REM ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
pushd "%~dp0.."

set MODE=%~1
if "%MODE%"=="" set MODE=all
if "%MODE%"=="-y" set MODE=all
set YES=
if /i "%~1"=="-y" set YES=1
if /i "%~2"=="-y" set YES=1

set FAILED=

if /i "%MODE%"=="system" goto :system

REM --------------------------------------------------------------------- unit
echo.
echo === unit ===================================================
python -m unittest discover -s tests\unit -t tests\unit -v
if errorlevel 1 set FAILED=!FAILED! unit

if /i "%MODE%"=="unit" goto :done

REM ------------------------------------------------------------------- system
:system
echo.
echo === system =================================================
echo.
echo These drive the real display and the real desktop. They will:
echo   - change your gamma, contrast and vibrance, briefly
echo   - move the mouse pointer and send keystrokes
echo   - uninstall ScreenTuner, then put your install back afterwards
echo     ^(files, profiles.json and run-at-login are restored^)
echo.
echo Close anything you would rather not have typed into first.
echo Your own profiles.json is not touched.
echo.
if not defined YES (
    choice /c yn /m "Run the system tests"
    if errorlevel 2 goto :done
)

if not exist "dist\ScreenTuner\ScreenTuner.exe" (
    echo.
    echo   No build in dist\ - skipping the tests that need one.
    echo   Run build.bat first, or build-installer.bat for the wizard test.
    echo.
    call :run tests\system\test_portability.py
    call :run tests\system\test_menu.py
    call :run tests\system\test_gui_logic.py
    call :run tests\system\test_permonitor.py
    call :run tests\system\test_click.py
    call :run tests\system\test_update.py
    goto :done
)

REM Cheapest and least disruptive first; the two that install software last.
call :run tests\system\test_portability.py
call :run tests\system\test_menu.py
call :run tests\system\test_gui_logic.py
call :run tests\system\test_permonitor.py
call :run tests\system\test_update.py
call :run tests\system\test_exe.py
call :run tests\system\test_enforce.py
call :run tests\system\test_click.py
call :run tests\system\test_altgr.py
call :run tests\system\test_install.py
if exist "dist\installer\*setup.exe" (
    call :run tests\system\test_wizard.py
) else (
    echo   -- skipped test_wizard.py, no installer in dist\installer\
)

:done
echo.
echo ============================================================
if defined FAILED (
    echo   FAILED:!FAILED!
    popd
    endlocal
    exit /b 1
)
echo   all passed
popd
endlocal
exit /b 0

:run
echo.
echo --- %~1
python "%~1"
if errorlevel 1 set FAILED=!FAILED! %~nx1
goto :eof
