# PS3 Morton Swizzle

## Background

Modern GPUs achieve better texture-cache performance when spatially
nearby pixels are also nearby in memory.  Row-major (linear) storage
does not guarantee this — pixels in the same column but adjacent rows
may be thousands of bytes apart.

The PS3 RSX GPU uses a **Morton curve** (also called a Z-order curve or
Z-curve) to address texture memory.  A Morton curve interleaves the bits
of the X and Y pixel coordinates to produce a single storage index,
ensuring that a 2×2 block of pixels always occupies 4 consecutive memory
locations regardless of texture size.

---

## Bit interleaving

For a pixel at position `(x, y)` in a texture, the Morton index is
computed by alternating bits of `x` and `y`:

```
x  =  x₀  x₁  x₂  x₃  …
y  =  y₀  y₁  y₂  y₃  …

Morton = x₀ y₀ x₁ y₁ x₂ y₂ x₃ y₃ …
         ↑                         ↑
      bit 0                   high bit
```

Example for a 4×4 texture:

```
Linear layout       Morton layout
(row-major)         (Z-curve)

 0  1  2  3          0  1  4  5
 4  5  6  7          2  3  6  7
 8  9 10 11          8  9 12 13
12 13 14 15         10 11 14 15
```

---

## DrSwizzler implementation

The converter uses a direct Python port of DrSwizzler's `Util.Morton()`
function.  It does not compute the interleave by bit manipulation;
instead it simulates the process iteratively by consuming one bit at a
time from an index counter, alternating between the x-accumulator and
the y-accumulator.

```python
def _morton(t: int, sx: int, sy: int) -> int:
    num1 = num2 = 1
    num3 = t          # bits to consume
    num4, num5 = sx, sy
    num6 = num7 = 0   # x and y contributions

    while num4 > 1 or num5 > 1:
        if num4 > 1:
            num6 += num2 * (num3 & 1)   # x bit
            num3 >>= 1; num2 <<= 1; num4 >>= 1
        if num5 > 1:
            num7 += num1 * (num3 & 1)   # y bit
            num3 >>= 1; num1 <<= 1; num5 >>= 1

    return num7 * sx + num6
```

This is equivalent to the standard bit-interleave but handles
non-square textures (where `sx ≠ sy`) gracefully by consuming x bits
and y bits at independent rates.

---

## Swizzle vs. deswizzle

Both operations use the same Morton function; only the copy direction
differs.

**Deswizzle** (PS3 GPU layout → linear, used for CTXR → DDS):

```python
for t in range(w * h):
    dst = morton(t, w, h) * BPP     # linear destination
    output[dst : dst+BPP] = input[t*BPP : (t+1)*BPP]
```

**Swizzle** (linear → PS3 GPU layout, used for DDS → CTXR):

```python
for t in range(w * h):
    src = morton(t, w, h) * BPP     # linear source
    output[t*BPP : (t+1)*BPP] = input[src : src+BPP]
```

---

## Channel order

After deswizzling the pixel layout is Morton → linear, but the channel
order is still PS3-native **ARGB** (`A` in byte 0).  A final byte
rotation converts to DDS-standard **RGBA** (`R` in byte 0):

```
CTXR byte order:  [A, R, G, B]  →  DDS byte order:  [R, G, B, A]
```

The inverse rotation is applied when packing DDS → CTXR.

---

## Performance note

The pure-Python Morton loop is `O(W × H)` per mip and noticeably slow
for large textures (a 1024×1024 RGBA8 mip has ~1 million iterations).
If performance matters, the loop body can be replaced with a NumPy
vectorised implementation or compiled with Cython/Numba without changing
any of the surrounding format logic.
