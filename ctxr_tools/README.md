# ctxr_tools

CTXR ↔ DDS texture converter for Bluepoint PS3 games.

**Supported games:** Shadow of the Colossus PS3, ICO PS3, Metal Gear Solid HD Collection  
**Supported format:** Uncompressed RGBA8 only (32 bpp, no block compression)

---

## Package layout

```
ctxr_tools/
├── README.md           ← this file
├── constants.py        ← shared numeric constants (header size, BPP, padding)
├── swizzle.py          ← PS3 Morton swizzle / deswizzle (ported from DrSwizzler)
├── formats.py          ← CTXR and DDS header parsing + building
├── converter.py        ← high-level ctxr_to_dds() and dds_to_ctxr() functions
├── gui/
│   ├── __init__.py     ← re-exports run_gui()
│   ├── preview.py      ← PIL-based image preview widget (checkerboard, channels, mip selector)
│   ├── single_tab.py   ← "Single file" tab (CTXR→DDS and DDS→CTXR sub-tabs)
│   └── batch_tab.py    ← "Batch" tab (file list, sort, progress, background worker)
└── docs/
    ├── file_format.md  ← detailed PS3 CTXR binary format reference
    └── swizzle.md      ← explanation of the PS3 Morton swizzle algorithm
```

Entry point: `__main__.py` in the project root — `python -m ctxr_tools` or `python main.py`.

---

## Quick start

```bash
# GUI (no arguments)
python main.py

# CLI — CTXR → DDS
python main.py ctxr_to_dds  input.ctxr  output.dds

# CLI — DDS → CTXR  (original.ctxr optional but recommended)
python main.py dds_to_ctxr  input.dds  output.ctxr  [original.ctxr]
```

### Dependencies

| Package  | Required for       | Install              |
|----------|--------------------|----------------------|
| Python ≥ 3.10 | everything    | —                    |
| tkinter  | GUI                | bundled with Python* |
| Pillow   | image preview only | `pip install Pillow` |

\* On Linux: `sudo apt install python3-tk`

---

## Using the library from your own code

```python
from ctxr_tools.converter import ctxr_to_dds, dds_to_ctxr

# Extract to DDS
ctxr_to_dds("texture.ctxr", "texture.dds")

# Re-pack edited DDS (provide original to preserve unknown header fields)
dds_to_ctxr("edited.dds", "texture.ctxr", original_ctxr_path="texture.ctxr")

# Custom log callback (default is print)
dds_to_ctxr("edited.dds", "out.ctxr", log=my_logger.info)
```

Lower-level access:

```python
from ctxr_tools.formats  import parse_ctxr_header, parse_dds, build_dds_header
from ctxr_tools.swizzle  import ps3_swizzle, ps3_deswizzle
from ctxr_tools.constants import CTXR_HEADER_SIZE, BPP
```
