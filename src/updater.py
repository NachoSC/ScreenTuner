"""Check GitHub for a newer release, and install it.

Deliberately split from screentuner.py: everything that decides *whether* to
update is pure, so it can be tested without a network, a GPU or a build. Only
`_fetch`, `download` and `apply_update` touch the outside world.

Trust model, stated plainly because this downloads and runs an executable:

- The API URL and the download prefix are constants here. A tampered API
  response cannot redirect the download somewhere else - `check` rejects any
  asset URL that is not under this repo's releases.
- GitHub reports a sha256 for each asset. The download is verified against it
  before anything is executed, and deleted on mismatch.
- That digest arrives over the same connection as the URL, so it proves the
  file arrived intact - not that the release itself is trustworthy. The binary
  is unsigned, so a compromised GitHub account could still publish anything.
  Code signing is the real fix and is on the roadmap; until then this is the
  same trust a user extends by downloading the installer by hand.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from collections import namedtuple

REPO = "NachoSC/ScreenTuner"
API_URL = "https://api.github.com/repos/%s/releases/latest" % REPO
DOWNLOAD_PREFIX = "https://github.com/%s/releases/download/" % REPO
RELEASES_PAGE = "https://github.com/%s/releases/latest" % REPO

SETUP_SUFFIX = "-setup.exe"
TIMEOUT = 10
SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")

Update = namedtuple("Update", "version url size sha256")


# --------------------------------------------------------------------------
# Pure: deciding whether there is anything to do
# --------------------------------------------------------------------------

def parse_version(text):
    """'v1.2.3' or '1.2.3' -> (1, 2, 3). None if it is not a version."""
    m = SEMVER.match(str(text or "").strip())
    return tuple(int(g) for g in m.groups()) if m else None


def is_newer(latest, current):
    """Numeric compare, so 1.0.10 beats 1.0.9 - a string compare would not."""
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def pick_asset(assets, suffix=SETUP_SUFFIX):
    for a in assets or []:
        if str(a.get("name", "")).endswith(suffix):
            return a
    return None


def read_release(payload, current_version):
    """Turn the API's JSON into an Update, or None if there is nothing to offer.

    Rejects anything it cannot fully vouch for rather than guessing: drafts,
    pre-releases, a download URL outside this repo, or a missing digest.
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("draft") or payload.get("prerelease"):
        return None

    version = payload.get("tag_name")
    if not is_newer(version, current_version):
        return None

    asset = pick_asset(payload.get("assets"))
    if not asset:
        return None

    url = str(asset.get("browser_download_url", ""))
    if not url.startswith(DOWNLOAD_PREFIX):
        return None                      # never follow a URL off our own repo

    digest = str(asset.get("digest", ""))
    if not digest.startswith("sha256:"):
        return None
    sha = digest.split(":", 1)[1].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        return None

    # Normalise "v1.2.3" to "1.2.3": the tag carries the v, nothing else should.
    return Update("%d.%d.%d" % parse_version(version),
                  url, int(asset.get("size") or 0), sha)


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------

def _request(url):
    # GitHub rejects requests with no User-Agent.
    return urllib.request.Request(url, headers={
        "User-Agent": "ScreenTuner-updater",
        "Accept": "application/vnd.github+json",
    })


def _fetch_json(url):
    with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def check(current_version, fetch=None):
    """The newer release, or None. Never raises - being offline is not an error."""
    try:
        payload = (fetch or _fetch_json)(API_URL)
    except Exception:
        return None
    try:
        return read_release(payload, current_version)
    except Exception:
        return None


def download(update, dest_dir=None, opener=None, chunk=64 * 1024):
    """Fetch the installer and verify its sha256. Returns the path.

    Raises on mismatch, having deleted the file - a partial or altered download
    must never be left somewhere that could later be executed.
    """
    dest_dir = dest_dir or tempfile.gettempdir()
    path = os.path.join(dest_dir, "ScreenTuner-%s-setup.exe" % update.version)
    digest = hashlib.sha256()
    opener = opener or (lambda u: urllib.request.urlopen(_request(u),
                                                         timeout=TIMEOUT))
    try:
        with opener(update.url) as r, io.open(path, "wb") as f:
            while True:
                block = r.read(chunk)
                if not block:
                    break
                digest.update(block)
                f.write(block)
    except Exception:
        _quietly_remove(path)
        raise

    got = digest.hexdigest()
    if got != update.sha256:
        _quietly_remove(path)
        raise ValueError("checksum mismatch: expected %s, got %s"
                         % (update.sha256, got))
    return path


def _quietly_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Installing
# --------------------------------------------------------------------------

def installed_by_wizard(app_dir):
    """The Inno installer leaves unins000.exe behind; a portable copy has none.

    Only a wizard install can be upgraded in place: Inno matches on AppId,
    closes the running copy and replaces the tree. Overwriting a portable
    folder while it runs would fail halfway and leave it broken.
    """
    try:
        return any(f.lower().startswith("unins") and f.lower().endswith(".exe")
                   for f in os.listdir(app_dir))
    except OSError:
        return False


def apply_update(setup_path, relaunch_exe, log=None):
    """Run the installer after we exit, then start the new copy.

    Same shape as the uninstall cleanup: a detached .bat from %TEMP%, because
    the installer is about to replace the very files this process is running
    from, and because a batch file sidesteps cmd's quoting rules.

    /SILENT rather than /VERYSILENT - a progress window is the only feedback
    that anything is happening, and the app's tray icon disappears meanwhile.
    """
    temp = tempfile.gettempdir()
    bat = os.path.join(temp, "screentuner-update.bat")
    try:
        with io.open(bat, "w", encoding="ascii", newline="\r\n") as f:
            f.write("@echo off\n")
            f.write("ping 127.0.0.1 -n 3 >nul\n")          # let us exit first
            f.write('"%s" /SILENT /NORESTART /SUPPRESSMSGBOXES\n' % setup_path)
            f.write("ping 127.0.0.1 -n 2 >nul\n")
            f.write('if exist "%s" start "" "%s"\n' % (relaunch_exe, relaunch_exe))
            f.write('del "%s" 2>nul\n' % setup_path)
            f.write('start "" /b cmd /c del "%~f0"\n')
        subprocess.Popen(["cmd", "/c", bat], cwd=temp,
                         creationflags=0x00000008)          # DETACHED_PROCESS
        return True
    except Exception as e:
        if log:
            log("  ! could not start the updater: %s" % e)
        return False
