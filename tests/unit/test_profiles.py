"""Monitor matching and profile expansion - the per-monitor logic.

These run against fabricated displays, so a four-screen mixed-vendor layout is
testable on a laptop, and a contributor with an AMD card can check that a change
to profile resolution behaves before they own the hardware to see it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes                      # noqa: E402
from fakes import FakeMon         # noqa: E402
import screentuner as sp          # noqa: E402


class TestMonitorMatches(unittest.TestCase):
    def setUp(self):
        self.m = FakeMon(2, "Dell", "DEL4141")
        self.p = FakeMon(1, "LG", "GSM7777", primary=True)

    def test_the_fake_adapter_name_looks_like_a_real_one(self):
        r"""Windows names them \\.\DISPLAYn. A fake that is a backslash short
        would make every adapter-matching test below pass against nothing."""
        self.assertEqual(self.m.adapter, "\\" * 2 + "." + "\\" + "DISPLAY2")

    def test_matches_adapter_name(self):
        self.assertTrue(self.m.matches(r"\\.\DISPLAY2"))
        self.assertTrue(self.m.matches(r"\\.\display2"))

    def test_matches_index_as_string_or_number(self):
        self.assertTrue(self.m.matches("2"))
        self.assertTrue(self.m.matches(2))
        self.assertFalse(self.m.matches("3"))

    def test_matches_primary_and_secondary(self):
        self.assertTrue(self.p.matches("primary"))
        self.assertFalse(self.p.matches("secondary"))
        self.assertTrue(self.m.matches("secondary"))
        self.assertTrue(self.m.matches("second"))

    def test_matches_edid_exactly_and_by_substring(self):
        self.assertTrue(self.m.matches("DEL4141"))
        self.assertTrue(self.m.matches("del4141"))
        self.assertTrue(self.m.matches("4141"))

    def test_matches_vendor_name(self):
        self.assertTrue(self.m.matches("Dell"))
        self.assertTrue(self.m.matches("dell"))

    def test_wildcards(self):
        self.assertTrue(self.m.matches("all"))
        self.assertTrue(self.m.matches("*"))

    def test_rejects_empty_and_unknown(self):
        for key in ("", "   ", "Acer", "99"):
            self.assertFalse(self.m.matches(key), repr(key))


class TestResolveMonitors(unittest.TestCase):
    def setUp(self):
        self.mons = fakes.quad()

    def test_none_means_every_monitor(self):
        self.assertEqual(len(sp.resolve_monitors(self.mons, None)), 4)

    def test_a_single_key(self):
        got = sp.resolve_monitors(self.mons, "primary")
        self.assertEqual([m.index for m in got], [1])

    def test_a_list_of_keys(self):
        got = sp.resolve_monitors(self.mons, ["AOC", "2"])
        self.assertEqual([m.index for m in got], [2, 3])

    def test_overlapping_keys_do_not_duplicate(self):
        got = sp.resolve_monitors(self.mons, ["primary", "Dell", "1"])
        self.assertEqual([m.index for m in got], [1, 4])

    def test_unknown_keys_match_nothing(self):
        self.assertEqual(sp.resolve_monitors(self.mons, "Acer"), [])


class TestResolveProfile(unittest.TestCase):
    def plan(self, profile, mons=None):
        return sp.resolve_profile(profile, mons or fakes.quad())

    def test_no_monitors_block_applies_to_all(self):
        plan = self.plan({"name": "x", "vibrance": 70, "gamma": 1.1})
        self.assertEqual(len(plan), 4)
        self.assertTrue(all(s["vibrance"] == 70 for _, s in plan))

    def test_missing_keys_become_none_not_zero(self):
        """None means 'leave that knob alone'; 0 would mean 'set it to nothing'."""
        _, s = self.plan({"name": "x", "vibrance": 70})[0]
        self.assertIsNone(s["gamma"])
        self.assertIsNone(s["contrast"])

    def test_an_override_wins_for_its_monitor_only(self):
        plan = self.plan({"name": "x", "vibrance": 50,
                          "monitors": {"AOC": {"vibrance": 90}}})
        got = {m.index: s["vibrance"] for m, s in plan}
        self.assertEqual(got, {1: 50, 2: 50, 3: 90, 4: 50})

    def test_an_override_merges_rather_than_replaces(self):
        plan = self.plan({"name": "x", "vibrance": 50, "gamma": 1.2,
                          "monitors": {"AOC": {"vibrance": 90}}})
        aoc = [s for m, s in plan if m.index == 3][0]
        self.assertEqual(aoc["vibrance"], 90)
        self.assertEqual(aoc["gamma"], 1.2, "untouched keys must survive")

    def test_skip_drops_the_monitor_entirely(self):
        for override in (False, {"skip": True}):
            plan = self.plan({"name": "x", "vibrance": 50,
                              "monitors": {"AOC": override}})
            self.assertEqual([m.index for m, _ in plan], [1, 2, 4], repr(override))

    def test_unknown_keys_in_an_override_are_ignored(self):
        _, s = self.plan({"name": "x", "vibrance": 50,
                          "monitors": {"primary": {"vibrance": 90,
                                                   "loudness": 11}}})[0]
        self.assertNotIn("loudness", s)
        self.assertEqual(s["vibrance"], 90)

    def test_first_matching_override_wins(self):
        """A monitor can match several keys; the earliest one decides."""
        plan = self.plan({"name": "x", "vibrance": 50,
                          "monitors": {"primary": {"vibrance": 10},
                                       "Dell": {"vibrance": 20}}})
        got = {m.index: s["vibrance"] for m, s in plan}
        self.assertEqual(got[1], 10, "primary listed first")
        self.assertEqual(got[4], 20, "the other Dell falls to the vendor rule")

    def test_naming_hardware_that_is_not_here_is_harmless(self):
        """Profiles get shared between people with different monitors."""
        plan = self.plan({"name": "x", "vibrance": 60,
                          "monitors": {"Acer": {"vibrance": 20},
                                       "Iiyama": {"skip": True}}})
        self.assertEqual(len(plan), 4)
        self.assertTrue(all(s["vibrance"] == 60 for _, s in plan))

    def test_secondary_rule_on_a_single_screen_laptop(self):
        plan = self.plan({"name": "x", "vibrance": 70,
                          "monitors": {"secondary": {"vibrance": 30}}},
                         fakes.laptop())
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][1]["vibrance"], 70)

    def test_every_monitor_skipped_gives_an_empty_plan(self):
        plan = self.plan({"name": "x", "monitors": {"all": {"skip": True}}})
        self.assertEqual(plan, [])


class TestProfileValue(unittest.TestCase):
    def test_missing_key_falls_back(self):
        self.assertEqual(sp.profile_value({}, "vibrance", 50), 50)

    def test_explicit_none_falls_back(self):
        self.assertEqual(sp.profile_value({"vibrance": None}, "vibrance", 50), 50)

    def test_zero_is_kept(self):
        """0 is a legitimate contrast; treating it as absent would silently reset."""
        self.assertEqual(sp.profile_value({"contrast": 0}, "contrast", 50), 0)


class TestSummarisePlan(unittest.TestCase):
    def test_empty_plan(self):
        self.assertEqual(sp.summarise_plan([]), "no monitors targeted")

    def test_uniform_plan_reads_as_one_line(self):
        text = sp.summarise_plan(sp.resolve_profile(
            {"name": "x", "vibrance": 70, "gamma": 1.1,
             "contrast": 55, "brightness": 50}, fakes.dual()))
        self.assertIn("vibrance 70", text)
        self.assertNotIn("|", text)

    def test_mixed_plan_names_each_monitor(self):
        text = sp.summarise_plan(sp.resolve_profile(
            {"name": "x", "vibrance": 70,
             "monitors": {"Samsung": {"vibrance": 30}}}, fakes.dual()))
        self.assertIn("|", text)
        self.assertIn("Dell", text)
        self.assertIn("Samsung", text)

    def test_unset_values_show_as_a_dash(self):
        self.assertIn("gamma -", sp.summarise_plan(
            sp.resolve_profile({"name": "x", "vibrance": 70}, fakes.laptop())))


if __name__ == "__main__":
    unittest.main(verbosity=2)
