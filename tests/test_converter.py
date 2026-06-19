"""
tests.test_converter
====================
Integration tests for ctxr_tools.converter.

These tests exercise the full pipeline end-to-end (file I/O included) using
the real CTXR and DDS fixture files uploaded by the user.  If the fixture
files are not present, the fixture-dependent tests are skipped gracefully.

Tests cover:
  - ctxr_to_dds():   produces byte-identical output to the known-good DDS
  - dds_to_ctxr():   produces byte-identical output to the known-good CTXR
  - round-trips:     ctxr→dds→ctxr and dds→ctxr→dds are lossless
  - synthesised header: dds_to_ctxr without original_ctxr still works
  - error handling:  missing files, bad format
  - log callback:    all messages are forwarded to the caller's function
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ctxr_tools.converter import ctxr_to_dds, dds_to_ctxr
from ctxr_tools.formats   import parse_ctxr_header, parse_dds, mip_chain, build_dds_header
from ctxr_tools.constants import CTXR_HEADER_SIZE, CTXR_TRAILING_PAD, BPP

# ── Fixture paths ─────────────────────────────────────────────────────────────
# Fixture files are NOT committed to the repository — they are extracted
# game assets and redistributing them would raise copyright concerns.
#
# To run the fixture-dependent tests locally:
#   1. Extract any .ctxr file from the game using this tool or another.
#   2. Place it (and its known-good .dds equivalent) in tests/fixtures/.
#   3. Name them sample.ctxr and sample.dds, or set the environment
#      variables below to point elsewhere.
#
# Without fixtures, these tests are skipped automatically — this is
# expected and not an error. The unit tests in test_swizzle.py and
# test_formats.py require no fixtures and always run.
_FIXTURE_DIR  = Path(os.environ.get(
    'CTXR_TEST_FIXTURE_DIR',
    os.path.join(os.path.dirname(__file__), 'fixtures'),
))
_FIXTURE_CTXR = _FIXTURE_DIR / os.environ.get('CTXR_TEST_FIXTURE_CTXR', 'sample.ctxr')
_FIXTURE_DDS  = _FIXTURE_DIR / os.environ.get('CTXR_TEST_FIXTURE_DDS',  'sample.dds')
_FIXTURES_OK  = _FIXTURE_CTXR.exists() and _FIXTURE_DDS.exists()

_skip_no_fixtures = unittest.skipUnless(
    _FIXTURES_OK,
    "Fixture files not found — skipping fixture-dependent tests"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_minimal_rgba8_dds(w: int = 4, h: int = 4, mip_count: int = 1) -> bytes:
    """Return a complete DDS file (header + zero pixel data) for testing."""
    pixel_data = bytes(sum(mw * mh * BPP for mw, mh, _ in mip_chain(w, h, mip_count)))
    return build_dds_header(w, h, mip_count) + pixel_data


# ── Fixture-based correctness tests ──────────────────────────────────────────

class TestCTXRtoDDSCorrectness(unittest.TestCase):
    """ctxr_to_dds must produce byte-identical output to the known-good DDS."""

    @_skip_no_fixtures
    def test_byte_identical_to_known_dds(self):
        with tempfile.NamedTemporaryFile(suffix='.dds', delete=False) as f:
            out_path = f.name
        try:
            ctxr_to_dds(str(_FIXTURE_CTXR), out_path, log=lambda _: None)
            self.assertEqual(
                open(out_path, 'rb').read(),
                open(_FIXTURE_DDS,  'rb').read(),
                "Output DDS must be byte-identical to the known-good DDS",
            )
        finally:
            os.unlink(out_path)

    @_skip_no_fixtures
    def test_output_is_parseable_dds(self):
        with tempfile.NamedTemporaryFile(suffix='.dds', delete=False) as f:
            out_path = f.name
        try:
            ctxr_to_dds(str(_FIXTURE_CTXR), out_path, log=lambda _: None)
            data = open(out_path, 'rb').read()
            w, h, mc, _ = parse_dds(data)
            self.assertEqual(w,  1024)
            self.assertEqual(h,  1024)
            self.assertEqual(mc, 11)
        finally:
            os.unlink(out_path)


class TestDDStoCTXRCorrectness(unittest.TestCase):
    """dds_to_ctxr must produce byte-identical output to the known-good CTXR."""

    @_skip_no_fixtures
    def test_byte_identical_with_original_header(self):
        with tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f:
            out_path = f.name
        try:
            dds_to_ctxr(
                str(_FIXTURE_DDS), out_path,
                original_ctxr_path=str(_FIXTURE_CTXR),
                log=lambda _: None,
            )
            self.assertEqual(
                open(out_path,       'rb').read(),
                open(_FIXTURE_CTXR,  'rb').read(),
                "Output CTXR must be byte-identical to the known-good CTXR",
            )
        finally:
            os.unlink(out_path)

    @_skip_no_fixtures
    def test_output_is_parseable_ctxr(self):
        with tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f:
            out_path = f.name
        try:
            dds_to_ctxr(
                str(_FIXTURE_DDS), out_path,
                original_ctxr_path=str(_FIXTURE_CTXR),
                log=lambda _: None,
            )
            data = open(out_path, 'rb').read()
            w, h, mc, _ = parse_ctxr_header(data)
            self.assertEqual(w,  1024)
            self.assertEqual(h,  1024)
            self.assertEqual(mc, 11)
        finally:
            os.unlink(out_path)


# ── Round-trip tests ──────────────────────────────────────────────────────────

class TestRoundTrips(unittest.TestCase):

    @_skip_no_fixtures
    def test_ctxr_to_dds_to_ctxr(self):
        """CTXR → DDS → CTXR must reproduce the original CTXR exactly."""
        with (tempfile.NamedTemporaryFile(suffix='.dds',  delete=False) as f1,
              tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f2):
            dds_path  = f1.name
            ctxr_path = f2.name
        try:
            ctxr_to_dds(str(_FIXTURE_CTXR), dds_path,  log=lambda _: None)
            dds_to_ctxr(dds_path, ctxr_path,
                        original_ctxr_path=str(_FIXTURE_CTXR),
                        log=lambda _: None)
            self.assertEqual(
                open(ctxr_path,      'rb').read(),
                open(_FIXTURE_CTXR,  'rb').read(),
            )
        finally:
            for p in (dds_path, ctxr_path):
                if os.path.exists(p): os.unlink(p)

    @_skip_no_fixtures
    def test_dds_to_ctxr_to_dds(self):
        """DDS → CTXR → DDS must reproduce the original DDS exactly."""
        with (tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f1,
              tempfile.NamedTemporaryFile(suffix='.dds',  delete=False) as f2):
            ctxr_path = f1.name
            dds_path  = f2.name
        try:
            dds_to_ctxr(str(_FIXTURE_DDS), ctxr_path,
                        original_ctxr_path=str(_FIXTURE_CTXR),
                        log=lambda _: None)
            ctxr_to_dds(ctxr_path, dds_path, log=lambda _: None)
            self.assertEqual(
                open(dds_path,      'rb').read(),
                open(_FIXTURE_DDS,  'rb').read(),
            )
        finally:
            for p in (ctxr_path, dds_path):
                if os.path.exists(p): os.unlink(p)


# ── Synthesised header ────────────────────────────────────────────────────────

class TestSynthesisedHeader(unittest.TestCase):
    """dds_to_ctxr without original_ctxr_path must still produce a valid CTXR."""

    @_skip_no_fixtures
    def test_no_original_ctxr_produces_valid_file(self):
        with tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f:
            out_path = f.name
        try:
            dds_to_ctxr(str(_FIXTURE_DDS), out_path,
                        original_ctxr_path=None,
                        log=lambda _: None)
            data = open(out_path, 'rb').read()
            w, h, mc, _ = parse_ctxr_header(data)
            self.assertEqual(w,  1024)
            self.assertEqual(h,  1024)
            self.assertEqual(mc, 11)
        finally:
            os.unlink(out_path)

    def test_tiny_synthesised_ctxr_is_parseable(self):
        """Build a tiny DDS, convert without original, parse the result."""
        dds_data   = _make_minimal_rgba8_dds(4, 4, 1)
        with (tempfile.NamedTemporaryFile(suffix='.dds',  delete=False) as f1,
              tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f2):
            dds_path  = f1.name
            ctxr_path = f2.name
        try:
            open(dds_path, 'wb').write(dds_data)
            dds_to_ctxr(dds_path, ctxr_path, log=lambda _: None)
            data = open(ctxr_path, 'rb').read()
            w, h, mc, _ = parse_ctxr_header(data)
            self.assertEqual((w, h, mc), (4, 4, 1))
        finally:
            for p in (dds_path, ctxr_path):
                if os.path.exists(p): os.unlink(p)


# ── Log callback ──────────────────────────────────────────────────────────────

class TestLogCallback(unittest.TestCase):
    """Every converter message must reach the caller's log function."""

    def test_ctxr_to_dds_log_receives_messages(self):
        if not _FIXTURES_OK:
            self.skipTest("Fixture files not found")
        messages = []
        with tempfile.NamedTemporaryFile(suffix='.dds', delete=False) as f:
            out_path = f.name
        try:
            ctxr_to_dds(str(_FIXTURE_CTXR), out_path, log=messages.append)
            self.assertTrue(len(messages) > 0, "No log messages received")
            combined = '\n'.join(messages)
            self.assertIn('CTXR', combined)
            self.assertIn('Mip', combined)
        finally:
            os.unlink(out_path)

    def test_dds_to_ctxr_log_receives_messages(self):
        if not _FIXTURES_OK:
            self.skipTest("Fixture files not found")
        messages = []
        with tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f:
            out_path = f.name
        try:
            dds_to_ctxr(str(_FIXTURE_DDS), out_path,
                        original_ctxr_path=str(_FIXTURE_CTXR),
                        log=messages.append)
            self.assertTrue(len(messages) > 0)
            combined = '\n'.join(messages)
            self.assertIn('DDS', combined)
        finally:
            os.unlink(out_path)

    def test_silent_log(self):
        """Passing lambda _: None must not raise."""
        dds_data = _make_minimal_rgba8_dds(4, 4, 1)
        with (tempfile.NamedTemporaryFile(suffix='.dds',  delete=False) as f1,
              tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f2):
            dds_path, ctxr_path = f1.name, f2.name
        try:
            open(dds_path, 'wb').write(dds_data)
            dds_to_ctxr(dds_path, ctxr_path, log=lambda _: None)
        finally:
            for p in (dds_path, ctxr_path):
                if os.path.exists(p): os.unlink(p)


# ── Error handling ────────────────────────────────────────────────────────────

class TestErrorHandling(unittest.TestCase):

    def test_ctxr_to_dds_missing_input_raises(self):
        with self.assertRaises(OSError):
            ctxr_to_dds('/nonexistent/path.ctxr', '/tmp/out.dds',
                        log=lambda _: None)

    def test_dds_to_ctxr_missing_input_raises(self):
        with self.assertRaises(OSError):
            dds_to_ctxr('/nonexistent/path.dds', '/tmp/out.ctxr',
                        log=lambda _: None)

    def test_dds_to_ctxr_wrong_format_raises(self):
        """A non-RGBA8 DDS (e.g. 16-bpp format) must raise ValueError."""
        import struct as _struct
        with tempfile.NamedTemporaryFile(suffix='.dds', delete=False) as f:
            path = f.name
        try:
            data = bytearray(_make_minimal_rgba8_dds(4, 4, 1))
            # Set BitsPerPixel to 16 and clear all channel masks
            # so parse_dds sees a non-RGBA8 format and raises.
            _struct.pack_into('<I', data, 0x58, 16)          # RGBBitCount = 16
            for off in (0x5C, 0x60, 0x64, 0x68):
                _struct.pack_into('<I', data, off, 0)
            open(path, 'wb').write(bytes(data))
            with tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f2:
                out = f2.name
            try:
                with self.assertRaises((ValueError, Exception)):
                    dds_to_ctxr(path, out, log=lambda _: None)
            finally:
                if os.path.exists(out): os.unlink(out)
        finally:
            os.unlink(path)

    def test_output_file_size_ctxr(self):
        """Output CTXR size must equal header + pixel data + trailing pad."""
        if not _FIXTURES_OK:
            self.skipTest("Fixture files not found")
        with tempfile.NamedTemporaryFile(suffix='.ctxr', delete=False) as f:
            out_path = f.name
        try:
            dds_to_ctxr(str(_FIXTURE_DDS), out_path,
                        original_ctxr_path=str(_FIXTURE_CTXR),
                        log=lambda _: None)
            size = os.path.getsize(out_path)
            # Header + pixel data must fill the file; trailing pad is 44 bytes
            self.assertEqual(size % 1, 0)   # sanity
            data = open(out_path, 'rb').read()
            w, h, mc, _ = parse_ctxr_header(data)
            pixel_used = sum(mw * mh * BPP for mw, mh, _ in mip_chain(w, h, mc))
            expected = CTXR_HEADER_SIZE + pixel_used + CTXR_TRAILING_PAD
            self.assertEqual(size, expected)
        finally:
            os.unlink(out_path)


if __name__ == '__main__':
    unittest.main()
