import os
import time
import pyperclip
import win32clipboard
import win32con
import ctypes
import threading
import json
import struct
from contextlib import contextmanager
from ctypes import wintypes

VK_CONTROL = 0x11
VK_V = 0x56
VK_BACK = 0x08
KEYEVENTF_KEYUP = 0x0002

user32 = ctypes.windll.user32

def _send_key_event(vk_code: int, flags: int):
    user32.keybd_event(vk_code, 0, flags, 0)

def backspace_chars(count: int):
    """Apaga N caracteres previamente digitados no cursor ativo"""
    if count <= 0:
        return
    for _ in range(count):
        _send_key_event(VK_BACK, 0)
        _send_key_event(VK_BACK, KEYEVENTF_KEYUP)
        time.sleep(0.005)

def inject_text(text: str, restore_clipboard: bool = True):
    """
    Injeta o texto diretamente no controle de foco ativo via simulação de Ctrl+V.
    Preserva o conteúdo anterior do clipboard caso restore_clipboard seja True,
    aguardando a confirmação de leitura do aplicativo em foco antes de restaurar.
    """
    if not text:
        return

    old_text = None
    if restore_clipboard:
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                old_text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
            old_text = None

    try:
        pyperclip.copy(text)
        time.sleep(0.05)

        # Simula Ctrl+V
        _send_key_event(VK_CONTROL, 0)
        _send_key_event(VK_V, 0)
        time.sleep(0.03)
        _send_key_event(VK_V, KEYEVENTF_KEYUP)
        _send_key_event(VK_CONTROL, KEYEVENTF_KEYUP)

        # Aguarda tempo suficiente (350ms) para que aplicativos mais lentos (VS Code, navegadores)
        # terminem de consumir o Ctrl+V antes de restaurar o clipboard antigo
        if restore_clipboard and old_text is not None and old_text != text:
            time.sleep(0.35)
            try:
                pyperclip.copy(old_text)
            except Exception:
                pass
    except Exception as e:
        print(f"[Injector] Erro ao injetar texto: {e}")


# Voice Transform is intentionally independent from the legacy F8 injector.
VK_C = 0x43
TRANSFORM_INPUT_MARKER = 0x44495441  # DITA; fits ULONG_PTR on both architectures.
_TRANSFORM_CLIPBOARD_LOCK = threading.RLock()
_HISTORY_FORMATS = (
    "ExcludeClipboardContentFromMonitorProcessing",
    "CanIncludeInClipboardHistory",
    "CanUploadToCloudClipboard",
)
_MODIFIER_KEYS = (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C)
_EXTENDED_KEYS = {0xA3, 0xA5, 0x5B, 0x5C}
# These formats contain GDI/owner-managed handles, not copyable HGLOBAL bytes.
_HANDLE_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}
_LINE_COPY_FORMATS = (
    "MSDEVLineSelect",
    "VisualStudioEditorOperationsLineCutCopyClipboardTag",
)
_CHROMIUM_METADATA_FORMAT = "Chromium Web Custom MIME Data Format"
_VSCODE_METADATA_FORMAT = "vscode-editor-data"
_MAX_COPY_METADATA_BYTES = 1024 * 1024


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", _INPUTUNION)]


kernel32 = ctypes.windll.kernel32
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
user32.CreateWindowExW.argtypes = (
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
)
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = (wintypes.HWND,)
user32.DestroyWindow.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalFree.restype = wintypes.HGLOBAL


def get_foreground_window() -> int:
    """Return the target window identity without activating any window."""
    return int(user32.GetForegroundWindow() or 0)


def is_own_input(data) -> bool:
    """Recognize our SendInput events in pynput's win32_event_filter."""
    return bool(data.flags & 0x10) and int(data.dwExtraInfo or 0) == TRANSFORM_INPUT_MARKER


def _send_input_events(events):
    inputs = (_INPUT * len(events))()
    for item, (key, flags) in zip(inputs, events):
        item.type = 1  # INPUT_KEYBOARD
        item.ki = _KEYBDINPUT(key, 0, flags | (1 if key in _EXTENDED_KEYS else 0),
                               0, TRANSFORM_INPUT_MARKER)
    if user32.SendInput(len(inputs), inputs, ctypes.sizeof(_INPUT)) != len(inputs):
        raise OSError("Windows did not accept the keyboard shortcut")


def _send_ctrl_shortcut(key):
    # A held Shift+F8 must become Ctrl+C, not Ctrl+Shift+C. A single batch also
    # minimizes the interval during which physically held modifiers are released.
    held = [vk for vk in _MODIFIER_KEYS if user32.GetAsyncKeyState(vk) & 0x8000]
    events = [(vk, KEYEVENTF_KEYUP) for vk in held]
    events += [(0xA2, 0), (key, 0), (key, KEYEVENTF_KEYUP), (0xA2, KEYEVENTF_KEYUP)]
    events += [(vk, 0) for vk in held]
    try:
        _send_input_events(events)
    except Exception:
        # SendInput can accept only part of a batch (e.g. UIPI). Do not leave a
        # synthetic Ctrl/key pressed after a partial failure.
        try:
            _send_input_events([(key, KEYEVENTF_KEYUP), (0xA2, KEYEVENTF_KEYUP)]
                               + [(vk, 0) for vk in held])
        except Exception:
            pass
        raise


@contextmanager
def _clipboard_window():
    # SetClipboardData needs a clipboard owner. A message-only STATIC window
    # provides one on this worker thread without becoming visible or taking focus.
    hwnd = user32.CreateWindowExW(0, "STATIC", "", 0, 0, 0, 0, 0, -3, None, None, None)
    if not hwnd:
        raise OSError("Could not create clipboard owner")
    try:
        yield hwnd
    finally:
        user32.DestroyWindow(hwnd)


@contextmanager
def _open_transform_clipboard(hwnd):
    for attempt in range(20):
        try:
            win32clipboard.OpenClipboard(hwnd)
            break
        except Exception:
            if attempt == 19:
                raise
            time.sleep(0.01)
    try:
        yield
    finally:
        win32clipboard.CloseClipboard()


def _snapshot_clipboard(hwnd):
    """Copy all memory formats to RAM; refuse unsupported handles before editing.

    This preserves empty clipboards, Unicode/ANSI text, HTML/RTF, DIB/PNG images,
    and file lists (CF_HDROP). Owner-rendered/GDI handles cannot be serialized
    safely this way, so their presence cancels the operation without clearing it.
    """
    snapshot = []
    with _open_transform_clipboard(hwnd):
        formats = []
        fmt = win32clipboard.EnumClipboardFormats(0)
        while fmt:
            formats.append(fmt)
            fmt = win32clipboard.EnumClipboardFormats(fmt)
        for fmt in formats:
            if fmt == 2 and (8 in formats or 17 in formats):
                # Windows synthesizes CF_BITMAP again from the preserved DIB.
                continue
            if fmt in _HANDLE_FORMATS or 0x200 <= fmt <= 0x2FF:
                raise OSError("Clipboard contains an unsupported owner-managed format")
            handle = user32.GetClipboardData(fmt)
            size = kernel32.GlobalSize(handle) if handle else 0
            address = kernel32.GlobalLock(handle) if size else None
            if not address:
                raise OSError("Could not preserve every clipboard format")
            try:
                snapshot.append((fmt, ctypes.string_at(address, size)))
            finally:
                kernel32.GlobalUnlock(handle)
    return snapshot


def _set_clipboard_bytes(fmt, data):
    handle = kernel32.GlobalAlloc(0x0002, max(1, len(data)))  # GMEM_MOVEABLE
    if not handle:
        raise OSError("Could not allocate clipboard memory")
    try:
        address = kernel32.GlobalLock(handle)
        if not address:
            raise OSError("Could not access clipboard memory")
        try:
            ctypes.memmove(address, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(fmt, handle):
            raise OSError("Could not write clipboard data")
        handle = None  # Ownership now belongs to Windows.
    finally:
        if handle:
            kernel32.GlobalFree(handle)


def _exclude_clipboard_history():
    # Documented Windows Cloud Clipboard controls. Applied while the clipboard
    # is locked, so our temporary payload is never published without the flags.
    for name in _HISTORY_FORMATS:
        _set_clipboard_bytes(win32clipboard.RegisterClipboardFormat(name), b"\0\0\0\0")


def _replace_transform_clipboard(hwnd, formats, transient=True):
    with _open_transform_clipboard(hwnd):
        win32clipboard.EmptyClipboard()
        if transient:
            _exclude_clipboard_history()
        for fmt, payload in formats:
            _set_clipboard_bytes(fmt, payload)
        if transient and formats:
            # Original history metadata may have opted in. Restoration should
            # not create another history entry containing the original payload.
            _exclude_clipboard_history()


def _restore_transform_clipboard(hwnd, snapshot):
    # Retry the complete restoration after a partial write failure as well as
    # retrying OpenClipboard itself. The snapshot stays in RAM until completion.
    for attempt in range(3):
        try:
            _replace_transform_clipboard(hwnd, snapshot, transient=bool(snapshot))
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.02)


def _read_copy_metadata(fmt):
    """Read a bounded HGLOBAL while the caller holds the clipboard open."""
    handle = user32.GetClipboardData(fmt)
    size = kernel32.GlobalSize(handle) if handle else 0
    if not 0 < size <= _MAX_COPY_METADATA_BYTES:
        return b""
    address = kernel32.GlobalLock(handle)
    if not address:
        return b""
    try:
        return ctypes.string_at(address, size)
    finally:
        kernel32.GlobalUnlock(handle)


def _chromium_vscode_metadata(raw):
    """Read the VS Code entry in Chromium's Windows custom MIME Pickle.

    Format source: chromium/ui/base/clipboard/custom_data_helper.cc and
    chromium/base/pickle.cc: uint32 payload size, uint32 entry count, then
    pairs of UTF-16 strings with int32 code-unit lengths and 4-byte alignment.
    """
    if not 8 <= len(raw) <= _MAX_COPY_METADATA_BYTES:
        return ""
    payload_size, count = struct.unpack_from("<II", raw)
    limit = 4 + payload_size
    if limit > len(raw) or payload_size < 4 or count > 256:
        return ""
    offset = 8

    def read_string():
        nonlocal offset
        if offset + 4 > limit:
            raise ValueError("Truncated clipboard metadata")
        length = struct.unpack_from("<i", raw, offset)[0]
        offset += 4
        end = offset + 2 * length
        if length < 0 or end > limit:
            raise ValueError("Invalid clipboard metadata length")
        value = raw[offset:end].decode("utf-16-le")
        offset = (end + 3) & ~3
        if offset > limit:
            raise ValueError("Truncated clipboard metadata alignment")
        return value

    try:
        for _ in range(count):
            name, value = read_string(), read_string()
            if name == _VSCODE_METADATA_FORMAT:
                return value
    except (ValueError, UnicodeError, struct.error):
        pass
    return ""


def _metadata_marks_empty_selection(value):
    try:
        metadata = json.loads(value)
        return (isinstance(metadata, dict) and metadata.get("version") == 1
                and metadata.get("isFromEmptySelection") is True)
    except (ValueError, TypeError, RecursionError):
        return False


def _clipboard_is_line_copy():
    """Reject known copy-current-line metadata, never infer from text content.

    VS Code writes isFromEmptySelection in clipboardUtils.ts. DOM custom MIME
    data is bundled in Chromium's native format on Windows. Some integrations
    expose the JSON directly, so accept that form too. Visual Studio/Scintilla
    markers are presence-only and can have a null data handle.
    """
    for name in (*_LINE_COPY_FORMATS, _CHROMIUM_METADATA_FORMAT, _VSCODE_METADATA_FORMAT):
        try:
            fmt = win32clipboard.RegisterClipboardFormat(name)
            if not win32clipboard.IsClipboardFormatAvailable(fmt):
                continue
            if name in _LINE_COPY_FORMATS:
                return True
            raw = _read_copy_metadata(fmt)
            if name == _CHROMIUM_METADATA_FORMAT:
                if _metadata_marks_empty_selection(_chromium_vscode_metadata(raw)):
                    return True
            else:
                # HGLOBAL may include a trailing NUL or allocation padding.
                for encoding in ("utf-8-sig", "utf-16-le"):
                    try:
                        data = raw.split(b"\0", 1)[0] if encoding == "utf-8-sig" else raw[:len(raw) & ~1]
                        value = data.decode(encoding).rstrip("\0")
                    except UnicodeError:
                        continue
                    if _metadata_marks_empty_selection(value):
                        return True
        except Exception:
            # Unrecognized or malformed optional metadata must not reject a
            # valid selection. Never print clipboard data in diagnostics.
            continue
    return False


def get_selected_text() -> str:
    """Capture Ctrl+C selection and always attempt to restore the prior clipboard.

    Clearing first prevents old clipboard text from masquerading as a selection.
    The external application's Ctrl+C may itself enter Windows clipboard history
    before we can add exclusion flags; its history policy is outside our control.
    """
    try:
        with _TRANSFORM_CLIPBOARD_LOCK, _clipboard_window() as hwnd:
            snapshot = _snapshot_clipboard(hwnd)
            try:
                _replace_transform_clipboard(hwnd, [])
                _send_ctrl_shortcut(VK_C)
                time.sleep(0.04)
                with _open_transform_clipboard(hwnd):
                    try:
                        _exclude_clipboard_history()
                    except Exception:
                        # The source application may still own its copy. These
                        # flags are only best effort for externally copied data.
                        pass
                    if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                        return ""
                    if _clipboard_is_line_copy():
                        return ""
                    text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                    return text if isinstance(text, str) and text.strip() else ""
            finally:
                _restore_transform_clipboard(hwnd, snapshot)
    except Exception:
        # Never log clipboard payloads or paste stale text on any failure.
        return ""


def inject_transformed_text(text: str, *, should_paste=None) -> bool:
    """Paste one transformation via SendInput, then restore every saved format."""
    if not text or not text.strip():
        return False
    try:
        with _TRANSFORM_CLIPBOARD_LOCK, _clipboard_window() as hwnd:
            snapshot = _snapshot_clipboard(hwnd)
            paste_attempted = False
            try:
                payload = (text + "\0").encode("utf-16-le")
                _replace_transform_clipboard(hwnd, [(win32con.CF_UNICODETEXT, payload)])
                if should_paste is not None and not should_paste():
                    return False
                paste_attempted = True
                _send_ctrl_shortcut(VK_V)
            finally:
                try:
                    if paste_attempted:
                        time.sleep(0.35)
                finally:
                    _restore_transform_clipboard(hwnd, snapshot)
        return True
    except Exception:
        return False
