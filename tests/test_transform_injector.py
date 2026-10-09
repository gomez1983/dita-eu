"""Voice Transform clipboard/input regressions; never touch the real clipboard."""
import ctypes
import unittest
from contextlib import ExitStack, nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

import injector


TEXT = injector.win32con.CF_UNICODETEXT


def encoded(text):
    return (text + "\0").encode("utf-16-le")


class TransformClipboardTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.clipboard = {TEXT: encoded("clipboard anterior"), 49155: b"<b>original</b>"}
        self.original = dict(self.clipboard)
        self.selected = "texto selecionado"
        self.stack.enter_context(patch.object(injector, "_clipboard_window", return_value=nullcontext(1)))
        self.stack.enter_context(patch.object(injector, "_open_transform_clipboard", side_effect=lambda _: nullcontext()))
        self.snapshot = self.stack.enter_context(patch.object(
            injector, "_snapshot_clipboard", side_effect=lambda _: list(self.clipboard.items())))
        self.replace = self.stack.enter_context(patch.object(
            injector, "_replace_transform_clipboard", side_effect=self._replace))
        self.send = self.stack.enter_context(patch.object(
            injector, "_send_ctrl_shortcut", side_effect=self._send))
        self.sleep = self.stack.enter_context(patch.object(injector.time, "sleep"))
        self.stack.enter_context(patch.object(injector, "_exclude_clipboard_history"))
        self.stack.enter_context(patch.object(injector.win32clipboard, "IsClipboardFormatAvailable",
                                            side_effect=lambda fmt: fmt in self.clipboard))
        self.read = self.stack.enter_context(patch.object(
            injector.win32clipboard, "GetClipboardData",
            side_effect=lambda fmt: self.clipboard[fmt].decode("utf-16-le").rstrip("\0")))

    def _replace(self, hwnd, formats, transient=True):
        self.clipboard.clear()
        self.clipboard.update(formats)

    def _send(self, key):
        if key == injector.VK_C and self.selected is not None:
            self.clipboard[TEXT] = encoded(self.selected)

    def test_copy_restores_all_original_formats_even_on_success(self):
        self.assertEqual(injector.get_selected_text(), self.selected)
        self.assertEqual(self.clipboard, self.original)
        self.send.assert_called_once_with(injector.VK_C)
        self.sleep.assert_called_once_with(0.04)

    def test_no_selection_never_reuses_previous_clipboard_text(self):
        self.selected = None
        self.assertEqual(injector.get_selected_text(), "")
        self.assertEqual(self.clipboard, self.original)
        self.read.assert_not_called()

    def test_empty_clipboard_is_restored_as_empty(self):
        self.clipboard.clear()
        self.assertEqual(injector.get_selected_text(), self.selected)
        self.assertEqual(self.clipboard, {})

    def test_non_text_clipboard_is_restored(self):
        self.clipboard = {15: b"file-list", 49155: b"image-payload"}
        original = dict(self.clipboard)
        self.assertEqual(injector.get_selected_text(), self.selected)
        self.assertEqual(self.clipboard, original)

    def test_blank_selection_is_ignored(self):
        self.selected = " \n\t "
        self.assertEqual(injector.get_selected_text(), "")
        self.assertEqual(self.clipboard, self.original)

    def test_failed_copy_restores_clipboard(self):
        self.send.side_effect = OSError("input denied")
        self.assertEqual(injector.get_selected_text(), "")
        self.assertEqual(self.clipboard, self.original)

    def test_failed_read_restores_clipboard(self):
        self.read.side_effect = OSError("read denied")
        self.assertEqual(injector.get_selected_text(), "")
        self.assertEqual(self.clipboard, self.original)

    def test_unsupported_snapshot_does_not_clear_or_send_input(self):
        self.snapshot.side_effect = OSError("unsupported format")
        self.assertEqual(injector.get_selected_text(), "")
        self.replace.assert_not_called()
        self.send.assert_not_called()
        self.assertEqual(self.clipboard, self.original)

    def test_paste_restores_all_formats_after_safe_delay(self):
        observed = []
        self.send.side_effect = lambda key: observed.append((key, dict(self.clipboard)))
        self.assertTrue(injector.inject_transformed_text("resultado \U0001f680\nlinha"))
        self.assertEqual(observed, [(injector.VK_V, {TEXT: encoded("resultado \U0001f680\nlinha")})])
        self.sleep.assert_called_once_with(0.35)
        self.assertEqual(self.clipboard, self.original)

    def test_paste_to_empty_clipboard_restores_empty(self):
        self.clipboard.clear()
        self.assertTrue(injector.inject_transformed_text("resultado"))
        self.assertEqual(self.clipboard, {})

    def test_paste_guard_runs_after_clipboard_write_and_can_cancel(self):
        def no_longer_safe():
            self.assertEqual(self.clipboard, {TEXT: encoded("resultado")})
            return False
        guard = Mock(side_effect=no_longer_safe)
        self.assertFalse(injector.inject_transformed_text("resultado", should_paste=guard))
        guard.assert_called_once_with()
        self.send.assert_not_called()
        self.sleep.assert_not_called()
        self.assertEqual(self.clipboard, self.original)

    def test_paste_guard_allows_valid_target(self):
        guard = Mock(return_value=True)
        self.assertTrue(injector.inject_transformed_text("resultado", should_paste=guard))
        guard.assert_called_once_with()
        self.send.assert_called_once_with(injector.VK_V)
        self.assertEqual(self.clipboard, self.original)

    def test_paste_guard_failure_restores_clipboard_without_pasting(self):
        guard = Mock(side_effect=OSError("target unavailable"))
        self.assertFalse(injector.inject_transformed_text("resultado", should_paste=guard))
        self.send.assert_not_called()
        self.assertEqual(self.clipboard, self.original)

    def test_failed_paste_still_waits_and_restores(self):
        self.send.side_effect = OSError("input denied")
        self.assertFalse(injector.inject_transformed_text("resultado"))
        self.sleep.assert_called_once_with(0.35)
        self.assertEqual(self.clipboard, self.original)

    def test_failed_temporary_write_still_restores(self):
        def fail_once(hwnd, formats, transient=True):
            self._replace(hwnd, formats)
            self.replace.side_effect = self._replace
            raise OSError("partial write")
        self.replace.side_effect = fail_once
        self.assertFalse(injector.inject_transformed_text("resultado"))
        self.send.assert_not_called()
        self.assertEqual(self.clipboard, self.original)

    def test_blank_transform_does_nothing(self):
        self.assertFalse(injector.inject_transformed_text(" \n"))
        self.snapshot.assert_not_called()
        self.send.assert_not_called()

    def test_capture_fails_closed_if_restore_cannot_complete(self):
        with patch.object(injector, "_restore_transform_clipboard", side_effect=OSError("busy")):
            self.assertEqual(injector.get_selected_text(), "")


class TransformInputTests(unittest.TestCase):
    def test_input_structure_has_correct_native_size(self):
        self.assertEqual(ctypes.sizeof(injector._INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_held_modifiers_are_released_and_restored_in_same_input_batch(self):
        batches = []
        held = (0xA0, 0xA3, 0xA5, 0x5B)
        def send(count, inputs, size):
            batches.append([(i.ki.wVk, i.ki.dwFlags, i.ki.dwExtraInfo) for i in inputs])
            self.assertEqual(size, ctypes.sizeof(injector._INPUT))
            return count
        with patch.object(injector.user32, "GetAsyncKeyState", side_effect=lambda key: 0x8000 if key in held else 0), \
             patch.object(injector.user32, "SendInput", side_effect=send), \
             patch.object(injector.user32, "keybd_event") as legacy:
            injector._send_ctrl_shortcut(injector.VK_C)
        self.assertEqual(len(batches), 1)
        events = batches[0]
        self.assertEqual([key for key, _, _ in events[:4]], list(held))
        self.assertTrue(all(flags & injector.KEYEVENTF_KEYUP for _, flags, _ in events[:4]))
        self.assertEqual([key for key, _, _ in events[4:8]], [0xA2, injector.VK_C, injector.VK_C, 0xA2])
        self.assertEqual([key for key, _, _ in events[-4:]], list(held))
        self.assertTrue(all(not flags & injector.KEYEVENTF_KEYUP for _, flags, _ in events[-4:]))
        self.assertTrue(all(marker == injector.TRANSFORM_INPUT_MARKER for _, _, marker in events))
        legacy.assert_not_called()

    def test_partial_send_input_cleans_up_keys_and_raises(self):
        batches = []
        def send(count, inputs, size):
            batches.append([(i.ki.wVk, i.ki.dwFlags) for i in inputs])
            return 1 if len(batches) == 1 else count
        with patch.object(injector.user32, "GetAsyncKeyState", side_effect=lambda key: 0x8000 if key == 0xA0 else 0), \
             patch.object(injector.user32, "SendInput", side_effect=send):
            with self.assertRaises(OSError):
                injector._send_ctrl_shortcut(injector.VK_V)
        self.assertEqual(batches[-1], [(injector.VK_V, 2), (0xA2, 2), (0xA0, 0)])

    def test_only_own_injected_events_are_identified(self):
        self.assertTrue(injector.is_own_input(SimpleNamespace(flags=0x10, dwExtraInfo=injector.TRANSFORM_INPUT_MARKER)))
        self.assertFalse(injector.is_own_input(SimpleNamespace(flags=0, dwExtraInfo=injector.TRANSFORM_INPUT_MARKER)))
        self.assertFalse(injector.is_own_input(SimpleNamespace(flags=0x10, dwExtraInfo=0)))
        self.assertFalse(injector.is_own_input(SimpleNamespace(flags=0x10, dwExtraInfo=None)))


class NativeClipboardTests(unittest.TestCase):
    def test_clipboard_open_retries_busy_and_always_closes(self):
        with patch.object(injector.win32clipboard, "OpenClipboard", side_effect=[OSError(), OSError(), None]) as opened, \
             patch.object(injector.win32clipboard, "CloseClipboard") as closed, \
             patch.object(injector.time, "sleep"):
            with self.assertRaises(ValueError):
                with injector._open_transform_clipboard(123):
                    raise ValueError("body failed")
        self.assertEqual(opened.call_count, 3)
        closed.assert_called_once_with()

    def test_clipboard_open_exhaustion_does_not_close_other_owners_clipboard(self):
        with patch.object(injector.win32clipboard, "OpenClipboard", side_effect=OSError()) as opened, \
             patch.object(injector.win32clipboard, "CloseClipboard") as closed, \
             patch.object(injector.time, "sleep"):
            with self.assertRaises(OSError):
                with injector._open_transform_clipboard(123):
                    self.fail("must not enter")
        self.assertEqual(opened.call_count, 20)
        closed.assert_not_called()

    def test_snapshot_preserves_raw_unicode_file_list_and_registered_data(self):
        payloads = {TEXT: encoded("original"), 15: b"file-list\0", 49155: b"html-data"}
        buffers = {fmt: ctypes.create_string_buffer(data, len(data)) for fmt, data in payloads.items()}
        with patch.object(injector, "_open_transform_clipboard", return_value=nullcontext()), \
             patch.object(injector.win32clipboard, "EnumClipboardFormats", side_effect=[*payloads, 0]), \
             patch.object(injector.user32, "GetClipboardData", side_effect=lambda fmt: fmt), \
             patch.object(injector.kernel32, "GlobalSize", side_effect=lambda h: len(payloads[h])), \
             patch.object(injector.kernel32, "GlobalLock", side_effect=lambda h: ctypes.addressof(buffers[h])), \
             patch.object(injector.kernel32, "GlobalUnlock"):
            self.assertEqual(injector._snapshot_clipboard(1), list(payloads.items()))

    def test_handle_only_clipboard_is_rejected_without_clearing(self):
        with patch.object(injector, "_open_transform_clipboard", return_value=nullcontext()), \
             patch.object(injector.win32clipboard, "EnumClipboardFormats", side_effect=[14, 0]), \
             patch.object(injector.win32clipboard, "EmptyClipboard") as cleared:
            with self.assertRaises(OSError):
                injector._snapshot_clipboard(1)
        cleared.assert_not_called()

    def test_zero_length_or_invalid_hglobal_is_rejected_without_clearing(self):
        with patch.object(injector, "_open_transform_clipboard", return_value=nullcontext()), \
             patch.object(injector.win32clipboard, "EnumClipboardFormats", side_effect=[49155, 0]), \
             patch.object(injector.user32, "GetClipboardData", return_value=123), \
             patch.object(injector.kernel32, "GlobalSize", return_value=0), \
             patch.object(injector.win32clipboard, "EmptyClipboard") as cleared:
            with self.assertRaises(OSError):
                injector._snapshot_clipboard(1)
        cleared.assert_not_called()

    def test_dib_is_saved_without_unsafe_synthesized_bitmap_handle(self):
        buffer = ctypes.create_string_buffer(b"dib")
        with patch.object(injector, "_open_transform_clipboard", return_value=nullcontext()), \
             patch.object(injector.win32clipboard, "EnumClipboardFormats", side_effect=[8, 2, 0]), \
             patch.object(injector.user32, "GetClipboardData", return_value=8) as read, \
             patch.object(injector.kernel32, "GlobalSize", return_value=3), \
             patch.object(injector.kernel32, "GlobalLock", return_value=ctypes.addressof(buffer)), \
             patch.object(injector.kernel32, "GlobalUnlock"):
            self.assertEqual(injector._snapshot_clipboard(1), [(8, b"dib")])
        read.assert_called_once_with(8)

    def test_failed_set_clipboard_releases_untransferred_memory(self):
        buffer = ctypes.create_string_buffer(20)
        with patch.object(injector.kernel32, "GlobalAlloc", return_value=123), \
             patch.object(injector.kernel32, "GlobalLock", return_value=ctypes.addressof(buffer)), \
             patch.object(injector.kernel32, "GlobalUnlock"), \
             patch.object(injector.kernel32, "GlobalFree") as freed, \
             patch.object(injector.user32, "SetClipboardData", return_value=0):
            with self.assertRaises(OSError):
                injector._set_clipboard_bytes(TEXT, b"payload")
        freed.assert_called_once_with(123)

    def test_history_exclusion_flags_are_all_written_as_zero(self):
        with patch.object(injector.win32clipboard, "RegisterClipboardFormat", side_effect=[49160, 49161, 49162]) as register, \
             patch.object(injector, "_set_clipboard_bytes") as write:
            injector._exclude_clipboard_history()
        self.assertEqual([call.args[0] for call in register.call_args_list], list(injector._HISTORY_FORMATS))
        self.assertEqual([call.args for call in write.call_args_list],
                         [(49160, bytes(4)), (49161, bytes(4)), (49162, bytes(4))])

    def test_complete_restore_retries_partial_write_failure(self):
        snapshot = [(TEXT, encoded("original"))]
        with patch.object(injector, "_replace_transform_clipboard", side_effect=[OSError(), None]) as replace, \
             patch.object(injector.time, "sleep"):
            injector._restore_transform_clipboard(1, snapshot)
        self.assertEqual(replace.call_count, 2)
        replace.assert_called_with(1, snapshot, transient=True)


if __name__ == "__main__":
    unittest.main()
