"""GammaController.build_ramp - the lookup table that actually reaches the driver.

This is the highest-traffic pure function in the app: every profile switch goes
through it, and the settings window's curve graph is drawn from it, so a change
here silently desynchronises the picture from the pixels.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "src"))
import screentuner as sp          # noqa: E402

build = sp.GammaController.build_ramp
NEUTRAL = (1.0, 50, 50)


def channel(ramp, ch=0):
    return [ramp[ch][i] for i in range(256)]


class TestNeutral(unittest.TestCase):
    def test_neutral_is_the_identity_ramp(self):
        """1.0 / 50 / 50 must be a no-op, or 'neutral' would tint the screen."""
        for ch in range(3):
            for i in (0, 1, 64, 128, 200, 255):
                self.assertEqual(build(*NEUTRAL)[ch][i], i * 257,
                                 f"channel {ch} entry {i}")

    def test_endpoints_stay_pinned(self):
        self.assertEqual(build(*NEUTRAL)[0][0], 0)
        self.assertEqual(build(*NEUTRAL)[0][255], 65535)


class TestInvariants(unittest.TestCase):
    """Properties that must hold for every input, not just tidy ones."""

    CASES = [(g, c, b)
             for g in (0.3, 0.8, 1.0, 1.6, 2.8)
             for c in (0, 25, 50, 75, 100)
             for b in (0, 50, 100)]

    def test_never_decreasing(self):
        """A ramp that dips inverts tones - visible as posterised banding."""
        for case in self.CASES:
            r = channel(build(*case))
            self.assertTrue(all(a <= b for a, b in zip(r, r[1:])),
                            f"non-monotonic at {case}")

    def test_stays_in_range(self):
        for case in self.CASES:
            for ch in range(3):
                for v in channel(build(*case), ch):
                    self.assertTrue(0 <= v <= 65535, f"{v} out of range at {case}")

    def test_out_of_range_gamma_is_clamped_not_rejected(self):
        """A hand-edited profiles.json must not be able to produce garbage."""
        self.assertEqual(channel(build(99.0, 50, 50)), channel(build(2.80, 50, 50)))
        self.assertEqual(channel(build(-5.0, 50, 50)), channel(build(0.30, 50, 50)))


class TestDirection(unittest.TestCase):
    """Each knob has to move the picture the way its label claims."""

    def mid(self, *args):
        return build(*args)[0][128]

    def test_higher_gamma_lifts_midtones(self):
        self.assertGreater(self.mid(1.5, 50, 50), self.mid(1.0, 50, 50))

    def test_lower_gamma_sinks_midtones(self):
        self.assertLess(self.mid(0.7, 50, 50), self.mid(1.0, 50, 50))

    def test_gamma_leaves_black_and_white_alone(self):
        for g in (0.5, 1.0, 2.0):
            self.assertEqual(build(g, 50, 50)[0][0], 0)
            self.assertEqual(build(g, 50, 50)[0][255], 65535)

    def test_brightness_offsets_the_whole_curve(self):
        self.assertGreater(self.mid(1.0, 50, 70), self.mid(1.0, 50, 50))
        self.assertLess(self.mid(1.0, 50, 30), self.mid(1.0, 50, 50))

    def test_raising_brightness_lifts_black(self):
        """Brightness is an offset, so it must raise the floor, unlike gamma."""
        self.assertGreater(build(1.0, 50, 70)[0][0], 0)

    def test_contrast_steepens_around_the_midpoint(self):
        low, high = build(1.0, 80, 50), build(1.0, 20, 50)
        self.assertLess(low[0][64], high[0][64])       # shadows pushed down
        self.assertGreater(low[0][192], high[0][192])  # highlights pushed up

    def test_contrast_holds_the_midpoint_still(self):
        for c in (0, 25, 50, 75, 100):
            self.assertAlmostEqual(build(1.0, c, 50)[0][128] / 65535.0, 0.5,
                                   delta=0.01)

    def test_zero_contrast_flattens_to_grey(self):
        r = channel(build(1.0, 0, 50))
        self.assertEqual(len(set(r)), 1)


class TestPerChannel(unittest.TestCase):
    """Config allows [r, g, b] anywhere a scalar is allowed."""

    def test_a_list_tints_only_its_channel(self):
        r = build([1.0, 1.8, 1.0], 50, 50)
        self.assertEqual(channel(r, 0), channel(build(*NEUTRAL), 0))
        self.assertEqual(channel(r, 2), channel(build(*NEUTRAL), 2))
        self.assertNotEqual(channel(r, 1), channel(build(*NEUTRAL), 1))

    def test_a_uniform_list_equals_the_scalar(self):
        self.assertEqual(channel(build([1.4, 1.4, 1.4], [60] * 3, [45] * 3)),
                         channel(build(1.4, 60, 45)))

    def test_mixed_scalar_and_list(self):
        build(1.2, [40, 50, 60], 50)      # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
