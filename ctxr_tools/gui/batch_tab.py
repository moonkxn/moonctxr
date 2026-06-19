"""
ctxr_tools.gui.batch_tab
========================
"Batch" notebook tab — convert many files in one click.

Layout
------
::

  ┌─ Mode: ● CTXR→DDS  ○ DDS→CTXR  │  Output folder: [____] [Browse] ─┐
  │                                                                      │
  │  ┌─ Files ─────────────────────────────────────────────────────────┐ │
  │  │ Filename  Size  Dims  Mips  Status                              │ │
  │  │ ...                                                             │ │
  │  ├─ [Add files] [Add folder] [Remove] [Clear] │ [Preview image] ─┤ │
  │  └─────────────────────────────────────────────────────────────────┘ │
  │                                                                      │
  │  Log (scrolled) ─────────────────────────────────────────────────── │
  │  [████████░░░░] progress   ▶ Run batch conversion                   │
  └──────────────────────────────────────────────────────────────────────┘

Key behaviours
--------------
- **Add files**: multi-select dialog filtered by the current mode extension.
- **Add folder**: scans a directory and adds every matching file.
- **Duplicate guard**: the same path is never added twice.
- **Sortable columns**: clicking any heading sorts by that column; clicking
  again reverses direction.  A ▲/▼ arrow indicates the active sort.
- **Preview image**: toolbar button or double-click opens the selected file
  in a standalone PreviewWindow (preview_window.py).
- **DDS→CTXR auto-orig**: for each ``.dds`` the worker looks for a ``.ctxr``
  with the same base name in the same directory and uses it as the header
  template if found.
- **Background thread**: conversion runs in a daemon thread so the UI stays
  responsive.  The Run button becomes Stop mid-run.
- **Progress bar** and live row colour updates (grey → amber → green/red).
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from typing import List

from ..converter import ctxr_to_dds, dds_to_ctxr
from ..formats   import parse_ctxr_header, parse_dds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(nbytes: int) -> str:
    if nbytes >= 1024 * 1024:
        return f'{nbytes / 1024 / 1024:.2f} MB'
    if nbytes >= 1024:
        return f'{nbytes // 1024} KB'
    return f'{nbytes} B'


# ── Column definitions ────────────────────────────────────────────────────────

_COLS = ('filename', 'size', 'dims', 'mips', 'status')
_COL_LABELS = {
    'filename': 'Filename',
    'size':     'Size',
    'dims':     'Dimensions',
    'mips':     'Mips',
    'status':   'Status',
}
_COL_WIDTHS = {
    'filename': (220, True),
    'size':     (80,  False),
    'dims':     (90,  False),
    'mips':     (45,  False),
    'status':   (100, False),
}
_COL_ANCHORS = {
    'filename': 'w',
    'size':     'e',
    'dims':     'center',
    'mips':     'center',
    'status':   'center',
}


# ── Public: build the tab ─────────────────────────────────────────────────────

def build_batch_tab(notebook: ttk.Notebook) -> ttk.Frame:
    """
    Build and return the "Batch" tab frame.

    Parameters
    ----------
    notebook:
        The parent ``ttk.Notebook`` to add this tab to.

    Returns
    -------
    ttk.Frame
        The top-level frame (already added to *notebook*).
    """
    tab = ttk.Frame(notebook)
    notebook.add(tab, text='  Batch  ')

    # Mutable state: list of dicts, one per file
    # Keys: path, status, bytes, pixels
    batch_items: List[dict] = []

    # ── Top controls ─────────────────────────────────────────────────────────
    top = ttk.Frame(tab)
    top.pack(fill='x', padx=8, pady=(8, 0))

    ttk.Label(top, text='Mode:').pack(side='left')
    batch_mode = tk.StringVar(value='ctxr_to_dds')
    ttk.Radiobutton(top, text='CTXR \u2192 DDS',
                    variable=batch_mode, value='ctxr_to_dds'
                    ).pack(side='left', padx=(4, 12))
    ttk.Radiobutton(top, text='DDS \u2192 CTXR',
                    variable=batch_mode, value='dds_to_ctxr'
                    ).pack(side='left')

    ttk.Separator(top, orient='vertical').pack(side='left', fill='y', padx=12, pady=2)

    ttk.Label(top, text='Output folder:').pack(side='left')
    v_out_dir = tk.StringVar()
    ttk.Entry(top, textvariable=v_out_dir, width=28).pack(side='left', padx=4)
    ttk.Button(top, text='Browse\u2026',
               command=lambda: v_out_dir.set(
                   filedialog.askdirectory() or v_out_dir.get())
               ).pack(side='left')
    ttk.Label(top, text='  (blank = same folder as input)',
              foreground='gray').pack(side='left')

    # ── File list ─────────────────────────────────────────────────────────────
    mid = ttk.Frame(tab)
    mid.pack(fill='both', expand=True, padx=8, pady=6)

    list_frame = ttk.LabelFrame(mid, text='Files')
    list_frame.pack(fill='both', expand=True)

    tree = ttk.Treeview(list_frame, columns=_COLS, show='headings',
                        selectmode='browse')
    for col in _COLS:
        w, stretch = _COL_WIDTHS[col]
        tree.column(col, width=w, stretch=stretch, anchor=_COL_ANCHORS[col])

    vsb = ttk.Scrollbar(list_frame, orient='vertical',   command=tree.yview)
    hsb = ttk.Scrollbar(list_frame, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky='nsew')
    vsb.grid(row=0, column=1, sticky='ns')
    hsb.grid(row=1, column=0, sticky='ew')
    list_frame.rowconfigure(0, weight=1)
    list_frame.columnconfigure(0, weight=1)

    tree.tag_configure('ok',      foreground='#44bb44')
    tree.tag_configure('error',   foreground='#ee5555')
    tree.tag_configure('pending', foreground='#aaaaaa')
    tree.tag_configure('running', foreground='#ddaa33')

    # ── Sortable headings ─────────────────────────────────────────────────────
    sort_state: dict = {}

    def _sort_by(col: str) -> None:
        """
        Re-order tree rows by *col*.  Click the same column again to reverse.

        Sort keys:
          filename / status  → case-insensitive string
          size               → raw byte count  (batch_items['bytes'])
          dims               → pixel count w×h (batch_items['pixels'])
          mips               → integer
        """
        asc = sort_state.get(col, 'desc') == 'desc'
        sort_state[col] = 'asc' if asc else 'desc'

        rows = []
        for iid in tree.get_children():
            item = batch_items[int(iid)]
            if col == 'size':
                key = item.get('bytes', 0)
            elif col == 'dims':
                key = item.get('pixels', 0)
            elif col == 'mips':
                try:    key = int(tree.set(iid, 'mips'))
                except: key = 0
            else:
                key = tree.set(iid, col).lower()
            rows.append((key, iid))

        rows.sort(key=lambda x: x[0], reverse=not asc)
        for pos, (_, iid) in enumerate(rows):
            tree.move(iid, '', pos)

        arrow = ' \u25b2' if asc else ' \u25bc'
        for c, base in _COL_LABELS.items():
            tree.heading(c, text=base + (arrow if c == col else ''))

    for _col in _COLS:
        tree.heading(_col, text=_COL_LABELS[_col],
                     command=lambda c=_col: _sort_by(c))

    # ── Toolbar ───────────────────────────────────────────────────────────────
    toolbar = ttk.Frame(list_frame)
    toolbar.grid(row=2, column=0, columnspan=2, sticky='ew', padx=4, pady=(2, 4))

    def _add_files() -> None:
        ext  = '*.ctxr' if batch_mode.get() == 'ctxr_to_dds' else '*.dds'
        name = 'CTXR files' if batch_mode.get() == 'ctxr_to_dds' else 'DDS files'
        paths = filedialog.askopenfilenames(
            filetypes=[(name, ext), ('All files', '*.*')])
        for p in paths:
            _add_path(p)

    def _add_folder() -> None:
        folder = filedialog.askdirectory()
        if not folder:
            return
        ext = '.ctxr' if batch_mode.get() == 'ctxr_to_dds' else '.dds'
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(ext):
                _add_path(os.path.join(folder, fname))

    def _add_path(path: str) -> None:
        """
        Add *path* to the list if it is not already present.

        Parses the file header to fill in Size, Dimensions, and Mips columns.
        Stores raw ``bytes`` and ``pixels`` counts in the metadata dict for
        numeric sorting.
        """
        if any(it['path'] == path for it in batch_items):
            return
        try:
            data   = open(path, 'rb').read()
            nbytes = len(data)
            if path.lower().endswith('.ctxr'):
                w, h, mc, _ = parse_ctxr_header(data)
            else:
                w, h, mc, _ = parse_dds(data)
            fsize  = _fmt_size(nbytes)
            dims   = f'{w}\u00d7{h}'
            status = 'Pending'
            tag    = 'pending'
            meta   = {'path': path, 'status': status,
                      'bytes': nbytes, 'pixels': w * h}
        except Exception:
            fsize  = '?'
            dims   = '?'
            mc     = 0
            status = 'Parse error'
            tag    = 'error'
            meta   = {'path': path, 'status': status, 'bytes': 0, 'pixels': 0}

        iid = len(batch_items)
        batch_items.append(meta)
        tree.insert('', 'end', iid=str(iid),
                    values=(os.path.basename(path), fsize, dims, mc or '?', status),
                    tags=(tag,))

    def _remove_selected() -> None:
        sel = tree.selection()
        if not sel:
            return
        tree.delete(sel[0])
        batch_items[int(sel[0])]['path'] = None   # keep indices stable

    def _clear_all() -> None:
        tree.delete(*tree.get_children())
        batch_items.clear()

    def _open_selected_in_viewer() -> None:
        """Open the selected file in a standalone PreviewWindow."""
        from .preview_window import PreviewWindow
        sel = tree.selection()
        if not sel:
            return
        item = batch_items[int(sel[0])]
        if item.get('path') and os.path.isfile(item['path']):
            PreviewWindow(tab, path=item['path'])

    ttk.Button(toolbar, text='Add files\u2026',  command=_add_files
               ).pack(side='left', padx=2)
    ttk.Button(toolbar, text='Add folder\u2026', command=_add_folder
               ).pack(side='left', padx=2)
    ttk.Button(toolbar, text='Remove',           command=_remove_selected
               ).pack(side='left', padx=2)
    ttk.Button(toolbar, text='Clear all',        command=_clear_all
               ).pack(side='left', padx=2)
    ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y',
                                                    padx=6, pady=2)
    ttk.Button(toolbar, text='Preview image\u2026',
               command=_open_selected_in_viewer).pack(side='left', padx=2)

    # Double-clicking a row also opens the viewer
    tree.bind('<Double-1>', lambda _: _open_selected_in_viewer())

    # ── Bottom: log + progress + run button ───────────────────────────────────
    bot = ttk.Frame(tab)
    bot.pack(fill='x', padx=8, pady=(0, 8))

    log_frame = ttk.LabelFrame(bot, text='Log')
    log_frame.pack(fill='both', expand=True)
    log_box = scrolledtext.ScrolledText(
        log_frame, height=6, state='disabled', font=('Courier', 9))
    log_box.pack(fill='both', expand=True, padx=4, pady=4)

    def _blog(msg: str) -> None:
        log_box.configure(state='normal')
        log_box.insert('end', msg + '\n')
        log_box.see('end')
        log_box.configure(state='disabled')
        log_box.update_idletasks()

    progress_var = tk.DoubleVar(value=0)
    ttk.Progressbar(bot, variable=progress_var, maximum=100
                    ).pack(fill='x', pady=(4, 2))

    status_var = tk.StringVar(value='Ready')
    ttk.Label(bot, textvariable=status_var,
              foreground='gray', font=('TkDefaultFont', 8)
              ).pack(anchor='w')

    stop_flag: List[bool] = [False]
    run_btn = ttk.Button(bot, text='\u25b6  Run batch conversion')
    run_btn.pack(pady=(4, 0))

    def _run_batch() -> None:
        active = [it for it in batch_items if it.get('path')]
        if not active:
            import tkinter.messagebox as mb
            mb.showwarning('No files', 'Add some files to the list first.')
            return

        out_dir = v_out_dir.get().strip() or None
        mode    = batch_mode.get()
        total   = len(active)
        stop_flag[0] = False
        progress_var.set(0)

        run_btn.configure(text='\u25a0  Stop', command=_stop_batch)
        mode_label = mode.replace('_', ' → ')
        _blog(f'Starting batch ({mode_label}) — {total} file(s)')
        if out_dir:
            _blog(f'Output folder: {out_dir}')
            os.makedirs(out_dir, exist_ok=True)

        def _worker() -> None:
            ok_count = err_count = 0
            for i, item in enumerate(active):
                if stop_flag[0]:
                    _blog('\u2298 Stopped by user.')
                    break

                src     = item['path']
                dst_ext = '.dds' if mode == 'ctxr_to_dds' else '.ctxr'
                dst_dir = out_dir or os.path.dirname(src)
                dst     = os.path.join(
                    dst_dir,
                    os.path.splitext(os.path.basename(src))[0] + dst_ext,
                )

                iid = str(batch_items.index(item))
                tree.item(iid, tags=('running',))
                tree.set(iid, 'status', 'Converting\u2026')
                status_var.set(f'{i + 1}/{total}  {os.path.basename(src)}')

                try:
                    if mode == 'ctxr_to_dds':
                        ctxr_to_dds(src, dst, log=lambda m: _blog(f'  {m}'))
                    else:
                        orig = os.path.splitext(src)[0] + '.ctxr'
                        orig = orig if os.path.isfile(orig) else None
                        dds_to_ctxr(src, dst, orig,
                                    log=lambda m: _blog(f'  {m}'))

                    tree.item(iid, tags=('ok',))
                    tree.set(iid, 'status', '\u2713 Done')
                    item['status'] = 'ok'
                    ok_count += 1
                    _blog(f'\u2713 [{i + 1}/{total}] {os.path.basename(src)}')
                except Exception as e:
                    tree.item(iid, tags=('error',))
                    tree.set(iid, 'status', '\u2717 Error')
                    item['status'] = 'error'
                    err_count += 1
                    _blog(f'\u2717 [{i + 1}/{total}] {os.path.basename(src)}: {e}')

                progress_var.set((i + 1) / total * 100)

            summary = (f'Batch done \u2014 {ok_count} succeeded'
                       + (f', {err_count} failed' if err_count else ''))
            _blog(f'\n{summary}')
            status_var.set(summary)
            run_btn.configure(text='\u25b6  Run batch conversion',
                              command=_run_batch)

        threading.Thread(target=_worker, daemon=True).start()

    def _stop_batch() -> None:
        stop_flag[0] = True
        run_btn.configure(text='\u25b6  Run batch conversion', command=_run_batch)

    run_btn.configure(command=_run_batch)

    return tab
