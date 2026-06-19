"""
ctxr_tools.gui
==============
GUI package.

Exports
-------
run_gui
    Launch the main converter application window.
PreviewWindow
    Standalone detachable texture viewer.  Can be opened from any
    tkinter widget::

        from ctxr_tools.gui import PreviewWindow
        PreviewWindow(root, path='/path/to/texture.ctxr')
"""

from .app            import run_gui
from .preview_window import PreviewWindow

__all__ = ['run_gui', 'PreviewWindow']
