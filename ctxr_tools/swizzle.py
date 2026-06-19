"""
ctxr_tools.swizzle
==================
PS3 Morton (Z-curve) swizzle / deswizzle and ARGB ↔ RGBA channel reordering.

Background
----------
The PS3 RSX GPU does not store texture mip levels in simple row-major
(linear) order.  Instead it uses a *Morton curve* (also called a Z-order
curve or Z-curve): the bits of the X and Y pixel coordinates are
interleaved to produce a single storage address.  This layout improves
GPU texture-cache hit rates when sampling spatially nearby pixels.

The algorithm here is a direct Python port of DrSwizzler's implementation
(Util.Morton, PS3Swizzler, PS3Deswizzler — MIT licence).

Morton function
---------------
Given tile index ``t`` in a grid of ``sx`` × ``sy`` tiles, the function
alternately pulls one bit from the x-counter and one from the y-counter,
accumulating them into separate x/y coordinate contributions.  The final
linear address is ``y_contribution * sx + x_contribution``.

Swizzle vs. deswizzle
---------------------
Both operations use the *same* Morton function; only the copy direction
differs:

  Swizzle   (linear → PS3):  ``output[t]         = input[Morton(t, w, h)]``
  Deswizzle (PS3 → linear):  ``output[Morton(t)] = input[t]``

Channel order
-------------
PS3 CTXR stores each pixel as **ARGB** (alpha in byte 0).
DDS stores each pixel as **RGBA** (red in byte 0).
The two ``*_channel`` helpers rotate every 4-byte pixel by one byte in the
appropriate direction.
"""

from .constants import BPP


# ── Morton index ─────────────────────────────────────────────────────────────

def _morton(t: int, sx: int, sy: int) -> int:
    """
    Map tile index *t* in an (*sx* × *sy*) grid to its Morton-curve address.

    Parameters
    ----------
    t:
        Linear tile index (0 … sx*sy-1).
    sx, sy:
        Grid width and height in tiles (must be powers of two).

    Returns
    -------
    int
        The Morton-curve storage address for tile *t*.

    Algorithm
    ---------
    Two accumulators build up the x and y coordinate contributions
    independently by consuming one bit at a time from the remaining index
    ``num3``, alternating between x (``num4`` / ``num2``) and y
    (``num5`` / ``num1``) until both dimension counters reach 1.
    """
    num1 = num2 = 1       # running bit-weights for y and x
    num3 = t              # bits still to consume
    num4 = sx             # remaining x dimension
    num5 = sy             # remaining y dimension
    num6 = 0              # accumulated x coordinate
    num7 = 0              # accumulated y coordinate

    while num4 > 1 or num5 > 1:
        if num4 > 1:
            num6 += num2 * (num3 & 1)   # consume one x bit
            num3 >>= 1
            num2 <<= 1
            num4 >>= 1
        if num5 > 1:
            num7 += num1 * (num3 & 1)   # consume one y bit
            num3 >>= 1
            num1 <<= 1
            num5 >>= 1

    return num7 * sx + num6


# ── Swizzle / deswizzle ───────────────────────────────────────────────────────

def ps3_swizzle(data: bytes, w: int, h: int) -> bytes:
    """
    Apply PS3 Morton swizzle: linear pixel data → PS3 GPU tiled layout.

    For each output slot *t* (in Morton order), the pixel is read from
    the linear position ``Morton(t, w, h)``.

    1×1 mips are returned unchanged (no reordering possible).

    Parameters
    ----------
    data:
        Raw pixel bytes in linear (row-major) RGBA order.
        Must be exactly ``w * h * BPP`` bytes.
    w, h:
        Texture width and height in pixels (should be powers of two).

    Returns
    -------
    bytes
        Pixel data in PS3 Morton-curve order, same length as *data*.
    """
    if w == 1 and h == 1:
        return data
    out = bytearray(w * h * BPP)
    for t in range(w * h):
        src = _morton(t, w, h) * BPP
        out[t * BPP:(t + 1) * BPP] = data[src:src + BPP]
    return bytes(out)


def ps3_deswizzle(data: bytes, w: int, h: int) -> bytes:
    """
    Reverse PS3 Morton swizzle: PS3 GPU tiled layout → linear pixel data.

    For each slot *t* in the swizzled input, the pixel is written to the
    linear position ``Morton(t, w, h)``.

    1×1 mips are returned unchanged.

    Parameters
    ----------
    data:
        Raw pixel bytes in PS3 Morton-curve order.
        Must be exactly ``w * h * BPP`` bytes.
    w, h:
        Texture width and height in pixels.

    Returns
    -------
    bytes
        Pixel data in linear (row-major) order, same length as *data*.
    """
    if w == 1 and h == 1:
        return data
    out = bytearray(w * h * BPP)
    for t in range(w * h):
        dst = _morton(t, w, h) * BPP
        out[dst:dst + BPP] = data[t * BPP:(t + 1) * BPP]
    return bytes(out)


# ── Channel reordering ────────────────────────────────────────────────────────

def argb_to_rgba(data: bytes) -> bytes:
    """
    Rotate every pixel one byte left: ``[A, R, G, B]`` → ``[R, G, B, A]``.

    Used when converting CTXR → DDS.
    Ported from ``CTXR.ARGBToRGBA()`` in the Aqua Library.

    Parameters
    ----------
    data:
        Pixel bytes in ARGB order (length must be a multiple of 4).

    Returns
    -------
    bytes
        Same pixels in RGBA order.
    """
    out = bytearray(len(data))
    for i in range(0, len(data), 4):
        a, r, g, b = data[i], data[i + 1], data[i + 2], data[i + 3]
        out[i] = r;  out[i + 1] = g;  out[i + 2] = b;  out[i + 3] = a
    return bytes(out)


def rgba_to_argb(data: bytes) -> bytes:
    """
    Rotate every pixel one byte right: ``[R, G, B, A]`` → ``[A, R, G, B]``.

    Used when converting DDS → CTXR.

    Parameters
    ----------
    data:
        Pixel bytes in RGBA order (length must be a multiple of 4).

    Returns
    -------
    bytes
        Same pixels in ARGB order.
    """
    out = bytearray(len(data))
    for i in range(0, len(data), 4):
        r, g, b, a = data[i], data[i + 1], data[i + 2], data[i + 3]
        out[i] = a;  out[i + 1] = r;  out[i + 2] = g;  out[i + 3] = b
    return bytes(out)
