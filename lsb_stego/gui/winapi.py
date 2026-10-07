"""The few Win32 calls the XP window chrome needs, via ctypes.

The chrome is drawn by Tk inside an override-redirect (borderless) toplevel.
These helpers give that window back what borderless windows lose on Windows:
a taskbar button, Alt-Tab, minimise, and XP's rounded top corners. Every
function is a no-op elsewhere so the app still runs with a plainer frame.
"""

from __future__ import annotations

import sys
import tkinter as tk

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetParent.restype = wintypes.HWND
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _user32.SetWindowLongW.restype = ctypes.c_long
    _SetWindowLongPtr = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _SetWindowLongPtr.restype = ctypes.c_ssize_t
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    _gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
    _gdi32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
    _gdi32.CreateRectRgn.restype = wintypes.HRGN
    _gdi32.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]

GWL_STYLE = -16
GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
WS_MINIMIZEBOX = 0x00020000
WS_SYSMENU = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SW_MINIMIZE = 6
RGN_OR = 2


def enable_dpi_awareness() -> None:
    """Render crisply on scaled displays. Must run before Tk is created."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system-DPI aware
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def set_app_id(app_id: str) -> None:
    """Group the taskbar button under our own icon instead of python.exe's."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


def hwnd(win: tk.Misc) -> int:
    """The outer (wrapper) window handle Tk creates for a toplevel."""
    win.update_idletasks()
    return _user32.GetParent(win.winfo_id()) or win.winfo_id()


def make_borderless(win: tk.Tk | tk.Toplevel, *, taskbar: bool, owner: tk.Misc | None = None) -> None:
    """Drop the native frame. ``taskbar`` keeps a taskbar button + Alt-Tab.

    Call while the window is withdrawn; the style change takes effect the
    next time it is shown.
    """
    win.overrideredirect(True)
    if not IS_WINDOWS:
        return
    handle = hwnd(win)
    if taskbar:
        ex = _user32.GetWindowLongW(handle, GWL_EXSTYLE)
        _user32.SetWindowLongW(handle, GWL_EXSTYLE, (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
        style = _user32.GetWindowLongW(handle, GWL_STYLE)
        # Lets a taskbar click minimise/restore and shows "Close window" on right-click.
        _user32.SetWindowLongW(handle, GWL_STYLE, style | WS_MINIMIZEBOX | WS_SYSMENU)
    if owner is not None:
        # Owned windows stay above their owner and never get a taskbar button.
        _SetWindowLongPtr(handle, GWLP_HWNDPARENT, hwnd(owner))
    _user32.SetWindowPos(handle, None, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def round_top_corners(win: tk.Misc, radius: int) -> None:
    """Clip the window to XP's shape: rounded top corners, square bottom."""
    if not IS_WINDOWS:
        return
    w, h = win.winfo_width(), win.winfo_height()
    if w <= 1 or h <= 1:
        return
    region = _gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius * 2, radius * 2)
    lower = _gdi32.CreateRectRgn(0, radius, w, h)
    _gdi32.CombineRgn(region, region, lower, RGN_OR)
    _gdi32.DeleteObject(lower)
    # The system owns the region after a successful call.
    if not _user32.SetWindowRgn(hwnd(win), region, True):
        _gdi32.DeleteObject(region)


def minimize(win: tk.Tk | tk.Toplevel) -> None:
    if IS_WINDOWS:
        _user32.ShowWindow(hwnd(win), SW_MINIMIZE)
    else:
        win.iconify()


def bring_to_front(win: tk.Misc) -> None:
    if IS_WINDOWS:
        _user32.SetForegroundWindow(hwnd(win))
    win.lift()
    win.focus_force()
