"""Save and restore the machine's real ScreenTuner install.

`test_install.py` and `test_wizard.py` exercise the genuine per-user install -
`%LOCALAPPDATA%\\Programs\\ScreenTuner`, the Run key, the uninstall entry - because
that is the thing that has to work, and a copy installed somewhere else would not
prove anything about it.

The cost is that they end by uninstalling, which removes whatever the person
running the tests had installed. That is not acceptable for a test suite someone
runs on their own desk: it happened, the app simply vanished, and it took a
diagnosis to work out why.

So the destructive tests bracket themselves with this. If an install was there
beforehand, it is put back afterwards - files, profiles.json and the run-at-login
setting - whether the test passed, failed or raised.
"""
import glob
import io
import os
import subprocess
import sys
import time
import winreg

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp          # noqa: E402

EXE = os.path.join(sp.INSTALL_DIR, "ScreenTuner.exe")
CONFIG = os.path.join(sp.INSTALL_DIR, "profiles.json")


def _read_run():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sp.RUN_KEY) as k:
            return winreg.QueryValueEx(k, sp.RUN_VALUE)[0]
    except OSError:
        return None


def _write_run(value):
    if value is None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sp.RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, sp.RUN_VALUE)
        except OSError:
            pass
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sp.RUN_KEY) as k:
        winreg.SetValueEx(k, sp.RUN_VALUE, 0, winreg.REG_SZ, value)


def _inno_uninstaller():
    """The wizard leaves unins000.exe behind; --install does not."""
    found = glob.glob(os.path.join(sp.INSTALL_DIR, "unins*.exe"))
    return found[0] if found else None


def snapshot():
    """Everything the destructive tests are about to trample."""
    snap = {"installed": os.path.exists(EXE), "run": _read_run(), "config": None,
            "via_wizard": _inno_uninstaller() is not None}
    if os.path.exists(CONFIG):
        # newline="" so CRLF survives the round trip - reading with universal
        # newlines and writing back would quietly rewrite the user's file.
        snap["config"] = io.open(CONFIG, encoding="utf-8", newline="").read()
    print("  [state] install present beforehand: %s%s" % (
        snap["installed"], " (via the wizard)" if snap["via_wizard"] else ""))
    return snap


def restore(snap):
    """Put the machine back. Safe to call twice, and never raises."""
    try:
        if not snap["installed"]:
            print("  [state] nothing was installed beforehand - leaving it uninstalled")
            return True

        if not os.path.exists(EXE):
            # Reinstall the same way it was installed, or the wizard's uninstaller
            # silently disappears and the entry in Installed apps stops working.
            setup = sorted(glob.glob(os.path.join(ROOT, "dist", "installer",
                                                  "*setup.exe")),
                           key=os.path.getmtime)
            if snap["via_wizard"] and setup:
                print("  [state] reinstalling via the wizard, since the test removed it...")
                cmd = [setup[-1], "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
            else:
                src = os.path.join(ROOT, "dist", "ScreenTuner", "ScreenTuner.exe")
                if not os.path.exists(src):
                    print("  [state] CANNOT RESTORE: nothing in dist\\ to reinstall from.")
                    print("  [state] run build-installer.bat, then reinstall by hand.")
                    return False
                print("  [state] reinstalling, since the test removed it...")
                cmd = [src, "--install"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            for _ in range(30):
                if os.path.exists(EXE):
                    break
                time.sleep(1)
            if not os.path.exists(EXE):
                print("  [state] REINSTALL FAILED: %s" % (r.stderr or r.stdout)[:200])
                return False

        # The reinstall writes a default profiles.json; the real one goes back on top.
        if snap["config"] is not None:
            io.open(CONFIG, "w", encoding="utf-8", newline="").write(snap["config"])

        _write_run(snap["run"])
        print("  [state] install restored (files, profiles.json, run-at-login)")
        return True
    except Exception as e:                      # never mask the test's own failure
        print("  [state] restore hit an error: %r" % (e,))
        return False
