"""
ctxr_tools.constants
====================
Shared numeric constants used across the package.

Keeping them in one place means a single source of truth — change a value
here and every module that imports it picks up the change automatically.
"""

# ── CTXR file layout ─────────────────────────────────────────────────────────

CTXR_HEADER_SIZE  = 0x80
"""Fixed size of the PS3 CTXR file header in bytes (always 128)."""

CTXR_TRAILING_PAD = 44
"""Zero bytes appended after all pixel data (alignment padding)."""

CTXR_MAGIC = 0x02000101
"""
Expected big-endian uint32 at offset 0x00 of a PS3 CTXR file.

The Aqua Library reads the file magic as a little-endian value (0x01010002)
and matches it in a switch statement.  When we read the same bytes as
big-endian we get 0x02000101 — both representations refer to the same
four bytes: 0x02, 0x00, 0x01, 0x01.
"""

# ── Pixel format ─────────────────────────────────────────────────────────────

BPP = 4
"""Bytes per pixel.  Only RGBA8 (32 bpp) is supported."""
