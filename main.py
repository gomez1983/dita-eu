import sys
import os
import time
import threading
import traceback
from dotenv import load_dotenv

load_dotenv()

from PyQt5 import QtCore, QtGui, QtWidgets
from pynput import keyboard

import config_manager
from audio_recorder import AudioRecorder
from transcriber import TranscriptionEngine
from injector import inject_text
from overlay import FloatingHUD
from settings_ui import SettingsWindow

def get_resource_path(relative_path: str) -> str:
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

class DictationApp(QtCore.QObject):
    sig_show_recording = QtCore.pyqtSignal()
    sig_show_processing = QtCore.pyqtSignal()
    sig_hide_hud = QtCore.pyqtSignal()
    sig_volume_update = QtCore.pyqtSignal(float)

    def __init__(self, q_app: QtWidgets.QApplication):
        super().__init__()
        self.q_app = q_app

        self.icon_ico_path = get_resource_path("icon.ico")
        self.icon_png_path = get_resource_path("icon_white.png")

        self.config = config_manager.load_config()

        self.hud = FloatingHUD(
            bottom_offset=self.config.get("hud_bottom_offset", 350),
            theme=self.config.get("theme", "dark")
        )

        self.recorder = AudioRecorder(device_index=self.config.get("microphone_index"))
        self.engine = TranscriptionEngine(
            engine_type=self.config.get("engine", "groq"),
            groq_api_key=self.config.get("groq_api_key", ""),
            gemini_api_key=self.config.get("gemini_api_key", ""),
            gemini_model=self.config.get("gemini_model", "gemini-flash-latest")
        )

        self.sig_show_recording.connect(self.hud.set_recording)
        self.sig_show_processing.connect(self.hud.set_processing)
        self.sig_hide_hud.connect(self.hud.hide_hud)
        self.sig_volume_update.connect(self.hud.update_volume)

        self._is_active = False
        self._lock = threading.Lock()
        self._currently_pressed_keys = set()

        self.volume_timer = QtCore.QTimer()
        self.volume_timer.setInterval(50)
        self.volume_timer.timeout.connect(self._check_volume)
        self.volume_timer.start()

        self.settings_window = SettingsWindow(self.config, icon_path=self.icon_png_path)
        self.settings_window.config_saved.connect(self._on_config_updated)

        self._setup_tray_icon()

        self.keyboard_listener = None
        self._start_keyboard_listener()

        QtCore.QTimer.singleShot(200, self.show_settings)

    def _setup_tray_icon(self):
        icon = QtGui.QIcon(self.icon_ico_path if os.path.exists(self.icon_ico_path) else self.icon_png_path)
        self.tray_icon = QtWidgets.QSystemTrayIcon(icon, self.q_app)
        
        keys_str = " + ".join([k.upper() for k in self.config.get("trigger_keys", ["F8"])])
        self.tray_icon.setToolTip(f"Dita-eu — Push-to-Talk ({keys_str})")

        tray_menu = QtWidgets.QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #27272a;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #27272a;
            }
        """)

        title_action = tray_menu.addAction("Dita-eu")
        title_action.setEnabled(False)
        tray_menu.addSeparator()

        settings_action = tray_menu.addAction("Configurações...")
        settings_action.triggered.connect(self.show_settings)

        tray_menu.addSeparator()
        exit_action = tray_menu.addAction("Sair")
        exit_action.triggered.connect(self._quit_app)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason in (QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick, QtWidgets.QSystemTrayIcon.ActivationReason.Trigger):
            self.show_settings()

    def show_settings(self):
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _on_config_updated(self, new_config: dict):
        self.config = new_config
        self.hud.bottom_offset = self.config.get("hud_bottom_offset", 350)
        self.hud.set_theme(self.config.get("theme", "dark"))
        self.recorder.device_index = self.config.get("microphone_index")
        
        self.engine = TranscriptionEngine(
            engine_type=self.config.get("engine", "groq"),
            groq_api_key=self.config.get("groq_api_key", ""),
            gemini_api_key=self.config.get("gemini_api_key", ""),
            gemini_model=self.config.get("gemini_model", "gemini-flash-latest")
        )

        keys_str = " + ".join([k.upper() for k in self.config.get("trigger_keys", ["F8"])])
        self.tray_icon.setToolTip(f"Dita-eu — Push-to-Talk ({keys_str})")
        print(f"[Dita-eu] Configuração aplicada: Atalho [{keys_str}], Motor [{self.config.get('engine')}], Tema [{self.config.get('theme')}]")

    def _check_volume(self):
        if self._is_active and self.recorder.is_recording:
            self.sig_volume_update.emit(self.recorder.current_volume)

    def _normalize_key(self, key) -> str:
        if isinstance(key, keyboard.Key):
            name = key.name.lower()
            if "shift" in name:
                return "shift"
            if "ctrl" in name:
                return "ctrl"
            if "alt" in name:
                return "alt"
            return name
        elif hasattr(key, 'char') and key.char:
            return key.char.lower()
        return str(key).lower().replace("'", "")

    def _start_keyboard_listener(self):
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self.keyboard_listener.daemon = True
        self.keyboard_listener.start()

    def _is_trigger_satisfied(self) -> bool:
        trigger_keys = [k.lower() for k in self.config.get("trigger_keys", ["f8"])]
        if not trigger_keys:
            return False
        return all(k in self._currently_pressed_keys for k in trigger_keys)

    def _on_key_press(self, key):
        k_str = self._normalize_key(key)
        self._currently_pressed_keys.add(k_str)

        if self._is_trigger_satisfied():
            self._start_dictation()

    def _on_key_release(self, key):
        k_str = self._normalize_key(key)
        if k_str in self._currently_pressed_keys:
            self._currently_pressed_keys.remove(k_str)

        trigger_keys = [k.lower() for k in self.config.get("trigger_keys", ["f8"])]
        if self._is_active and k_str in trigger_keys:
            self._stop_dictation()

    def _start_dictation(self):
        with self._lock:
            if self._is_active:
                return
            self._is_active = True

        print(f"[Dita-eu] Gravando... (Motor: {self.config.get('engine')})")
        self.sig_show_recording.emit()
        self.recorder.start()

    def _stop_dictation(self):
        with self._lock:
            if not self._is_active:
                return
            self._is_active = False

        print("[Dita-eu] Finalizado. Transcrevendo...")
        self.sig_show_processing.emit()
        threading.Thread(target=self._process_and_inject, daemon=True).start()

    def _process_and_inject(self):
        try:
            audio_bytes = self.recorder.stop()
            if not audio_bytes or len(audio_bytes) < 4000:
                print("[Dita-eu] Áudio muito curto ou inaudível.")
                return

            text = self.engine.transcribe(audio_bytes)
            if text:
                print(f"[Dita-eu] Texto transcrito: '{text}'")
                inject_text(text, restore_clipboard=True)
            else:
                print("[Dita-eu] Nenhuma fala identificada.")
        except Exception as e:
            print(f"[Dita-eu] Erro na transcrição ou injeção: {e}")
        finally:
            self.sig_hide_hud.emit()

    def _quit_app(self):
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.tray_icon.hide()
        self.q_app.quit()

def handle_exception(exc_type, exc_value, exc_traceback):
    """Handler global para capturar exceções não tratadas e evitar travamento silencioso"""
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"[Dita-eu Fatal Error] {err_msg}", file=sys.stderr)
    try:
        with open("crash.log", "a", encoding="utf-8") as f:
            f.write(f"--- Crash {time.ctime()} ---\n{err_msg}\n")
    except Exception:
        pass

def main():
    sys.excepthook = handle_exception
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    ico_path = get_resource_path("icon.ico")
    if os.path.exists(ico_path):
        app.setWindowIcon(QtGui.QIcon(ico_path))

    dictation_app = DictationApp(app)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
