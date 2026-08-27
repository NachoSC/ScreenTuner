"""Generate icon.ico for Screen Profiles - no image libraries needed.

The mark: a rounded square running from flat grey on the left to fully saturated
blue-cyan on the right. That is literally what the app does to your screen.

Run: python src/make_icon.py
"""

import os
import struct

# Written to the repo root, not beside this script: the installer and the
# PyInstaller --add-data both reference it from there.
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "icon.ico")
SIZES = (16, 24, 32, 48, 64, 128, 256)

# left (desaturated) -> right (vivid), sampled top and bottom for a slight gradient
TOP_L, TOP_R = (0x6E, 0x74, 0x80), (0x35, 0xC8, 0xF0)
BOT_L, BOT_R = (0x4A, 0x4F, 0x59), (0x2F, 0x6F, 0xED)


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(lerp(c1[i], c2[i], t) for i in range(3))


def coverage(x, y, size, radius):
    """Anti-aliased rounded-square mask via 3x3 supersampling."""
    hits = 0
    for sy in range(3):
        for sx in range(3):
            px = x + (sx + 0.5) / 3.0
            py = y + (sy + 0.5) / 3.0
            # distance outside the rounded rect
            dx = max(radius - px, px - (size - radius), 0.0)
            dy = max(radius - py, py - (size - radius), 0.0)
            if dx == 0.0 and dy == 0.0:
                hits += 1
            elif (dx * dx + dy * dy) ** 0.5 <= radius:
                hits += 1
    return hits / 9.0


def glyph(x, y, size):
    """The half-filled circle used everywhere for contrast/brightness, anti-aliased."""
    cx = cy = size / 2.0
    radius = size * 0.27
    ring = max(0.75, size * 0.05)
    hits = 0
    for sy in range(3):
        for sx in range(3):
            px = x + (sx + 0.5) / 3.0
            py = y + (sy + 0.5) / 3.0
            d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            if abs(d - radius) <= ring / 2.0:        # the outline
                hits += 1
            elif d < radius and px < cx:             # the filled half
                hits += 1
    return hits / 9.0


def render(size):
    """Rows of BGRA bytes, top-down."""
    radius = max(2.0, size * 0.22)
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            tx = x / max(1, size - 1)
            ty = y / max(1, size - 1)
            top = mix(TOP_L, TOP_R, tx)
            bot = mix(BOT_L, BOT_R, tx)
            r, g, b = mix(top, bot, ty)

            a = coverage(x, y, size, radius)
            # subtle top highlight so it does not look flat
            if a > 0:
                hl = max(0.0, 1.0 - ty * 3.0) * 0.16
                r, g, b = (min(255, c + 255 * hl) for c in (r, g, b))
                gl = glyph(x, y, size)
                if gl > 0:
                    r, g, b = (lerp(c, 255, gl * 0.92) for c in (r, g, b))
            row += bytes((int(b + 0.5), int(g + 0.5), int(r + 0.5),
                          int(a * 255 + 0.5)))          # BGRA, as a DIB wants
        rows.append(bytes(row))
    return rows


def dib(size, rows):
    """A 32-bit BITMAPINFOHEADER image. ICO stores DIBs, not PNGs - PNG entries
    are only reliably understood by newer shells, and several decoders read them
    as raw pixels and render noise."""
    header = struct.pack("<IiiHHIIiiII",
                         40, size, size * 2,     # height is doubled: XOR + AND masks
                         1, 32, 0, 0, 0, 0, 0, 0)
    xor = b"".join(reversed(rows))               # DIB scanlines run bottom-up
    stride = ((size + 31) // 32) * 4             # AND mask: 1bpp, 4-byte aligned rows
    and_mask = b"\x00" * (stride * size)
    return header + xor + and_mask


def main():
    images = [(s, dib(s, render(s))) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        entries += struct.pack("<BBBBHHII",
                               0 if size >= 256 else size,
                               0 if size >= 256 else size,
                               0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    with open(OUT, "wb") as f:
        f.write(header + entries + blobs)
    print(f"wrote {OUT}  ({len(header + entries + blobs):,} bytes, "
          f"sizes {', '.join(str(s) for s in SIZES)})")


if __name__ == "__main__":
    main()
