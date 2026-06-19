"""
ctxr_tools.gui.preview
=======================
Self-contained image preview widget for a tkinter UI.

``PreviewPanel`` is a ttk.LabelFrame that embeds:
  - A tk.Canvas showing the current mip level composited over a grey
    checkerboard (to make transparent areas visible).
  - A mip-level Spinbox.
  - Four R/G/B/A channel toggle Checkbuttons.

Usage
-----
::

    panel = PreviewPanel(parent_frame)
    panel.pack(side='right', fill='y')

    # Load all mips from a list of PIL RGBA Images:
    panel.load(mip_images)

    # Clear back to the "no image" placeholder:
    panel.clear()

PIL (Pillow) is required.  Import errors are caught at call time and
reported inside the canvas rather than crashing the application.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

try:
    from PIL import Image, ImageTk, ImageDraw
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# Canvas size in pixels
PREVIEW_SIZE = 400
# Checkerboard tile size in pixels
CHECKER_TILE = 16


def _make_checker(size: int) -> "Image.Image":
    """Return a ``size × size`` RGB checkerboard PIL Image."""
    img  = Image.new('RGB', (size, size))
    draw = ImageDraw.Draw(img)
    c1, c2 = (180, 180, 180), (110, 110, 110)
    for y in range(0, size, CHECKER_TILE):
        for x in range(0, size, CHECKER_TILE):
            col = c1 if ((x // CHECKER_TILE + y // CHECKER_TILE) % 2 == 0) else c2
            draw.rectangle([x, y, x + CHECKER_TILE - 1, y + CHECKER_TILE - 1], fill=col)
    return img


def _composite(img: "Image.Image", bg: "Image.Image") -> "Image.Image":
    """
    Paste *img* (RGBA) centred on *bg* (RGB), maintaining aspect ratio.

    Returns a new RGB Image the same size as *bg*.
    """
    iw, ih  = img.size
    scale   = min(bg.width / iw, bg.height / ih)
    nw      = max(1, int(iw * scale))
    nh      = max(1, int(ih * scale))
    interp  = Image.NEAREST if scale >= 1 else Image.LANCZOS
    img     = img.resize((nw, nh), interp)
    out     = bg.copy()
    ox      = (bg.width  - nw) // 2
    oy      = (bg.height - nh) // 2
    out.paste(img, (ox, oy), mask=img.split()[3])
    return out


class PreviewPanel(ttk.LabelFrame):
    """
    A self-contained tkinter widget that shows a CTXR/DDS texture preview.

    Parameters
    ----------
    parent:
        Parent tkinter widget.
    size:
        Canvas width and height in pixels (default: ``PREVIEW_SIZE``).
    **kwargs:
        Passed through to ``ttk.LabelFrame``.
    """

    def __init__(self, parent: tk.Widget, size: int = PREVIEW_SIZE, **kwargs):
        kwargs.setdefault('text', 'Preview')
        super().__init__(parent, **kwargs)

        self._size      = size
        self._mips: List["Image.Image"] = []
        self._photo_ref: Optional["ImageTk.PhotoImage"] = None

        # Build checkerboard once; reused for every render
        if _PIL_OK:
            self._checker = _make_checker(size)

        # ── Canvas ────────────────────────────────────────────────────────────
        self._canvas = tk.Canvas(
            self, width=size, height=size,
            bg='#3a3a3a', highlightthickness=1, highlightbackground='#666',
        )
        self._canvas.pack(padx=6, pady=(6, 2))

        # ── Mip selector ──────────────────────────────────────────────────────
        mip_row = ttk.Frame(self)
        mip_row.pack(fill='x', padx=6, pady=(2, 0))
        ttk.Label(mip_row, text="Mip:").pack(side='left')

        self._mip_var  = tk.IntVar(value=0)
        self._mip_spin = ttk.Spinbox(
            mip_row, from_=0, to=0, width=3,
            textvariable=self._mip_var,
            command=self._refresh,
        )
        self._mip_spin.pack(side='left', padx=4)

        # ── Channel toggles ───────────────────────────────────────────────────
        ch_row = ttk.Frame(self)
        ch_row.pack(pady=(2, 6))

        self._show_r = tk.BooleanVar(value=True)
        self._show_g = tk.BooleanVar(value=True)
        self._show_b = tk.BooleanVar(value=True)
        self._show_a = tk.BooleanVar(value=True)

        for label, var, color in [
            ('R', self._show_r, '#e05555'),
            ('G', self._show_g, '#55b855'),
            ('B', self._show_b, '#5588e0'),
            ('A', self._show_a, '#aaaaaa'),
        ]:
            tk.Checkbutton(
                ch_row, text=label, variable=var, command=self._refresh,
                fg=color, selectcolor='#1e1e1e', activeforeground=color,
                font=('TkDefaultFont', 9, 'bold'),
            ).pack(side='left', padx=6)

        self._show_placeholder()

    # ── Public interface ──────────────────────────────────────────────────────

    def load(self, mips: List["Image.Image"]) -> None:
        """
        Display a new set of mip images.

        Parameters
        ----------
        mips:
            List of PIL RGBA Images, mip 0 (largest) first.  Must not be empty.
        """
        if not mips:
            self.clear()
            return
        self._mips = mips
        self._mip_spin.configure(to=max(0, len(mips) - 1))
        self._mip_var.set(0)
        self._refresh()

    def clear(self) -> None:
        """Remove the current image and show the placeholder text."""
        self._mips = []
        self._mip_spin.configure(to=0)
        self._mip_var.set(0)
        self._show_placeholder()

    def thumbnail(self, size: int = 64) -> Optional["ImageTk.PhotoImage"]:
        """
        Return a ``PhotoImage`` thumbnail of mip 0 for use in a list widget.

        Returns ``None`` if no image is loaded or PIL is unavailable.
        """
        if not _PIL_OK or not self._mips:
            return None
        checker = _make_checker(size)
        img = self._mips[0].copy()
        img.thumbnail((size, size), Image.LANCZOS)
        out   = _composite(img, checker)
        return ImageTk.PhotoImage(out)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _show_placeholder(self) -> None:
        c = self._canvas
        c.delete('all')
        if not _PIL_OK:
            c.create_text(
                self._size // 2, self._size // 2,
                text="pip install Pillow\nto enable preview",
                fill='#e08060', font=('TkDefaultFont', 10), justify='center',
            )
        else:
            c.create_text(
                self._size // 2, self._size // 2,
                text="Select a file\nto preview",
                fill='gray', font=('TkDefaultFont', 11), justify='center',
            )

    def _refresh(self, *_) -> None:
        """Re-render the canvas from the current mip index and channel state."""
        c = self._canvas
        c.delete('all')

        if not _PIL_OK:
            self._show_placeholder()
            return
        if not self._mips:
            self._show_placeholder()
            return

        idx = min(self._mip_var.get(), len(self._mips) - 1)
        img = self._mips[idx].copy()

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

        out   = _composite(img, self._checker)
        photo = ImageTk.PhotoImage(out)
        self._photo_ref = photo          # prevent GC
        c.create_image(0, 0, anchor='nw', image=photo)

        iw, ih = self._mips[idx].size
        c.create_text(
            4, self._size - 4, anchor='sw',
            text=f"Mip {idx}  {iw}×{ih}  ({len(self._mips)} mips)",
            fill='white', font=('Courier', 9),
        )
