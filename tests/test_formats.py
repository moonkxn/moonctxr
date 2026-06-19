"""
tests.test_formats
==================
Unit tests for ctxr_tools.formats.

Tests cover:
  - mip_chain():          correct dimensions, sizes, and count at every level
  - parse_ctxr_header():  accepts valid data, rejects bad magic / truncation
  - build_ctxr_header():  round-trips with / without original header
  - parse_dds():          accepts valid RGBA8, rejects non-RGBA8 formats
  - build_dds_header():   produces a parseable header with correct fields
  - Integration:          build → parse round-trips for both formats
"""

import sys
import os
import struct
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ctxr_tools.formats import (
    mip_chain,
    parse_ctxr_header,
    build_ctxr_header,
    parse_dds,
    build_dds_header,
)
from ctxr_tools.constants import (
    CTXR_HEADER_SIZE,
    CTXR_TRAILING_PAD,
    CTXR_MAGIC,
    BPP,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctxr(width: int, height: int, mip_count: int,
               pixel_data: bytes = b'') -> bytes:
    """
    Build a minimal but valid PS3 CTXR byte string.

    If *pixel_data* is empty, a zero buffer of the correct size is used.
    """
    if not pixel_data:
        pixel_data = bytes(sum(w * h * BPP
                               for w, h, _ in mip_chain(width, height, mip_count)))
    hdr = build_ctxr_header(
        width=width, height=height, mip_count=mip_count,
        pixel_data_used=len(pixel_data),
        original_header=None,
    )
    return hdr + pixel_data + bytes(CTXR_TRAILING_PAD)


def _make_dds(width: int, height: int, mip_count: int,
              pixel_data: bytes = b'') -> bytes:
    """
    Build a minimal but valid DDS byte string (RGBA8, uncompressed).
    """
    if not pixel_data:
        pixel_data = bytes(sum(w * h * BPP
                               for w, h, _ in mip_chain(width, height, mip_count)))
    return build_dds_header(width, height, mip_count) + pixel_data


# ── mip_chain ─────────────────────────────────────────────────────────────────

class TestMipChain(unittest.TestCase):

    def test_1024x1024_11_mips_dimensions(self):
        mips = list(mip_chain(1024, 1024, 11))
        self.assertEqual(len(mips), 11)
        expected_dims = [
            (1024, 1024), (512, 512), (256, 256), (128, 128),
            (64, 64),     (32, 32),   (16, 16),   (8, 8),
            (4, 4),       (2, 2),     (1, 1),
        ]
        for i, (w, h, _) in enumerate(mips):
            self.assertEqual((w, h), expected_dims[i], msg=f"mip {i} dims wrong")

    def test_byte_sizes(self):
        for w, h, size in mip_chain(64, 64, 7):
            self.assertEqual(size, w * h * BPP)

    def test_total_size_1024(self):
        total = sum(s for _, _, s in mip_chain(1024, 1024, 11))
        self.assertEqual(total, 5_592_404)

    def test_stops_at_1x1(self):
        mips = list(mip_chain(4, 4, 10))  # request more mips than possible
        # Should still yield 10 entries; after 2x2 all are 1x1
        self.assertEqual(len(mips), 10)
        self.assertEqual(mips[-1][:2], (1, 1))

    def test_non_square(self):
        mips = list(mip_chain(16, 8, 4))
        self.assertEqual(mips[0][:2], (16, 8))
        self.assertEqual(mips[1][:2], (8, 4))
        self.assertEqual(mips[2][:2], (4, 2))
        self.assertEqual(mips[3][:2], (2, 1))

    def test_single_mip(self):
        mips = list(mip_chain(256, 256, 1))
        self.assertEqual(len(mips), 1)
        self.assertEqual(mips[0], (256, 256, 256 * 256 * BPP))


# ── parse_ctxr_header ─────────────────────────────────────────────────────────

class TestParseCTXRHeader(unittest.TestCase):

    def _valid(self, w=64, h=64, mc=7):
        return _make_ctxr(w, h, mc)

    def test_valid_1024x1024(self):
        data = _make_ctxr(1024, 1024, 11)
        w, h, mc, sc = parse_ctxr_header(data)
        self.assertEqual(w, 1024)
        self.assertEqual(h, 1024)
        self.assertEqual(mc, 11)
        self.assertEqual(sc, 1)

    def test_valid_64x64(self):
        data = _make_ctxr(64, 64, 7)
        w, h, mc, _ = parse_ctxr_header(data)
        self.assertEqual((w, h, mc), (64, 64, 7))

    def test_valid_non_square(self):
        data = _make_ctxr(128, 64, 8)
        w, h, mc, _ = parse_ctxr_header(data)
        self.assertEqual((w, h), (128, 64))

    def test_bad_magic_raises(self):
        data = bytearray(_make_ctxr(64, 64, 7))
        data[0] = 0xFF   # corrupt magic
        with self.assertRaises(ValueError, msg="Bad magic should raise"):
            parse_ctxr_header(bytes(data))

    def test_truncated_file_raises(self):
        data = _make_ctxr(64, 64, 7)
        with self.assertRaises(ValueError):
            parse_ctxr_header(data[:CTXR_HEADER_SIZE - 1])

    def test_size_sentinel_mismatch_raises(self):
        data = bytearray(_make_ctxr(64, 64, 7))
        # Corrupt totalBufferSize at 0x04
        struct.pack_into('>I', data, 0x04, 0xDEADBEEF)
        with self.assertRaises(ValueError):
            parse_ctxr_header(bytes(data))

    def test_zero_width_raises(self):
        data = bytearray(_make_ctxr(64, 64, 7))
        struct.pack_into('>H', data, 0x2C, 0)
        with self.assertRaises(ValueError):
            parse_ctxr_header(bytes(data))

    def test_zero_mip_count_raises(self):
        data = bytearray(_make_ctxr(64, 64, 7))
        data[0x25] = 0
        with self.assertRaises(ValueError):
            parse_ctxr_header(bytes(data))


# ── build_ctxr_header ─────────────────────────────────────────────────────────

class TestBuildCTXRHeader(unittest.TestCase):

    def test_magic_correct(self):
        hdr = build_ctxr_header(64, 64, 7, 64*64*7*BPP)
        self.assertEqual(struct.unpack_from('>I', hdr, 0)[0], CTXR_MAGIC)

    def test_total_buffer_size(self):
        pixel_used = 64 * 64 * BPP
        hdr = build_ctxr_header(64, 64, 1, pixel_used)
        total = struct.unpack_from('>I', hdr, 0x04)[0]
        self.assertEqual(total, pixel_used + CTXR_TRAILING_PAD)

    def test_used_data_size(self):
        pixel_used = 1024 * 1024 * BPP
        hdr = build_ctxr_header(1024, 1024, 1, pixel_used)
        used = struct.unpack_from('>I', hdr, 0x14)[0]
        self.assertEqual(used, pixel_used)

    def test_width_height_encoded(self):
        hdr = build_ctxr_header(256, 128, 9, 256*128*BPP)
        w = struct.unpack_from('>H', hdr, 0x2C)[0]
        h = struct.unpack_from('>H', hdr, 0x2E)[0]
        self.assertEqual(w, 256)
        self.assertEqual(h, 128)

    def test_mip_count_encoded(self):
        hdr = build_ctxr_header(64, 64, 7, 64*64*7*BPP)
        self.assertEqual(hdr[0x25], 7)

    def test_header_length(self):
        hdr = build_ctxr_header(64, 64, 7, 64*64*7*BPP)
        self.assertEqual(len(hdr), CTXR_HEADER_SIZE)

    def test_original_header_preserved(self):
        """Non-content fields from original_header must survive unchanged."""
        orig = bytearray(_make_ctxr(64, 64, 7)[:CTXR_HEADER_SIZE])
        # Put a sentinel byte in an opaque region
        orig[0x24] = 0xAB
        pixel_used = 128 * 128 * BPP
        hdr = build_ctxr_header(
            128, 128, 1, pixel_used,
            original_header=bytes(orig),
        )
        self.assertEqual(hdr[0x24], 0xAB, "Opaque field should be preserved")
        # But content-dependent fields must be updated
        w = struct.unpack_from('>H', hdr, 0x2C)[0]
        self.assertEqual(w, 128)

    def test_synthesised_without_original(self):
        """Without original_header the synthesised header must be parseable."""
        pixel_used = 64 * 64 * BPP
        pixel_data = bytes(pixel_used)
        full_file  = (build_ctxr_header(64, 64, 1, pixel_used)
                      + pixel_data + bytes(CTXR_TRAILING_PAD))
        w, h, mc, _ = parse_ctxr_header(full_file)
        self.assertEqual((w, h, mc), (64, 64, 1))


# ── parse_dds ─────────────────────────────────────────────────────────────────

class TestParseDDS(unittest.TestCase):

    def test_valid_rgba8_1024x1024(self):
        data = _make_dds(1024, 1024, 11)
        w, h, mc, pixels = parse_dds(data)
        self.assertEqual(w, 1024)
        self.assertEqual(h, 1024)
        self.assertEqual(mc, 11)

    def test_valid_rgba8_64x64(self):
        data = _make_dds(64, 64, 7)
        w, h, mc, _ = parse_dds(data)
        self.assertEqual((w, h, mc), (64, 64, 7))

    def test_pixel_bytes_correct_size(self):
        data = _make_dds(64, 64, 7)
        _, _, _, pixels = parse_dds(data)
        expected = sum(w * h * BPP for w, h, _ in mip_chain(64, 64, 7))
        self.assertEqual(len(pixels), expected)

    def test_bad_magic_raises(self):
        data = bytearray(_make_dds(64, 64, 1))
        data[:4] = b'FAIL'
        with self.assertRaises(ValueError):
            parse_dds(bytes(data))

    def test_compressed_bc1_raises(self):
        data = bytearray(_make_dds(64, 64, 1))
        # Set FourCC to DXT1 (BC1)
        data[0x54:0x58] = b'DXT1'
        # Clear RGB/A masks so it looks like a compressed format
        struct.pack_into('<I', data, 0x58, 0)   # RGBBitCount
        with self.assertRaises(ValueError):
            parse_dds(bytes(data))

    def test_wrong_channel_masks_accepted_as_bgra8(self):
        """Swapped R/B masks → BGRA8, which is now auto-reordered, not rejected."""
        import warnings
        data = bytearray(_make_dds(4, 4, 1))
        # Swap R and B masks → BGRA8
        struct.pack_into('<I', data, 0x5C, 0x00FF0000)  # R mask at blue position
        struct.pack_into('<I', data, 0x64, 0x000000FF)  # B mask at red position
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            w, h, mc, px = parse_dds(bytes(data))   # must not raise
        self.assertEqual((w, h, mc), (4, 4, 1))

    def test_too_small_raises(self):
        with self.assertRaises(ValueError):
            parse_dds(b'DDS ' + bytes(10))

    def test_zero_mip_count_treated_as_one(self):
        data = bytearray(_make_dds(64, 64, 1))
        struct.pack_into('<I', data, 0x1C, 0)   # mipMapCount = 0
        _, _, mc, _ = parse_dds(bytes(data))
        self.assertEqual(mc, 1)


# ── DDS layout reordering ─────────────────────────────────────────────────────

class TestDDSLayoutReorder(unittest.TestCase):
    """
    parse_dds must accept BGRA8, ARGB8 and ABGR8 and reorder them
    to canonical RGBA8 transparently.

    We build a 1×1 DDS with a single known pixel, feed it through
    parse_dds, and verify the output pixel is in RGBA order.
    """

    # Reference pixel with all channels distinct so any swap is detectable
    _R, _G, _B, _A = 0x11, 0x22, 0x33, 0x44

    def _make_dds_with_masks(self, pixel_bytes: bytes,
                              r_mask: int, g_mask: int,
                              b_mask: int, a_mask: int) -> bytes:
        """Build a 1×1 single-mip DDS with custom channel masks."""
        hdr = bytearray(build_dds_header(1, 1, 1))
        # Overwrite channel masks
        struct.pack_into('<I', hdr, 0x5C, r_mask)
        struct.pack_into('<I', hdr, 0x60, g_mask)
        struct.pack_into('<I', hdr, 0x64, b_mask)
        struct.pack_into('<I', hdr, 0x68, a_mask)
        return bytes(hdr) + pixel_bytes

    def test_rgba8_passthrough(self):
        """RGBA8 pixels must pass through unchanged."""
        pixel = bytes([self._R, self._G, self._B, self._A])
        dds = self._make_dds_with_masks(
            pixel,
            r_mask=0x000000FF, g_mask=0x0000FF00,
            b_mask=0x00FF0000, a_mask=0xFF000000,
        )
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, _, _, px = parse_dds(dds)
        self.assertEqual(list(px), [self._R, self._G, self._B, self._A])

    def test_bgra8_reordered(self):
        """BGRA8 (GIMP default) must be reordered to RGBA8."""
        # BGRA8 storage order: [B, G, R, A]
        pixel = bytes([self._B, self._G, self._R, self._A])
        dds = self._make_dds_with_masks(
            pixel,
            r_mask=0x00FF0000, g_mask=0x0000FF00,
            b_mask=0x000000FF, a_mask=0xFF000000,
        )
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, _, _, px = parse_dds(dds)
        self.assertEqual(list(px), [self._R, self._G, self._B, self._A],
                         "BGRA8 must be reordered to RGBA8")

    def test_argb8_reordered(self):
        """ARGB8 must be reordered to RGBA8."""
        # ARGB8 correct masks: R=0x0000FF00, G=0x00FF0000, B=0xFF000000, A=0x000000FF
        # Storage order: byte0=A, byte1=R, byte2=G, byte3=B
        pixel = bytes([self._A, self._R, self._G, self._B])
        dds = self._make_dds_with_masks(
            pixel,
            r_mask=0x0000FF00, g_mask=0x00FF0000,
            b_mask=0xFF000000, a_mask=0x000000FF,
        )
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, _, _, px = parse_dds(dds)
        # After reorder to RGBA: byte 0=R, byte 1=G, byte 2=B, byte 3=A
        self.assertEqual(px[0], self._R, "R must end up in byte 0")
        self.assertEqual(px[1], self._G, "G must end up in byte 1")
        self.assertEqual(px[2], self._B, "B must end up in byte 2")
        self.assertEqual(px[3], self._A, "A must end up in byte 3")

    def test_abgr8_reordered(self):
        """ABGR8 must be reordered to RGBA8 — specifically alpha must move."""
        # ABGR8 correct masks: R=0xFF000000, G=0x00FF0000, B=0x0000FF00, A=0x000000FF
        # Storage order: byte0=A, byte1=B, byte2=G, byte3=R
        pixel = bytes([self._A, self._B, self._G, self._R])
        dds = self._make_dds_with_masks(
            pixel,
            r_mask=0xFF000000, g_mask=0x00FF0000,
            b_mask=0x0000FF00, a_mask=0x000000FF,
        )
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, _, _, px = parse_dds(dds)
        self.assertEqual(px[0], self._R, "R must end up in byte 0")
        self.assertEqual(px[1], self._G, "G must end up in byte 1")
        self.assertEqual(px[2], self._B, "B must end up in byte 2")
        self.assertEqual(px[3], self._A, "A must end up in byte 3")

    def test_bgra8_alpha_preserved(self):
        """
        The critical real-world case: GIMP BGRA8 export.

        BGRA8 puts R in byte 2. Without reordering, the converter
        would read R as the alpha channel — making text with R≈255
        appear fully opaque even when intended to be semi-transparent.
        """
        # Semi-transparent white text: R=255 G=255 B=255 A=102 (40%)
        r, g, b, a = 255, 255, 255, 102
        # BGRA8 storage: [B, G, R, A]
        pixel = bytes([b, g, r, a])
        dds = self._make_dds_with_masks(
            pixel,
            r_mask=0x00FF0000, g_mask=0x0000FF00,
            b_mask=0x000000FF, a_mask=0xFF000000,
        )
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, _, _, px = parse_dds(dds)
        self.assertEqual(px[3], 102,
            "Alpha must be 102 (40%) not 255 after BGRA8 reorder")
        self.assertEqual(px[0], 255, "R must be 255")

    def test_reorder_issues_warning(self):
        """parse_dds must emit a UserWarning when reordering is needed."""
        import warnings
        pixel = bytes([self._B, self._G, self._R, self._A])   # BGRA8
        dds = self._make_dds_with_masks(
            pixel,
            r_mask=0x00FF0000, g_mask=0x0000FF00,
            b_mask=0x000000FF, a_mask=0xFF000000,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            parse_dds(dds)
        self.assertTrue(any("BGRA8" in str(warning.message) for warning in w),
                        "Expected a UserWarning mentioning BGRA8")

    def test_16bpp_still_rejected(self):
        """Non-32bpp formats must still raise ValueError."""
        dds = bytearray(_make_dds(4, 4, 1))
        struct.pack_into('<I', dds, 0x58, 16)   # RGBBitCount = 16
        for off in (0x5C, 0x60, 0x64, 0x68):
            struct.pack_into('<I', dds, off, 0)
        with self.assertRaises(ValueError):
            parse_dds(bytes(dds))


# ── build_dds_header ──────────────────────────────────────────────────────────

class TestBuildDDSHeader(unittest.TestCase):

    def test_magic(self):
        hdr = build_dds_header(64, 64, 1)
        self.assertEqual(hdr[:4], b'DDS ')

    def test_header_size_field(self):
        hdr = build_dds_header(64, 64, 1)
        self.assertEqual(struct.unpack_from('<I', hdr, 4)[0], 124)

    def test_width_height(self):
        hdr = build_dds_header(256, 128, 1)
        h = struct.unpack_from('<I', hdr, 12)[0]
        w = struct.unpack_from('<I', hdr, 16)[0]
        self.assertEqual(w, 256)
        self.assertEqual(h, 128)

    def test_mip_count(self):
        hdr = build_dds_header(64, 64, 9)
        mc = struct.unpack_from('<I', hdr, 0x1C)[0]
        self.assertEqual(mc, 9)

    def test_pitch(self):
        hdr = build_dds_header(512, 512, 1)
        pitch = struct.unpack_from('<I', hdr, 0x14)[0]
        self.assertEqual(pitch, 512 * BPP)

    def test_rgba8_masks(self):
        hdr = build_dds_header(64, 64, 1)
        self.assertEqual(struct.unpack_from('<I', hdr, 0x58)[0], 32)          # bit count
        self.assertEqual(struct.unpack_from('<I', hdr, 0x5C)[0], 0x000000FF)  # R
        self.assertEqual(struct.unpack_from('<I', hdr, 0x60)[0], 0x0000FF00)  # G
        self.assertEqual(struct.unpack_from('<I', hdr, 0x64)[0], 0x00FF0000)  # B
        self.assertEqual(struct.unpack_from('<I', hdr, 0x68)[0], 0xFF000000)  # A

    def test_output_length(self):
        self.assertEqual(len(build_dds_header(64, 64, 1)), 0x80)

    def test_round_trip_via_parse(self):
        """build_dds_header + zero pixels must be parseable by parse_dds."""
        pixel_data = bytes(64 * 64 * BPP)
        data = build_dds_header(64, 64, 1) + pixel_data
        w, h, mc, _ = parse_dds(data)
        self.assertEqual((w, h, mc), (64, 64, 1))


# ── Integration: build → parse round-trips ────────────────────────────────────

class TestBuildParseRoundTrips(unittest.TestCase):
    """
    End-to-end: build a complete file, parse it back, verify fields survive.
    """

    def test_ctxr_round_trip(self):
        dims_cases = [(64, 64, 7), (128, 128, 8), (512, 256, 10)]
        for w, h, mc in dims_cases:
            with self.subTest(w=w, h=h, mc=mc):
                data = _make_ctxr(w, h, mc)
                pw, ph, pmc, _ = parse_ctxr_header(data)
                self.assertEqual((pw, ph, pmc), (w, h, mc))

    def test_dds_round_trip(self):
        dims_cases = [(64, 64, 7), (256, 256, 9), (1024, 512, 11)]
        for w, h, mc in dims_cases:
            with self.subTest(w=w, h=h, mc=mc):
                data = _make_dds(w, h, mc)
                pw, ph, pmc, _ = parse_dds(data)
                self.assertEqual((pw, ph, pmc), (w, h, mc))


if __name__ == '__main__':
    unittest.main()
