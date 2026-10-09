"""Regressões de atalhos e da orquestração, sem microfone, rede ou clipboard real."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt5 import QtCore, QtWidgets
from pynput import keyboard

import config_manager
import main


class VoiceTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.app = main.DictationApp.__new__(main.DictationApp)
        QtCore.QObject.__init__(self.app)
        self.app.config = {"trigger_keys": ["f8"], "translation_target": "en"}
        self.app._lock = threading.Lock()
        self.app._currently_pressed_keys = set()
        self.app._transform_latched_keys = frozenset()
        self.app._transform_session = None
        self.app._dictation_jobs = 0
        self.app._is_active = False
        self.app.engine = Mock()
        self.app.recorder = Mock()
        self.app.recorder.stop.return_value = b"a" * 5000
        self.app.hud = Mock()
        self.app.hud_safety_timer = Mock()
        self.app.sig_transform_state.connect(self.app._on_transform_state)

    def session(self):
        session = main._TransformSession(frozenset({"shift", "f8"}), self.app.engine, 123)
        self.app._transform_session = session
        self.app.recorder.start.side_effect = session.released.set
        return session

    def run_transform(self, session, selection="Texto original"):
        with patch.object(main, "get_selected_text", return_value=selection), \
                patch.object(main, "get_foreground_window", return_value=123), \
                patch.object(main, "inject_transformed_text") as inject:
            self.app._process_transform(session)
        return inject

    def test_config_default(self):
        self.assertEqual(config_manager.DEFAULT_CONFIG["transform_trigger_keys"], ["shift+f8"])

    def test_f8_alone_keeps_dictation(self):
        with patch.object(self.app, "_start_dictation") as normal, \
                patch.object(self.app, "_start_transform") as transform:
            self.app._on_key_press(keyboard.Key.f8)
        normal.assert_called_once_with()
        transform.assert_not_called()

    def test_f8_release_keeps_normal_stop(self):
        self.app._is_active = True
        self.app._currently_pressed_keys = {"f8"}
        with patch.object(self.app, "_stop_dictation") as stop:
            self.app._on_key_release(keyboard.Key.f8)
        stop.assert_called_once_with()

    def test_shift_f8_takes_priority_and_ignores_repeat(self):
        with patch.object(self.app, "_start_dictation") as normal, \
                patch.object(self.app, "_start_transform") as transform:
            self.app._on_key_press(keyboard.Key.shift_r)
            self.app._on_key_press(keyboard.Key.f8)
            self.app._on_key_press(keyboard.Key.f8)
        normal.assert_not_called()
        transform.assert_called_once_with(frozenset({"shift", "f8"}))

    def test_shift_release_stops_transform_without_starting_f8(self):
        session = self.session()
        self.app._currently_pressed_keys = {"shift", "f8"}
        self.app._transform_latched_keys = frozenset({"f8"})
        with patch.object(self.app, "_start_dictation") as normal:
            self.app._on_key_release(keyboard.Key.shift_r)
            self.app._on_key_press(keyboard.Key.f8)
        self.assertTrue(session.released.is_set())
        normal.assert_not_called()
        self.app._on_key_release(keyboard.Key.f8)
        self.assertFalse(self.app._transform_latched_keys)

    def test_next_f8_can_transform_while_shift_remains_held(self):
        with patch.object(self.app, "_start_transform") as transform:
            self.app._on_key_press(keyboard.Key.shift)
            self.app._on_key_press(keyboard.Key.f8)
            self.app._on_key_release(keyboard.Key.f8)
            self.app._on_key_press(keyboard.Key.f8)
        self.assertEqual(transform.call_count, 2)

    def test_configured_transform_chord_formats(self):
        for keys in (["ctrl+shift+f7"], ["ctrl", "shift", "f7"]):
            self.app.config["transform_trigger_keys"] = keys
            self.assertEqual(self.app._transform_trigger_keys(), {"ctrl", "shift", "f7"})

    def test_only_own_synthetic_keyboard_events_are_ignored(self):
        self.assertFalse(self.app._filter_keyboard_event(0, SimpleNamespace(dwExtraInfo=main.TRANSFORM_INPUT_MARKER)))
        self.assertTrue(self.app._filter_keyboard_event(0, SimpleNamespace(dwExtraInfo=0)))

    def test_transform_does_not_overlap_dictation_recording_or_processing(self):
        with patch.object(main.threading, "Thread") as worker:
            self.app._is_active = True
            self.app._start_transform(frozenset({"shift", "f8"}))
            self.app._is_active = False
            self.app._dictation_jobs = 1
            self.app._start_transform(frozenset({"shift", "f8"}))
        worker.assert_not_called()

    def test_dictation_does_not_overlap_transform(self):
        self.session()
        self.app._start_dictation()
        self.app.recorder.start.assert_not_called()

    def test_empty_selection_notifies_without_recording(self):
        inject = self.run_transform(self.session(), " \n ")
        self.app.recorder.start.assert_not_called()
        self.app.engine.transform_text.assert_not_called()
        inject.assert_not_called()
        self.app.hud.show_no_selection.assert_called_once_with()
        self.assertIsNone(self.app._transform_session)

    def test_release_during_selection_capture_does_not_start_microphone(self):
        session = self.session()
        session.released.set()
        self.run_transform(session)
        self.app.recorder.start.assert_not_called()

    def test_selection_capture_failure_releases_session(self):
        with patch.object(main, "get_selected_text", side_effect=OSError()), \
                patch.object(main, "inject_transformed_text") as inject:
            self.app._process_transform(self.session())
        inject.assert_not_called()
        self.app.recorder.start.assert_not_called()
        self.assertIsNone(self.app._transform_session)

    def test_transform_uses_session_engine_and_ignores_dictation_translation(self):
        session = self.session()
        self.app.engine = Mock()  # Simula mudança posterior de configuração.
        session.engine.transform_text.return_value = "Texto formal"
        inject = self.run_transform(session)
        session.engine.transform_text.assert_called_once_with("Texto original", b"a" * 5000)
        session.engine.transcribe.assert_not_called()
        self.app.engine.transform_text.assert_not_called()
        self.assertEqual(inject.call_args.args, ("Texto formal",))
        self.assertTrue(callable(inject.call_args.kwargs["should_paste"]))
        self.app.hud.set_transform.assert_called_once_with()
        self.app.hud.set_transform_processing.assert_called_once_with()
        self.app.hud_safety_timer.start.assert_called_once_with(15000)
        self.assertIsNone(self.app._transform_session)

    def test_empty_transformation_never_replaces_selection(self):
        self.app.engine.transform_text.return_value = ""
        self.run_transform(self.session()).assert_not_called()

    def test_short_audio_never_calls_engine(self):
        self.app.recorder.stop.return_value = b"short"
        self.run_transform(self.session()).assert_not_called()
        self.app.engine.transform_text.assert_not_called()

    def test_microphone_error_releases_session_and_cleans_recorder(self):
        session = self.session()
        self.app.recorder.start.side_effect = RuntimeError("dispositivo indisponível")
        self.run_transform(session).assert_not_called()
        self.app.recorder.stop.assert_called_once_with()
        self.assertIsNone(self.app._transform_session)

    def test_provider_error_cleans_hud_without_logging_payload(self):
        self.app.engine.transform_text.side_effect = RuntimeError("SEGREDO DA SELEÇÃO")
        with patch("builtins.print") as log:
            self.run_transform(self.session()).assert_not_called()
        self.assertNotIn("SEGREDO", str(log.call_args_list))
        self.assertIsNone(self.app._transform_session)
        self.app.hud.hide_hud.assert_called_once_with()

    def test_timeout_discards_late_result(self):
        session = self.session()
        def late_result(*args):
            self.app._on_hud_timeout()
            return "Resultado tardio"
        self.app.engine.transform_text.side_effect = late_result
        self.run_transform(session).assert_not_called()
        self.assertTrue(session.cancelled.is_set())
        self.assertIsNone(self.app._transform_session)

    def test_injection_does_not_lock_keyboard_or_release_clipboard_guard_early(self):
        session = self.session()
        self.app.engine.transform_text.return_value = "Resultado"
        def inject_result(text, *, should_paste):
            self.assertTrue(should_paste())
            # O hook pode obter o lock durante os 350 ms de restauração.
            acquired = self.app._lock.acquire(blocking=False)
            self.assertTrue(acquired)
            if acquired:
                self.app._lock.release()
            self.app._on_hud_timeout()
            self.assertFalse(should_paste())
            self.assertIs(self.app._transform_session, session)
            with patch.object(main.threading, "Thread") as worker:
                self.app._start_transform(session.trigger_keys)
            worker.assert_not_called()
        with patch.object(main, "get_selected_text", return_value="Original"), \
                patch.object(main, "get_foreground_window", return_value=123), \
                patch.object(main, "inject_transformed_text", side_effect=inject_result) as inject:
            self.app._process_transform(session)
        self.assertEqual(inject.call_count, 1)
        self.assertEqual(inject.call_args.args, ("Resultado",))
        self.assertIsNone(self.app._transform_session)

    def test_elapsed_deadline_discards_result_even_before_qt_timer_runs(self):
        self.app.engine.transform_text.return_value = "Resultado tardio"
        with patch.object(main.time, "monotonic", side_effect=[100.0, 115.1]):
            self.run_transform(self.session()).assert_not_called()

    def test_focus_change_does_not_paste_into_another_window(self):
        self.app.engine.transform_text.return_value = "Resultado"
        with patch.object(main, "get_selected_text", return_value="Original"), \
                patch.object(main, "get_foreground_window", side_effect=[123, 456]), \
                patch.object(main, "inject_transformed_text") as inject:
            self.app._process_transform(self.session())
        inject.assert_not_called()

    def test_old_completion_cannot_hide_current_hud(self):
        old = self.session()
        current = self.session()
        self.app._on_transform_state(old, "finished")
        self.assertIs(self.app._transform_session, current)
        self.app.hud.hide_hud.assert_not_called()

    def test_normal_dictation_keeps_translation_and_legacy_injector(self):
        self.app._dictation_jobs = 1
        self.app.engine.transcribe.return_value = "Normal dictation"
        with patch.object(main, "inject_text") as inject, \
                patch.object(main, "inject_transformed_text") as transform, \
                patch.object(main.QtCore.QMetaObject, "invokeMethod"):
            self.app._process_and_inject()
        self.app.engine.transcribe.assert_called_once_with(b"a" * 5000, target_lang="en")
        inject.assert_called_once_with("Normal dictation", restore_clipboard=True)
        transform.assert_not_called()
        self.assertEqual(self.app._dictation_jobs, 0)

    def test_application_initialization_connects_existing_hud_methods(self):
        with patch.object(config_manager, "load_config", return_value=config_manager.DEFAULT_CONFIG.copy()), \
                patch.object(main, "AudioRecorder"), \
                patch.object(main, "TranscriptionEngine"), \
                patch.object(main, "SettingsWindow"), \
                patch.object(main.DictationApp, "_setup_tray_icon"), \
                patch.object(main.DictationApp, "_start_keyboard_listener"), \
                patch.object(main.QtCore.QTimer, "singleShot"):
            app = main.DictationApp(self.qt_app)
        app.volume_timer.stop()
        app.hud_safety_timer.stop()
        app.hud.close()
        self.assertIsNone(app._transform_session)


if __name__ == "__main__":
    unittest.main()
