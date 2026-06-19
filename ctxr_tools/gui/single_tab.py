"""
ctxr_tools.gui.single_tab
=========================
"Single file" notebook tab — two sub-tabs for CTXR→DDS and DDS→CTXR.

Each sub-tab contains:
  - File-path rows with Browse buttons.
  - A Convert button and a Preview image button.
  - A scrolled log widget that receives the converter's progress messages.

The PreviewPanel has been removed; texture inspection is done exclusively
through the standalone PreviewWindow (preview_window.py).
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from ..converter import ctxr_to_dds, dds_to_ctxr


# ── Shared widget helpers ─────────────────────────────────────────────────────

_PAD = dict(padx=8, pady=4)


def _browse(var: tk.StringVar, filetypes: list, save: bool = False) -> None:
    if save:
        p = filedialog.asksaveasfilename(
            filetypes=filetypes, defaultextension=filetypes[0][1])
    else:
        p = filedialog.askopenfilename(filetypes=filetypes)
    if p:
        var.set(p)


def _auto_out(src_var: tk.StringVar, dst_var: tk.StringVar, new_ext: str) -> None:
    """If dst is empty, fill it with src's base name + new_ext."""
    p = src_var.get()
    if p and not dst_var.get():
        dst_var.set(os.path.splitext(p)[0] + new_ext)


def _file_row(
    parent: tk.Widget,
    label: str,
    var: tk.StringVar,
    filetypes: list,
    optional: bool = False,
    save: bool = False,
    row: int = 0,
) -> None:
    """One label + entry + Browse button laid out on a grid row."""
    text = label + (' (optional)' if optional else '')
    ttk.Label(parent, text=text, width=16, anchor='w'
              ).grid(row=row, column=0, sticky='w', **_PAD)
    ttk.Entry(parent, textvariable=var, width=44
              ).grid(row=row, column=1, sticky='ew', **_PAD)
    ttk.Button(parent, text='Browse\u2026',
               command=lambda: _browse(var, filetypes, save)
               ).grid(row=row, column=2, **_PAD)


def _log_widget(parent: tk.Widget, height: int = 8):
    """
    Create a scrolled read-only log area.

    Returns
    -------
    tuple[ttk.LabelFrame, Callable[[str], None]]
        The frame widget and a ``write(msg)`` function.
    """
    frame = ttk.LabelFrame(parent, text='Log')
    box   = scrolledtext.ScrolledText(
        frame, width=56, height=height, state='disabled', font=('Courier', 9))
    box.pack(fill='both', expand=True, padx=4, pady=4)

    def write(msg: str) -> None:
        box.configure(state='normal')
        box.insert('end', msg + '\n')
        box.see('end')
        box.configure(state='disabled')
        box.update_idletasks()

    return frame, write


def _open_viewer(path_var: tk.StringVar, parent: tk.Widget) -> None:
    """
    Open a ``PreviewWindow`` for the file currently in *path_var*.

    Shows a warning if the path is empty or the file does not exist.
    """
    from .preview_window import PreviewWindow
    p = path_var.get().strip()
    if not p or not os.path.isfile(p):
        messagebox.showwarning('No file', 'Select a valid input file first.',
                               master=parent)
        return
    PreviewWindow(parent, path=p)


# ── Public: build the tab ─────────────────────────────────────────────────────

def build_single_tab(notebook: ttk.Notebook) -> ttk.Frame:
    """
    Build and return the "Single file" tab frame.

    The tab contains a nested Notebook with two sub-tabs:
      - CTXR \u2192 DDS
      - DDS \u2192 CTXR

    Parameters
    ----------
    notebook:
        The parent ``ttk.Notebook`` to add this tab to.

    Returns
    -------
    ttk.Frame
        The top-level frame for this tab (already added to *notebook*).
    """
    tab = ttk.Frame(notebook)
    notebook.add(tab, text='  Single file  ')

    sub_nb = ttk.Notebook(tab)
    sub_nb.pack(fill='both', expand=True)

    _build_ctxr_to_dds_subtab(sub_nb)
    _build_dds_to_ctxr_subtab(sub_nb)

    return tab


# ── Sub-tab A: CTXR → DDS ────────────────────────────────────────────────────

def _build_ctxr_to_dds_subtab(notebook: ttk.Notebook) -> None:
    frame = ttk.Frame(notebook)
    notebook.add(frame, text='  CTXR \u2192 DDS  ')
    frame.columnconfigure(1, weight=1)

    ttk.Label(frame,
              text='Extract a PS3 CTXR texture to an editable DDS file.',
              foreground='gray'
              ).grid(row=0, column=0, columnspan=3, sticky='w', padx=8, pady=(8, 2))

    v_in  = tk.StringVar()
    v_out = tk.StringVar()

    _file_row(frame, 'Input CTXR', v_in,
              [('CTXR files', '*.ctxr'), ('All files', '*.*')], row=1)
    _file_row(frame, 'Output DDS',  v_out,
              [('DDS files',  '*.dds'),  ('All files', '*.*')], save=True, row=2)

    v_in.trace_add('write', lambda *_: _auto_out(v_in, v_out, '.dds'))

    log_frame, log = _log_widget(frame)
    log_frame.grid(row=4, column=0, columnspan=3, sticky='nsew', padx=8, pady=4)
    frame.rowconfigure(4, weight=1)

    def _run() -> None:
        src, dst = v_in.get().strip(), v_out.get().strip()
        if not src or not dst:
            messagebox.showwarning('Missing paths', 'Fill in both paths.')
            return
        try:
            ctxr_to_dds(src, dst, log=log)
            messagebox.showinfo('Done', f'Saved:\n{dst}')
        except Exception as e:
            log(f'\n\u2717 ERROR: {e}')
            messagebox.showerror('Error', str(e))

    btn_row = ttk.Frame(frame)
    btn_row.grid(row=3, column=0, columnspan=3, pady=6)
    ttk.Button(btn_row, text='Convert  CTXR \u2192 DDS',
               command=_run).pack(side='left', padx=4)
    ttk.Button(btn_row, text='Preview image\u2026',
               command=lambda: _open_viewer(v_in, frame)).pack(side='left', padx=4)


# ── Sub-tab B: DDS → CTXR ────────────────────────────────────────────────────

def _build_dds_to_ctxr_subtab(notebook: ttk.Notebook) -> None:
    frame = ttk.Frame(notebook)
    notebook.add(frame, text='  DDS \u2192 CTXR  ')
    frame.columnconfigure(1, weight=1)

    ttk.Label(frame,
              text='Re-pack an edited DDS back into PS3 CTXR format.',
              foreground='gray'
              ).grid(row=0, column=0, columnspan=3, sticky='w', padx=8, pady=(8, 2))

    v_in   = tk.StringVar()
    v_orig = tk.StringVar()
    v_out  = tk.StringVar()

    _file_row(frame, 'Input DDS',     v_in,
              [('DDS files',  '*.dds'),  ('All files', '*.*')], row=1)
    _file_row(frame, 'Original CTXR', v_orig,
              [('CTXR files', '*.ctxr'), ('All files', '*.*')], optional=True, row=2)
    _file_row(frame, 'Output CTXR',   v_out,
              [('CTXR files', '*.ctxr'), ('All files', '*.*')], save=True, row=3)

    v_in.trace_add('write', lambda *_: _auto_out(v_in, v_out, '.ctxr'))

    log_frame, log = _log_widget(frame)
    log_frame.grid(row=5, column=0, columnspan=3, sticky='nsew', padx=8, pady=4)
    frame.rowconfigure(5, weight=1)

    def _run() -> None:
        src  = v_in.get().strip()
        orig = v_orig.get().strip() or None
        dst  = v_out.get().strip()
        if not src or not dst:
            messagebox.showwarning('Missing paths',
                                   'Fill in Input DDS and Output CTXR.')
            return
        try:
            dds_to_ctxr(src, dst, orig, log=log)
            messagebox.showinfo('Done', f'Saved:\n{dst}')
        except Exception as e:
            log(f'\n\u2717 ERROR: {e}')
            messagebox.showerror('Error', str(e))

    btn_row = ttk.Frame(frame)
    btn_row.grid(row=4, column=0, columnspan=3, pady=6)
    ttk.Button(btn_row, text='Convert  DDS \u2192 CTXR',
               command=_run).pack(side='left', padx=4)
    ttk.Button(btn_row, text='Preview image\u2026',
               command=lambda: _open_viewer(v_in, frame)).pack(side='left', padx=4)
