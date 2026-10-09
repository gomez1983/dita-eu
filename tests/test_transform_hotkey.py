"""Exercise pynput's real Windows event conversion without installing a hook."""
import ctypes
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import unittest
from unittest.mock import Mock

from PyQt5 import QtCore, QtWidgets
from pynput._util.win32 import SystemHook

import main


class TransformHotkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.app = main.DictationApp.__new__(main.DictationApp)
        QtCore.QObject.__init__(self.app)
        self.app.config = {"trigger_keys": ["f8"]}
        self.app._lock = threading.Lock()
        self.app._currently_pressed_keys = set()
        self.app._transform_latched_keys = frozenset()
        self.app._transform_session = None
        self.app._is_active = False
        self.app._start_dictation = Mock()
        self.app._start_transform = Mock()
        self.queued = []
        self.listener = main._TransformKeyboardListener(
            on_press=self.app._on_key_press,
            on_release=self.app._on_key_release,
            win32_event_filter=self.app._filter_keyboard_event,
        )
        self.app.keyboard_listener = self.listener
        self.listener._message_loop = Mock()
        self.listener._message_loop.post.side_effect = lambda *args: self.queued.append(args)

    def event(self, vk, pressed=True, marker=0, system=False):
        msg = (0x104 if pressed else 0x105) if system else (0x100 if pressed else 0x101)
        data = self.listener._KBDLLHOOKSTRUCT(vk, 0, 0, 0, marker)
        try:
            self.listener._handler(SystemHook.HC_ACTION, msg, ctypes.pointer(data))
        except SystemHook.SuppressException:
            return True
        return False

    def drain_callbacks(self):
        while self.queued:
            message, msg, vk = self.queued.pop(0)
            self.assertEqual(message, self.listener._WM_PROCESS)
            self.listener._process(msg, vk)

    def test_f8_alone_still_reaches_target_and_dictation_callback(self):
        self.assertFalse(self.event(0x77))
        self.drain_callbacks()
        self.app._start_dictation.assert_called_once_with()
        self.app._start_transform.assert_not_called()
        self.assertFalse(self.event(0x77, pressed=False))
        self.drain_callbacks()
        self.assertNotIn("f8", self.app._currently_pressed_keys)

    def test_transform_is_suppressed_before_delayed_shift_callback_is_delivered(self):
        self.assertFalse(self.event(0xA0))  # Shift press stays visible to target.
        self.assertTrue(self.event(0x77))
        # _handler must queue both callbacks before raising suppression. The
        # filter cannot rely on the application's not-yet-updated key set.
        self.assertEqual(len(self.queued), 2)
        self.assertFalse(self.app._currently_pressed_keys)
        self.drain_callbacks()
        self.app._start_transform.assert_called_once_with(frozenset({"shift", "f8"}))
        self.app._start_dictation.assert_not_called()

    def test_repeat_and_key_up_are_suppressed_but_callbacks_are_preserved(self):
        self.event(0xA0)
        self.assertTrue(self.event(0x77))
        self.assertTrue(self.event(0x77))
        self.assertTrue(self.event(0x77, pressed=False))
        self.assertFalse(self.event(0xA0, pressed=False))
        self.drain_callbacks()
        self.app._start_transform.assert_called_once()
        self.app._start_dictation.assert_not_called()
        self.assertFalse(self.app._currently_pressed_keys)
        self.assertFalse(self.listener.transform_suppressed_vks)

    def test_release_shift_first_does_not_leak_f8_repeat_or_release(self):
        self.event(0xA1)
        self.assertTrue(self.event(0x77))
        self.assertFalse(self.event(0xA1, pressed=False))
        self.assertTrue(self.event(0x77))
        self.assertTrue(self.event(0x77, pressed=False))
        self.drain_callbacks()
        self.app._start_transform.assert_called_once()
        self.app._start_dictation.assert_not_called()
        self.assertFalse(self.event(0x77))  # Next F8 is normal again.
        self.drain_callbacks()
        self.app._start_dictation.assert_called_once()

    def test_own_copy_paste_events_are_neither_suppressed_nor_delivered(self):
        self.event(0xA0)
        self.assertTrue(self.event(0x77))
        queued_count = len(self.queued)
        for vk, pressed in ((0xA0, False), (0xA2, True), (0x43, True),
                            (0x43, False), (0xA2, False), (0xA0, True)):
            self.assertFalse(self.event(vk, pressed, marker=main.TRANSFORM_INPUT_MARKER))
        self.assertEqual(len(self.queued), queued_count)
        self.assertEqual(set(self.listener.transform_pressed_vks), {0xA0, 0x77})
        self.drain_callbacks()
        self.app._start_transform.assert_called_once()
        self.assertIn("shift", self.app._currently_pressed_keys)

    def test_other_keys_and_modifier_key_up_are_not_suppressed(self):
        self.event(0xA0)
        self.assertTrue(self.event(0x77))
        self.assertFalse(self.event(0x78))  # F9
        self.assertFalse(self.event(0x78, pressed=False))
        self.assertFalse(self.event(0xA0, pressed=False))
        self.assertTrue(self.event(0x77, pressed=False))

    def test_configured_transform_chord_suppresses_only_its_action_key(self):
        self.app.config["transform_trigger_keys"] = ["ctrl+shift+f7"]
        self.assertFalse(self.event(0xA2))
        self.assertFalse(self.event(0xA1))
        self.assertTrue(self.event(0x76))
        self.assertFalse(self.event(0xA2, pressed=False))
        self.assertTrue(self.event(0x76, pressed=False))
        self.drain_callbacks()
        self.app._start_transform.assert_called_once_with(frozenset({"ctrl", "shift", "f7"}))
        self.app._start_dictation.assert_not_called()

    def test_system_key_messages_support_alt_transform_chord(self):
        self.app.config["transform_trigger_keys"] = ["alt+f7"]
        self.assertFalse(self.event(0xA4, system=True))
        self.assertTrue(self.event(0x76, system=True))
        self.assertTrue(self.event(0x76, pressed=False, system=True))
        self.assertFalse(self.event(0xA4, pressed=False, system=True))
        self.drain_callbacks()
        self.app._start_transform.assert_called_once_with(frozenset({"alt", "f7"}))

    def test_disabled_transform_does_not_suppress_shift_f8(self):
        self.app.config["transform_trigger_keys"] = []
        self.assertFalse(self.event(0xA0))
        self.assertFalse(self.event(0x77))
        self.assertFalse(self.event(0x77, pressed=False))

    def test_changing_config_during_hold_still_suppresses_original_key_up(self):
        self.event(0xA0)
        self.assertTrue(self.event(0x77))
        self.app.config["transform_trigger_keys"] = ["ctrl+f7"]
        self.assertTrue(self.event(0x77, pressed=False))
        self.assertFalse(self.listener.transform_suppressed_vks)


if __name__ == "__main__":
    unittest.main()
