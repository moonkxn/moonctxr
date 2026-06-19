# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ctxr_tools.
Compatible with PyInstaller 5.x and 6.x.

Run from the folder containing main.py:
    pyinstaller ctxr_tools.spec

Size optimisations applied:
  - Custom PIL hook (hooks/hook-PIL.py) strips unused image format plugins
  - UPX compression enabled (install UPX from https://upx.github.io first,
    or let the GitHub Actions workflow install it automatically)
  - Unused stdlib modules excluded
  - One-file mode (single .exe, no temp folder on launch)
"""

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("ctxr_tools/docs", "ctxr_tools/docs"),
        ("ctxr_tools/README.md", "ctxr_tools"),
    ],
    hiddenimports=[
        "ctxr_tools.constants",
        "ctxr_tools.swizzle",
        "ctxr_tools.formats",
        "ctxr_tools.converter",
        "ctxr_tools.gui",
        "ctxr_tools.gui.app",
        "ctxr_tools.gui.preview",
        "ctxr_tools.gui.preview_window",
        "ctxr_tools.gui.single_tab",
        "ctxr_tools.gui.batch_tab",
    ],
    hookspath=["hooks"],  # our custom hook-PIL.py lives here
    hooksconfig={},
    runtime_hooks=[],
    # Exclude heavy stdlib modules we never import
    excludes=[
        "numpy",
        "scipy",
        "matplotlib",
        "pandas",
        "email",
        "html",
        "http",
        "xml",
        "xmlrpc",
        "unittest",
        "doctest",
        "pdb",
        "profile",
        "pstats",
        "curses",
        "readline",
        "rlcompleter",
        "sqlite3",
        "dbm",
        "shelve",
        "multiprocessing",
        "concurrent",
        "asyncio",
        "ssl",
        "socket",
        "selectors",
    ],
    noarchive=False,
    optimize=2,  # equivalent to python -OO: removes docstrings and assertions
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ctxr_tools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # strip debug symbols (Linux/Mac only, ignored on Windows)
    upx=True,  # compress with UPX — requires UPX on PATH
    upx_exclude=[
        # Don't compress these — UPX can corrupt them or slow startup badly
        "vcruntime*.dll",
        "msvcp*.dll",
        "python*.dll",
        "_tkinter*.pyd",
    ],
    runtime_tmpdir=None,
    console=False,  # no console window
    # icon='ctxr_tools.ico',   # uncomment + add .ico for a custom icon
)
