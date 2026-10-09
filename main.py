import sys
import os
import time
import threading
import traceback
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

from PyQt5 import QtCore, QtGui, QtWidgets
from pynput import keyboard

import config_manager
from audio_recorder import AudioRecorder
from transcriber import TranscriptionEngine
from injector import (
    inject_text, get_selected_text, inject_transformed_text,
    get_foreground_window, TRANSFORM_INPUT_MARKER,
)
from overlay import FloatingHUD
from settings_ui import SettingsWindow

def get_resource_path(relative_path: str) -> str:
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


@dataclass
class _TransformSession:
    trigger_keys: frozenset
    engine: TranscriptionEngine
    window: int
    released: threading.Event = field(default_factory=threading.Event)
    cancelled: threading.Event = field(default_factory=threading.Event)
    processing_started: float = 0.0
    injecting: bool = False


class _TransformKeyboardListener(keyboard.Listener):
    """Suppress only the current transform key after pynput queues its callback.

    The Windows backend checks ``suppress`` after posting on_press/on_release.
    Calling suppress_event inside the filter would discard those callbacks and
    leave the push-to-talk state unaware of the key it just intercepted.
    """
    def __init__(self, *args, **kwargs):
        self.suppress_transform_event = False
        self.transform_pressed_vks = {}
        self.transform_suppressed_vks = set()
        super().__init__(*args, **kwargs)

    @property
    def suppress(self):
        return self._suppress or self.suppress_transform_event


class DictationApp(QtCore.QObject):
    sig_show_recording = QtCore.pyqtSignal()
    sig_show_processing = QtCore.pyqtSignal()
    sig_hide_hud = QtCore.pyqtSignal()
    sig_volume_update = QtCore.pyqtSignal(float)
    sig_transform_state = QtCore.pyqtSignal(object, str)

    def __init__(self, q_app: QtWidgets.QApplication):
        super().__init__()
        self.q_app = q_app

        self.icon_ico_path = get_resource_path("icon.ico")
        self.icon_white_path = get_resource_path("icon_white.png")
        self.icon_dark_path = get_resource_path("icon.png")

        self.config = config_manager.load_config()

        self.hud = FloatingHUD(
            bottom_offset=self.config.get("hud_bottom_offset", 350),
            theme=self.config.get("theme", "dark"),
            translation_target=self.config.get("translation_target", "original")
        )

        self.recorder = AudioRecorder(device_index=self.config.get("microphone_index"))
        self.engine = TranscriptionEngine(
            engine_type=self.config.get("engine", "groq"),
            groq_api_key=self.config.get("groq_api_key", ""),
            gemini_api_key=self.config.get("gemini_api_key", ""),
            gemini_model=self.config.get("gemini_model", "gemini-flash-lite-latest")
        )

        self.sig_show_recording.connect(self.hud.set_recording)
        self.sig_show_processing.connect(self.hud.set_processing)
        self.sig_hide_hud.connect(self.hud.hide_hud)
        self.sig_volume_update.connect(self.hud.update_volume)
        self.sig_transform_state.connect(self._on_transform_state)

        self._is_active = False
        self._lock = threading.Lock()
        self._currently_pressed_keys = set()
        self._transform_session = None
        self._transform_latched_keys = frozenset()
        self._dictation_jobs = 0

        self.hud_safety_timer = QtCore.QTimer()
        self.hud_safety_timer.setSingleShot(True)
        self.hud_safety_timer.timeout.connect(self._on_hud_timeout)

        self.volume_timer = QtCore.QTimer()
        self.volume_timer.setInterval(50)
        self.volume_timer.timeout.connect(self._check_volume)
        self.volume_timer.start()

        self.settings_window = SettingsWindow(
            self.config,
            icon_path=self.icon_white_path,
            icon_white_path=self.icon_white_path,
            icon_dark_path=self.icon_dark_path
        )
        self.settings_window.config_saved.connect(self._on_config_updated)

        self.tray_lang_actions = {}
        self._setup_tray_icon()

        self.keyboard_listener = None
        self._start_keyboard_listener()

        QtCore.QTimer.singleShot(200, self.show_settings)

    def _setup_tray_icon(self):
        icon = QtGui.QIcon(self.icon_ico_path if os.path.exists(self.icon_ico_path) else self.icon_white_path)
        self.tray_icon = QtWidgets.QSystemTrayIcon(icon, self.q_app)
        
        self._update_tray_tooltip()

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
            QMenu::item:checked {
                color: #60a5fa;
                font-weight: bold;
            }
        """)

        title_action = tray_menu.addAction("Dita-eu")
        title_action.setEnabled(False)
        tray_menu.addSeparator()

        # Submenu de Tradução Rápida
        trans_menu = tray_menu.addMenu("🌐 Modo Tradução")
        self.tray_lang_group = QtWidgets.QActionGroup(self)
        self.tray_lang_group.setExclusive(True)

        lang_options = [
            ("original", "Transcrição Original"),
            ("en", "🇺🇸 Inglês (EN)"),
            ("es", "🇪🇸 Espanhol (ES)"),
            ("fr", "🇫🇷 Francês (FR)"),
            ("de", "🇩🇪 Alemão (DE)"),
            ("it", "🇮🇹 Italiano (IT)")
        ]

        current_target = self.config.get("translation_target", "original")
        for code, label in lang_options:
            act = QtWidgets.QAction(label, self)
            act.setCheckable(True)
            if code == current_target:
                act.setChecked(True)
            act.triggered.connect(lambda checked, c=code: self._set_translation_language(c))
            self.tray_lang_group.addAction(act)
            trans_menu.addAction(act)
            self.tray_lang_actions[code] = act

        tray_menu.addSeparator()
        settings_action = tray_menu.addAction("Configurações...")
        settings_action.triggered.connect(self.show_settings)

        tray_menu.addSeparator()
        exit_action = tray_menu.addAction("Sair")
        exit_action.triggered.connect(self._quit_app)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _update_tray_tooltip(self):
        keys_str = " + ".join([k.upper() for k in self.config.get("trigger_keys", ["F8"])])
        target = self.config.get("translation_target", "original")
        trans_tag = f" | 🌐 {target.upper()}" if target != "original" else ""
        self.tray_icon.setToolTip(f"Dita-eu — Push-to-Talk ({keys_str}){trans_tag}")

    def _set_translation_language(self, lang_code: str):
        self.config["translation_target"] = lang_code
        config_manager.save_config(self.config)
        self.hud.set_translation_target(lang_code)
        self.settings_window.set_translation_target(lang_code)

        if lang_code in self.tray_lang_actions:
            self.tray_lang_actions[lang_code].setChecked(True)

        self._update_tray_tooltip()
        print(f"[Dita-eu] Modo Tradução alterado via bandeja: {lang_code}")

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
        
        target_lang = self.config.get("translation_target", "original")
        self.hud.set_translation_target(target_lang)
        if target_lang in self.tray_lang_actions:
            self.tray_lang_actions[target_lang].setChecked(True)

        self.recorder.device_index = self.config.get("microphone_index")
        
        self.engine = TranscriptionEngine(
            engine_type=self.config.get("engine", "groq"),
            groq_api_key=self.config.get("groq_api_key", ""),
            gemini_api_key=self.config.get("gemini_api_key", ""),
            gemini_model=self.config.get("gemini_model", "gemini-flash-lite-latest")
        )

        self._update_tray_tooltip()
        keys_str = " + ".join([k.upper() for k in self.config.get("trigger_keys", ["F8"])])
        print(f"[Dita-eu] Configuração aplicada: Atalho [{keys_str}], Motor [{self.config.get('engine')}], Tema [{self.config.get('theme')}], Tradução [{target_lang}]")

    def _check_volume(self):
        if (self._is_active or self._transform_session is not None) and self.recorder.is_recording:
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
        self.keyboard_listener = _TransformKeyboardListener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
            win32_event_filter=self._filter_keyboard_event,
        )
        self.keyboard_listener.daemon = True
        self.keyboard_listener.start()

    def _filter_keyboard_event(self, msg, data):
        listener = getattr(self, "keyboard_listener", None)
        if listener is not None:
            listener.suppress_transform_event = False
        # Ctrl+C/V soltam Shift temporariamente. Esses eventos não são a
        # soltura física do atalho e não devem encerrar a gravação.
        if data.dwExtraInfo == TRANSFORM_INPUT_MARKER:
            return False
        if listener is None or msg not in (0x100, 0x104, 0x101, 0x105):
            return True

        vk = data.vkCode
        pressed = msg in (0x100, 0x104)  # WM_KEYDOWN / WM_SYSKEYDOWN
        if pressed:
            try:
                key_name = self._normalize_key(listener._event_to_key(msg, vk))
            except OSError:
                return True
            # Hook-local state is current even when pynput has not delivered
            # its queued Shift callback yet. Keep both left/right modifier VKs.
            listener.transform_pressed_vks[vk] = key_name
            transform_keys = self._transform_trigger_keys()
            if (key_name in transform_keys - {"shift", "ctrl", "alt", "cmd", "cmd_r"}
                    and transform_keys.issubset(listener.transform_pressed_vks.values())):
                listener.transform_suppressed_vks.add(vk)

        listener.suppress_transform_event = vk in listener.transform_suppressed_vks
        if not pressed:
            listener.transform_pressed_vks.pop(vk, None)
            listener.transform_suppressed_vks.discard(vk)
        # Returning True preserves callback delivery. The listener suppresses
        # the event afterward, preventing IDE shortcuts from moving selection.
        return True

    def _transform_trigger_keys(self):
        # Aceita tanto ["shift+f8"] da especificação quanto ["shift", "f8"].
        return frozenset(
            part.strip().lower()
            for combo in self.config.get("transform_trigger_keys", ["shift+f8"])
            for part in combo.split("+") if part.strip()
        )

    def _is_trigger_satisfied(self) -> bool:
        trigger_keys = [k.lower() for k in self.config.get("trigger_keys", ["f8"])]
        if not trigger_keys:
            return False
        return all(k in self._currently_pressed_keys for k in trigger_keys)

    def _on_key_press(self, key):
        k_str = self._normalize_key(key)
        self._currently_pressed_keys.add(k_str)

        if self._transform_latched_keys:
            return
        transform_keys = self._transform_trigger_keys()
        if transform_keys and transform_keys.issubset(self._currently_pressed_keys):
            # Prioridade sobre F8 e uma única tentativa por aperto, inclusive
            # quando não existe seleção ou Shift é solto antes de F8.
            self._transform_latched_keys = (
                transform_keys - {"shift", "ctrl", "alt", "cmd"}
            ) or transform_keys
            self._start_transform(transform_keys)
            return
        if self._is_trigger_satisfied():
            self._start_dictation()

    def _on_key_release(self, key):
        k_str = self._normalize_key(key)
        if k_str in self._currently_pressed_keys:
            self._currently_pressed_keys.remove(k_str)

        with self._lock:
            session = self._transform_session
            if session is not None and k_str in session.trigger_keys:
                session.released.set()
        if not self._transform_latched_keys.intersection(self._currently_pressed_keys):
            self._transform_latched_keys = frozenset()

        trigger_keys = [k.lower() for k in self.config.get("trigger_keys", ["f8"])]
        if self._is_active and k_str in trigger_keys:
            self._stop_dictation()

    def _start_dictation(self):
        with self._lock:
            if self._is_active or self._transform_session is not None:
                return
            self._is_active = True

        target_lang = self.config.get("translation_target", "original")
        print(f"[Dita-eu] Gravando... (Motor: {self.config.get('engine')}, Tradução: {target_lang})")
        self.sig_show_recording.emit()
        self.recorder.start()

    def _stop_dictation(self):
        with self._lock:
            if not self._is_active:
                return
            self._is_active = False
            self._dictation_jobs += 1

        print("[Dita-eu] Finalizado. Transcrevendo...")
        self.sig_show_processing.emit()
        QtCore.QMetaObject.invokeMethod(self.hud_safety_timer, "start", QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(int, 15000))
        threading.Thread(target=self._process_and_inject, daemon=True).start()

    def _on_hud_timeout(self):
        with self._lock:
            if self._transform_session is not None:
                session = self._transform_session
                session.cancelled.set()
                session.released.set()
                # A colagem já começou: aguardar apenas a restauração do
                # clipboard antes de liberar uma nova gravação.
                if not session.injecting:
                    self._transform_session = None
        print("[Dita-eu] Watchdog: Processamento excedeu tempo limite. Ocultando HUD por segurança.")
        self.sig_hide_hud.emit()

    def _process_and_inject(self):
        try:
            audio_bytes = self.recorder.stop()
            if not audio_bytes or len(audio_bytes) < 4000:
                print("[Dita-eu] Áudio muito curto ou inaudível.")
                return

            target_lang = self.config.get("translation_target", "original")
            text = self.engine.transcribe(audio_bytes, target_lang=target_lang)
            if text:
                print(f"[Dita-eu] Texto transcrito ({target_lang}): '{text}'")
                inject_text(text, restore_clipboard=True)
            else:
                print("[Dita-eu] Nenhuma fala identificada.")
        except Exception as e:
            print(f"[Dita-eu] Erro na transcrição ou injeção: {e}")
        finally:
            with self._lock:
                QtCore.QMetaObject.invokeMethod(self.hud_safety_timer, "stop", QtCore.Qt.ConnectionType.QueuedConnection)
                self.sig_hide_hud.emit()
                self._dictation_jobs -= 1

    def _start_transform(self, trigger_keys):
        with self._lock:
            if self._is_active or self._dictation_jobs or self._transform_session is not None:
                return
            session = _TransformSession(trigger_keys, self.engine, get_foreground_window())
            self._transform_session = session
        # Capturar/copiar e abrir o microfone nunca bloqueiam o hook global.
        threading.Thread(target=self._process_transform, args=(session,), daemon=True).start()

    def _process_transform(self, session):
        recording = False
        final_state = "finished"
        try:
            original_text = get_selected_text()
            if not original_text.strip():
                final_state = "no_selection"
                return
            if (session.cancelled.is_set() or session.released.is_set()
                    or get_foreground_window() != session.window):
                return

            recording = True
            self.recorder.start()
            self.sig_transform_state.emit(session, "recording")
            session.released.wait()
            audio_bytes = self.recorder.stop()
            recording = False
            if session.cancelled.is_set() or not audio_bytes or len(audio_bytes) < 4000:
                return

            session.processing_started = time.monotonic()
            self.sig_transform_state.emit(session, "processing")
            text = session.engine.transform_text(original_text, audio_bytes)
            with self._lock:
                should_inject = (text and text.strip() and self._transform_session is session
                        and not session.cancelled.is_set()
                        and time.monotonic() - session.processing_started < 15
                        and get_foreground_window() == session.window)
                session.injecting = bool(should_inject)
            if should_inject:
                inject_transformed_text(
                    text,
                    should_paste=lambda: (
                        not session.cancelled.is_set()
                        and time.monotonic() - session.processing_started < 15
                        and get_foreground_window() == session.window
                        and self._transform_session is session
                    ),
                )
        except Exception as e:
            # Mensagens das APIs podem conter o texto original; não persistir
            # nem imprimir conteúdo da seleção ou da ordem de voz.
            print(f"[Dita-eu] Falha na transformação: {type(e).__name__}")
        finally:
            if recording:
                try:
                    self.recorder.stop()
                except Exception:
                    pass
            self.sig_transform_state.emit(session, final_state)

    @QtCore.pyqtSlot(object, str)
    def _on_transform_state(self, session, state):
        # Sinais tardios de uma API expirada não podem esconder um novo HUD.
        with self._lock:
            if self._transform_session is not session:
                return
            if state in ("finished", "no_selection"):
                self._transform_session = None
        if state == "recording":
            self.hud.set_transform()
        elif state == "processing":
            self.hud.set_transform_processing()
            self.hud_safety_timer.start(15000)
        else:
            self.hud_safety_timer.stop()
            if state == "no_selection":
                self.hud.show_no_selection()
            else:
                self.hud.hide_hud()

    def _quit_app(self):
        with self._lock:
            if self._transform_session is not None:
                self._transform_session.cancelled.set()
                self._transform_session.released.set()
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
