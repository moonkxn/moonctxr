"""
ctxr_tools.formats
==================
CTXR and DDS header parsing and building.

This module knows the binary layout of both file formats but contains no
swizzle or conversion logic — that lives in ``swizzle.py`` and
``converter.py``.

CTXR header layout (PS3 variant, all fields big-endian)
--------------------------------------------------------
  Offset  Size  Field
  0x00    4     magic = 0x02000101  (LE identifier 0x01010002)
  0x04    4     totalBufferSize = file_size − 0x80
  0x08    4     const = 0x00000001
  0x0C    4     const = 0x00000000
  0x10    4     const = 0x00000080  (header size)
  0x14    4     usedDataSize = sum of raw mip pixel bytes
  0x18    4     const = 0x00000000
  0x1C    4     const = 0xBFBFBF80  (opaque, game-specific)
  0x20    4     const = 0x00000000
  0x24    1     const = 0x85        (opaque)
  0x25    1     mipCount
  0x26    1     const = 0x02
  0x27    1     const = 0x00
  0x28    2     const = 0x0000
  0x2A    1     const = 0xAA        (opaque)
  0x2B    1     const = 0xE4        (opaque)
  0x2C    2     width   (BE uint16)
  0x2E    2     height  (BE uint16)
  0x30    2     sliceCount (BE uint16, = 1 for standard textures)
  0x32–0x7F    zeros

Only five fields change when texture content changes:
  totalBufferSize, usedDataSize, mipCount, width, height.
All other fields are preserved verbatim from the original file when
available, or synthesised from the constants listed above.

DDS header layout (uncompressed 32-bit RGBA, all fields little-endian)
-----------------------------------------------------------------------
  Standard 128-byte header (no DX10 extension).
  Accepted channel layouts: RGBA8, BGRA8, ARGB8, ABGR8.
  All are automatically reordered to canonical RGBA8 on read.
  See ``build_dds_header`` docstring for the full field map.
"""

import struct
from typing import Optional

from .constants import BPP, CTXR_HEADER_SIZE, CTXR_MAGIC, CTXR_TRAILING_PAD


# ── Mip chain helper ──────────────────────────────────────────────────────────

def mip_chain(width: int, height: int, mip_count: int):
    """
    Yield ``(w, h, byte_size)`` for each mip level, largest first.

    Each level halves in both dimensions down to a minimum of 1×1.
    ``byte_size = w * h * BPP`` (RGBA8, no block-compression rounding).

    Parameters
    ----------
    width, height:
        Dimensions of the top-level (mip 0) texture.
    mip_count:
        Number of mip levels to yield.

    Yields
    ------
    tuple[int, int, int]
        *(w, h, byte_size)* for each mip level.
    """
    w, h = width, height
    for _ in range(mip_count):
        yield w, h, w * h * BPP
        w = max(1, w >> 1)
        h = max(1, h >> 1)


# ── CTXR ─────────────────────────────────────────────────────────────────────

def parse_ctxr_header(data: bytes) -> tuple[int, int, int, int]:
    """
    Parse the 128-byte PS3 CTXR header.

    Parameters
    ----------
    data:
        Raw bytes of the entire CTXR file (or at least the first 0x80 bytes).

    Returns
    -------
    tuple[int, int, int, int]
        *(width, height, mip_count, slice_count)*

    Raises
    ------
    ValueError
        If the magic is wrong, the size sentinel does not match, or the
        dimensions / mip count are zero.
    """
    if len(data) < CTXR_HEADER_SIZE:
        raise ValueError(
            f"File too small to be a CTXR ({len(data)} bytes, need ≥ {CTXR_HEADER_SIZE})"
        )

    magic = struct.unpack_from('>I', data, 0x00)[0]
    if magic != CTXR_MAGIC:
        raise ValueError(
            f"Not a PS3 CTXR file — magic 0x{magic:08X}, expected 0x{CTXR_MAGIC:08X}"
        )

    # The totalBufferSize field must equal file_size − header_size.
    # This acts as a second sanity check that the file is not truncated.
    total_buf = struct.unpack_from('>I', data, 0x04)[0]
    expected  = len(data) - CTXR_HEADER_SIZE
    if total_buf != expected:
        raise ValueError(
            f"CTXR size sentinel mismatch: header says {total_buf} pixel bytes, "
            f"file has {expected}. File may be truncated or not a PS3 CTXR."
        )

    width       = struct.unpack_from('>H', data, 0x2C)[0]
    height      = struct.unpack_from('>H', data, 0x2E)[0]
    mip_count   = data[0x25]
    slice_count = struct.unpack_from('>H', data, 0x30)[0]

    if width == 0 or height == 0:
        raise ValueError(f"CTXR reports invalid dimensions: {width}×{height}")
    if mip_count == 0:
        raise ValueError("CTXR header reports 0 mip levels")

    return width, height, mip_count, slice_count


def build_ctxr_header(
    width: int,
    height: int,
    mip_count: int,
    pixel_data_used: int,
    original_header: Optional[bytes] = None,
) -> bytes:
    """
    Build a 128-byte PS3 CTXR header.

    Strategy
    --------
    If *original_header* is provided it is copied byte-for-byte and only
    the five content-dependent fields are patched.  This preserves every
    opaque / unknown byte exactly, making the output as close to the
    original as possible.

    Without *original_header*, a header is synthesised from the constant
    values observed in SOTC PS3 textures.  This is fine for newly created
    textures but may not work in every PS3 title.

    Parameters
    ----------
    width, height:
        Texture dimensions in pixels.
    mip_count:
        Number of mip levels.
    pixel_data_used:
        Total bytes of pixel data (excluding the 44-byte trailing padding).
    original_header:
        Optional 128-byte header from the source CTXR file.

    Returns
    -------
    bytes
        The 128-byte CTXR header.
    """
    total_buf = pixel_data_used + CTXR_TRAILING_PAD   # = file_size − 0x80

    if original_header is not None:
        if len(original_header) < CTXR_HEADER_SIZE:
            raise ValueError(
                f"original_header is too short ({len(original_header)} bytes)"
            )
        hdr = bytearray(original_header[:CTXR_HEADER_SIZE])
    else:
        # Synthesise from observed SOTC PS3 constants
        hdr = bytearray(CTXR_HEADER_SIZE)
        struct.pack_into('>I', hdr, 0x00, CTXR_MAGIC)
        struct.pack_into('>I', hdr, 0x08, 0x00000001)
        struct.pack_into('>I', hdr, 0x10, 0x00000080)
        struct.pack_into('>I', hdr, 0x18, 0x00000000)
        struct.pack_into('>I', hdr, 0x1C, 0xBFBFBF80)
        hdr[0x24] = 0x85
        hdr[0x26] = 0x02
        hdr[0x2A] = 0xAA
        hdr[0x2B] = 0xE4
        struct.pack_into('>H', hdr, 0x30, 1)  # sliceCount

    # Patch the five fields that always depend on texture content
    struct.pack_into('>I', hdr, 0x04, total_buf)
    struct.pack_into('>I', hdr, 0x14, pixel_data_used)
    hdr[0x25] = mip_count & 0xFF
    struct.pack_into('>H', hdr, 0x2C, width)
    struct.pack_into('>H', hdr, 0x2E, height)

    return bytes(hdr)


# ── DDS ──────────────────────────────────────────────────────────────────────

def _mask_to_shift(mask: int) -> int:
    """
    Return the byte shift for a 32-bit channel mask.

    For example 0x000000FF → 0,  0x0000FF00 → 1,
                0x00FF0000 → 2,  0xFF000000 → 3.
    """
    if mask == 0:
        return 0
    shift = 0
    while not (mask & 0xFF):
        mask >>= 8
        shift += 1
    return shift


def _reorder_pixels(pixels: bytes, r_shift: int, g_shift: int,
                    b_shift: int, a_shift: int) -> bytes:
    """
    Reorder every 4-byte pixel so the output is canonical RGBA8
    (R in byte 0, G in byte 1, B in byte 2, A in byte 3).

    If the input is already RGBA8 (shifts = 0,1,2,3) the data is returned
    unchanged without copying.
    """
    if (r_shift, g_shift, b_shift, a_shift) == (0, 1, 2, 3):
        return pixels   # already canonical RGBA8 — no work needed
    out = bytearray(len(pixels))
    for i in range(0, len(pixels), 4):
        out[i]     = pixels[i + r_shift]
        out[i + 1] = pixels[i + g_shift]
        out[i + 2] = pixels[i + b_shift]
        out[i + 3] = pixels[i + a_shift]
    return bytes(out)


# Common 32-bit RGBA layout names for the error message.
# Key = (r_mask, g_mask, b_mask, a_mask) as written in the DDS pixel format block.
_LAYOUT_NAMES = {
    (0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000): "RGBA8",   # R@byte0
    (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000): "BGRA8",   # B@byte0 — GIMP default
    (0x0000FF00, 0x00FF0000, 0xFF000000, 0x000000FF): "ARGB8",   # A@byte0
    (0xFF000000, 0x00FF0000, 0x0000FF00, 0x000000FF): "ABGR8",   # A@byte0, B@byte1
}


def parse_dds(data: bytes) -> tuple[int, int, int, bytes]:
    """
    Parse a DDS file and extract header fields plus raw pixel bytes.

    Accepted formats
    ----------------
    Any uncompressed 32-bit RGBA layout is accepted and automatically
    reordered to canonical RGBA8 (R in byte 0):

      - RGBA8   R=0x000000FF  G=0x0000FF00  B=0x00FF0000  A=0xFF000000
      - BGRA8   R=0x00FF0000  G=0x0000FF00  B=0x000000FF  A=0xFF000000
      - ARGB8   R=0xFF000000  G=0x00FF0000  B=0x0000FF00  A=0x000000FF
      - ABGR8   R=0x0000FF00  G=0x00FF0000  B=0xFF000000  A=0x000000FF

    GIMP exports BGRA8 by default when "RGBA8" is selected in its DDS
    plugin — this is handled transparently.

    Parameters
    ----------
    data:
        Raw bytes of the entire DDS file.

    Returns
    -------
    tuple[int, int, int, bytes]
        *(width, height, mip_count, pixel_bytes)*
        pixel_bytes are always in canonical RGBA8 order.

    Raises
    ------
    ValueError
        If the file is not a DDS, is compressed, or is not 32 bpp.
    """
    if len(data) < 0x80:
        raise ValueError("File too small to be a DDS")
    if data[:4] != b'DDS ':
        raise ValueError("Not a DDS file — missing 'DDS ' magic")

    height    = struct.unpack_from('<I', data, 0x0C)[0]
    width     = struct.unpack_from('<I', data, 0x10)[0]
    mip_count = struct.unpack_from('<I', data, 0x1C)[0] or 1

    # DDS_PIXELFORMAT block at file offset 0x4C
    fourcc   = data[0x54:0x58]
    rgb_bits = struct.unpack_from('<I', data, 0x58)[0]
    r_mask   = struct.unpack_from('<I', data, 0x5C)[0]
    g_mask   = struct.unpack_from('<I', data, 0x60)[0]
    b_mask   = struct.unpack_from('<I', data, 0x64)[0]
    a_mask   = struct.unpack_from('<I', data, 0x68)[0]

    # Must be 32 bpp and uncompressed (no FourCC) with an alpha channel
    if rgb_bits != 32 or (fourcc not in (b'\x00\x00\x00\x00', b'DX10') and a_mask == 0):
        layout = _LAYOUT_NAMES.get((r_mask, g_mask, b_mask, a_mask), "unknown layout")
        raise ValueError(
            f"Only uncompressed 32-bit RGBA DDS is supported (got {layout}).\n"
            f"  BitsPerPixel = {rgb_bits},  FourCC = {fourcc!r}\n"
            f"  R = 0x{r_mask:08X}  G = 0x{g_mask:08X}  "
            f"B = 0x{b_mask:08X}  A = 0x{a_mask:08X}\n\n"
            "Export your texture as 32-bit RGBA (uncompressed) from your image editor.\n"
            "Accepted layouts: RGBA8, BGRA8, ARGB8, ABGR8."
        )

    # Work out where each channel lives and reorder to canonical RGBA8
    r_shift = _mask_to_shift(r_mask)
    g_shift = _mask_to_shift(g_mask)
    b_shift = _mask_to_shift(b_mask)
    a_shift = _mask_to_shift(a_mask)

    pixel_start = 0xA0 if fourcc == b'DX10' else 0x80
    raw_pixels  = data[pixel_start:]

    layout_name = _LAYOUT_NAMES.get((r_mask, g_mask, b_mask, a_mask), "custom")
    if layout_name != "RGBA8":
        # Log the reorder so callers can surface it if needed
        import warnings
        warnings.warn(
            f"DDS channel layout is {layout_name} — reordering to RGBA8 automatically.",
            stacklevel=2,
        )

    return width, height, mip_count, _reorder_pixels(raw_pixels, r_shift, g_shift,
                                                      b_shift, a_shift)


def build_dds_header(width: int, height: int, mip_count: int) -> bytes:
    """
    Build a standard 128-byte DDS header for uncompressed RGBA8.

    Field map (all little-endian)
    -----------------------------
    ::

      0x00  'DDS '              magic (4 bytes, outside DDS_HEADER struct)
      0x04  124                 dwSize of DDS_HEADER
      0x08  0x0002100F          dwFlags  (CAPS|HEIGHT|WIDTH|PIXELFORMAT|MIPMAPCOUNT|PITCH)
      0x0C  height
      0x10  width
      0x14  width * 4           dwPitchOrLinearSize (bytes per row)
      0x18  1                   dwDepth
      0x1C  mip_count           dwMipMapCount
      0x20–0x49                 dwReserved1[11]  (zeros)
      0x4C  32                  DDS_PIXELFORMAT.dwSize
      0x50  0x41                DDS_PIXELFORMAT.dwFlags  (DDPF_RGB|DDPF_ALPHAPIXELS)
      0x54  0                   DDS_PIXELFORMAT.dwFourCC  (unused, uncompressed)
      0x58  32                  DDS_PIXELFORMAT.dwRGBBitCount
      0x5C  0x000000FF          DDS_PIXELFORMAT.dwRBitMask
      0x60  0x0000FF00          DDS_PIXELFORMAT.dwGBitMask
      0x64  0x00FF0000          DDS_PIXELFORMAT.dwBBitMask
      0x68  0xFF000000          DDS_PIXELFORMAT.dwABitMask
      0x6C  0x00401008          dwCaps  (COMPLEX|MIPMAP|TEXTURE)
      0x70–0x7F                 dwCaps2, reserved  (zeros)

    Parameters
    ----------
    width, height:
        Texture dimensions in pixels.
    mip_count:
        Number of mip levels.

    Returns
    -------
    bytes
        The 128-byte DDS header.
    """
    hdr = bytearray(0x80)
    p   = struct.pack_into
    p('<4s', hdr, 0x00, b'DDS ')
    p('<I',  hdr, 0x04, 124)
    p('<I',  hdr, 0x08, 0x0002100F)
    p('<I',  hdr, 0x0C, height)
    p('<I',  hdr, 0x10, width)
    p('<I',  hdr, 0x14, width * BPP)   # pitch = bytes per row
    p('<I',  hdr, 0x18, 1)             # depth
    p('<I',  hdr, 0x1C, mip_count)
    p('<I',  hdr, 0x4C, 32)            # pfSize
    p('<I',  hdr, 0x50, 0x41)          # DDPF_RGB | DDPF_ALPHAPIXELS
    p('<I',  hdr, 0x54, 0)             # FourCC (none)
    p('<I',  hdr, 0x58, 32)            # RGBBitCount
    p('<I',  hdr, 0x5C, 0x000000FF)    # R mask
    p('<I',  hdr, 0x60, 0x0000FF00)    # G mask
    p('<I',  hdr, 0x64, 0x00FF0000)    # B mask
    p('<I',  hdr, 0x68, 0xFF000000)    # A mask
    p('<I',  hdr, 0x6C, 0x00401008)    # COMPLEX|MIPMAP|TEXTURE
    return bytes(hdr)
