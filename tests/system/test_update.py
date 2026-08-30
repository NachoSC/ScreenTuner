"""The update check against the live GitHub API.

The unit tests pin what the updater does with a payload. This pins that the real
payload still looks the way it expects - which is the way this feature rots
silently. If GitHub stopped reporting a per-asset `digest`, `read_release` would
start returning None for every release and updates would simply never appear
again, with nothing in the log to say why.

Needs network. Downloads the real installer once (~10 MB) to prove the integrity
path end to end; it is deleted afterwards.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp          # noqa: E402
import updater                    # noqa: E402

fails = []


def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


print("=== the live releases API still has what we need ===")
try:
    payload = updater._fetch_json(updater.API_URL)
except Exception as e:
    print(f"  no network, or the API is unreachable: {e}")
    print("\nSKIPPED (this test needs internet)")
    sys.exit(0)

check("returned a release object", isinstance(payload, dict))
tag = payload.get("tag_name")
print(f"   latest published release: {tag}")
check("has a tag we can parse", updater.parse_version(tag) is not None)

asset = updater.pick_asset(payload.get("assets"))
check(f"an installer asset is attached ({updater.SETUP_SUFFIX})", asset is not None)

if asset:
    print(f"   asset: {asset.get('name')}  {asset.get('size')} bytes")
    url = str(asset.get("browser_download_url", ""))
    check("its URL is under this repo's releases",
          url.startswith(updater.DOWNLOAD_PREFIX))
    digest = str(asset.get("digest", ""))
    check(f"GitHub still reports a sha256 digest ({digest[:14]}...)",
          digest.startswith("sha256:") and len(digest) == 7 + 64)

print("\n=== the decision the app would actually make ===")
u = updater.read_release(payload, "0.0.1")
check("a very old copy is offered the update", u is not None)
check("the newest release is not offered to itself",
      updater.read_release(payload, updater.parse_version(tag) and
                           "%d.%d.%d" % updater.parse_version(tag)) is None)
check("this build is up to date or an update is available",
      updater.check(sp.VERSION) is None or
      updater.is_newer(tag, sp.VERSION))

print("\n=== the download really does verify ===")
if u:
    tmp = tempfile.mkdtemp()
    path = None
    try:
        path = updater.download(u, tmp)
        check(f"downloaded and sha256 verified ({os.path.getsize(path)} bytes)",
              os.path.getsize(path) == u.size)
    except Exception as e:
        check(f"downloaded and sha256 verified - FAILED: {e}", False)
    finally:
        if path and os.path.exists(path):
            os.remove(path)
        os.rmdir(tmp)

    print("\n=== a tampered download is rejected and not left on disk ===")
    tmp = tempfile.mkdtemp()
    try:
        bad = updater.Update(u.version, u.url, u.size, "0" * 64)
        try:
            updater.download(bad, tmp)
            check("refused a file whose hash does not match", False)
        except ValueError:
            check("refused a file whose hash does not match", True)
        check("and deleted it rather than leaving it runnable",
              os.listdir(tmp) == [])
    finally:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
