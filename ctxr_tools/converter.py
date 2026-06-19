"""
ctxr_tools.converter
====================
High-level conversion functions: CTXR → DDS and DDS → CTXR.

These are the functions you call from your own scripts or from the GUI.
They own all the file I/O and orchestrate the pipeline:

  CTXR → DDS
    parse_ctxr_header → iterate mip_chain → ps3_deswizzle + argb_to_rgba
    → build_dds_header → write

  DDS → CTXR
    parse_dds → iterate mip_chain → ps3_swizzle + rgba_to_argb
    → build_ctxr_header → write

The ``log`` parameter accepts any callable that takes a single string.
Pass ``print`` (the default) for terminal output, a GUI text-widget writer
for the interface, or ``lambda _: None`` to suppress all output.
"""

from typing import Callable, Optional

from .constants import CTXR_HEADER_SIZE, CTXR_TRAILING_PAD
from .formats   import (
    parse_ctxr_header, build_ctxr_header,
    parse_dds,         build_dds_header,
    mip_chain,
)
from .swizzle   import ps3_swizzle, ps3_deswizzle, argb_to_rgba, rgba_to_argb

Log = Callable[[str], None]


def ctxr_to_dds(ctxr_path: str, dds_path: str, log: Log = print) -> None:
    """
    Convert a PS3 CTXR texture file to an uncompressed RGBA8 DDS file.

    Pipeline
    --------
    1. Read the CTXR file and parse its 128-byte header to get width,
       height, and mip count.
    2. For each mip level (largest first):

       a. Slice the raw PS3-tiled ARGB pixel bytes from the pixel region.
       b. Apply ``ps3_deswizzle`` to convert Morton-curve layout → linear.
       c. Apply ``argb_to_rgba`` to rotate the channel order.

    3. Build a standard DDS header and write header + linear pixels to disk.

    Parameters
    ----------
    ctxr_path:
        Path to the source ``.ctxr`` file.
    dds_path:
        Path to write the output ``.dds`` file.
    log:
        Callable used for progress messages.  Defaults to ``print``.

    Raises
    ------
    ValueError
        If the CTXR header is invalid or the pixel region is truncated.
    OSError
        If either file cannot be opened.
    """
    log("[CTXR → DDS]")
    log(f"  Input  : {ctxr_path}")
    log(f"  Output : {dds_path}")

    ctxr_data = open(ctxr_path, 'rb').read()
    width, height, mip_count, slice_count = parse_ctxr_header(ctxr_data)
    log(f"\n  Texture : {width}×{height},  {mip_count} mip(s),  {slice_count} slice(s)")

    pixel_region = ctxr_data[CTXR_HEADER_SIZE:]
    out_pixels   = bytearray()
    offset       = 0

    for m, (w, h, size) in enumerate(mip_chain(width, height, mip_count)):
        chunk = pixel_region[offset:offset + size]
        if len(chunk) != size:
            raise ValueError(
                f"CTXR pixel data truncated at mip {m} ({w}×{h}): "
                f"need {size} bytes, got {len(chunk)}"
            )
        out_pixels += argb_to_rgba(ps3_deswizzle(chunk, w, h))
        log(f"  Mip {m:2d}  : {w:4d}×{h:4d}  {size:8d} bytes  ✓")
        offset += size

    dds_header = build_dds_header(width, height, mip_count)
    open(dds_path, 'wb').write(dds_header + bytes(out_pixels))
    log(f"\n  Saved → {dds_path}")


def dds_to_ctxr(
    dds_path: str,
    ctxr_path: str,
    original_ctxr_path: Optional[str] = None,
    log: Log = print,
) -> None:
    """
    Convert an uncompressed RGBA8 DDS file back to a PS3 CTXR texture file.

    Pipeline
    --------
    1. Read the DDS file and validate its pixel format (must be RGBA8).
    2. Optionally load the first 128 bytes of the original CTXR as a header
       template (strongly recommended to preserve unknown/opaque fields).
    3. For each mip level (largest first):

       a. Slice the linear RGBA pixel bytes.
       b. Apply ``ps3_swizzle`` to convert linear layout → Morton-curve.
       c. Apply ``rgba_to_argb`` to rotate the channel order.

    4. Build the CTXR header (patching the five content-dependent fields),
       concatenate header + swizzled pixels + 44 zero-byte padding, write.

    Parameters
    ----------
    dds_path:
        Path to the source ``.dds`` file (must be uncompressed RGBA8).
    ctxr_path:
        Path to write the output ``.ctxr`` file.
    original_ctxr_path:
        Optional path to the original ``.ctxr`` file.  Its header bytes are
        used as a template so opaque fields are preserved verbatim.  If
        omitted, a header is synthesised from SOTC PS3 constants — this may
        not work correctly in every PS3 title.
    log:
        Callable used for progress messages.  Defaults to ``print``.

    Raises
    ------
    ValueError
        If the DDS pixel format is not RGBA8, or the pixel region is
        truncated.
    OSError
        If any file cannot be opened.
    """
    log("[DDS → CTXR]")
    log(f"  Input DDS  : {dds_path}")
    if original_ctxr_path:
        log(f"  Orig CTXR  : {original_ctxr_path}")
    else:
        log(f"  Orig CTXR  : (none — synthesising header)")
    log(f"  Output     : {ctxr_path}")

    dds_data = open(dds_path, 'rb').read()

    original_header: Optional[bytes] = None
    if original_ctxr_path:
        orig = open(original_ctxr_path, 'rb').read()
        if len(orig) < CTXR_HEADER_SIZE:
            raise ValueError(
                f"Original CTXR too small ({len(orig)} bytes, need ≥ {CTXR_HEADER_SIZE})"
            )
        original_header = orig[:CTXR_HEADER_SIZE]

    width, height, mip_count, dds_pixels = parse_dds(dds_data)
    log(f"\n  Texture    : {width}×{height},  {mip_count} mip(s),  RGBA8 uncompressed")

    out_pixels = bytearray()
    offset     = 0

    for m, (w, h, size) in enumerate(mip_chain(width, height, mip_count)):
        chunk = dds_pixels[offset:offset + size]
        if len(chunk) != size:
            raise ValueError(
                f"DDS pixel data truncated at mip {m} ({w}×{h}): "
                f"need {size} bytes, got {len(chunk)}"
            )
        out_pixels += rgba_to_argb(ps3_swizzle(chunk, w, h))
        log(f"  Mip {m:2d}     : {w:4d}×{h:4d}  {size:8d} bytes  ✓")
        offset += size

    pixel_data_used = len(out_pixels)
    hdr = build_ctxr_header(
        width=width, height=height, mip_count=mip_count,
        pixel_data_used=pixel_data_used,
        original_header=original_header,
    )
    output = hdr + bytes(out_pixels) + bytes(CTXR_TRAILING_PAD)

    hdr_src = 'original header + patched fields' if original_header else 'synthesised'
    log(f"\n  Header     : {CTXR_HEADER_SIZE} bytes  ({hdr_src})")
    log(f"  Pixel data : {pixel_data_used} bytes  (0x{pixel_data_used:X})")
    log(f"  Padding    : {CTXR_TRAILING_PAD} bytes")
    log(f"  Total      : {len(output)} bytes  (0x{len(output):X})")

    open(ctxr_path, 'wb').write(output)
    log(f"\n  Saved → {ctxr_path}")
