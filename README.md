# ctxr_tools

A texture converter and viewer for Bluepoint PS3 game remasters. Converts
`.ctxr` texture files to editable `.dds` files and back, with a GUI that
includes batch processing and a standalone texture viewer.

**Supported games**
- Shadow of the Colossus (PS3, 2011)
- ICO (PS3, 2011)
- Metal Gear Solid HD Collection (PS3, 2011)

**Supported texture format:** Uncompressed RGBA8 only (32 bpp).

---

## Installation

**Requirements:** Python 3.10 or later.

```bash
# Clone the repo
git clone https://github.com/you/ctxr_tools.git
cd ctxr_tools

# Install Pillow for image preview (optional but recommended)
pip install Pillow
```

tkinter comes bundled with Python on Windows and macOS.
On Linux: `sudo apt install python3-tk`

---

## Usage

### GUI

```bash
python main.py
```

Or if you are inside the `ctxr_tools/` folder:

```bash
python __init__.py
```

### Command line

```bash
# Extract CTXR → DDS
python main.py ctxr_to_dds  input.ctxr  output.dds

# Re-pack DDS → CTXR
# Providing the original .ctxr preserves unknown header fields exactly.
# Without it a header is synthesised — may not work in every title.
python main.py dds_to_ctxr  input.dds  output.ctxr  [original.ctxr]
```

### As a Python library

```python
from ctxr_tools.converter import ctxr_to_dds, dds_to_ctxr

ctxr_to_dds("wanda.ctxr", "wanda.dds")
dds_to_ctxr("wanda_edited.dds", "wanda_new.ctxr", original_ctxr_path="wanda.ctxr")
```

---

## Building a standalone .exe (Windows)

Double-click `build.bat` — it installs PyInstaller and produces
`dist\ctxr_tools.exe`. No Python needed on the target machine.

---

## Features

### Single file tab
Convert one file at a time. Both directions: CTXR → DDS and DDS → CTXR.
The optional **Original CTXR** field on the DDS → CTXR tab preserves all
opaque header bytes from the original file, which is important for the game
to accept the texture.

### Batch tab
- Add individual files or an entire folder in one click.
- Click any column heading to sort (filename, size, dimensions, mip count,
  status). Click again to reverse.
- The batch worker runs on a background thread — the UI stays responsive
  during long conversions.
- **Auto-orig detection**: when converting DDS → CTXR in batch, a `.ctxr`
  with the same base name in the same folder is used automatically as the
  header template.
- The Run button becomes a Stop button mid-run.

### Texture viewer (Preview image…)
Opens a standalone window — you can have multiple viewers open at once.

- **Mip selector** — step through every mip level with the spinbox or the
  arrow keys.
- **Channel toggles R / G / B / A** — isolate any channel or combination.
  Useful for inspecting normal maps, alpha masks, roughness maps.
- **Zoom** — Fit (default), 25%, 50%, 100%, 200%, 400%. Scrollbars appear
  when the image is larger than the window.
- **Checkerboard background** — makes transparent areas visible.
- **Export PNG** — save the current mip with the channel mask applied.
- **Convert from viewer** — CTXR → DDS or DDS → CTXR directly from the
  viewer's File menu.
- **Non-blocking load** — large textures decode on a background thread.
  The window stays responsive and shows a loading indicator while
  deswizzling.

---

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```

The tests in `test_converter.py` use the real `.ctxr` and `.dds` fixture
files. If those files are not present the fixture tests are skipped
gracefully; the swizzle and format tests run without any fixtures.

---

## How it works

### The CTXR format

CTXR is a proprietary texture format used internally by Bluepoint Games'
PS3 engine. Each file has a 128-byte big-endian header followed by the raw
pixel data for all mip levels concatenated largest-first, then 44 bytes of
zero padding.

The header stores width, height, mip count, and two size sentinels. All
other fields are either fixed constants or opaque values whose purpose is
unknown — these are preserved verbatim from the original file when
re-packing. See `docs/file_format.md` for the full field map.

### PS3 Morton swizzle

The PS3 RSX GPU stores textures in Morton curve order rather than row-major
order. A Morton curve interleaves the bits of the X and Y pixel coordinates
to produce a storage address, so spatially nearby pixels are also nearby in
memory. This improves GPU texture-cache hit rates.

Converting CTXR → DDS requires reversing this permutation (deswizzle).
Converting DDS → CTXR requires applying it (swizzle). Both directions use
the same Morton index function — only the copy direction differs.
See `docs/swizzle.md` for a detailed explanation with diagrams.

### Channel order

PS3 CTXR stores pixels as **ARGB** (alpha in byte 0).
DDS stores pixels as **RGBA** (red in byte 0).
Every pixel is rotated by one byte when crossing the format boundary.

---

## Limitations

- **RGBA8 only.** The PS3 SOTC / ICO textures this tool was tested on are
  all uncompressed RGBA8. The PS3 RSX supports DXT1/DXT3/DXT5 (BC1/BC2/BC3)
  but those variants have not been observed in these titles and are not
  implemented.
- **PS3 variant only.** The CTXR format also exists in PS4 (version 0x25,
  Shadow of the Colossus remake) and PS5 (version 0x6E, Demon's Souls
  remake) variants. Those use different swizzle algorithms (DrSwizzler
  PS4/PS5 variants) and are not supported yet.
- **Single slice only.** Array textures (multiple slices) parse but only
  slice 0 is converted.
- **No cubemap support.** Cubemap textures have not been tested.

---

## Acknowledgements

- **Shadowth117** — author of Aqua Toolset and PSO2 Aqua Library, whose
  C# source code revealed the CTXR format structure and the deswizzle
  pipeline.
- **Pear0533** — author of DrSwizzler, whose Morton curve implementation
  this project ports directly.
- **The Bluepoint modding community** — for documenting the PSARC layout
  and providing test files.
