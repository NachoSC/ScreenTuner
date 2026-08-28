"""Silent install via the Inno wizard, verify, then silent uninstall."""
import glob
import os
import subprocess
import sys
import time
import winreg

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SETUP = glob.glob(os.path.join(ROOT, "dist", "installer", "*setup.exe"))[0]
APP = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "ScreenTuner")
EXE = os.path.join(APP, "ScreenTuner.exe")
LNK_GROUP = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                         "Start Menu", "Programs", "ScreenTuner")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

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


def uninstall_entry():
    """Inno registers under its AppId; find it by DisplayName."""
    base = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as b:
            for i in range(winreg.QueryInfoKey(b)[0]):
                sub = winreg.EnumKey(b, i)
                try:
                    with winreg.OpenKey(b, sub) as k:
                        if winreg.QueryValueEx(k, "DisplayName")[0] == "ScreenTuner":
                            return sub, dict(
                                (winreg.EnumValue(k, j)[0], winreg.EnumValue(k, j)[1])
                                for j in range(winreg.QueryInfoKey(k)[1]))
                except OSError:
                    continue
    except OSError:
        pass
    return None, {}


def kill():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process ScreenTuner -EA SilentlyContinue|Stop-Process -Force"],
                   capture_output=True)
    time.sleep(1)


print(f"setup: {os.path.basename(SETUP)} ({os.path.getsize(SETUP)//1024} KB)\n")
print("=== silent install, with the run-at-login task ===")
r = subprocess.run([SETUP, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                    "/TASKS=startup"], capture_output=True, text=True)
print(f"  exit code {r.returncode}")
time.sleep(3)
check("installer exited cleanly", r.returncode == 0)
check("app installed", os.path.exists(EXE))
n = sum(len(f) for _, _, f in os.walk(APP)) if os.path.isdir(APP) else 0
check(f"full onedir tree copied ({n} files)", n > 900)
check("Start Menu group created", os.path.isdir(LNK_GROUP))
check("run-at-login set by the task",
      (hkcu(RUN_KEY, "ScreenTuner") or "").strip('"').lower() == EXE.lower())
key, vals = uninstall_entry()
check("listed in Installed apps", key is not None)
check("uninstaller registered", "UninstallString" in vals)
check("no admin needed (installed per-user under LOCALAPPDATA)",
      APP.lower().startswith(os.environ["LOCALAPPDATA"].lower()))

print("\n=== the installed app runs ===")
log = os.path.join(APP, "screentuner.log")
if os.path.exists(log):
    os.remove(log)
subprocess.Popen([EXE])
started = None
t0 = time.perf_counter()
while time.perf_counter() - t0 < 25:
    if os.path.exists(log) and "Running." in open(log, encoding="utf-8",
                                                  errors="ignore").read():
        started = time.perf_counter() - t0
        break
    time.sleep(0.05)
print(f"  started in {started:.2f} s" if started else "  DID NOT START")
check("installed app starts", started is not None)

print("\n=== silent uninstall ===")
unins = vals.get("UninstallString", "").strip('"')
print(f"  {os.path.basename(unins)}")
r = subprocess.run([unins, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                   capture_output=True, text=True)
for _ in range(40):
    time.sleep(1)
    if not os.path.exists(EXE):
        break
check("app files removed", not os.path.exists(EXE))
check("run-at-login entry removed", hkcu(RUN_KEY, "ScreenTuner") is None)
check("Installed apps entry removed", uninstall_entry()[0] is None)
check("Start Menu group removed", not os.path.isdir(LNK_GROUP))
check("process not left running", subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "[bool](Get-Process ScreenTuner -EA SilentlyContinue)"],
    capture_output=True, text=True).stdout.strip() == "False")
leftovers = sorted(os.path.basename(p) for p in
                   glob.glob(os.path.join(APP, "**", "*"), recursive=True)
                   if os.path.isfile(p))
# A silent uninstall must not throw away the user's own profiles; an interactive
# one asks. So exactly one survivor is expected here, and only that one.
check(f"only profiles.json survives a silent uninstall ({leftovers})",
      leftovers in ([], ["profiles.json"]))

kill()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
