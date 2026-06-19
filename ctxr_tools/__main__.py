"""
Allows running the package as a module:  python -m ctxr_tools
"""
from ctxr_tools.__init__ import *   # noqa: F401,F403
import sys, os

# Re-use the same entry point logic as __init__.py's __main__ block
args = sys.argv[1:]

if not args:
    from ctxr_tools.gui import run_gui
    run_gui()
elif args[0] == 'ctxr_to_dds' and len(args) >= 3:
    from ctxr_tools.converter import ctxr_to_dds
    ctxr_to_dds(ctxr_path=args[1], dds_path=args[2])
elif args[0] == 'dds_to_ctxr' and len(args) >= 3:
    from ctxr_tools.converter import dds_to_ctxr
    dds_to_ctxr(
        dds_path=args[1],
        ctxr_path=args[2],
        original_ctxr_path=args[3] if len(args) > 3 else None,
    )
else:
    print("Usage: python -m ctxr_tools [ctxr_to_dds in.ctxr out.dds | dds_to_ctxr in.dds out.ctxr [orig.ctxr]]")
    sys.exit(1)
