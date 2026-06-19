# PS3 CTXR Binary Format Reference

Reverse-engineered from **Shadow of the Colossus PS3** via byte-level
comparison of CTXR files against their DDS equivalents produced by the
Aqua Toolset.  Cross-referenced against the Aqua Library source
(`AquaModelLibrary.Data/BluePoint/CTXR/CTXR.cs`).

---

## File structure

```
[0x000 – 0x07F]  Header       128 bytes, big-endian fields
[0x080 – ...]    Pixel data   All mip levels concatenated, largest first
[last 44 bytes]  Padding      Zero bytes (alignment)
```

Total file size = `0x80 + pixel_data_size + 44`

---

## Header (128 bytes, all big-endian)

| Offset | Size | Field              | Notes |
|--------|------|--------------------|-------|
| 0x00   | 4    | magic              | Always `0x02000101`.  As little-endian: `0x01010002` (the value the Aqua Library matches in its switch statement). |
| 0x04   | 4    | totalBufferSize    | `file_size − 0x80`.  Acts as a file-integrity sentinel. |
| 0x08   | 4    | const_0x08         | Always `0x00000001`. |
| 0x0C   | 4    | const_0x0C         | Always `0x00000000`. |
| 0x10   | 4    | const_0x10         | Always `0x00000080` (= header size). |
| 0x14   | 4    | usedDataSize       | Sum of raw mip pixel bytes, excluding the 44-byte trailing padding.  Equals the DDS pixel data size exactly. |
| 0x18   | 4    | const_0x18         | Always `0x00000000`. |
| 0x1C   | 4    | const_0x1C         | Always `0xBFBFBF80`.  Purpose unknown; possibly a GPU memory hint. |
| 0x20   | 4    | const_0x20         | Always `0x00000000`. |
| 0x24   | 1    | const_0x24         | Always `0x85`.  Purpose unknown. |
| 0x25   | 1    | mipCount           | Number of mip levels stored in the pixel region. |
| 0x26   | 1    | const_0x26         | Always `0x02`. |
| 0x27   | 1    | const_0x27         | Always `0x00`. |
| 0x28   | 2    | const_0x28         | Always `0x0000`. |
| 0x2A   | 1    | const_0x2A         | Always `0xAA`.  Purpose unknown. |
| 0x2B   | 1    | const_0x2B         | Always `0xE4`.  Purpose unknown. |
| 0x2C   | 2    | width              | Texture width in pixels (big-endian uint16). |
| 0x2E   | 2    | height             | Texture height in pixels (big-endian uint16). |
| 0x30   | 2    | sliceCount         | Number of array slices.  `1` for standard (non-array) textures. |
| 0x32–0x7F | 78 | padding           | Zeros. |

### Variable vs. constant fields

Only **five** fields change when the texture content changes:

- `totalBufferSize` (0x04)
- `usedDataSize` (0x14)
- `mipCount` (0x25)
- `width` (0x2C)
- `height` (0x2E)

All other fields are either fixed constants or opaque values that should be
copied verbatim from the original file when re-packing.

---

## Pixel data region

Starts at offset `0x80`.  Contains all mip levels back-to-back, largest
first.  Each mip level occupies exactly `width × height × 4` bytes.

### Pixel format

- **Channel order**: ARGB (`A` in byte 0, `R` in byte 1, `G` in byte 2, `B` in byte 3)
- **Memory layout**: PS3 Morton (Z-curve) swizzle — see `docs/swizzle.md`

### Mip dimensions

Each successive mip halves in both dimensions, down to a minimum of 1×1:

```
Mip 0: W × H
Mip 1: (W/2) × (H/2)
Mip 2: (W/4) × (H/4)
...
Mip n: max(1, W/2ⁿ) × max(1, H/2ⁿ)
```

---

## Trailing padding

44 zero bytes are always appended after the last mip's pixel data.
The purpose is alignment (likely to a 64-byte or 128-byte boundary on the
PS3's RSX memory bus), but the exact reason is not confirmed.

---

## Relationship to Aqua Library `ReadTopHeaderPS3`

The Aqua Library's `ReadTopHeaderPS3` function reads the header starting
at file offset `0x04` (after consuming the 4-byte magic).  Its local
variable names use the **struct offset** in the original game data, not
the sequential read position — so `int_0C` refers to the value at struct
offset `0x0C` (file offset `0x08`), not a field read at file offset `0x0C`.
This naming mismatch caused confusion during reverse engineering.

Additionally, `ReadTopHeaderPS3` reads `internalMipCount` from file offset
`0x21`, which is always `0x00` in SOTC PS3 files (the actual mip count is
at `0x25`).  As a result the reader's inner loop runs zero times and no
pixel data is parsed through that path — the pixel data extraction must
happen via a different code path or tool version.  Our converter reads
`mipCount` from the correct offset `0x25`.
