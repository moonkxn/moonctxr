"""
ctxr_tools.gui.preview_window
==============================
Standalone, detachable texture viewer window.

``PreviewWindow`` is a ``tk.Toplevel`` that can be opened from anywhere
in the application (the batch list, the single-file tab, or standalone).
It is fully self-contained: loading, converting, and displaying textures
needs nothing from the parent window.

Features
--------
- **Open CTXR or DDS** via File menu or drag-and-drop (when supported).
- **Mip selector** — step through every mip level with a Spinbox or arrow
  keys.
- **Channel toggles R / G / B / A** — isolate any channel or combination.
- **Zoom** — fit-to-window (default), 1× (actual pixels), 2×, 4×, 0.5×.
- **Checkerboard background** for transparent areas.
- **Info bar** — filename, dimensions, mip index, channel mode, zoom.
- **Export current view** — save the currently displayed mip (with channel
  mask applied) as a PNG.
- **Convert** — CTXR → DDS or DDS → CTXR directly from the viewer,
  using the same converter pipeline as the main tabs.

Usage
-----
Open from any tkinter widget::

    from ctxr_tools.gui.preview_window import PreviewWindow

    # Open with a file already loaded:
    PreviewWindow(root, path='/path/to/texture.ctxr')

    # Open empty (user chooses file from menu):
    PreviewWindow(root)

    # Called from batch list on double-click:
    PreviewWindow(root, path=selected_path)
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Optional

try:
    from PIL import Image, ImageTk, ImageDraw
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from ..converter  import ctxr_to_dds, dds_to_ctxr
from ..formats    import parse_ctxr_header, parse_dds, mip_chain
from ..swizzle    import argb_to_rgba, ps3_deswizzle
from ..constants  import CTXR_HEADER_SIZE

# ── Constants ─────────────────────────────────────────────────────────────────
_MIN_W       = 640
_MIN_H       = 520
_CHECKER_TILE = 16
_ZOOM_LEVELS  = [0.25, 0.5, 1.0, 2.0, 4.0]   # available discrete zoom steps


# ── Internal helpers ──────────────────────────────────────────────────────────

def _make_checker(size: int) -> "Image.Image":
    img  = Image.new('RGB', (size, size))
    draw = ImageDraw.Draw(img)
    c1, c2 = (180, 180, 180), (110, 110, 110)
    for y in range(0, size, _CHECKER_TILE):
        for x in range(0, size, _CHECKER_TILE):
            col = c1 if ((x // _CHECKER_TILE + y // _CHECKER_TILE) % 2 == 0) else c2
            draw.rectangle([x, y, x + _CHECKER_TILE - 1,
                            y + _CHECKER_TILE - 1], fill=col)
    return img


def _decode_ctxr(path: str) -> List["Image.Image"]:
    """Decode all mip levels of a CTXR file into linear RGBA PIL Images."""
    data = open(path, 'rb').read()
    w, h, mc, _ = parse_ctxr_header(data)
    pixels = data[CTXR_HEADER_SIZE:]
    mips, off = [], 0
    for mw, mh, sz in mip_chain(w, h, mc):
        chunk = pixels[off:off + sz]
        if len(chunk) < sz:
            break
        mips.append(Image.frombytes('RGBA', (mw, mh),
                     argb_to_rgba(ps3_deswizzle(chunk, mw, mh))))
        off += sz
    return mips


def _decode_dds(path: str) -> List["Image.Image"]:
    """Decode all mip levels of an RGBA8 DDS file into PIL Images."""
    data = open(path, 'rb').read()
    w, h, mc, pxs = parse_dds(data)
    mips, off = [], 0
    for mw, mh, sz in mip_chain(w, h, mc):
        chunk = pxs[off:off + sz]
        if len(chunk) < sz:
            break
        mips.append(Image.frombytes('RGBA', (mw, mh), chunk))
        off += sz
    return mips


# ── PreviewWindow ─────────────────────────────────────────────────────────────

class PreviewWindow(tk.Toplevel):
    """
    A standalone, detachable texture viewer window.

    Parameters
    ----------
    master:
        Parent tkinter window or widget.
    path:
        Optional file path to load immediately on open.
        Accepts both ``.ctxr`` and ``.dds`` files.
    """

    def __init__(self, master: tk.Widget, path: Optional[str] = None):
        super().__init__(master)
        self.title('Texture Viewer')
        self.minsize(_MIN_W, _MIN_H)
        self.configure(bg='#2b2b2b')

        # ── State ─────────────────────────────────────────────────────────────
        self._mips:       List["Image.Image"] = []
        self._path:       Optional[str]       = None
        self._photo_ref:  Optional[object]    = None
        self._checker:    Optional["Image.Image"] = None
        # Each load gets a unique token; if a new load starts the old
        # background thread sees a stale token and discards its result.
        self._load_token: int                 = 0

        self._mip_var    = tk.IntVar(value=0)
        self._show_r     = tk.BooleanVar(value=True)
        self._show_g     = tk.BooleanVar(value=True)
        self._show_b     = tk.BooleanVar(value=True)
        self._show_a     = tk.BooleanVar(value=True)
        self._zoom_var   = tk.StringVar(value='Fit')
        self._fit_mode   = True     # True = fit-to-window, False = fixed zoom
        self._zoom_level = 1.0      # used when _fit_mode is False

        # ── Menu bar ──────────────────────────────────────────────────────────
        menubar = tk.Menu(self)
        self.configure(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label='File', menu=file_menu)
        file_menu.add_command(label='Open CTXR…', command=self._open_ctxr)
        file_menu.add_command(label='Open DDS…',  command=self._open_dds)
        file_menu.add_separator()
        file_menu.add_command(label='Export current view as PNG…',
                              command=self._export_png)
        file_menu.add_separator()
        file_menu.add_command(label='Close', command=self.destroy)

        conv_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label='Convert', menu=conv_menu)
        conv_menu.add_command(label='CTXR → DDS…', command=self._convert_to_dds)
        conv_menu.add_command(label='DDS → CTXR…', command=self._convert_to_ctxr)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg='#3a3a3a', pady=4)
        toolbar.pack(fill='x', side='top')

        # Open buttons
        tk.Button(toolbar, text='Open CTXR', command=self._open_ctxr,
                  bg='#4a4a4a', fg='white', relief='flat', padx=8
                  ).pack(side='left', padx=(8, 2))
        tk.Button(toolbar, text='Open DDS', command=self._open_dds,
                  bg='#4a4a4a', fg='white', relief='flat', padx=8
                  ).pack(side='left', padx=2)

        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y',
                                                        padx=8, pady=2)

        # Mip selector
        tk.Label(toolbar, text='Mip:', bg='#3a3a3a', fg='white'
                 ).pack(side='left')
        self._mip_spin = tk.Spinbox(
            toolbar, from_=0, to=0, width=3,
            textvariable=self._mip_var,
            command=self._refresh,
            bg='#4a4a4a', fg='white', buttonbackground='#5a5a5a',
            disabledbackground='#3a3a3a',
        )
        self._mip_spin.pack(side='left', padx=(2, 8))

        # Channel toggles
        tk.Label(toolbar, text='Channels:', bg='#3a3a3a', fg='white'
                 ).pack(side='left')
        for label, var, fg_col in [
            ('R', self._show_r, '#e05555'),
            ('G', self._show_g, '#55b855'),
            ('B', self._show_b, '#5588e0'),
            ('A', self._show_a, '#aaaaaa'),
        ]:
            tk.Checkbutton(
                toolbar, text=label, variable=var, command=self._refresh,
                bg='#3a3a3a', fg=fg_col, selectcolor='#1e1e1e',
                activebackground='#3a3a3a', activeforeground=fg_col,
                font=('TkDefaultFont', 9, 'bold'),
            ).pack(side='left', padx=2)

        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y',
                                                        padx=8, pady=2)

        # Zoom control
        tk.Label(toolbar, text='Zoom:', bg='#3a3a3a', fg='white'
                 ).pack(side='left')
        zoom_options = ['Fit', '25%', '50%', '100%', '200%', '400%']
        zoom_menu = ttk.OptionMenu(
            toolbar, self._zoom_var, 'Fit', *zoom_options,
            command=self._on_zoom_change,
        )
        zoom_menu.pack(side='left', padx=(2, 8))

        # Export button
        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y',
                                                        padx=4, pady=2)
        tk.Button(toolbar, text='Export PNG…', command=self._export_png,
                  bg='#4a4a4a', fg='white', relief='flat', padx=8
                  ).pack(side='left', padx=4)

        # ── Canvas (scrollable) ───────────────────────────────────────────────
        canvas_frame = tk.Frame(self, bg='#2b2b2b')
        canvas_frame.pack(fill='both', expand=True)

        self._canvas = tk.Canvas(
            canvas_frame, bg='#2b2b2b',
            highlightthickness=0,
            xscrollincrement=1, yscrollincrement=1,
        )
        h_scroll = ttk.Scrollbar(canvas_frame, orient='horizontal',
                                  command=self._canvas.xview)
        v_scroll = ttk.Scrollbar(canvas_frame, orient='vertical',
                                  command=self._canvas.yview)
        self._canvas.configure(xscrollcommand=h_scroll.set,
                                yscrollcommand=v_scroll.set)

        h_scroll.pack(side='bottom', fill='x')
        v_scroll.pack(side='right',  fill='y')
        self._canvas.pack(side='left', fill='both', expand=True)

        # ── Info bar ──────────────────────────────────────────────────────────
        self._info_var = tk.StringVar(value='No file loaded — use File menu or Open buttons')
        info_bar = tk.Label(self, textvariable=self._info_var,
                            bg='#1e1e1e', fg='#aaaaaa',
                            font=('Courier', 9), anchor='w', padx=8)
        info_bar.pack(fill='x', side='bottom')

        # ── Keyboard shortcuts ────────────────────────────────────────────────
        self.bind('<Left>',  lambda _: self._step_mip(-1))
        self.bind('<Right>', lambda _: self._step_mip(+1))
        self.bind('<Up>',    lambda _: self._step_mip(-1))
        self.bind('<Down>',  lambda _: self._step_mip(+1))
        self.bind('<Configure>', self._on_resize)

        # ── PIL check ────────────────────────────────────────────────────────
        if not _PIL_OK:
            self._canvas.create_text(
                320, 260, text='pip install Pillow\nto use the texture viewer',
                fill='#e08060', font=('TkDefaultFont', 14), justify='center',
            )

        # ── Load initial file ─────────────────────────────────────────────────
        if path:
            self._load(path)

    # ── File loading ──────────────────────────────────────────────────────────

    def _open_ctxr(self) -> None:
        p = filedialog.askopenfilename(
            parent=self,
            title='Open CTXR',
            filetypes=[('CTXR files', '*.ctxr'), ('All files', '*.*')],
        )
        if p:
            self._load(p)

    def _open_dds(self) -> None:
        p = filedialog.askopenfilename(
            parent=self,
            title='Open DDS',
            filetypes=[('DDS files', '*.dds'), ('All files', '*.*')],
        )
        if p:
            self._load(p)

    def load(self, path: str) -> None:
        """
        Public interface: load a file programmatically.

        Parameters
        ----------
        path:
            Path to a ``.ctxr`` or ``.dds`` file.
        """
        self._load(path)

    def _load(self, path: str) -> None:
        """
        Load *path* in a background thread so the UI stays responsive.

        The technique used is a "load token": an integer that increments
        each time a new load starts.  The background thread captures the
        token at the moment it begins; when it finishes it checks whether
        the token is still current before touching any UI state.  If the
        user opens a second file before the first finishes decoding, the
        first thread's result is silently discarded.
        """
        if not _PIL_OK:
            return

        # Increment token — any in-flight thread with the old token will bail
        self._load_token += 1
        my_token = self._load_token

        # Show loading indicator immediately on the main thread
        self._show_loading(os.path.basename(path))

        def _worker():
            try:
                if path.lower().endswith('.ctxr'):
                    mips = _decode_ctxr(path)
                else:
                    mips = _decode_dds(path)
                if not mips:
                    raise ValueError('No mip levels decoded')
                error = None
            except Exception as e:
                mips  = []
                error = str(e)

            # Hand results back to the main thread via after()
            # after() is the only tkinter-safe way to update widgets
            # from a background thread.
            self.after(0, lambda: self._on_load_done(my_token, path, mips, error))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_loading(self, filename: str) -> None:
        """Display a loading indicator while the background thread works."""
        c = self._canvas
        c.delete('all')
        cx = c.winfo_width()  // 2 or _MIN_W // 2
        cy = c.winfo_height() // 2 or _MIN_H // 2
        c.create_text(cx, cy - 16, text=f'Loading {filename}…',
                      fill='#aaaaaa', font=('TkDefaultFont', 11))
        c.create_text(cx, cy + 12, text='Deswizzling pixel data',
                      fill='#666666', font=('TkDefaultFont', 9))
        self._info_var.set(f'Loading {filename}…')
        self.update_idletasks()   # flush so the text appears before decode starts

    def _on_load_done(
        self,
        token: int,
        path: str,
        mips: List["Image.Image"],
        error: Optional[str],
    ) -> None:
        """
        Called on the main thread when the background decode finishes.

        If *token* no longer matches ``self._load_token`` another load
        started after this one, so we discard the result.
        """
        if token != self._load_token:
            return   # stale result — a newer load already started

        if error:
            messagebox.showerror('Load error', error, parent=self)
            self._show_placeholder()
            return

        self._path = path
        self._mips = mips
        self._mip_spin.configure(to=max(0, len(mips) - 1))
        self._mip_var.set(0)
        self.title(f'Texture Viewer — {os.path.basename(path)}')
        self._build_checker()
        self._refresh()

    def _show_placeholder(self) -> None:
        """Restore the empty-state canvas text."""
        c = self._canvas
        c.delete('all')
        cx = c.winfo_width()  // 2 or _MIN_W // 2
        cy = c.winfo_height() // 2 or _MIN_H // 2
        c.create_text(cx, cy, text='No file loaded',
                      fill='gray', font=('TkDefaultFont', 12))
        self._info_var.set('No file loaded — use File menu or Open buttons')

    def _build_checker(self) -> None:
        """Build a checkerboard large enough to fill the canvas at current zoom."""
        if not _PIL_OK or not self._mips:
            return
        iw, ih = self._mips[0].size
        size    = max(iw, ih, 512)
        self._checker = _make_checker(size)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _refresh(self, *_) -> None:
        """Re-render the canvas from the current state."""
        c = self._canvas
        c.delete('all')

        if not _PIL_OK or not self._mips:
            return

        idx = min(self._mip_var.get(), len(self._mips) - 1)
        img = self._mips[idx].copy()
        iw, ih = img.size

        # Apply channel toggles
        r, g, b, a = img.split()
        black = Image.new('L', img.size, 0)
        white = Image.new('L', img.size, 255)
        img = Image.merge('RGBA', (
            r if self._show_r.get() else black,
            g if self._show_g.get() else black,
            b if self._show_b.get() else black,
            a if self._show_a.get() else white,
        ))

        # Determine display size
        if self._fit_mode:
            cw = c.winfo_width()  or _MIN_W
            ch = c.winfo_height() or _MIN_H
            scale = min(cw / iw, ch / ih, 1.0)   # never upscale in fit mode
        else:
            scale = self._zoom_level

        nw = max(1, int(iw * scale))
        nh = max(1, int(ih * scale))

        interp = Image.NEAREST if scale >= 1 else Image.LANCZOS
        img_scaled = img.resize((nw, nh), interp)

        # Composite over checkerboard
        checker = (_make_checker(max(nw, nh))
                   if self._checker is None else self._checker)
        bg = checker.crop((0, 0, nw, nh))
        bg.paste(img_scaled, (0, 0), mask=img_scaled.split()[3])

        photo = ImageTk.PhotoImage(bg)
        self._photo_ref = photo          # keep alive

        # Centre in canvas when smaller than canvas, or scroll when larger
        cw = c.winfo_width()  or nw
        ch = c.winfo_height() or nh
        ox = max(0, (cw - nw) // 2)
        oy = max(0, (ch - nh) // 2)

        c.create_image(ox, oy, anchor='nw', image=photo)
        c.configure(scrollregion=(0, 0, max(nw + ox, cw), max(nh + oy, ch)))

        # Update info bar
        ch_str = ''.join(
            label for label, var in (
                ('R', self._show_r), ('G', self._show_g),
                ('B', self._show_b), ('A', self._show_a),
            ) if var.get()
        ) or 'none'
        zoom_str = 'Fit' if self._fit_mode else f'{scale * 100:.0f}%'
        fname    = os.path.basename(self._path) if self._path else '—'
        self._info_var.set(
            f'{fname}   │   Mip {idx} of {len(self._mips) - 1}   '
            f'│   {iw}×{ih}   │   Channels: {ch_str}   │   Zoom: {zoom_str}'
        )

    def _on_resize(self, event) -> None:
        """Re-render when the window is resized (only matters in fit mode)."""
        if self._fit_mode and self._mips:
            self._refresh()

    # ── Controls ──────────────────────────────────────────────────────────────

    def _step_mip(self, delta: int) -> None:
        """Move the mip index by *delta* (keyboard arrow keys)."""
        if not self._mips:
            return
        new = max(0, min(len(self._mips) - 1, self._mip_var.get() + delta))
        self._mip_var.set(new)
        self._refresh()

    def _on_zoom_change(self, value: str) -> None:
        if value == 'Fit':
            self._fit_mode   = True
            self._zoom_level = 1.0
        else:
            self._fit_mode   = False
            self._zoom_level = float(value.rstrip('%')) / 100.0
        self._refresh()

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_png(self) -> None:
        """Save the currently displayed mip (with channel mask) as a PNG."""
        if not self._mips:
            messagebox.showinfo('Nothing to export', 'Load a texture first.',
                                parent=self)
            return

        idx = min(self._mip_var.get(), len(self._mips) - 1)
        img = self._mips[idx].copy()

        # Apply channel mask
        r, g, b, a = img.split()
        black = Image.new('L', img.size, 0)
        white = Image.new('L', img.size, 255)
        img = Image.merge('RGBA', (
            r if self._show_r.get() else black,
            g if self._show_g.get() else black,
            b if self._show_b.get() else black,
            a if self._show_a.get() else white,
        ))

        default = (
            os.path.splitext(os.path.basename(self._path))[0]
            + f'_mip{idx}.png'
            if self._path else f'mip{idx}.png'
        )
        out = filedialog.asksaveasfilename(
            parent=self,
            initialfile=default,
            filetypes=[('PNG', '*.png'), ('All files', '*.*')],
            defaultextension='.png',
        )
        if not out:
            return
        try:
            img.save(out)
            messagebox.showinfo('Exported', f'Saved:\n{out}', parent=self)
        except Exception as e:
            messagebox.showerror('Export error', str(e), parent=self)

    # ── Conversion ────────────────────────────────────────────────────────────

    def _convert_to_dds(self) -> None:
        """Convert the currently loaded CTXR to DDS."""
        if not self._path:
            messagebox.showinfo('No file', 'Open a CTXR file first.', parent=self)
            return
        if not self._path.lower().endswith('.ctxr'):
            messagebox.showinfo('Not a CTXR',
                                'This file is not a .ctxr — nothing to convert.',
                                parent=self)
            return
        out = filedialog.asksaveasfilename(
            parent=self,
            initialfile=os.path.splitext(os.path.basename(self._path))[0] + '.dds',
            filetypes=[('DDS files', '*.dds'), ('All files', '*.*')],
            defaultextension='.dds',
        )
        if not out:
            return
        try:
            messages = []
            ctxr_to_dds(self._path, out, log=messages.append)
            messagebox.showinfo('Done', f'Saved:\n{out}', parent=self)
        except Exception as e:
            messagebox.showerror('Conversion error', str(e), parent=self)

    def _convert_to_ctxr(self) -> None:
        """Convert the currently loaded DDS to CTXR."""
        if not self._path:
            messagebox.showinfo('No file', 'Open a DDS file first.', parent=self)
            return
        if not self._path.lower().endswith('.dds'):
            messagebox.showinfo('Not a DDS',
                                'This file is not a .dds — nothing to convert.',
                                parent=self)
            return
        # Offer to locate the matching original CTXR for header preservation
        orig = os.path.splitext(self._path)[0] + '.ctxr'
        if not os.path.isfile(orig):
            orig = None

        out = filedialog.asksaveasfilename(
            parent=self,
            initialfile=os.path.splitext(os.path.basename(self._path))[0] + '.ctxr',
            filetypes=[('CTXR files', '*.ctxr'), ('All files', '*.*')],
            defaultextension='.ctxr',
        )
        if not out:
            return
        try:
            dds_to_ctxr(self._path, out,
                        original_ctxr_path=orig,
                        log=lambda _: None)
            note = ('\n(original CTXR header preserved)'
                    if orig else '\n(header synthesised — no original CTXR found)')
            messagebox.showinfo('Done', f'Saved:\n{out}{note}', parent=self)
        except Exception as e:
            messagebox.showerror('Conversion error', str(e), parent=self)
