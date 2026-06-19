"""
ctxr_tools
==========
CTXR ↔ DDS texture converter for Bluepoint PS3 games.

Running directly
----------------
You can run this file directly from inside the folder::

    python __init__.py                         # GUI
    python __init__.py ctxr_to_dds  in.ctxr  out.dds
    python __init__.py dds_to_ctxr  in.dds   out.ctxr  [original.ctxr]

Or from the parent folder using main.py::

    python main.py

Public API (when used as a package)
------------------------------------
::

    from ctxr_tools import ctxr_to_dds, dds_to_ctxr

    ctxr_to_dds('texture.ctxr', 'texture.dds')
    dds_to_ctxr('edited.dds',   'texture.ctxr', original_ctxr_path='texture.ctxr')

See ``converter.py`` for full parameter documentation.
"""

import sys as _sys
import os as _os

# ── Bootstrap: make relative imports work when this file is run directly ──────
# When Python runs __init__.py as a script, __package__ is None and relative
# imports like "from .converter import ..." fail with ImportError.
# We detect this situation and re-add the package's parent directory to sys.path
# so that absolute imports (from ctxr_tools.xxx import ...) work instead.
if __package__ is None or __package__ == "":
    # Insert the directory that CONTAINS ctxr_tools/ into sys.path
    _pkg_parent = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    if _pkg_parent not in _sys.path:
        _sys.path.insert(0, _pkg_parent)
    # Also mark ourselves as the ctxr_tools package so sub-imports resolve
    import importlib as _importlib
    import types as _types
    _pkg = _types.ModuleType("ctxr_tools")
    _pkg.__path__ = [_os.path.dirname(_os.path.abspath(__file__))]
    _pkg.__package__ = "ctxr_tools"
    _pkg.__spec__ = None
    _sys.modules.setdefault("ctxr_tools", _pkg)
    __package__ = "ctxr_tools"

from .converter import ctxr_to_dds, dds_to_ctxr

__all__ = ['ctxr_to_dds', 'dds_to_ctxr']
__version__ = '1.0.0'


# ── Entry point when run as a script: python __init__.py ──────────────────────
if __name__ == '__main__':
    import sys

    args = sys.argv[1:]

    if not args:
        from ctxr_tools.gui import run_gui
        run_gui()

    elif args[0] == 'ctxr_to_dds' and len(args) >= 3:
        ctxr_to_dds(ctxr_path=args[1], dds_path=args[2])

    elif args[0] == 'dds_to_ctxr' and len(args) >= 3:
        dds_to_ctxr(
            dds_path=args[1],
            ctxr_path=args[2],
            original_ctxr_path=args[3] if len(args) > 3 else None,
        )

    else:
        print(__doc__)
        sys.exit(1)
