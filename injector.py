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
KEYEVENTF_SCANCODE = 0x0008

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

        # Simula Ctrl+V atomicamente via SendInput (liberando modificadores)
        _send_ctrl_shortcut(VK_V)

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
_COPY_TIMEOUT_SECONDS = 0.8
_COPY_POLL_INTERVAL = 0.01


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
user32.GetClipboardSequenceNumber.argtypes = ()
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetClipboardOwner.argtypes = ()
user32.GetClipboardOwner.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
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
kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


kernel32.Process32First.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32))
kernel32.Process32First.restype = wintypes.BOOL
kernel32.Process32Next.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32))
kernel32.Process32Next.restype = wintypes.BOOL


user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT


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
        scan = user32.MapVirtualKeyW(key, 0)
        if not scan:
            raise OSError("Could not map keyboard scan code")
        item.ki = _KEYBDINPUT(0, scan, flags | KEYEVENTF_SCANCODE
                              | (1 if key in _EXTENDED_KEYS else 0),
                              0, TRANSFORM_INPUT_MARKER)
    sent = user32.SendInput(len(inputs), inputs, ctypes.sizeof(_INPUT))
    if sent == 0:
        # Legacy compatibility fallback; this does not bypass Windows UIPI.
        for key, flags in events:
            scan = user32.MapVirtualKeyW(key, 0)
            user32.keybd_event(key, scan, flags | (1 if key in _EXTENDED_KEYS else 0), TRANSFORM_INPUT_MARKER)
    elif sent != len(inputs):
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


def _snapshot_clipboard(hwnd, with_sequence=False):
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
        if with_sequence:
            return snapshot, user32.GetClipboardSequenceNumber()
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


def _replace_transform_clipboard(hwnd, formats, transient=True, expected_sequence=None):
    failure = None
    with _open_transform_clipboard(hwnd):
        # Compare while holding the clipboard: a newer user copy must survive.
        if (expected_sequence is not None
                and user32.GetClipboardSequenceNumber() != expected_sequence):
            return False
        try:
            win32clipboard.EmptyClipboard()
            if transient:
                _exclude_clipboard_history()
            for fmt, payload in formats:
                _set_clipboard_bytes(fmt, payload)
            if transient and formats:
                # Original history metadata may have opted in. Restoration should
                # not create another history entry containing the original payload.
                _exclude_clipboard_history()
        except Exception as error:
            failure = error
    if failure is not None:
        # Windows can advance the sequence on CloseClipboard. Save that version
        # only if our owner still holds it; a competing copy must survive retry.
        error = OSError("Could not replace clipboard formats")
        current = user32.GetClipboardSequenceNumber()
        if user32.GetClipboardOwner() == hwnd:
            error.clipboard_sequence = current
        raise error from failure
    return True


def _restore_transform_clipboard(hwnd, snapshot, expected_sequence=None):
    # Retry the complete restoration after a partial write failure as well as
    # retrying OpenClipboard itself. The snapshot stays in RAM until completion.
    for attempt in range(3):
        try:
            if expected_sequence is None:
                return _replace_transform_clipboard(hwnd, snapshot, transient=bool(snapshot))
            return _replace_transform_clipboard(
                hwnd, snapshot, transient=bool(snapshot), expected_sequence=expected_sequence)
        except Exception as error:
            if attempt == 2:
                raise
            if expected_sequence is not None:
                expected_sequence = getattr(error, "clipboard_sequence", expected_sequence)
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


def _get_process_lineage(pid: int) -> set:
    """Retorna o conjunto de PIDs na árvore de processos (ancestrais e descendentes diretos)."""
    if not pid:
        return set()
    lineage = {pid}
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == -1:
        return lineage
    try:
        pe = _PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(_PROCESSENTRY32)
        parent_map = {}
        if kernel32.Process32First(snapshot, ctypes.byref(pe)):
            while True:
                p_id = int(pe.th32ProcessID)
                pp_id = int(pe.th32ParentProcessID)
                if p_id:
                    parent_map[p_id] = pp_id
                if not kernel32.Process32Next(snapshot, ctypes.byref(pe)):
                    break

        # Mapeia ancestrais
        curr = pid
        for _ in range(10):
            parent = parent_map.get(curr)
            if not parent or parent in lineage:
                break
            lineage.add(parent)
            curr = parent

        # Mapeia filhos e netos diretos
        for _ in range(5):
            new_added = False
            for child, parent in parent_map.items():
                if parent in lineage and child not in lineage:
                    lineage.add(child)
                    new_added = True
            if not new_added:
                break
    except Exception:
        pass
    finally:
        kernel32.CloseHandle(snapshot)
    return lineage


def _clipboard_belongs_to_target(target):
    # Suporta processos únicos (Dota 2, Reddit/Chrome) e multi-processos (Teams/WebView2).
    if not target:
        return False
    owner = user32.GetClipboardOwner()
    if not owner:
        return False

    owner_pid, target_pid = wintypes.DWORD(), wintypes.DWORD()
    if not user32.GetWindowThreadProcessId(owner, ctypes.byref(owner_pid)):
        return False
    if not user32.GetWindowThreadProcessId(target, ctypes.byref(target_pid)):
        return False

    o_pid = int(owner_pid.value)
    t_pid = int(target_pid.value)
    if not o_pid or not t_pid:
        return False
    if o_pid == t_pid:
        return True

    # Verifica se pertencem à mesma árvore de processos (arquitetura multi-processo de Teams/Chrome/Edge)
    target_tree = _get_process_lineage(t_pid)
    return o_pid in target_tree


def get_selected_text():
    """Capture a fresh Ctrl+C without clearing or locking out the source app.

    A new sequence, not different text, distinguishes a copy from stale data.
    The external application's Ctrl+C may itself enter Windows clipboard history
    according to its own policy; reading it does not change that policy.
    """
    try:
        with _TRANSFORM_CLIPBOARD_LOCK, _clipboard_window() as hwnd:
            target = get_foreground_window()
            # Pair the baseline with its snapshot under the same clipboard lock.
            snapshot, sequence = _snapshot_clipboard(hwnd, with_sequence=True)
            copied_sequence = None
            try:
                if (not target or get_foreground_window() != target
                        or user32.GetClipboardSequenceNumber() != sequence):
                    return ""
                _send_ctrl_shortcut(VK_C)
                deadline = time.monotonic() + _COPY_TIMEOUT_SECONDS
                while time.monotonic() < deadline:
                    if get_foreground_window() != target:
                        return ""
                    current = user32.GetClipboardSequenceNumber()
                    if current != sequence:
                        if not _clipboard_belongs_to_target(target):
                            return ""
                        copied_sequence = current
                        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                            try:
                                # One attempt per poll. Never sleep with it open,
                                # or compete while the source is still writing.
                                win32clipboard.OpenClipboard(hwnd)
                            except Exception:
                                pass
                            else:
                                try:
                                    if (get_foreground_window() != target
                                            or not _clipboard_belongs_to_target(target)):
                                        return ""
                                    current = user32.GetClipboardSequenceNumber()
                                    if current != sequence:
                                        copied_sequence = current
                                        try:
                                            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                                                if _clipboard_is_line_copy():
                                                    return ""
                                                text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                                                if get_foreground_window() != target:
                                                    return ""
                                                return text if isinstance(text, str) and text.strip() else ""
                                        finally:
                                            # Text or metadata may render delayed data.
                                            copied_sequence = user32.GetClipboardSequenceNumber()
                                finally:
                                    win32clipboard.CloseClipboard()
                    time.sleep(min(_COPY_POLL_INTERVAL, max(0, deadline - time.monotonic())))
                return ""
            finally:
                if copied_sequence is not None:
                    _restore_transform_clipboard(hwnd, snapshot, expected_sequence=copied_sequence)
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
