"""Regression coverage for lost hotkeys, microphone ownership and SDK timeouts."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import concurrent.futures
import threading
import time
import unittest
from unittest.mock import Mock, patch

# Load the native runtimes before Qt, including when this file is run alone.
import main
from PyQt5 import QtCore, QtWidgets
import numpy as np
import audio_recorder
import transcriber


class RecorderRecoveryTests(unittest.TestCase):
    def test_failed_start_closes_partial_stream_and_can_retry(self):
        recorder = audio_recorder.AudioRecorder()
        broken, healthy = Mock(), Mock()
        broken.start.side_effect = RuntimeError("device unavailable")
        with patch.object(audio_recorder.sd, "InputStream", side_effect=[broken, healthy]):
            with self.assertRaises(RuntimeError):
                recorder.start()
            self.assertFalse(recorder.is_recording)
            self.assertIsNone(recorder._stream)
            broken.close.assert_called_once()
            recorder.start()
            self.assertTrue(recorder.is_recording)
            recorder.stop()
        healthy.close.assert_called_once()

    def test_constructor_failure_resets_recording(self):
        recorder = audio_recorder.AudioRecorder()
        with patch.object(audio_recorder.sd, "InputStream", side_effect=OSError()):
            with self.assertRaises(OSError):
                recorder.start()
        self.assertFalse(recorder.is_recording)
        self.assertEqual(recorder._frames, [])

    def test_stop_always_closes_stream_even_when_driver_stop_fails(self):
        recorder = audio_recorder.AudioRecorder()
        with patch.object(audio_recorder.sd, "InputStream") as factory:
            recorder.start()
            recorder._audio_callback(np.ones((100, 1), dtype=np.float32), 100, None, None)
            factory.return_value.stop.side_effect = OSError()
            self.assertGreater(len(recorder.stop()), 44)
        factory.return_value.close.assert_called_once()
        self.assertFalse(recorder.is_recording)

    def test_new_start_waits_for_old_stop_and_keeps_its_own_stream(self):
        recorder = audio_recorder.AudioRecorder()
        first, second = Mock(), Mock()
        stopping, release, attempted = threading.Event(), threading.Event(), threading.Event()

        def slow_stop():
            stopping.set()
            release.wait(2)

        def new_start():
            attempted.set()
            recorder.start()

        first.stop.side_effect = slow_stop
        with patch.object(audio_recorder.sd, "InputStream", side_effect=[first, second]) as factory:
            recorder.start()
            old_worker = threading.Thread(target=recorder.stop)
            new_worker = threading.Thread(target=new_start)
            old_worker.start()
            try:
                self.assertTrue(stopping.wait(1))
                new_worker.start()
                self.assertTrue(attempted.wait(1))
                self.assertFalse(second.start.called)
            finally:
                release.set()
                old_worker.join(2)
                new_worker.join(2)
            self.assertFalse(old_worker.is_alive())
            self.assertFalse(new_worker.is_alive())
            self.assertEqual(factory.call_count, 2)
            self.assertIs(recorder._stream, second)
            self.assertTrue(recorder.is_recording)
            first.close.assert_called_once()
            second.close.assert_not_called()
            recorder.stop()

    def test_old_stream_callback_cannot_append_to_next_recording(self):
        recorder = audio_recorder.AudioRecorder()
        with patch.object(audio_recorder.sd, "InputStream") as factory:
            recorder.start()
            old_callback = factory.call_args.kwargs["callback"]
            recorder.stop()
            recorder.start()
            old_callback(np.ones((10, 1), dtype=np.float32), 10, None, None)
            self.assertEqual(recorder.get_current_audio_bytes(), b"")
            recorder.stop()

    def test_lost_release_cannot_accumulate_unbounded_audio(self):
        recorder = audio_recorder.AudioRecorder(sample_rate=10)
        with patch.object(audio_recorder.sd, "InputStream"), \
                patch.object(audio_recorder, "MAX_RECORDING_SECONDS", 1):
            recorder.start()
            for _ in range(5):
                recorder._audio_callback(np.ones((20, 1), dtype=np.float32), 20, None, None)
            self.assertEqual(sum(len(frame) for frame in recorder._frames), 10)
            recorder.stop()


class DictationRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.app = main.DictationApp.__new__(main.DictationApp)
        QtCore.QObject.__init__(self.app)
        self.app.config = {"trigger_keys": ["f8"], "engine": "groq", "translation_target": "original"}
        self.app._lock = threading.Lock()
        self.app._currently_pressed_keys = set()
        self.app._transform_latched_keys = frozenset()
        self.app._transform_session = None
        self.app._dictation_session = None
        self.app._dictation_jobs = 0
        self.app._is_active = False
        self.app._shutting_down = False
        self.app.recorder = Mock()
        self.app.recorder.stop.return_value = b"a" * 5000
        self.app.engine = Mock()
        self.app.engine.transcribe.return_value = "mock result"
        self.app.hud_safety_timer = Mock()
        self.invoke = patch.object(main.QtCore.QMetaObject, "invokeMethod").start()
        self.inject = patch.object(main, "inject_text").start()
        self.addCleanup(patch.stopall)

    def run_session(self, release_on_start=True):
        with patch.object(main.threading, "Thread"):
            self.app._start_dictation()
        session = self.app._dictation_session
        if release_on_start:
            self.app.recorder.start.side_effect = session.released.set
        self.app._process_and_inject(session)
        return session

    def test_callback_dispatches_microphone_work_and_release_does_not_wait_for_it(self):
        with patch.object(main.threading, "Thread") as worker:
            self.app._on_key_press(main.keyboard.Key.f8)
            session = self.app._dictation_session
            self.app.recorder.start.assert_not_called()
            self.app._on_key_release(main.keyboard.Key.f8)
        self.assertTrue(session.released.is_set())
        worker.assert_called_once()
        self.app._process_and_inject(session)
        self.app.recorder.start.assert_not_called()
        self.assertEqual(self.app._dictation_jobs, 0)

    def test_device_failure_keeps_listener_alive_and_next_press_can_record(self):
        real_thread = threading.Thread
        workers = []

        def create_worker(*args, **kwargs):
            worker = real_thread(*args, **kwargs)
            workers.append(worker)
            return worker

        listener = main._TransformKeyboardListener(
            on_press=self.app._on_key_press, on_release=self.app._on_key_release)
        listener._running = True
        listener._message_loop = Mock()
        self.app.recorder.start.side_effect = RuntimeError("private error")
        with patch.object(main.threading, "Thread", side_effect=create_worker):
            listener._process(0x100, 0x77)
            workers[-1].join(2)
            self.assertTrue(listener.running)
            self.assertFalse(self.app._is_active)
            self.assertEqual(self.app._dictation_jobs, 0)
            self.assertIsNone(self.app._dictation_session)
            listener._process(0x101, 0x77)

            def release():
                self.app._dictation_session.released.set()

            self.app.recorder.start.side_effect = release
            listener._process(0x100, 0x77)
            workers[-1].join(2)
        self.assertFalse(workers[-1].is_alive())
        self.inject.assert_called_once_with("mock result", restore_clipboard=True)

    def test_dictation_cannot_open_microphone_while_previous_job_owns_it(self):
        self.app._dictation_jobs = 1
        with patch.object(main.threading, "Thread") as worker:
            self.app._start_dictation()
        worker.assert_not_called()
        self.app.recorder.start.assert_not_called()

    def test_lost_release_finishes_at_duration_limit(self):
        with patch.object(main, "MAX_RECORDING_SECONDS", 0.01):
            self.run_session(release_on_start=False)
        self.assertFalse(self.app._is_active)
        self.assertEqual(self.app._dictation_jobs, 0)
        self.app.recorder.stop.assert_called_once()

    def test_expired_result_cannot_paste_later(self):
        def expire(*args, **kwargs):
            self.app._on_hud_timeout()
            return "late text"

        self.app.engine.transcribe.side_effect = expire
        session = self.run_session()
        self.assertTrue(session.cancelled.is_set())
        self.inject.assert_not_called()
        self.assertEqual(self.app._dictation_jobs, 0)

    def test_engine_exception_does_not_leave_busy_state(self):
        self.app.engine.transcribe.side_effect = OSError("private payload")
        with self.assertLogs("dita_eu", level="WARNING") as logs:
            self.run_session()
        self.assertNotIn("private payload", " ".join(logs.output))
        self.assertIsNone(self.app._dictation_session)
        self.assertFalse(self.app._is_active)
        self.assertEqual(self.app._dictation_jobs, 0)

    def test_config_changes_do_not_switch_engine_mid_session(self):
        with patch.object(main.threading, "Thread"):
            self.app._start_dictation()
        session = self.app._dictation_session
        original_engine = self.app.engine
        self.app.engine = Mock()
        self.app.config["translation_target"] = "fr"
        self.app.recorder.start.side_effect = session.released.set
        self.app._process_and_inject(session)
        original_engine.transcribe.assert_called_once_with(b"a" * 5000, target_lang="original")
        self.app.engine.transcribe.assert_not_called()

    def test_dead_listener_is_recreated_and_pending_recording_is_cancelled(self):
        session = main._DictationSession(self.app.engine, self.app.config)
        self.app._dictation_session = session
        self.app._currently_pressed_keys = {"f8"}
        self.app.keyboard_listener = Mock()
        self.app.keyboard_listener.is_alive.return_value = False
        self.app.keyboard_listener.join.side_effect = OSError("private key")
        with patch.object(self.app, "_start_keyboard_listener") as restart, \
                self.assertLogs("dita_eu", level="WARNING") as logs:
            self.app._check_keyboard_listener()
        restart.assert_called_once()
        self.assertTrue(session.cancelled.is_set())
        self.assertTrue(session.released.is_set())
        self.assertEqual(self.app._currently_pressed_keys, set())
        self.assertNotIn("private key", " ".join(logs.output))

    def test_shutdown_does_not_restart_listener(self):
        self.app._shutting_down = True
        with patch.object(self.app, "_start_keyboard_listener") as restart:
            self.app._check_keyboard_listener()
        restart.assert_not_called()


class GeminiTimeoutRecoveryTests(unittest.TestCase):
    def test_all_normal_calls_return_on_timeout_without_accumulating_workers(self):
        real_executor = concurrent.futures.ThreadPoolExecutor
        for method, args, fallback in (
            ("transcribe", (b"mock wav",), ""),
            ("translate_text", ("mock text", "en"), ""),
            ("apply_custom_style", ("mock text", "mock prompt"), "mock text"),
        ):
            with self.subTest(method=method):
                release = threading.Event()
                executors = []

                def create_executor(*args, **kwargs):
                    executor = real_executor(*args, **kwargs)
                    executors.append(executor)
                    return executor

                def block(**kwargs):
                    release.wait(2)
                    return Mock(text="late response")

                with patch.object(transcriber.genai, "Client"):
                    engine = transcriber.GeminiTranscriber(api_key="test-key")
                engine.client.models.generate_content.side_effect = block
                try:
                    with patch.object(transcriber, "GEMINI_TRANSCRIBE_TIMEOUT_SECONDS", 0.03), \
                            patch.object(transcriber, "GEMINI_TEXT_TIMEOUT_SECONDS", 0.03), \
                            patch.object(transcriber.concurrent.futures, "ThreadPoolExecutor", side_effect=create_executor):
                        started = time.monotonic()
                        self.assertEqual(getattr(engine, method)(*args), fallback)
                        self.assertLess(time.monotonic() - started, 0.75)
                        self.assertEqual(getattr(engine, method)(*args), fallback)
                        self.assertEqual(len(executors), 1)
                        engine.client.models.generate_content.assert_called_once()
                        config = engine.client.models.generate_content.call_args.kwargs["config"]
                        self.assertEqual(config.http_options.timeout, 30)
                finally:
                    release.set()
                    for executor in executors:
                        executor.shutdown(wait=True)
                engine.client.models.generate_content.side_effect = None
                engine.client.models.generate_content.return_value = Mock(text="next response")
                self.assertEqual(getattr(engine, method)(*args), "next response")


if __name__ == "__main__":
    unittest.main()
