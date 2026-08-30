"""Update checking, offline.

The network is injected, so every decision this module makes is testable without
one. That matters more here than elsewhere: this is the only code in the app that
downloads and then *executes* something, so the rules about what it will refuse
need to be pinned, not assumed.
"""
import hashlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "src"))
import updater                    # noqa: E402

GOOD_SHA = "a" * 64


def release(version="1.1.0", name="ScreenTuner-1.1.0-setup.exe", url=None,
            digest="sha256:" + GOOD_SHA, size=1234, **kw):
    """A payload shaped like the real GitHub API response."""
    payload = {
        "tag_name": "v" + version,
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": "ScreenTuner-%s-portable.zip" % version,
             "browser_download_url": updater.DOWNLOAD_PREFIX + "v%s/x.zip" % version,
             "digest": "sha256:" + "b" * 64, "size": 99},
            {"name": name,
             "browser_download_url":
                 url if url is not None
                 else updater.DOWNLOAD_PREFIX + "v%s/%s" % (version, name),
             "digest": digest, "size": size},
        ],
    }
    payload.update(kw)
    return payload


class TestParseVersion(unittest.TestCase):
    def test_plain_and_tagged(self):
        self.assertEqual(updater.parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))

    def test_ignores_trailing_junk(self):
        self.assertEqual(updater.parse_version("1.2.3-beta"), (1, 2, 3))

    def test_rejects_nonsense(self):
        for bad in (None, "", "  ", "banana", "1.2", "v", "1..3"):
            self.assertIsNone(updater.parse_version(bad), repr(bad))


class TestIsNewer(unittest.TestCase):
    def test_numeric_not_lexical(self):
        """The bug a string compare would introduce: '1.0.9' > '1.0.10'."""
        self.assertTrue(updater.is_newer("1.0.10", "1.0.9"))
        self.assertFalse(updater.is_newer("1.0.9", "1.0.10"))

    def test_same_version_is_not_newer(self):
        self.assertFalse(updater.is_newer("1.0.1", "1.0.1"))

    def test_older_is_not_newer(self):
        self.assertFalse(updater.is_newer("1.0.0", "1.0.1"))

    def test_each_component_counts(self):
        self.assertTrue(updater.is_newer("2.0.0", "1.9.9"))
        self.assertTrue(updater.is_newer("1.2.0", "1.1.9"))

    def test_unparseable_never_triggers_an_update(self):
        self.assertFalse(updater.is_newer("banana", "1.0.0"))
        self.assertFalse(updater.is_newer("1.0.0", "banana"))


class TestReadRelease(unittest.TestCase):
    def test_the_happy_path(self):
        u = updater.read_release(release("1.1.0"), "1.0.1")
        self.assertEqual(u.version, "1.1.0", "the v prefix is stripped")
        self.assertTrue(u.url.endswith("ScreenTuner-1.1.0-setup.exe"))
        self.assertEqual(u.sha256, GOOD_SHA)
        self.assertEqual(u.size, 1234)

    def test_picks_the_installer_not_the_zip(self):
        self.assertIn("setup.exe", updater.read_release(release(), "1.0.0").url)

    def test_no_update_when_current_or_older(self):
        self.assertIsNone(updater.read_release(release("1.0.1"), "1.0.1"))
        self.assertIsNone(updater.read_release(release("1.0.0"), "1.0.1"))

    def test_drafts_and_prereleases_are_ignored(self):
        self.assertIsNone(updater.read_release(release(draft=True), "1.0.0"))
        self.assertIsNone(updater.read_release(release(prerelease=True), "1.0.0"))

    def test_refuses_a_url_outside_our_own_repo(self):
        """The check that stops a tampered API response redirecting the download."""
        for bad in ("https://example.com/evil.exe",
                    "https://github.com/someone/else/releases/download/v1/x.exe",
                    "http://github.com/NachoSC/ScreenTuner/releases/download/v1/x.exe",
                    "file:///C:/evil.exe", ""):
            self.assertIsNone(updater.read_release(release(url=bad), "1.0.0"), bad)

    def test_requires_a_usable_sha256(self):
        for bad in ("", "md5:" + "a" * 32, "sha256:", "sha256:xyz",
                    "sha256:" + "a" * 63, "sha256:" + "g" * 64):
            self.assertIsNone(updater.read_release(release(digest=bad), "1.0.0"),
                              repr(bad))

    def test_no_installer_asset_means_no_update(self):
        self.assertIsNone(updater.read_release(release(name="notes.txt"), "1.0.0"))

    def test_garbage_payload_does_not_raise(self):
        for bad in (None, [], "", 42, {}):
            self.assertIsNone(updater.read_release(bad, "1.0.0"), repr(bad))


class TestCheck(unittest.TestCase):
    def test_network_failure_is_not_an_error(self):
        """Being offline is normal; it must never surface to the user."""
        def boom(url):
            raise OSError("no network")
        self.assertIsNone(updater.check("1.0.0", fetch=boom))

    def test_returns_the_update_when_there_is_one(self):
        u = updater.check("1.0.0", fetch=lambda url: release("1.2.0"))
        self.assertEqual(u.version, "1.2.0")

    def test_it_asks_the_right_url(self):
        seen = []
        updater.check("1.0.0", fetch=lambda url: seen.append(url) or release())
        self.assertEqual(seen, [updater.API_URL])


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.body = b"pretend installer" * 100
        self.sha = hashlib.sha256(self.body).hexdigest()

    def tearDown(self):
        for f in os.listdir(self.dir):
            os.unlink(os.path.join(self.dir, f))
        os.rmdir(self.dir)

    def update(self, sha=None):
        return updater.Update("1.1.0", updater.DOWNLOAD_PREFIX + "v1.1.0/s.exe",
                              len(self.body), sha or self.sha)

    def test_writes_the_file_when_the_hash_matches(self):
        path = updater.download(self.update(), self.dir,
                                opener=lambda u: FakeResponse(self.body))
        self.assertTrue(os.path.exists(path))
        self.assertEqual(io.open(path, "rb").read(), self.body)

    def test_rejects_and_deletes_a_file_whose_hash_is_wrong(self):
        """A tampered or truncated download must not be left on disk, where it
        could be executed later."""
        with self.assertRaises(ValueError):
            updater.download(self.update(sha="c" * 64), self.dir,
                             opener=lambda u: FakeResponse(self.body))
        self.assertEqual(os.listdir(self.dir), [],
                         "the rejected download was left behind")

    def test_a_failed_transfer_leaves_nothing_behind(self):
        class Broken(FakeResponse):
            def read(self, n=-1):
                raise IOError("connection reset")

        with self.assertRaises(IOError):
            updater.download(self.update(), self.dir,
                             opener=lambda u: Broken(b""))
        self.assertEqual(os.listdir(self.dir), [])


class TestApplyUpdate(unittest.TestCase):
    """The handover script, checked without running it."""

    def setUp(self):
        self.spawned = []
        self._popen = updater.subprocess.Popen
        updater.subprocess.Popen = lambda *a, **k: self.spawned.append((a, k))

    def tearDown(self):
        updater.subprocess.Popen = self._popen

    def script(self, setup=r"C:\T\ScreenTuner-1.1.0-setup.exe",
               exe=r"C:\App\ScreenTuner.exe"):
        self.assertTrue(updater.apply_update(setup, exe))
        bat = os.path.join(tempfile.gettempdir(), "screentuner-update.bat")
        return io.open(bat, encoding="ascii").read()

    def test_runs_the_installer_silently(self):
        s = self.script()
        self.assertIn("/SILENT", s)
        self.assertIn("ScreenTuner-1.1.0-setup.exe", s)

    def test_relaunches_the_app_afterwards(self):
        """The .iss marks its post-install launch skipifsilent, so a silent
        upgrade never restarts the app - the script has to do it."""
        s = self.script()
        self.assertIn(r"C:\App\ScreenTuner.exe", s)
        self.assertLess(s.index("/SILENT"), s.index("start"),
                        "must install before relaunching")

    def test_waits_before_starting_so_we_can_exit_first(self):
        """Inno closes the running copy itself, but exiting cleanly first means
        the tray icon goes away instead of being killed."""
        self.assertIn("ping", self.script().split("/SILENT")[0])

    def test_cleans_up_the_installer_and_itself(self):
        s = self.script()
        self.assertIn("del", s)
        self.assertIn("%~f0", s, "the script must delete itself")

    def test_spawns_detached(self):
        self.script()
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.spawned[0][1].get("creationflags"), 0x00000008)


class TestInstallFlavour(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.dir):
            os.unlink(os.path.join(self.dir, f))
        os.rmdir(self.dir)

    def touch(self, name):
        io.open(os.path.join(self.dir, name), "w").close()

    def test_wizard_install_is_recognised_by_its_uninstaller(self):
        self.touch("ScreenTuner.exe")
        self.touch("unins000.exe")
        self.assertTrue(updater.installed_by_wizard(self.dir))

    def test_portable_copy_has_none(self):
        self.touch("ScreenTuner.exe")
        self.assertFalse(updater.installed_by_wizard(self.dir))

    def test_missing_directory_is_not_a_wizard_install(self):
        self.assertFalse(updater.installed_by_wizard(
            os.path.join(self.dir, "nope")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
