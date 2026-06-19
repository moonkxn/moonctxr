"""
ctxr_tools.gui.app
==================
Top-level GUI application.

``run_gui()`` creates the root ``tk.Tk`` window, assembles the two tabs
(single-file and batch), adds a footer, and starts the event loop.

All actual tab logic lives in ``single_tab.py`` and ``batch_tab.py``.
This file is intentionally thin — it is only responsible for layout
and wiring.
"""

import tkinter as tk
from tkinter import ttk


def run_gui() -> None:
    """
    Launch the CTXR ↔ DDS Converter GUI.

    Blocks until the window is closed.  Safe to call from ``__main__``.
    """
    root = tk.Tk()
    root.title('CTXR \u2194 DDS Converter \u2014 Bluepoint PS3')
    root.resizable(True, True)
    root.minsize(560, 420)

    # Import here so tkinter is already initialised
    from .single_tab import build_single_tab
    from .batch_tab  import build_batch_tab

    nb = ttk.Notebook(root)
    nb.pack(fill='both', expand=True, padx=10, pady=10)

    build_single_tab(nb)
    build_batch_tab(nb)

    # ── Footer ────────────────────────────────────────────────────────────────
    ttk.Separator(root).pack(fill='x', padx=10)
    ttk.Label(
        root,
        text='Bluepoint PS3  \u2022  SOTC / ICO / MGS HD  \u2022  RGBA8 uncompressed only'
             '  \u2022  Viewer: pip install Pillow',
        foreground='gray',
        font=('TkDefaultFont', 8),
    ).pack(pady=(2, 6))

    root.mainloop()
