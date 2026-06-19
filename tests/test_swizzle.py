"""
tests.test_swizzle
==================
Unit tests for ctxr_tools.swizzle.

Tests cover:
  - _morton():         known good values from the DrSwizzler source
  - ps3_swizzle():     inverse of ps3_deswizzle (round-trip property)
  - ps3_deswizzle():   inverse of ps3_swizzle (round-trip property)
  - argb_to_rgba():    correct byte rotation and its own inverse
  - rgba_to_argb():    correct byte rotation and its own inverse
  - edge cases:        1×1 mip, non-square textures, all-zero data
"""

import sys
import os
import unittest

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ctxr_tools.swizzle import (
    _morton,
    ps3_swizzle,
    ps3_deswizzle,
    argb_to_rgba,
    rgba_to_argb,
)
from ctxr_tools.constants import BPP


# ── Helpers ───────────────────────────────────────────────────────────────────

def _solid(w: int, h: int, r: int, g: int, b: int, a: int) -> bytes:
    """Return a w×h RGBA image filled with a single colour."""
    return bytes([r, g, b, a] * (w * h))


def _gradient(w: int, h: int) -> bytes:
    """
    Return a w×h RGBA image where each pixel encodes its own (x, y) coords.
    pixel(x, y) = [x & 0xFF, y & 0xFF, (x+y) & 0xFF, 0xFF]
    This makes every pixel unique for small textures, so permutation
    errors are immediately visible.
    """
    data = bytearray(w * h * BPP)
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * BPP
            data[i]     = x & 0xFF
            data[i + 1] = y & 0xFF
            data[i + 2] = (x + y) & 0xFF
            data[i + 3] = 0xFF
    return bytes(data)


# ── Morton tests ──────────────────────────────────────────────────────────────

class TestMorton(unittest.TestCase):
    """
    Verify _morton() against a hand-computed 4×4 Z-curve table.

    For a 4×4 grid the Morton curve visits pixels in this order:
      (0,0)→0  (1,0)→1  (0,1)→2  (1,1)→3
      (2,0)→4  (3,0)→5  (2,1)→6  (3,1)→7
      (0,2)→8  (1,2)→9  (0,3)→10 (1,3)→11
      (2,2)→12 (3,2)→13 (2,3)→14 (3,3)→15

    So _morton(t=0,sx=4,sy=4) must return 0,  _morton(t=4) must return 4, etc.
    """

    # Expected: _morton(t, 4, 4) → linear pixel index at that Morton position
    _EXPECTED_4x4 = {
        0: 0,   1: 1,   2: 4,   3: 5,
        4: 2,   5: 3,   6: 6,   7: 7,
        8: 8,   9: 9,   10: 12, 11: 13,
        12: 10, 13: 11, 14: 14, 15: 15,
    }

    def test_4x4_known_values(self):
        for t, expected in self._EXPECTED_4x4.items():
            with self.subTest(t=t):
                self.assertEqual(_morton(t, 4, 4), expected)

    def test_1x1_returns_zero(self):
        self.assertEqual(_morton(0, 1, 1), 0)

    def test_2x2(self):
        # Z-curve for 2×2: t=0→(0,0), t=1→(1,0), t=2→(0,1), t=3→(1,1)
        self.assertEqual(_morton(0, 2, 2), 0)
        self.assertEqual(_morton(1, 2, 2), 1)
        self.assertEqual(_morton(2, 2, 2), 2)
        self.assertEqual(_morton(3, 2, 2), 3)

    def test_non_square_8x4(self):
        # For an 8×4 grid: all returned addresses must be in [0, 31]
        seen = set()
        for t in range(32):
            addr = _morton(t, 8, 4)
            self.assertIn(addr, range(32), msg=f"t={t}: addr={addr} out of range")
            seen.add(addr)
        self.assertEqual(seen, set(range(32)), "Morton must be a bijection")

    def test_bijection_8x8(self):
        """_morton must be a bijection: every address appears exactly once."""
        addresses = [_morton(t, 8, 8) for t in range(64)]
        self.assertEqual(sorted(addresses), list(range(64)))


# ── Swizzle / deswizzle round-trip ───────────────────────────────────────────

class TestSwizzleRoundTrip(unittest.TestCase):
    """
    Core property: ps3_deswizzle(ps3_swizzle(data)) == data for any input,
    and ps3_swizzle(ps3_deswizzle(data)) == data.
    """

    def _check_round_trip(self, w: int, h: int):
        original = _gradient(w, h)
        swizzled   = ps3_swizzle(original, w, h)
        deswizzled = ps3_deswizzle(swizzled, w, h)
        self.assertEqual(deswizzled, original,
                         msg=f"Round-trip failed for {w}×{h}")

    def _check_inverse_round_trip(self, w: int, h: int):
        """Start from swizzled data (simulate reading from CTXR)."""
        swizzled   = _gradient(w, h)    # treat gradient as already-swizzled
        linear     = ps3_deswizzle(swizzled, w, h)
        reswizzled = ps3_swizzle(linear, w, h)
        self.assertEqual(reswizzled, swizzled,
                         msg=f"Inverse round-trip failed for {w}×{h}")

    def test_2x2(self):
        self._check_round_trip(2, 2)
        self._check_inverse_round_trip(2, 2)

    def test_4x4(self):
        self._check_round_trip(4, 4)
        self._check_inverse_round_trip(4, 4)

    def test_8x8(self):
        self._check_round_trip(8, 8)
        self._check_inverse_round_trip(8, 8)

    def test_16x16(self):
        self._check_round_trip(16, 16)

    def test_64x64(self):
        self._check_round_trip(64, 64)

    def test_128x128(self):
        self._check_round_trip(128, 128)

    def test_non_square_8x4(self):
        self._check_round_trip(8, 4)
        self._check_inverse_round_trip(8, 4)

    def test_non_square_16x8(self):
        self._check_round_trip(16, 8)

    def test_solid_colour_unchanged_after_round_trip(self):
        """Solid images must survive swizzle→deswizzle unchanged."""
        data = _solid(16, 16, 0xAA, 0xBB, 0xCC, 0xFF)
        self.assertEqual(ps3_deswizzle(ps3_swizzle(data, 16, 16), 16, 16), data)


class TestSwizzleEdgeCases(unittest.TestCase):

    def test_1x1_swizzle_is_identity(self):
        px = bytes([0x11, 0x22, 0x33, 0xFF])
        self.assertEqual(ps3_swizzle(px, 1, 1), px)

    def test_1x1_deswizzle_is_identity(self):
        px = bytes([0x11, 0x22, 0x33, 0xFF])
        self.assertEqual(ps3_deswizzle(px, 1, 1), px)

    def test_all_zeros_survives(self):
        data = bytes(4 * 4 * BPP)
        self.assertEqual(ps3_deswizzle(ps3_swizzle(data, 4, 4), 4, 4), data)

    def test_swizzle_changes_layout(self):
        """Swizzling a non-uniform gradient must actually reorder bytes."""
        data = _gradient(4, 4)
        self.assertNotEqual(ps3_swizzle(data, 4, 4), data,
                            "Swizzle of gradient should not be identity")

    def test_output_length_preserved(self):
        data = _gradient(8, 8)
        self.assertEqual(len(ps3_swizzle(data, 8, 8)),   len(data))
        self.assertEqual(len(ps3_deswizzle(data, 8, 8)), len(data))


# ── Known 4×4 swizzle pattern ────────────────────────────────────────────────

class TestSwizzleKnownPattern(unittest.TestCase):
    """
    Verify the swizzle permutation for a 2×2 texture against the Z-curve:

      Linear:   [px0, px1, px2, px3]
                 (0,0) (1,0) (0,1) (1,1)

      Z-curve:  t=0 → Morton(0,2,2)=0 → reads px0
                t=1 → Morton(1,2,2)=1 → reads px1
                t=2 → Morton(2,2,2)=2 → reads px2
                t=3 → Morton(3,2,2)=3 → reads px3

      For 2×2 the Morton curve is the identity, so swizzle == identity.
    """

    def test_2x2_swizzle_is_identity_permutation(self):
        px = [bytes([i, i, i, 0xFF]) for i in range(4)]
        linear = b''.join(px)
        swizzled = ps3_swizzle(linear, 2, 2)
        self.assertEqual(swizzled, linear)

    def test_4x4_first_pixel_correct(self):
        """
        For a 4×4 gradient, swizzled[0] must equal linear[Morton(0,4,4)].
        Morton(0,4,4) = 0, so swizzled[0] == linear[0].
        """
        data = _gradient(4, 4)
        swizzled = ps3_swizzle(data, 4, 4)
        m0 = _morton(0, 4, 4)
        self.assertEqual(
            swizzled[:BPP],
            data[m0 * BPP:(m0 + 1) * BPP],
        )

    def test_4x4_slot2_correct(self):
        """
        swizzled pixel at slot t=2 must come from Morton(2,4,4)=4 in linear.
        """
        data = _gradient(4, 4)
        swizzled = ps3_swizzle(data, 4, 4)
        m2 = _morton(2, 4, 4)   # should be 4
        self.assertEqual(
            swizzled[2 * BPP:3 * BPP],
            data[m2 * BPP:(m2 + 1) * BPP],
        )


# ── Channel reordering ────────────────────────────────────────────────────────

class TestChannelSwap(unittest.TestCase):
    """
    argb_to_rgba: [A,R,G,B] → [R,G,B,A]
    rgba_to_argb: [R,G,B,A] → [A,R,G,B]
    Both must be each other's inverse.
    """

    # One pixel with all distinct bytes so any mis-rotation is detectable
    _ARGB = bytes([0xAA, 0x11, 0x22, 0x33])   # A=0xAA R=0x11 G=0x22 B=0x33
    _RGBA = bytes([0x11, 0x22, 0x33, 0xAA])   # R=0x11 G=0x22 B=0x33 A=0xAA

    def test_argb_to_rgba_single_pixel(self):
        self.assertEqual(argb_to_rgba(self._ARGB), self._RGBA)

    def test_rgba_to_argb_single_pixel(self):
        self.assertEqual(rgba_to_argb(self._RGBA), self._ARGB)

    def test_argb_rgba_are_inverses(self):
        """argb_to_rgba(rgba_to_argb(x)) == x for any pixel sequence."""
        data = bytes([0xAA, 0xBB, 0xCC, 0xDD,
                      0x01, 0x02, 0x03, 0x04,
                      0xFF, 0x00, 0x7F, 0x80])
        self.assertEqual(argb_to_rgba(rgba_to_argb(data)), data)

    def test_rgba_argb_are_inverses(self):
        data = bytes([0x10, 0x20, 0x30, 0x40,
                      0xAA, 0xBB, 0xCC, 0xDD])
        self.assertEqual(rgba_to_argb(argb_to_rgba(data)), data)

    def test_output_length_preserved(self):
        data = bytes(16)
        self.assertEqual(len(argb_to_rgba(data)), 16)
        self.assertEqual(len(rgba_to_argb(data)), 16)

    def test_all_zeros_unchanged(self):
        data = bytes(8)
        self.assertEqual(argb_to_rgba(data), data)
        self.assertEqual(rgba_to_argb(data), data)

    def test_fully_opaque_red_pixel(self):
        # RGBA fully opaque red: R=FF G=00 B=00 A=FF
        rgba = bytes([0xFF, 0x00, 0x00, 0xFF])
        argb = bytes([0xFF, 0xFF, 0x00, 0x00])   # A=FF R=FF G=00 B=00
        self.assertEqual(rgba_to_argb(rgba), argb)
        self.assertEqual(argb_to_rgba(argb), rgba)

    def test_multiple_pixels(self):
        pixels = [
            (bytes([0xAA, 0x01, 0x02, 0x03]),  # ARGB
             bytes([0x01, 0x02, 0x03, 0xAA])), # RGBA
            (bytes([0x00, 0xFF, 0x80, 0x40]),
             bytes([0xFF, 0x80, 0x40, 0x00])),
        ]
        argb_all = b''.join(a for a, _ in pixels)
        rgba_all = b''.join(r for _, r in pixels)
        self.assertEqual(argb_to_rgba(argb_all), rgba_all)
        self.assertEqual(rgba_to_argb(rgba_all), argb_all)


if __name__ == '__main__':
    unittest.main()
