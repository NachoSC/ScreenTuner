"""Startup timing for onedir, then a full install -> verify -> uninstall cycle."""
import os
import subprocess
import sys
import time
import winreg

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp

DIST = os.path.join(ROOT, "dist", "ScreenTuner", "ScreenTuner.exe")
INSTALLED = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "ScreenTuner",
                         "ScreenTuner.exe")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
UNINST = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ScreenTuner"
LNK = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu",
                   "Programs", "ScreenTuner.lnk")

fails = []


def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


def hkcu(key, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def kill():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process ScreenTuner -EA SilentlyContinue|Stop-Process -Force"],
                   capture_output=True)
    time.sleep(1)


def time_start(exe):
    log = os.path.join(os.path.dirname(exe), "screentuner.log")
    if os.path.exists(log):
        os.remove(log)
    t0 = time.perf_counter()
    subprocess.Popen([exe])
    while time.perf_counter() - t0 < 30:
        if os.path.exists(log) and "Running." in open(log, encoding="utf-8",
                                                      errors="ignore").read():
            return time.perf_counter() - t0
        time.sleep(0.01)
    return None


print("=== startup time, onedir (3 runs) ===")
times = []
for _ in range(3):
    kill()
    t = time_start(DIST)
    times.append(t)
    print(f"  {t:.2f} s")
kill()
print(f"  onefile was 0.57 s -> onedir {min(times):.2f} s "
      f"({0.57 / min(times):.1f}x faster)")
check("startup under 0.3 s", min(times) < 0.3)

mei_before = {d for d in os.listdir(os.environ["TEMP"]) if d.startswith("_MEI")}
kill(); time_start(DIST); kill()
mei_after = {d for d in os.listdir(os.environ["TEMP"]) if d.startswith("_MEI")}
check("onedir creates no _MEI unpack dir", mei_after <= mei_before)

print("\n=== install ===")
r = subprocess.run([DIST, "--install"], capture_output=True, text=True)
print("  " + "\n  ".join(l for l in r.stdout.splitlines() if l.strip()))
check("exe copied to LOCALAPPDATA", os.path.exists(INSTALLED))
check("Start Menu shortcut created", os.path.exists(LNK))
check("run-at-login points at the installed copy",
      (hkcu(RUN_KEY, "ScreenTuner") or "").strip('"').lower() == INSTALLED.lower())
check("listed in Installed apps", hkcu(UNINST, "DisplayName") == "ScreenTuner")
check("uninstall string registered",
      "--uninstall" in (hkcu(UNINST, "UninstallString") or ""))
check("version recorded", hkcu(UNINST, "DisplayVersion") == sp.VERSION)

print("\n=== the installed copy runs ===")
kill()
t = time_start(INSTALLED)
print(f"  started in {t:.2f} s" if t else "  DID NOT START")
check("installed copy starts and registers hotkeys", t is not None)
check("config created beside the exe",
      os.path.exists(os.path.join(os.path.dirname(INSTALLED), "profiles.json")))

print("\n=== uninstall (quiet) ===")
r = subprocess.run([INSTALLED, "--uninstall", "--quiet"], capture_output=True,
                   text=True)
print("  " + r.stdout.strip())
for _ in range(40):    # detached rmdir retries while DLLs unlock
    time.sleep(1)
    if not os.path.exists(os.path.dirname(INSTALLED)):
        break
check("run-at-login entry removed", hkcu(RUN_KEY, "ScreenTuner") is None)
check("Installed apps entry removed", hkcu(UNINST, "DisplayName") is None)
check("Start Menu shortcut removed", not os.path.exists(LNK))
check("install folder deleted", not os.path.exists(os.path.dirname(INSTALLED)))
check("process stopped", subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "[bool](Get-Process ScreenTuner -EA SilentlyContinue)"],
    capture_output=True, text=True).stdout.strip() == "False")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
