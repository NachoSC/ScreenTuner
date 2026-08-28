"""The diagnostics report must not identify whoever pasted it.

This is the only pure function in the app whose silent failure hurts the *user*
rather than annoying them: it fails by putting someone's real name into a public
GitHub issue, where it cannot be taken back.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "src"))
import screentuner as sp          # noqa: E402


class TestScrub(unittest.TestCase):
    def test_replaces_the_username(self):
        user = os.environ.get("USERNAME")
        if not user:
            self.skipTest("no USERNAME in this environment")
        self.assertNotIn(user, sp._scrub(f"failed for user {user} at boot"))

    def test_replaces_known_path_roots(self):
        r"""Which variable wins is not fixed: USERPROFILE is a prefix of
        LOCALAPPDATA and APPDATA, so it substitutes first and those never get
        their turn - %USERPROFILE%\AppData\Local is the correct answer, and
        the readable one. What must hold is that no real path survives."""
        for var in ("USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP"):
            val = os.environ.get(var)
            if not val:
                continue
            out = sp._scrub(os.path.join(val, "ScreenTuner", "profiles.json"))
            self.assertNotIn(val, out, var)
            self.assertIn("%", out, var)

    def test_replaces_every_occurrence_not_just_the_first(self):
        user = os.environ.get("USERNAME") or "someone"
        text = f"{user} logged in; {user} logged out; see C:/Users/{user}/x"
        self.assertNotIn(user, sp._scrub(text))

    def test_leaves_unrelated_text_intact(self):
        self.assertEqual(sp._scrub("NVAPI: available, 3 displays"),
                         "NVAPI: available, 3 displays")

    def test_survives_empty_input(self):
        self.assertEqual(sp._scrub(""), "")


class TestDiagnosticsReport(unittest.TestCase):
    """Read-only: it inspects the machine but writes nothing outside a temp file."""

    @classmethod
    def setUpClass(cls):
        fd, cls.cfg = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(cls.cfg)              # let load_config write its defaults
        cls._log, sp.log = sp.log, lambda *a, **k: None
        try:
            cls.report = sp.build_diagnostics(cls.cfg)
        finally:
            sp.log = cls._log

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.cfg):
            os.unlink(cls.cfg)

    def test_says_nothing_about_who_ran_it(self):
        for var in ("USERNAME", "COMPUTERNAME", "USERDOMAIN"):
            val = os.environ.get(var)
            if val and len(val) > 2:
                self.assertNotIn(val, self.report, f"{var} leaked into the report")

    def test_contains_no_home_directory(self):
        for var in ("USERPROFILE", "LOCALAPPDATA", "APPDATA"):
            val = os.environ.get(var)
            if val:
                self.assertNotIn(val, self.report, f"{var} leaked into the report")

    def test_still_says_something_useful(self):
        """Scrubbing must not have eaten the report itself."""
        self.assertIn(sp.VERSION, self.report)
        self.assertIn("NVAPI", self.report)
        self.assertIn("monitors:", self.report)

    def test_lists_profile_names_but_not_their_contents(self):
        """People name profiles after games; nobody expects their values shared."""
        self.assertIn("Competitive FPS", self.report)
        self.assertNotIn('"vibrance": 80', self.report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
