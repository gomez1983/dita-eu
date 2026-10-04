import os
import time
import pyperclip
import win32clipboard
import win32con
import ctypes

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
