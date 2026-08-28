"""parse_hotkey and the AltGr conflict check.

Windows implements AltGr as Ctrl+Alt, so on most non-US layouts a Ctrl+Alt
binding fires while the user is simply typing. Five of the six original default
hotkeys collided this way on a Spanish keyboard.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "src"))
import screentuner as sp          # noqa: E402

CTRL, SHIFT, ALT, WIN = (sp.MOD_CONTROL, sp.MOD_SHIFT, sp.MOD_ALT, sp.MOD_WIN)


class TestParsing(unittest.TestCase):
    def test_a_typical_binding(self):
        self.assertEqual(sp.parse_hotkey("ctrl+shift+1"),
                         (CTRL | SHIFT | sp.MOD_NOREPEAT, ord("1")))

    def test_norepeat_is_always_set(self):
        """Without it, holding the key retriggers the profile many times a second."""
        for spec in ("a", "ctrl+f5", "win+shift+space"):
            self.assertTrue(sp.parse_hotkey(spec)[0] & sp.MOD_NOREPEAT, spec)

    def test_case_and_spaces_are_ignored(self):
        self.assertEqual(sp.parse_hotkey("  Ctrl + Shift + A  "),
                         sp.parse_hotkey("ctrl+shift+a"))

    def test_modifier_aliases(self):
        self.assertEqual(sp.parse_hotkey("control+a"), sp.parse_hotkey("ctrl+a"))
        self.assertEqual(sp.parse_hotkey("super+a"), sp.parse_hotkey("win+a"))

    def test_modifiers_combine(self):
        mods = sp.parse_hotkey("ctrl+alt+shift+win+a")[0]
        for m in (CTRL, ALT, SHIFT, WIN):
            self.assertTrue(mods & m)

    def test_letters_and_digits(self):
        self.assertEqual(sp.parse_hotkey("a")[1], ord("A"))
        self.assertEqual(sp.parse_hotkey("Z")[1], ord("Z"))
        self.assertEqual(sp.parse_hotkey("7")[1], ord("7"))

    def test_function_keys(self):
        self.assertEqual(sp.parse_hotkey("f1")[1], 0x70)
        self.assertEqual(sp.parse_hotkey("f12")[1], 0x7B)
        self.assertEqual(sp.parse_hotkey("f24")[1], 0x87)

    def test_numpad_keys(self):
        self.assertEqual(sp.parse_hotkey("numpad0")[1], 0x60)
        self.assertEqual(sp.parse_hotkey("numpad9")[1], 0x69)

    def test_named_keys(self):
        self.assertEqual(sp.parse_hotkey("space")[1], 0x20)
        self.assertEqual(sp.parse_hotkey("escape"), sp.parse_hotkey("esc"))
        self.assertEqual(sp.parse_hotkey("pgup"), sp.parse_hotkey("pageup"))

    def test_punctuation_keys(self):
        """The vibrance nudge defaults are '=' and '-'."""
        self.assertEqual(sp.parse_hotkey("ctrl+shift+=")[1], 0xBB)
        self.assertEqual(sp.parse_hotkey("ctrl+shift+-")[1], 0xBD)

    def test_a_literal_plus_as_the_key(self):
        """'ctrl++' splits into an empty part - it means the + key, not a typo."""
        self.assertEqual(sp.parse_hotkey("ctrl++"), (CTRL | sp.MOD_NOREPEAT, 0xBB))


class TestRejection(unittest.TestCase):
    """Bad input must return None, never raise - it comes from a hand-edited file."""

    def test_rejects_empty_and_none(self):
        for spec in (None, "", "   "):
            self.assertIsNone(sp.parse_hotkey(spec), repr(spec))

    def test_rejects_modifiers_with_no_key(self):
        self.assertIsNone(sp.parse_hotkey("ctrl+shift"))

    def test_rejects_unknown_key_names(self):
        for spec in ("ctrl+notakey", "f25", "f0", "numpadx", "ctrl+~~"):
            self.assertIsNone(sp.parse_hotkey(spec), spec)


class TestAltGrConflicts(unittest.TestCase):
    def test_ctrl_alt_is_flagged(self):
        found = sp.altgr_conflicts([("Vivid", "ctrl+alt+3")])
        self.assertEqual(found, [("Vivid", "ctrl+alt+3")])

    def test_order_of_modifiers_does_not_hide_it(self):
        self.assertTrue(sp.altgr_conflicts([("x", "alt+ctrl+3")]))
        self.assertTrue(sp.altgr_conflicts([("x", "ctrl+alt+shift+3")]))

    def test_safe_bindings_are_not_flagged(self):
        for spec in ("ctrl+shift+3", "alt+3", "ctrl+3", "win+3", "f9"):
            self.assertEqual(sp.altgr_conflicts([("x", spec)]), [], spec)

    def test_unparseable_bindings_are_not_flagged(self):
        self.assertEqual(sp.altgr_conflicts([("x", "ctrl+alt+notakey")]), [])

    def test_the_shipped_defaults_are_all_safe(self):
        """The 1.0.0 defaults moved off Ctrl+Alt for exactly this reason."""
        d = sp.DEFAULT_PROFILES
        keys = ([(k, v) for k, v in d["hotkeys"].items()]
                + [(p["name"], p.get("hotkey")) for p in d["profiles"]])
        self.assertEqual(sp.altgr_conflicts(keys), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
