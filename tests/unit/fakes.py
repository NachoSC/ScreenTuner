"""Stand-in hardware, so these tests run on a machine with any GPU or none.

`resolve_profile` and friends only ever ask a monitor to describe or match
itself, so a plain object with the same attributes is indistinguishable from a
real one - and lets us test four-monitor and single-laptop layouts that no
single developer's desk can provide.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "src"))

import screentuner as sp          # noqa: E402


class FakeMon:
    def __init__(self, index, vendor, edid, primary=False,
                 width=1920, height=1080, refresh=60):
        self.index, self.vendor, self.edid = index, vendor, edid
        self.is_primary = primary
        self.adapter = r"\\.\DISPLAY%d" % index
        self.gpu = "Fake Adapter"
        self.width, self.height, self.refresh = width, height, refresh
        self.x = self.y = 0

    # The real matching logic, not a reimplementation of it.
    matches = sp.Monitor.matches
    label = sp.Monitor.label


def laptop():
    """One built-in panel."""
    return [FakeMon(1, "LG", "LGD1234", primary=True)]


def dual():
    """The common case: two screens, different vendors."""
    return [FakeMon(1, "Dell", "DEL4141", primary=True),
            FakeMon(2, "Samsung", "SAM0F90")]


def quad():
    """Four screens with a duplicated vendor, to catch over-eager matching."""
    return [FakeMon(1, "Dell", "DEL4141", primary=True),
            FakeMon(2, "LG", "GSM7777"),
            FakeMon(3, "AOC", "AOCB403"),
            FakeMon(4, "Dell", "DELAAAA")]
