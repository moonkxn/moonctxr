#!/usr/bin/env python3
"""
CTXR \u2194 DDS Converter \u2014 Bluepoint PS3
=====================================
Entry point.  Run with no arguments to open the GUI.
Run with arguments for command-line use.

Usage
-----
::

  python main.py                                              # GUI
  python main.py ctxr_to_dds  input.ctxr  output.dds
  python main.py dds_to_ctxr  input.dds   output.ctxr  [original.ctxr]
"""

import sys
from ctxr_tools.converter import ctxr_to_dds, dds_to_ctxr


def _usage() -> None:
    print(__doc__)


def main() -> None:
    args = sys.argv[1:]

    if not args:
        # No arguments — launch GUI
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
        _usage()
        sys.exit(1)


if __name__ == '__main__':
    main()
