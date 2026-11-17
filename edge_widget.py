"""Native Windows left-edge half-moon trigger and vertical dock controller.

Mirrors the SixF edge widget architecture adapted for Python + PyQt5:
- Invisible hot-edge detection on the primary/active monitor left work area
  (``rcWork.left``), offset vertically from the SixF widget so both can
  coexist on the left edge without overlapping.
- Native Win32 layered popup (``WS_POPUP`` + ``WS_EX_LAYERED | WS_EX_TOPMOST |
  WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE``) rendered with GDI+
  (``PixelFormat32bppPARGB``) and ``UpdateLayeredWindow`` for crisp alpha edges.
- Clicking expands the main window along the left edge at full work-area
  height with ``alwaysOnTop`` enabled, collapsing back on blur outside the app.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import math
import os
import sys
import time
from typing import Callable, Optional


# --- Constantes Win32 & GDI+ ---
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

GWL_EXSTYLE = -20
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

WM_DESTROY = 0x0002
WM_SETCURSOR = 0x0020
WM_MOUSEACTIVATE = 0x0021
WM_TIMER = 0x0113
WM_LBUTTONUP = 0x0202

MA_NOACTIVATE = 3
IDC_HAND = 32649
MONITOR_DEFAULTTOPRIMARY = 1
SPI_GETWORKAREA = 0x0030
LOGPIXELSX = 88

AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
ULW_ALPHA = 0x00000002

PIXEL_FORMAT_32BPP_PARGB = 0x000E200B
SMOOTHING_MODE_ANTI_ALIAS = 4
TEXT_RENDERING_ANTI_ALIAS_GRID_FIT = 3
FILL_MODE_ALTERNATE = 0
UNIT_PIXEL = 2
FONT_STYLE_BOLD = 1
STRING_ALIGNMENT_CENTER = 1
LINE_CAP_ROUND = 2
LINE_JOIN_ROUND = 2

EDGE_TIMER_ID = 1001
IDLE_TIMER_MS = 40
ANIM_TIMER_MS = 16
HIDE_GRACE_TICKS = 16  # ~256 ms em 16 ms/tick antes de recolher ao sair
OPENING_GRACE_SECONDS = 0.45  # ~450 ms de tolerância após abrir pela borda

LOGICAL_WIN_WIDTH = 52.0
LOGICAL_WIN_HEIGHT = 88.0
LOGICAL_SHAPE_HEIGHT = 76.0
LOGICAL_BASE_WIDTH = 30.0
LOGICAL_HOVER_EXTRA_WIDTH = 9.0
LOGICAL_MARGIN_Y = 28.0
# Deslocamento dedicado para não ocupar a mesma posição do widget do SixF.
LOGICAL_SIXF_SEPARATION = 104.0
LOGICAL_BAND_PAD = 12.0
EXPANDED_WIDTH = 440


@dataclass(frozen=True)
class WorkArea:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass(frozen=True)
class WindowBounds:
    left: int
    top: int
    width: int
    height: int


def clamp(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def ease_out_cubic(t: float) -> float:
    inv = 1.0 - clamp(t, 0.0, 1.0)
    return 1.0 - inv * inv * inv


def argb(alpha: int, red: int, green: int, blue: int) -> int:
    a = int(clamp(alpha, 0, 255))
    r = int(clamp(red, 0, 255))
    g = int(clamp(green, 0, 255))
    b = int(clamp(blue, 0, 255))
    return ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)


def half_moon_palette(theme: str, hover: float) -> dict:
    """Cores RGB da meia-lua por tema; ``hover`` (0..1) clareia o corpo ao passar o mouse."""
    name = str(theme or "dark").lower()
    h = clamp(hover, 0.0, 1.0)
    if name == "light":  # Fluent Clarity: corpo branco e seta azul
        return {
            "body": (round(255 - 14 * h), round(255 - 12 * h), round(255 - 8 * h)),
            "border": (15, 23, 42), "border_alpha": 45,
            "ink": (37, 99, 235), "text": (71, 85, 105),
        }
    if name == "dark_andre":  # André Dark Minimal: neutros quentes
        return {
            "body": (round(26 + 22 * h), round(26 + 22 * h), round(25 + 22 * h)),
            "border": (255, 255, 255), "border_alpha": 65,
            "ink": (242, 242, 239), "text": (220, 220, 215),
        }
    return {  # Obsidian Whisper: corpo azul-petróleo profundo e seta ciano
        "body": (round(13 + 18 * h), round(18 + 22 * h), round(28 + 26 * h)),
        "border": (142, 213, 255), "border_alpha": 70,
        "ink": (142, 213, 255), "text": (189, 200, 209),
    }


def compute_half_moon_rect_physical(
    work_rect: tuple[int, int, int, int],
    position: str,
    scale: float = 1.0,
) -> tuple[int, int, int, int]:
    """Calcula (x, y, w, h) da meia-lua deslocada da posição do SixF."""
    work_left, work_top, work_right, work_bottom = work_rect
    win_w = int(round(LOGICAL_WIN_WIDTH * scale))
    win_h = int(round(LOGICAL_WIN_HEIGHT * scale))
    margin_y = int(round(LOGICAL_MARGIN_Y * scale))
    peer_offset = int(round(LOGICAL_SIXF_SEPARATION * scale))
    work_h = max(0, work_bottom - work_top)

    pos = str(position or "middle").strip().lower()
    if pos == "top":
        y = work_top + margin_y + peer_offset
    elif pos == "bottom":
        y = work_bottom - win_h - margin_y - peer_offset
    else:
        y = work_top + (work_h - win_h) // 2 + peer_offset

    max_y = max(work_top, work_bottom - win_h)
    y = max(work_top, min(y, max_y))
    return (int(work_left), int(y), win_w, win_h)


def compute_expanded_bounds(
    work_area: WorkArea,
    expanded_width: int = EXPANDED_WIDTH,
) -> tuple[WindowBounds, tuple[int, int]]:
    """Calcula geometria expandida na borda esquerda e tamanho mínimo compatível."""
    max_w = max(420, work_area.width)
    width = max(420, min(int(expanded_width), max_w))
    min_h = min(570, max(240, work_area.height))
    bounds = WindowBounds(
        left=work_area.left,
        top=work_area.top,
        width=width,
        height=work_area.height,
    )
    return bounds, (420, min_h)


if sys.platform == "win32":
    class _POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class _SIZE(ctypes.Structure):
        _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", _RECT),
            ("rcWork", _RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    class _BLENDFUNCTION(ctypes.Structure):
        _fields_ = [
            ("BlendOp", ctypes.c_ubyte),
            ("BlendFlags", ctypes.c_ubyte),
            ("SourceConstantAlpha", ctypes.c_ubyte),
            ("AlphaFormat", ctypes.c_ubyte),
        ]

    class _PointF(ctypes.Structure):
        _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float)]

    class _RectF(ctypes.Structure):
        _fields_ = [
            ("X", ctypes.c_float),
            ("Y", ctypes.c_float),
            ("Width", ctypes.c_float),
            ("Height", ctypes.c_float),
        ]

    class _GdiplusStartupInput(ctypes.Structure):
        _fields_ = [
            ("GdiplusVersion", ctypes.c_uint32),
            ("DebugEventCallback", ctypes.c_void_p),
            ("SuppressBackgroundThread", wintypes.BOOL),
            ("SuppressExternalCodecs", wintypes.BOOL),
        ]

    _WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    class _WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", _WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        ]

    _WIN32_INITIALIZED = False

    def _init_win32_apis():
        global _WIN32_INITIALIZED
        if _WIN32_INITIALIZED:
            return
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        kernel32 = ctypes.windll.kernel32
        gdiplus = ctypes.windll.gdiplus

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEXW)]
        user32.RegisterClassExW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = wintypes.LONG
        user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
        user32.SetTimer.restype = ctypes.c_size_t
        user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        user32.KillTimer.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        user32.LoadCursorW.restype = wintypes.HANDLE
        user32.SetCursor.argtypes = [wintypes.HANDLE]
        user32.SetCursor.restype = wintypes.HANDLE
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
        user32.SystemParametersInfoW.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.BringWindowToTop.argtypes = [wintypes.HWND]
        user32.BringWindowToTop.restype = wintypes.BOOL
        user32.SetFocus.argtypes = [wintypes.HWND]
        user32.SetFocus.restype = wintypes.HWND
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        user32.AttachThreadInput.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        user32.WindowFromPoint.argtypes = [_POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = ctypes.c_int
        user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC, ctypes.POINTER(_POINT), ctypes.POINTER(_SIZE),
            wintypes.HDC, ctypes.POINTER(_POINT), wintypes.COLORREF,
            ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD,
        ]
        user32.UpdateLayeredWindow.restype = wintypes.BOOL
        if hasattr(user32, "GetDpiForWindow"):
            user32.GetDpiForWindow.argtypes = [wintypes.HWND]
            user32.GetDpiForWindow.restype = wintypes.UINT

        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
        gdi32.GetDeviceCaps.restype = ctypes.c_int

        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetCurrentProcessId.argtypes = []
        kernel32.GetCurrentProcessId.restype = wintypes.DWORD
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        gdiplus.GdiplusStartup.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(_GdiplusStartupInput),
            ctypes.c_void_p,
        ]
        gdiplus.GdiplusStartup.restype = ctypes.c_int
        gdiplus.GdiplusShutdown.argtypes = [ctypes.c_void_p]
        gdiplus.GdiplusShutdown.restype = None

        gdiplus.GdipCreateBitmapFromScan0.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        gdiplus.GdipGetImageGraphicsContext.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        gdiplus.GdipSetSmoothingMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gdiplus.GdipSetTextRenderingHint.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gdiplus.GdipGraphicsClear.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        gdiplus.GdipCreatePath.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        gdiplus.GdipAddPathArc.argtypes = [
            ctypes.c_void_p, ctypes.c_float, ctypes.c_float,
            ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ]
        gdiplus.GdipClosePathFigure.argtypes = [ctypes.c_void_p]
        gdiplus.GdipDeletePath.argtypes = [ctypes.c_void_p]
        gdiplus.GdipCreateSolidFill.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
        gdiplus.GdipFillPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        gdiplus.GdipFillEllipse.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ]
        gdiplus.GdipDeleteBrush.argtypes = [ctypes.c_void_p]
        gdiplus.GdipCreatePen1.argtypes = [
            ctypes.c_uint32, ctypes.c_float, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p),
        ]
        gdiplus.GdipSetPenStartCap.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gdiplus.GdipSetPenEndCap.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gdiplus.GdipSetPenLineJoin.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gdiplus.GdipDrawArc.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
            ctypes.c_float, ctypes.c_float,
        ]
        gdiplus.GdipDrawLines.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_PointF), ctypes.c_int,
        ]
        gdiplus.GdipDeletePen.argtypes = [ctypes.c_void_p]
        gdiplus.GdipCreateFontFamilyFromName.argtypes = [
            wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        gdiplus.GdipCreateFont.argtypes = [
            ctypes.c_void_p, ctypes.c_float, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p),
        ]
        gdiplus.GdipCreateStringFormat.argtypes = [
            ctypes.c_int, ctypes.c_uint16, ctypes.POINTER(ctypes.c_void_p),
        ]
        gdiplus.GdipSetStringFormatAlign.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gdiplus.GdipSetStringFormatLineAlign.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gdiplus.GdipDrawString.argtypes = [
            ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p,
            ctypes.POINTER(_RectF), ctypes.c_void_p, ctypes.c_void_p,
        ]
        gdiplus.GdipDeleteStringFormat.argtypes = [ctypes.c_void_p]
        gdiplus.GdipDeleteFont.argtypes = [ctypes.c_void_p]
        gdiplus.GdipDeleteFontFamily.argtypes = [ctypes.c_void_p]
        gdiplus.GdipCreateHBITMAPFromBitmap.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.HBITMAP), ctypes.c_uint32,
        ]
        gdiplus.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
        gdiplus.GdipDisposeImage.argtypes = [ctypes.c_void_p]

        _WIN32_INITIALIZED = True


class NativeEdgeHalfMoon:
    """Janela nativa Win32 em meia-lua na borda esquerda com GDI+ e hot-edge."""

    CLASS_NAME = "DitaEuEdgeHalfMoonWindow"
    _instances: dict[int, "NativeEdgeHalfMoon"] = {}

    def __init__(
        self,
        main_hwnd: Optional[int],
        on_open_requested: Callable[[Optional[WorkArea]], None],
    ):
        self._main_hwnd = main_hwnd
        self._on_open_requested = on_open_requested
        self._hwnd: Optional[int] = None
        self._gdip_token = ctypes.c_void_p()
        self._gdip_started = False
        self._wndproc_ref = None

        self._enabled = False
        self._position = "middle"
        self._is_dark = True
        self._theme_name = "dark"
        self._is_active = True
        self._main_expanded = False

        self._window_shown = False
        self._target_visible = False
        self._is_hovering = False
        self._hide_grace_ticks = 0
        self._reveal_progress = 0.0
        self._hover_progress = 0.0
        self._current_timer_ms = 0

        if sys.platform == "win32":
            self._initialize()

    def _initialize(self):
        _init_win32_apis()
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        gdiplus = ctypes.windll.gdiplus

        startup = _GdiplusStartupInput(1, None, False, False)
        if gdiplus.GdiplusStartup(ctypes.byref(self._gdip_token), ctypes.byref(startup), None) == 0:
            self._gdip_started = True

        hinst = kernel32.GetModuleHandleW(None)
        self._wndproc_ref = _WNDPROC(self._static_wndproc)

        wc = _WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = self.CLASS_NAME
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_HAND))

        user32.RegisterClassExW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            self.CLASS_NAME,
            "DitaEuEdgeTrigger",
            WS_POPUP,
            0, 0, 1, 1,
            None, None, hinst, None,
        )
        if hwnd:
            self._hwnd = int(hwnd)
            NativeEdgeHalfMoon._instances[self._hwnd] = self

    @staticmethod
    def _static_wndproc(hwnd, msg, wparam, lparam):
        inst = NativeEdgeHalfMoon._instances.get(int(hwnd))
        if inst is not None:
            res = inst._handle_message(int(hwnd), int(msg), int(wparam), int(lparam))
            if res is not None:
                return res
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle_message(self, hwnd: int, msg: int, wparam: int, lparam: int) -> Optional[int]:
        if msg == WM_TIMER and wparam == EDGE_TIMER_ID:
            self._on_timer_tick()
            return 0
        if msg == WM_SETCURSOR:
            user32 = ctypes.windll.user32
            user32.SetCursor(user32.LoadCursorW(None, ctypes.c_void_p(IDC_HAND)))
            return 1
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_LBUTTONUP:
            if self._enabled and not self._main_expanded and self._reveal_progress > 0.15:
                self._notify_open_from_edge()
            return 0
        if msg == WM_DESTROY:
            NativeEdgeHalfMoon._instances.pop(hwnd, None)
            return 0
        return None

    def set_main_hwnd(self, hwnd: Optional[int]):
        self._main_hwnd = int(hwnd) if hwnd else None

    def configure(
        self,
        enabled: bool,
        position: str,
        theme: str,
        active: bool = True,
        main_expanded: Optional[bool] = None,
    ):
        self._enabled = bool(enabled)
        self._position = str(position or "middle").lower()
        self._is_dark = (str(theme or "dark").lower() != "light")
        self._theme_name = str(theme or "dark").lower()
        self._is_active = bool(active)
        if main_expanded is not None:
            self._main_expanded = bool(main_expanded)

        if not self._enabled or self._main_expanded:
            self.hide_immediate()
        elif self._window_shown:
            self._render_half_moon()
        self._update_polling_timer()

    def set_main_expanded(self, expanded: bool):
        self._main_expanded = bool(expanded)
        if self._main_expanded:
            self.hide_immediate()
        self._update_polling_timer()

    def _get_dpi_scale(self) -> float:
        if sys.platform != "win32":
            return 1.0
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        ref = self._main_hwnd or self._hwnd
        if hasattr(user32, "GetDpiForWindow") and ref:
            dpi = user32.GetDpiForWindow(ref)
            if dpi >= 96:
                return float(dpi) / 96.0
        hdc = user32.GetDC(None)
        dpi = gdi32.GetDeviceCaps(hdc, LOGPIXELSX) if hdc else 96
        if hdc:
            user32.ReleaseDC(None, hdc)
        return float(max(96, dpi)) / 96.0

    def _compute_work_and_rect(self) -> tuple[tuple[int, int, int, int], int, int, int, int, float]:
        user32 = ctypes.windll.user32
        ref = self._main_hwnd or self._hwnd
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        hmon = user32.MonitorFromWindow(ref, MONITOR_DEFAULTTOPRIMARY)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(mi.rcWork), 0)
        work = (
            int(mi.rcWork.left),
            int(mi.rcWork.top),
            int(mi.rcWork.right),
            int(mi.rcWork.bottom),
        )
        scale = self._get_dpi_scale()
        wx, wy, ww, wh = compute_half_moon_rect_physical(work, self._position, scale)
        return work, wx, wy, ww, wh, scale

    def get_work_area(self) -> Optional[WorkArea]:
        if sys.platform != "win32":
            return None
        work, _, _, _, _, _ = self._compute_work_and_rect()
        left, top, right, bottom = work
        if right <= left or bottom <= top:
            return None
        return WorkArea(left=left, top=top, width=right - left, height=bottom - top)

    def is_foreground_owned_by_app(self) -> bool:
        if sys.platform != "win32":
            return False
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        fg = user32.GetForegroundWindow()
        if not fg:
            return False
        fg_pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))
        return int(fg_pid.value) == int(kernel32.GetCurrentProcessId())

    def get_mouse_outside_state(self) -> tuple[bool, bool]:
        """Retorna (mouse_button_down, cursor_over_app_window)."""
        if sys.platform != "win32":
            return (False, True)
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        left_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
        right_down = bool(user32.GetAsyncKeyState(0x02) & 0x8000)
        mouse_down = left_down or right_down
        if not mouse_down:
            return (False, True)
        pt = _POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return (True, False)
        hwnd_under = user32.WindowFromPoint(pt)
        if not hwnd_under:
            return (True, False)
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd_under, ctypes.byref(pid))
        owned = int(pid.value) == int(kernel32.GetCurrentProcessId())
        return (True, owned)

    def _update_polling_timer(self):
        if not self._hwnd or sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        if not self._enabled or self._main_expanded:
            if self._current_timer_ms != 0:
                user32.KillTimer(self._hwnd, EDGE_TIMER_ID)
                self._current_timer_ms = 0
            return

        animating = (
            self._window_shown
            or self._target_visible
            or self._reveal_progress > 0.001
            or (self._is_hovering and self._hover_progress < 0.999)
            or (not self._is_hovering and self._hover_progress > 0.001)
        )
        desired = ANIM_TIMER_MS if animating else IDLE_TIMER_MS
        if self._current_timer_ms != desired:
            user32.SetTimer(self._hwnd, EDGE_TIMER_ID, desired, None)
            self._current_timer_ms = desired

    def hide_immediate(self):
        self._target_visible = False
        self._is_hovering = False
        self._hide_grace_ticks = 0
        self._reveal_progress = 0.0
        self._hover_progress = 0.0
        if self._window_shown and self._hwnd and sys.platform == "win32":
            ctypes.windll.user32.ShowWindow(self._hwnd, SW_HIDE)
            self._window_shown = False
        self._update_polling_timer()

    def _on_timer_tick(self):
        if not self._hwnd or not self._enabled or self._main_expanded:
            self.hide_immediate()
            return

        user32 = ctypes.windll.user32
        work, win_x, win_y, win_w, win_h, scale = self._compute_work_and_rect()
        pt = _POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return

        edge_threshold = int(round(4.0 * scale))
        band_pad = int(round(LOGICAL_BAND_PAD * scale))
        band_top = win_y - band_pad
        band_bottom = win_y + win_h + band_pad

        on_hot_edge = (
            (work[0] - 2 <= pt.x <= work[0] + edge_threshold)
            and (band_top <= pt.y <= band_bottom)
        )

        cur_shape_w = (
            (LOGICAL_BASE_WIDTH + LOGICAL_HOVER_EXTRA_WIDTH * self._hover_progress)
            * ease_out_cubic(self._reveal_progress)
            * scale
        )
        hit_w = int(round(cur_shape_w + 10.0 * scale))
        over_half_moon = (
            self._window_shown
            and (win_x - 2 <= pt.x <= win_x + hit_w)
            and (win_y <= pt.y <= win_y + win_h)
        )

        if on_hot_edge or over_half_moon:
            self._target_visible = True
            self._is_hovering = over_half_moon
            self._hide_grace_ticks = HIDE_GRACE_TICKS
        else:
            self._is_hovering = False
            if self._hide_grace_ticks > 0:
                self._hide_grace_ticks -= 1
            else:
                self._target_visible = False

        reveal_step = 0.14
        hover_step = 0.16
        prev_reveal = self._reveal_progress
        prev_hover = self._hover_progress

        if self._target_visible:
            self._reveal_progress = min(1.0, self._reveal_progress + reveal_step)
        else:
            self._reveal_progress = max(0.0, self._reveal_progress - reveal_step)

        if self._is_hovering and self._target_visible:
            self._hover_progress = min(1.0, self._hover_progress + hover_step)
        else:
            self._hover_progress = max(0.0, self._hover_progress - hover_step)

        if self._target_visible and not self._window_shown:
            user32.SetWindowPos(
                self._hwnd, HWND_TOPMOST, win_x, win_y, win_w, win_h,
                SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
            self._window_shown = True
            self._render_half_moon()
        elif self._window_shown:
            if self._reveal_progress <= 0.001 and not self._target_visible:
                user32.ShowWindow(self._hwnd, SW_HIDE)
                self._window_shown = False
            elif (
                abs(self._reveal_progress - prev_reveal) > 0.0001
                or abs(self._hover_progress - prev_hover) > 0.0001
            ):
                user32.SetWindowPos(
                    self._hwnd, HWND_TOPMOST, win_x, win_y, win_w, win_h,
                    SWP_NOACTIVATE | SWP_NOZORDER,
                )
                self._render_half_moon()

        self._update_polling_timer()

    def _render_half_moon(self):
        if not self._hwnd or not self._gdip_started or not self._window_shown:
            return

        _, win_x, win_y, win_w, win_h, scale = self._compute_work_and_rect()
        if win_w <= 0 or win_h <= 0:
            return

        eased_reveal = ease_out_cubic(self._reveal_progress)
        eased_hover = ease_out_cubic(self._hover_progress)
        shape_w = float((LOGICAL_BASE_WIDTH + LOGICAL_HOVER_EXTRA_WIDTH * eased_hover) * eased_reveal * scale)
        if shape_w < 1.5:
            return

        shape_h = float(LOGICAL_SHAPE_HEIGHT * scale)
        shape_y = (float(win_h) - shape_h) * 0.5

        gdiplus = ctypes.windll.gdiplus
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        bmp = ctypes.c_void_p()
        g = ctypes.c_void_p()
        if gdiplus.GdipCreateBitmapFromScan0(
            win_w, win_h, 0, PIXEL_FORMAT_32BPP_PARGB, None, ctypes.byref(bmp)
        ) != 0 or not bmp.value:
            return

        try:
            if gdiplus.GdipGetImageGraphicsContext(bmp, ctypes.byref(g)) != 0 or not g.value:
                return
            gdiplus.GdipSetSmoothingMode(g, SMOOTHING_MODE_ANTI_ALIAS)
            gdiplus.GdipSetTextRenderingHint(g, TEXT_RENDERING_ANTI_ALIAS_GRID_FIT)
            gdiplus.GdipGraphicsClear(g, 0x00000000)

            # Sombra suave na borda curva
            for i in (2, 1):
                pad = float(i * 2.0 * scale)
                sp = ctypes.c_void_p()
                sb = ctypes.c_void_p()
                gdiplus.GdipCreatePath(FILL_MODE_ALTERNATE, ctypes.byref(sp))
                gdiplus.GdipAddPathArc(
                    sp, -shape_w - pad, shape_y - pad * 0.5,
                    (shape_w + pad) * 2.0, shape_h + pad, -90.0, 180.0,
                )
                gdiplus.GdipClosePathFigure(sp)
                s_alpha = int((22 if i == 2 else 42) * eased_reveal)
                gdiplus.GdipCreateSolidFill(argb(s_alpha, 0, 0, 0), ctypes.byref(sb))
                gdiplus.GdipFillPath(g, sb, sp)
                gdiplus.GdipDeleteBrush(sb)
                gdiplus.GdipDeletePath(sp)

            # Corpo da meia-lua colado na borda esquerda (x = 0)
            bp = ctypes.c_void_p()
            bb = ctypes.c_void_p()
            gdiplus.GdipCreatePath(FILL_MODE_ALTERNATE, ctypes.byref(bp))
            gdiplus.GdipAddPathArc(bp, -shape_w, shape_y, shape_w * 2.0, shape_h, -90.0, 180.0)
            gdiplus.GdipClosePathFigure(bp)

            colors = half_moon_palette(self._theme_name, eased_hover)
            base_alpha = int(round((220.0 + 25.0 * eased_hover) * eased_reveal))
            fill_argb = argb(base_alpha, *colors["body"])
            gdiplus.GdipCreateSolidFill(fill_argb, ctypes.byref(bb))
            gdiplus.GdipFillPath(g, bb, bp)
            gdiplus.GdipDeleteBrush(bb)
            gdiplus.GdipDeletePath(bp)

            # Contorno sutil ao longo do arco
            border_alpha = int(round(colors["border_alpha"] * eased_reveal))
            border_argb = argb(border_alpha, *colors["border"])
            bpen = ctypes.c_void_p()
            gdiplus.GdipCreatePen1(border_argb, float(1.1 * scale), UNIT_PIXEL, ctypes.byref(bpen))
            gdiplus.GdipDrawArc(g, bpen, -shape_w, shape_y, shape_w * 2.0, shape_h, -90.0, 180.0)
            gdiplus.GdipDeletePen(bpen)

            # Conteúdo interno (LED de status, seta "›" e sigla discreta "DE")
            if eased_reveal > 0.35:
                content_alpha_f = clamp((eased_reveal - 0.35) / 0.65, 0.0, 1.0)

                # LED de status ativo
                dot_d = float(6.0 * scale)
                dot_x = max(float(4.0 * scale), shape_w * 0.44 - dot_d * 0.5)
                dot_y = shape_y + float(14.0 * scale)
                dot_alpha = int(round(255.0 * content_alpha_f))
                dot_argb = (
                    argb(dot_alpha, 56, 188, 55) if self._is_active
                    else argb(dot_alpha, 142, 142, 137)
                )
                dbrush = ctypes.c_void_p()
                gdiplus.GdipCreateSolidFill(dot_argb, ctypes.byref(dbrush))
                gdiplus.GdipFillEllipse(g, dbrush, dot_x, dot_y, dot_d, dot_d)
                gdiplus.GdipDeleteBrush(dbrush)

                # Seta indicativa "›" (destaca no hover)
                cx = max(float(7.0 * scale), shape_w * 0.48 + float(2.0 * eased_hover * scale))
                cy = shape_y + shape_h * 0.52
                arm = float((4.2 + 0.8 * eased_hover) * scale)
                chevron_alpha = int(round((190.0 + 65.0 * eased_hover) * content_alpha_f))
                ink_argb = argb(chevron_alpha, *colors["ink"])
                cpen = ctypes.c_void_p()
                gdiplus.GdipCreatePen1(ink_argb, float(1.9 * scale), UNIT_PIXEL, ctypes.byref(cpen))
                gdiplus.GdipSetPenStartCap(cpen, LINE_CAP_ROUND)
                gdiplus.GdipSetPenEndCap(cpen, LINE_CAP_ROUND)
                gdiplus.GdipSetPenLineJoin(cpen, LINE_JOIN_ROUND)
                pts = (_PointF * 3)(
                    _PointF(cx - arm * 0.45, cy - arm),
                    _PointF(cx + arm * 0.55, cy),
                    _PointF(cx - arm * 0.45, cy + arm),
                )
                gdiplus.GdipDrawLines(g, cpen, pts, 3)
                gdiplus.GdipDeletePen(cpen)

                # Pequena sigla "DE" discreta na parte inferior da meia-lua
                text_alpha = int(round((155.0 + 80.0 * eased_hover) * content_alpha_f))
                text_argb = argb(text_alpha, *colors["text"])
                family = ctypes.c_void_p()
                font = ctypes.c_void_p()
                fmt = ctypes.c_void_p()
                tbrush = ctypes.c_void_p()
                if gdiplus.GdipCreateFontFamilyFromName("Segoe UI", None, ctypes.byref(family)) == 0 and family.value:
                    gdiplus.GdipCreateFont(
                        family, float(8.0 * scale), FONT_STYLE_BOLD, UNIT_PIXEL, ctypes.byref(font),
                    )
                    gdiplus.GdipCreateStringFormat(0, 0, ctypes.byref(fmt))
                    gdiplus.GdipSetStringFormatAlign(fmt, STRING_ALIGNMENT_CENTER)
                    gdiplus.GdipSetStringFormatLineAlign(fmt, STRING_ALIGNMENT_CENTER)
                    gdiplus.GdipCreateSolidFill(text_argb, ctypes.byref(tbrush))
                    rect = _RectF(
                        float(1.0 * scale),
                        shape_y + shape_h - float(22.0 * scale),
                        max(float(14.0 * scale), shape_w * 0.85),
                        float(14.0 * scale),
                    )
                    if font.value and fmt.value and tbrush.value:
                        gdiplus.GdipDrawString(g, "DE", -1, font, ctypes.byref(rect), fmt, tbrush)
                    if tbrush.value:
                        gdiplus.GdipDeleteBrush(tbrush)
                    if fmt.value:
                        gdiplus.GdipDeleteStringFormat(fmt)
                    if font.value:
                        gdiplus.GdipDeleteFont(font)
                    gdiplus.GdipDeleteFontFamily(family)

            screen_dc = user32.GetDC(None)
            mem_dc = gdi32.CreateCompatibleDC(screen_dc)
            hbmp = wintypes.HBITMAP()
            if gdiplus.GdipCreateHBITMAPFromBitmap(bmp, ctypes.byref(hbmp), 0x00000000) == 0 and hbmp.value:
                old_obj = gdi32.SelectObject(mem_dc, hbmp)
                pt_src = _POINT(0, 0)
                pt_dst = _POINT(win_x, win_y)
                size_wnd = _SIZE(win_w, win_h)
                blend = _BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
                user32.UpdateLayeredWindow(
                    self._hwnd, screen_dc, ctypes.byref(pt_dst), ctypes.byref(size_wnd),
                    mem_dc, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA,
                )
                gdi32.SelectObject(mem_dc, old_obj)
                gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(None, screen_dc)
        finally:
            if g.value:
                gdiplus.GdipDeleteGraphics(g)
            gdiplus.GdipDisposeImage(bmp)

    def _notify_open_from_edge(self):
        self._main_expanded = True
        self.hide_immediate()
        work_area = self.get_work_area()
        if self._on_open_requested:
            self._on_open_requested(work_area)

    def shutdown(self):
        if self._hwnd and sys.platform == "win32":
            user32 = ctypes.windll.user32
            user32.KillTimer(self._hwnd, EDGE_TIMER_ID)
            user32.DestroyWindow(self._hwnd)
            NativeEdgeHalfMoon._instances.pop(self._hwnd, None)
            self._hwnd = None
        self._current_timer_ms = 0
        self._window_shown = False
        self._target_visible = False
        self._is_hovering = False
        self._reveal_progress = 0.0
        self._hover_progress = 0.0
        if self._gdip_started and sys.platform == "win32":
            ctypes.windll.gdiplus.GdiplusShutdown(self._gdip_token)
            self._gdip_started = False
        self._main_hwnd = None


class QtWindowAdapter:
    """Adaptador de janela PyQt5 + Win32 para o EdgeWidgetService."""

    def __init__(self, widget):
        self._widget = widget
        self._use_win32 = (
            sys.platform == "win32" and os.environ.get("QT_QPA_PLATFORM") != "offscreen"
        )
        if self._use_win32:
            _init_win32_apis()

    def hwnd(self) -> Optional[int]:
        try:
            return int(self._widget.winId())
        except Exception:
            return None

    def get_bounds(self) -> WindowBounds:
        if self._use_win32:
            h = self.hwnd()
            if h:
                rc = _RECT()
                if ctypes.windll.user32.GetWindowRect(h, ctypes.byref(rc)):
                    return WindowBounds(
                        left=int(rc.left),
                        top=int(rc.top),
                        width=int(rc.right - rc.left),
                        height=int(rc.bottom - rc.top),
                    )
        g = self._widget.geometry()
        return WindowBounds(left=g.x(), top=g.y(), width=g.width(), height=g.height())

    def set_bounds(self, bounds: WindowBounds):
        if self._use_win32:
            h = self.hwnd()
            if h:
                ctypes.windll.user32.SetWindowPos(
                    h, 0, bounds.left, bounds.top, bounds.width, bounds.height,
                    SWP_NOZORDER | SWP_NOACTIVATE,
                )
                return
        self._widget.setGeometry(bounds.left, bounds.top, bounds.width, bounds.height)

    def get_minimum_size(self) -> tuple[int, int]:
        sz = self._widget.minimumSize()
        return (int(sz.width()), int(sz.height()))

    def set_minimum_size(self, width: int, height: int):
        self._widget.setMinimumSize(int(width), int(height))

    def is_maximized(self) -> bool:
        return bool(self._widget.isMaximized())

    def unmaximize(self):
        if self._widget.isMaximized():
            self._widget.showNormal()

    def maximize(self):
        self._widget.showMaximized()

    def is_always_on_top(self) -> bool:
        if self._use_win32:
            h = self.hwnd()
            if h:
                ex = ctypes.windll.user32.GetWindowLongW(h, GWL_EXSTYLE)
                return bool(ex & WS_EX_TOPMOST)
        from PyQt5 import QtCore
        return bool(self._widget.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint)

    def set_always_on_top(self, enabled: bool):
        if self._use_win32:
            h = self.hwnd()
            if h:
                insert_after = HWND_TOPMOST if enabled else HWND_NOTOPMOST
                ctypes.windll.user32.SetWindowPos(
                    h, insert_after, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                )
                return
        from PyQt5 import QtCore
        was_visible = self._widget.isVisible()
        self._widget.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, bool(enabled))
        if was_visible:
            self._widget.show()

    def show(self):
        self._widget.show()

    def hide(self):
        self._widget.hide()

    def focus(self):
        if self._use_win32:
            h = self.hwnd()
            if h:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                fg = user32.GetForegroundWindow()
                cur_tid = kernel32.GetCurrentThreadId()
                attached = False
                fg_tid = 0
                if fg and fg != h:
                    fg_tid = user32.GetWindowThreadProcessId(fg, None)
                    if fg_tid and fg_tid != cur_tid:
                        attached = bool(user32.AttachThreadInput(fg_tid, cur_tid, True))
                try:
                    user32.SetForegroundWindow(h)
                    user32.BringWindowToTop(h)
                    user32.SetFocus(h)
                finally:
                    if attached:
                        user32.AttachThreadInput(fg_tid, cur_tid, False)
        self._widget.raise_()
        self._widget.activateWindow()

    def is_active(self) -> bool:
        return bool(self._widget.isActiveWindow())


class EdgeWidgetService:
    """Gerencia o widget retrátil em meia-lua e a expansão vertical na borda esquerda."""

    def __init__(
        self,
        window_adapter,
        native_edge: Optional[NativeEdgeHalfMoon] = None,
        use_native: Optional[bool] = None,
        clock: Callable[[], float] = time.monotonic,
        on_expanded_changed: Optional[Callable[[bool], None]] = None,
    ):
        self._window = window_adapter
        self._clock = clock
        self._on_expanded_changed = on_expanded_changed
        self._enabled = False
        self._position = "middle"
        self._theme = "dark"
        self._active = True
        self._is_expanded_from_edge = False
        self._busy = False
        self._opening_grace_until = 0.0
        self._saw_app_foreground = False
        self._prev_mouse_down = False

        self._saved_normal_bounds: Optional[WindowBounds] = None
        self._saved_min_size: Optional[tuple[int, int]] = None
        self._saved_maximized = False
        self._saved_always_on_top = False

        if use_native is None:
            use_native = (
                sys.platform == "win32" and os.environ.get("QT_QPA_PLATFORM") != "offscreen"
            )

        if native_edge is not None:
            self._native = native_edge
        elif use_native:
            main_hwnd = window_adapter.hwnd() if hasattr(window_adapter, "hwnd") else None
            self._native = NativeEdgeHalfMoon(main_hwnd, self.open_expanded_from_edge)
        else:
            self._native = None

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def position(self) -> str:
        return self._position

    @property
    def is_expanded_from_edge(self) -> bool:
        return self._is_expanded_from_edge

    def configure(
        self,
        enabled: bool,
        position: str = "middle",
        theme: str = "dark",
        active: bool = True,
    ):
        was_enabled = self._enabled
        self._enabled = bool(enabled)
        self._position = str(position or "middle").lower()
        if self._position not in ("top", "middle", "bottom"):
            self._position = "middle"
        self._theme = str(theme or "dark").lower()
        self._active = bool(active)

        if was_enabled and not self._enabled:
            self._restore_after_disabling()

        if self._native is not None:
            self._native.configure(
                enabled=self._enabled,
                position=self._position,
                theme=self._theme,
                active=self._active,
                main_expanded=self._is_expanded_from_edge,
            )

    def _fetch_work_area(self) -> Optional[WorkArea]:
        if self._native is not None:
            return self._native.get_work_area()
        return None

    def _is_foreground_owned_by_app(self) -> bool:
        if self._native is not None:
            return bool(self._native.is_foreground_owned_by_app())
        return False

    def _get_mouse_outside_state(self) -> tuple[bool, bool]:
        if self._native is not None and hasattr(self._native, "get_mouse_outside_state"):
            return self._native.get_mouse_outside_state()
        return (False, True)

    def _set_native_main_expanded(self, expanded: bool):
        if self._native is not None:
            self._native.set_main_expanded(expanded)
        if self._on_expanded_changed is not None:
            self._on_expanded_changed(bool(expanded))

    def open_expanded_from_edge(self, work_area: Optional[WorkArea] = None):
        """Expande a janela principal na borda esquerda com altura máxima útil."""
        if self._busy:
            return
        self._busy = True
        self._opening_grace_until = self._clock() + OPENING_GRACE_SECONDS
        self._saw_app_foreground = False
        self._prev_mouse_down = False
        try:
            target = work_area or self._fetch_work_area()
            if target is None or target.height <= 0 or target.width <= 0:
                self._window.show()
                self._window.focus()
                return

            if not self._is_expanded_from_edge and self._saved_normal_bounds is None:
                self._saved_maximized = self._window.is_maximized()
                self._saved_always_on_top = self._window.is_always_on_top()
                self._saved_min_size = self._window.get_minimum_size()
                if not self._saved_maximized:
                    self._saved_normal_bounds = self._window.get_bounds()

            if self._window.is_maximized():
                self._window.unmaximize()
                if self._saved_normal_bounds is None:
                    self._saved_normal_bounds = self._window.get_bounds()

            bounds, min_size = compute_expanded_bounds(target, EXPANDED_WIDTH)
            self._window.set_minimum_size(min_size[0], min_size[1])
            self._is_expanded_from_edge = True
            self._set_native_main_expanded(True)

            self._window.show()
            self._window.set_bounds(bounds)
            self._window.set_always_on_top(True)
            self._window.focus()
            if self._is_foreground_owned_by_app():
                self._saw_app_foreground = True
        finally:
            self._busy = False

    def handle_window_blur(self):
        """Recolhe para a borda quando perde o foco fora do processo do app."""
        if not self._enabled or self._busy or not self._is_expanded_from_edge:
            return
        if self._clock() < self._opening_grace_until:
            return
        if self._is_foreground_owned_by_app():
            self._saw_app_foreground = True
            return
        self.collapse_to_edge()

    def check_outside_interaction(self):
        """Detecta clique fora do app ou perda de foreground após abertura pela borda."""
        if not self._enabled or self._busy or not self._is_expanded_from_edge:
            return

        mouse_down, cursor_owned = self._get_mouse_outside_state()
        if self._clock() < self._opening_grace_until:
            self._prev_mouse_down = mouse_down
            return

        if self._is_foreground_owned_by_app():
            self._saw_app_foreground = True
        elif self._saw_app_foreground:
            self._prev_mouse_down = mouse_down
            self.collapse_to_edge()
            return

        just_clicked_outside = mouse_down and not self._prev_mouse_down and not cursor_owned
        self._prev_mouse_down = mouse_down
        if just_clicked_outside:
            self.collapse_to_edge()

    def collapse_to_edge(self):
        """Recolhe a janela principal de volta para o gatilho invisível na borda."""
        if self._busy:
            return
        self._busy = True
        try:
            self._is_expanded_from_edge = False
            self._set_native_main_expanded(False)
            self._window.hide()
        finally:
            self._busy = False

    def mark_hidden(self):
        """Chamado quando a janela principal é ocultada/fechada para a bandeja."""
        self._is_expanded_from_edge = False
        self._set_native_main_expanded(False)

    def _restore_after_disabling(self):
        if self._busy:
            return
        self._busy = True
        try:
            was_expanded = self._is_expanded_from_edge
            self._is_expanded_from_edge = False
            self._set_native_main_expanded(False)

            min_size = self._saved_min_size or (600, 570)
            self._window.set_always_on_top(self._saved_always_on_top)
            self._window.set_minimum_size(min_size[0], min_size[1])
            if was_expanded and self._saved_normal_bounds is not None:
                self._window.set_bounds(self._saved_normal_bounds)
            if was_expanded and self._saved_maximized:
                self._window.maximize()

            self._saved_normal_bounds = None
            self._saved_min_size = None
            self._saved_maximized = False
            self._saved_always_on_top = False
        finally:
            self._busy = False

    def shutdown(self):
        if self._native is not None:
            self._native.shutdown()
            self._native = None
