"""Single source of truth for the version number.

`VERSION` in src/screentuner.py is authoritative - the app has to know its own version
anyway, so everything else derives from it. This script keeps the other places in
step and shouts if they have drifted.

    python tools/version.py                 print the current version
    python tools/version.py --check         verify every file agrees (exit 1 if not)
    python tools/version.py --set 1.1.0     update every file
    python tools/version.py --tag           create the annotated git tag
"""

import argparse
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "src", "screentuner.py")
WINGET = os.path.join(ROOT, "winget")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def read(path):
    return io.open(path, encoding="utf-8").read()


def write(path, text):
    io.open(path, "w", encoding="utf-8", newline="").write(text)


def current():
    m = re.search(r'^VERSION = "([^"]+)"', read(APP), re.MULTILINE)
    if not m:
        sys.exit("could not find VERSION in src/screentuner.py")
    return m.group(1)


def winget_dir(version=None):
    """The manifest folder for a version, whatever it happens to be called."""
    if version:
        return os.path.join(WINGET, version)
    dirs = [d for d in os.listdir(WINGET)
            if os.path.isdir(os.path.join(WINGET, d)) and SEMVER.match(d)]
    return os.path.join(WINGET, dirs[0]) if len(dirs) == 1 else None


def check(verbose=True):
    """Report every place the version appears and whether it matches."""
    want = current()
    problems = []
    found = [("src/screentuner.py VERSION", want, True)]

    wdir = winget_dir()
    if wdir is None:
        problems.append("winget/ has zero or several version folders")
    else:
        name = os.path.basename(wdir)
        ok = name == want
        found.append(("winget/ folder name", name, ok))
        if not ok:
            problems.append(f"winget folder is {name}, expected {want}")
        for f in sorted(os.listdir(wdir)):
            if not f.endswith(".yaml"):
                continue
            m = re.search(r"^PackageVersion: (.+)$", read(os.path.join(wdir, f)),
                          re.MULTILINE)
            got = m.group(1).strip() if m else "(missing)"
            ok = got == want
            found.append((f"winget/{name}/{f}", got, ok))
            if not ok:
                problems.append(f"{f} says {got}, expected {want}")

    if os.path.exists(CHANGELOG):
        m = re.search(r"^## \[?(\d+\.\d+\.\d+)\]?", read(CHANGELOG), re.MULTILINE)
        got = m.group(1) if m else "(none)"
        ok = got == want
        found.append(("CHANGELOG.md newest entry", got, ok))
        if not ok:
            problems.append(f"CHANGELOG's newest entry is {got}, expected {want}")

    if verbose:
        for label, value, ok in found:
            print(f"  {'ok  ' if ok else 'DIFF'}  {label:<44} {value}")
    return want, problems


def set_version(new):
    if not SEMVER.match(new):
        sys.exit(f"'{new}' is not a MAJOR.MINOR.PATCH version")
    old = current()

    s = read(APP)
    s = re.sub(r'^VERSION = "[^"]+"', f'VERSION = "{new}"', s, count=1,
               flags=re.MULTILINE)
    write(APP, s)
    print(f"  src/screentuner.py {old} -> {new}")

    wdir = winget_dir()
    if wdir:
        for f in os.listdir(wdir):
            if f.endswith(".yaml"):
                p = os.path.join(wdir, f)
                write(p, re.sub(r"^PackageVersion: .+$", f"PackageVersion: {new}",
                                read(p), flags=re.MULTILINE))
        target = winget_dir(new)
        if os.path.abspath(wdir) != os.path.abspath(target):
            os.rename(wdir, target)
            print(f"  winget/            {os.path.basename(wdir)} -> {new}")
        # URLs embed the tag and the file name
        for f in os.listdir(target):
            p = os.path.join(target, f)
            write(p, read(p).replace(f"/v{old}/", f"/v{new}/")
                            .replace(f"-{old}-setup.exe", f"-{new}-setup.exe")
                            .replace(f"/tag/v{old}", f"/tag/v{new}"))
        print(f"  winget manifests   updated (URLs and PackageVersion)")

    if os.path.exists(CHANGELOG):
        s = read(CHANGELOG)
        if f"## [{new}]" not in s and f"## {new}" not in s:
            s = s.replace("<!-- next -->",
                          f"<!-- next -->\n\n## {new} - unreleased\n\n### Added\n\n"
                          f"### Fixed\n", 1)
            write(CHANGELOG, s)
            print(f"  CHANGELOG.md       stub added for {new}")

    print("\n  Installer version comes from screentuner.py at build time; "
          "nothing to change there.")


def tag():
    v = current()
    _, problems = check(verbose=False)
    if problems:
        print("Refusing to tag - the version is inconsistent:")
        for p in problems:
            print(f"  - {p}")
        return 1
    existing = subprocess.run(["git", "tag", "-l", f"v{v}"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    if existing:
        print(f"tag v{v} already exists")
        return 1
    subprocess.run(["git", "tag", "-a", f"v{v}", "-m", f"ScreenTuner {v}"],
                   cwd=ROOT, check=True)
    print(f"created tag v{v}   (push it with: git push origin v{v})")
    return 0


ap = argparse.ArgumentParser(description="Keep the version consistent everywhere.")
ap.add_argument("--check", action="store_true", help="verify every file agrees")
ap.add_argument("--set", metavar="X.Y.Z", help="set a new version everywhere")
ap.add_argument("--tag", action="store_true", help="create the annotated git tag")
args = ap.parse_args()

if args.set:
    set_version(args.set)
elif args.check:
    v, problems = check()
    print(f"\n  version: {v}")
    if problems:
        print("  INCONSISTENT:")
        for p in problems:
            print(f"    - {p}")
        sys.exit(1)
    print("  all consistent")
elif args.tag:
    sys.exit(tag())
else:
    print(current())
