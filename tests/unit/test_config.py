"""Reading profiles.json, and the coercion the settings window relies on.

Every value here can arrive from a file a person edited by hand, so the tests
care mostly about what happens when it is wrong.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "src"))
import screentuner as sp          # noqa: E402
import configui                   # noqa: E402


class TempConfig(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "profiles.json")
        self._log, sp.log = sp.log, lambda *a, **k: None

    def tearDown(self):
        sp.log = self._log
        for f in os.listdir(self.dir):
            os.unlink(os.path.join(self.dir, f))
        os.rmdir(self.dir)

    def write(self, obj):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(obj, f)


class TestLoadConfig(TempConfig):
    def test_creates_defaults_on_first_run(self):
        cfg = sp.load_config(self.path)
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(len(cfg["profiles"]), len(sp.DEFAULT_PROFILES["profiles"]))

    def test_what_it_writes_is_what_it_reads_back(self):
        first = sp.load_config(self.path)
        self.assertEqual(first, sp.load_config(self.path))

    def test_the_defaults_it_returns_are_a_copy(self):
        """A caller mutating its config must not poison the module defaults."""
        cfg = sp.load_config(self.path)
        cfg["profiles"][0]["vibrance"] = 999
        self.assertNotEqual(sp.DEFAULT_PROFILES["profiles"][0]["vibrance"], 999)

    def test_missing_settings_are_filled_in(self):
        """Someone upgrading from an older version has none of the new keys."""
        self.write({"settings": {"notify": False}, "profiles": []})
        st = sp.load_config(self.path)["settings"]
        self.assertIs(st["notify"], False, "the user's own value must survive")
        for key in sp.DEFAULT_PROFILES["settings"]:
            self.assertIn(key, st)

    def test_missing_sections_do_not_raise(self):
        self.write({})
        cfg = sp.load_config(self.path)
        self.assertEqual(cfg["profiles"], [])
        self.assertEqual(cfg["hotkeys"], {})
        self.assertIn("vibrance_step", cfg["settings"])

    def test_unknown_keys_are_preserved(self):
        """Forward compatibility: a newer version's keys must not be dropped."""
        self.write({"settings": {}, "profiles": [], "future_thing": 42})
        self.assertEqual(sp.load_config(self.path)["future_thing"], 42)

    def test_broken_json_raises_rather_than_silently_resetting(self):
        """Overwriting a corrupt file would destroy profiles someone spent time on."""
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ not json")
        with self.assertRaises(ValueError):
            sp.load_config(self.path)

    def test_the_shipped_defaults_are_internally_consistent(self):
        cfg = sp.load_config(self.path)
        names = [p["name"] for p in cfg["profiles"]]
        self.assertEqual(len(names), len(set(names)), "duplicate profile names")
        keys = [p["hotkey"] for p in cfg["profiles"]] + list(cfg["hotkeys"].values())
        self.assertEqual(len(keys), len(set(keys)), "a hotkey is bound twice")
        for spec in keys:
            self.assertIsNotNone(sp.parse_hotkey(spec), spec)


class TestAsScalar(unittest.TestCase):
    """The sliders are single values; the config format allows [r, g, b]."""

    def test_a_plain_number_passes_through(self):
        self.assertEqual(configui.as_scalar(1.2, 1.0), (1.2, False))

    def test_none_uses_the_default(self):
        self.assertEqual(configui.as_scalar(None, 1.0), (1.0, False))

    def test_a_list_averages_and_flags_itself(self):
        value, per_channel = configui.as_scalar([1.0, 1.4, 1.2], 1.0)
        self.assertAlmostEqual(value, 1.2)
        self.assertTrue(per_channel, "the window has to warn it is flattening a tint")

    def test_an_empty_list_falls_back_but_still_flags(self):
        self.assertEqual(configui.as_scalar([], 1.0), (1.0, True))

    def test_zero_is_not_treated_as_missing(self):
        self.assertEqual(configui.as_scalar(0, 50), (0, False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
