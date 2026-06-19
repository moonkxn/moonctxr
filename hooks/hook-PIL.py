"""
PyInstaller hook for Pillow — strips image format plugins we don't use.

ctxr_tools only needs:
  PIL.Image      — core image operations
  PIL.ImageTk    — display in tkinter canvas
  PIL.ImageDraw  — checkerboard generation

All other format-specific plugins (TIFF, JPEG2000, WebP, PDF, BMP encoders,
ICO, PCX, PPM, SGI, SUN, TGA, XBM, ...) are excluded to reduce bundle size.
"""

from PyInstaller.utils.hooks import collect_submodules

# Start with everything PIL has
all_modules = collect_submodules("PIL")

# Plugins we actually use
keep = {
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageDraw",
    "PIL.ImageFile",
    "PIL.ImageMode",
    "PIL.ImagePalette",
    "PIL.ImageColor",
    "PIL.PngImagePlugin",  # needed for PNG export in preview window
    "PIL.PpmImagePlugin",  # PIL internal dependency
    "PIL._imaging",  # C extension — core
    "PIL._imagingft",  # freetype (text rendering)
    "PIL._imagingcms",  # colour management (PIL dependency)
    "PIL._webp",  # sometimes required by PIL core
}

# Only include what we need
hiddenimports = list(keep)

# Exclude everything else
excludedimports = [m for m in all_modules if m not in keep]
