"""Voice Transform clipboard/input regressions; never touch the real clipboard."""
import ctypes
import unittest
from contextlib import ExitStack, contextmanager, nullcontext
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
        self.sequence = 100
        self.now = 0.0
        self.scheduled = []
        self.clipboard_open = False
        self.busy_until = 0.0
        self.stack.enter_context(patch.object(injector, "_clipboard_window", return_value=nullcontext(1)))
        self.open_context = self.stack.enter_context(patch.object(
            injector, "_open_transform_clipboard", side_effect=lambda _: nullcontext()))
        self.opened = self.stack.enter_context(patch.object(
            injector.win32clipboard, "OpenClipboard", side_effect=self._open))
        self.closed = self.stack.enter_context(patch.object(
            injector.win32clipboard, "CloseClipboard", side_effect=self._close))
        self.stack.enter_context(patch.object(
            injector.user32, "GetClipboardSequenceNumber", side_effect=lambda: self.sequence))
        self.foreground = self.stack.enter_context(patch.object(
            injector, "get_foreground_window", return_value=10))
        self.origin = self.stack.enter_context(patch.object(
            injector, "_clipboard_belongs_to_target", return_value=True, create=True))
        self.line_copy = self.stack.enter_context(patch.object(
            injector, "_clipboard_is_line_copy", return_value=False))
        self.snapshot = self.stack.enter_context(patch.object(
            injector, "_snapshot_clipboard", side_effect=self._snapshot))
        self.replace = self.stack.enter_context(patch.object(
            injector, "_replace_transform_clipboard", side_effect=self._replace))
        self.send = self.stack.enter_context(patch.object(
            injector, "_send_ctrl_shortcut", side_effect=self._send))
        self.sleep = self.stack.enter_context(patch.object(injector.time, "sleep", side_effect=self._sleep))
        self.stack.enter_context(patch.object(injector.time, "monotonic", side_effect=lambda: self.now))
        self.exclude_history = self.stack.enter_context(patch.object(injector, "_exclude_clipboard_history"))
        self.stack.enter_context(patch.object(injector.win32clipboard, "IsClipboardFormatAvailable",
                                            side_effect=lambda fmt: fmt in self.clipboard))
        self.read = self.stack.enter_context(patch.object(
            injector.win32clipboard, "GetClipboardData",
            side_effect=self._read))

    def _snapshot(self, hwnd, with_sequence=False):
        formats = list(self.clipboard.items())
        return (formats, self.sequence) if with_sequence else formats

    def _replace(self, hwnd, formats, transient=True, expected_sequence=None):
        self.assertFalse(self.clipboard_open)
        if expected_sequence is not None and expected_sequence != self.sequence:
            return False
        self.clipboard.clear()
        self.clipboard.update(formats)
        self.sequence += 1
        return True

    def _publish(self, formats):
        self.assertFalse(self.clipboard_open, "The source must be able to publish between polls")
        self.clipboard = dict(formats)
        self.sequence += 1

    def _open(self, hwnd):
        self.assertFalse(self.clipboard_open)
        if self.now < self.busy_until:
            raise OSError("clipboard busy")
        self.clipboard_open = True

    def _close(self):
        self.assertTrue(self.clipboard_open)
        self.clipboard_open = False

    def _read(self, fmt):
        self.assertTrue(self.clipboard_open)
        return self.clipboard[fmt].decode("utf-16-le").rstrip("\0")

    def _sleep(self, seconds):
        self.assertFalse(self.clipboard_open, "Never sleep with the clipboard open")
        self.assertGreater(seconds, 0)
        self.now += seconds
        due = [entry for entry in self.scheduled if entry[0] <= self.now]
        self.scheduled = [entry for entry in self.scheduled if entry[0] > self.now]
        for _, callback in due:
            callback()

    def _send(self, key):
        self.assertFalse(self.clipboard_open)
        if key == injector.VK_C and self.selected is not None:
            self._publish({TEXT: encoded(self.selected)})

    def test_copy_restores_all_original_formats_even_on_success(self):
        self.assertEqual(injector.get_selected_text(), self.selected)
        self.assertEqual(self.clipboard, self.original)
        self.send.assert_called_once_with(injector.VK_C)
        self.assertEqual(self.replace.call_count, 1)
        self.assertEqual(self.replace.call_args.kwargs["expected_sequence"], 101)
        self.exclude_history.assert_not_called()

    def test_no_selection_never_reuses_previous_clipboard_text(self):
        self.selected = None
        self.assertEqual(injector.get_selected_text(), "")
        self.assertEqual(self.clipboard, self.original)
        self.read.assert_not_called()
        self.replace.assert_not_called()
        self.opened.assert_not_called()
        self.assertGreaterEqual(self.now, injector._COPY_TIMEOUT_SECONDS)
        self.assertLessEqual(self.now, injector._COPY_TIMEOUT_SECONDS + injector._COPY_POLL_INTERVAL)

    def test_delayed_web_copy_is_accepted_without_clearing_clipboard_first(self):
        self.selected = None
        self.scheduled.append((0.45, lambda: self._publish({TEXT: encoded("cópia assíncrona")})))
        self.send.side_effect = lambda key: self.assertEqual(self.clipboard, self.original)
        self.assertEqual(injector.get_selected_text(), "cópia assíncrona")
        self.assertGreaterEqual(self.now, 0.45)
        self.assertLess(self.now, injector._COPY_TIMEOUT_SECONDS)
        self.assertEqual(self.clipboard, self.original)
        self.assertEqual(self.replace.call_count, 1)
        self.open_context.assert_not_called()

    def test_same_text_is_valid_when_copy_changes_the_sequence(self):
        self.selected = "clipboard anterior"
        self.assertEqual(injector.get_selected_text(), self.selected)
        self.read.assert_called_once_with(TEXT)
        self.assertEqual(self.clipboard, self.original)

    def test_snapshot_rendering_does_not_count_as_a_new_copy(self):
        self.selected = None
        def render_snapshot(hwnd, with_sequence=False):
            self.sequence += 1
            return self._snapshot(hwnd, with_sequence=with_sequence)
        self.snapshot.side_effect = render_snapshot
        self.assertEqual(injector.get_selected_text(), "")
        self.read.assert_not_called()
        self.replace.assert_not_called()

    def test_external_copy_after_snapshot_cancels_before_shortcut_without_writes(self):
        other = {TEXT: encoded("nova cópia externa"), 49155: b"new-html"}
        def racing_snapshot(hwnd, with_sequence=False):
            result = self._snapshot(hwnd, with_sequence=with_sequence)
            self._publish(other)
            return result
        self.snapshot.side_effect = racing_snapshot
        self.assertEqual(injector.get_selected_text(), "")
        self.snapshot.assert_called_once_with(1, with_sequence=True)
        self.send.assert_not_called()
        self.read.assert_not_called()
        self.replace.assert_not_called()
        self.assertEqual(self.clipboard, other)

    def test_delayed_metadata_rendering_uses_latest_sequence_for_restore(self):
        def render_metadata():
            self.sequence += 1
            return False
        self.line_copy.side_effect = render_metadata
        self.assertEqual(injector.get_selected_text(), self.selected)
        self.assertEqual(self.replace.call_args.kwargs["expected_sequence"], 102)
        self.assertEqual(self.clipboard, self.original)

    def test_intermediate_html_update_does_not_end_wait_for_unicode(self):
        self.selected = None
        self.scheduled.extend([
            (0.15, lambda: self._publish({49155: b"<b>copy in progress</b>"})),
            (0.40, lambda: self._publish({TEXT: encoded("texto completo"), 49155: b"<b>complete</b>"})),
        ])
        self.assertEqual(injector.get_selected_text(), "texto completo")
        self.assertGreaterEqual(self.now, 0.40)
        self.read.assert_called_once_with(TEXT)
        self.assertEqual(self.clipboard, self.original)

    def test_temporarily_busy_clipboard_retries_without_blocking_source(self):
        self.busy_until = 0.30
        self.assertEqual(injector.get_selected_text(), self.selected)
        self.assertGreater(self.opened.call_count, 1)
        self.closed.assert_called_once_with()
        self.open_context.assert_not_called()
        self.assertFalse(self.clipboard_open)
        self.assertGreaterEqual(self.now, self.busy_until)

    def test_busy_clipboard_respects_capture_deadline(self):
        self.busy_until = 10.0
        self.assertEqual(injector.get_selected_text(), "")
        self.assertLessEqual(self.now, injector._COPY_TIMEOUT_SECONDS + injector._COPY_POLL_INTERVAL)
        self.read.assert_not_called()
        self.closed.assert_not_called()
        self.open_context.assert_not_called()

    def test_concurrent_clipboard_change_before_restore_is_preserved(self):
        restore = injector._restore_transform_clipboard
        other = {TEXT: encoded("nova cópia do usuário"), 49155: b"new-html"}
        def concurrent_change(hwnd, snapshot, expected_sequence=None):
            self._publish(other)
            return restore(hwnd, snapshot, expected_sequence=expected_sequence)
        with patch.object(injector, "_restore_transform_clipboard", side_effect=concurrent_change):
            self.assertEqual(injector.get_selected_text(), self.selected)
        self.assertEqual(self.clipboard, other)
        self.assertEqual(self.replace.call_count, 1)
        self.assertEqual(self.replace.call_args.kwargs["expected_sequence"], 101)

    def test_update_from_another_process_is_not_read_or_overwritten(self):
        self.origin.return_value = False
        self.assertEqual(injector.get_selected_text(), "")
        self.read.assert_not_called()
        self.replace.assert_not_called()
        self.assertEqual(self.clipboard, {TEXT: encoded(self.selected)})

    def test_focus_change_during_snapshot_cancels_before_shortcut(self):
        def changed_focus(hwnd, with_sequence=False):
            self.foreground.return_value = 20
            return self._snapshot(hwnd, with_sequence=with_sequence)
        self.snapshot.side_effect = changed_focus
        self.assertEqual(injector.get_selected_text(), "")
        self.send.assert_not_called()
        self.read.assert_not_called()
        self.replace.assert_not_called()

    def test_focus_change_while_waiting_never_accepts_later_text(self):
        self.selected = None
        self.scheduled.extend([
            (0.15, lambda: setattr(self.foreground, "return_value", 20)),
            (0.40, lambda: self._publish({TEXT: encoded("texto de outra janela")})),
        ])
        self.assertEqual(injector.get_selected_text(), "")
        self.read.assert_not_called()
        self.replace.assert_not_called()

    def test_line_copy_remains_rejected_and_restored(self):
        self.line_copy.return_value = True
        self.assertEqual(injector.get_selected_text(), "")
        self.read.assert_not_called()
        self.assertEqual(self.clipboard, self.original)

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

    def test_failed_copy_without_update_never_rewrites_clipboard(self):
        self.send.side_effect = OSError("input denied")
        self.assertEqual(injector.get_selected_text(), "")
        self.assertEqual(self.clipboard, self.original)
        self.replace.assert_not_called()

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
        def fail_once(hwnd, formats, transient=True, expected_sequence=None):
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
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.scans = {injector.VK_C: 0x2E, injector.VK_V: 0x2F,
                      0xA0: 0x2A, 0xA1: 0x36, 0xA2: 0x1D, 0xA3: 0x1D,
                      0xA4: 0x38, 0xA5: 0x38, 0x5B: 0x5B, 0x5C: 0x5C}
        self.map_key = self.stack.enter_context(patch.object(
            injector.user32, "MapVirtualKeyW", side_effect=lambda key, mode: self.scans.get(key, 0)))

    def test_input_structure_has_correct_native_size(self):
        self.assertEqual(ctypes.sizeof(injector._INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_held_modifiers_are_released_and_restored_in_same_input_batch(self):
        batches = []
        held = (0xA0, 0xA3, 0xA5, 0x5B)
        def send(count, inputs, size):
            batches.append([(i.ki.wVk, i.ki.wScan, i.ki.dwFlags, i.ki.dwExtraInfo) for i in inputs])
            self.assertEqual(size, ctypes.sizeof(injector._INPUT))
            return count
        with patch.object(injector.user32, "GetAsyncKeyState", side_effect=lambda key: 0x8000 if key in held else 0), \
             patch.object(injector.user32, "SendInput", side_effect=send), \
             patch.object(injector.user32, "keybd_event") as legacy:
            injector._send_ctrl_shortcut(injector.VK_C)
        self.assertEqual(len(batches), 1)
        events = batches[0]
        self.assertTrue(all(key == 0 for key, _, _, _ in events))
        self.assertTrue(all(flags & injector.KEYEVENTF_SCANCODE for _, _, flags, _ in events))
        self.assertEqual([scan for _, scan, _, _ in events[:4]], [self.scans[key] for key in held])
        self.assertTrue(all(flags & injector.KEYEVENTF_KEYUP for _, _, flags, _ in events[:4]))
        self.assertEqual([scan for _, scan, _, _ in events[4:8]], [0x1D, 0x2E, 0x2E, 0x1D])
        self.assertEqual([scan for _, scan, _, _ in events[-4:]], [self.scans[key] for key in held])
        self.assertTrue(all(not flags & injector.KEYEVENTF_KEYUP for _, _, flags, _ in events[-4:]))
        self.assertTrue(all(marker == injector.TRANSFORM_INPUT_MARKER for _, _, _, marker in events))
        self.assertEqual([bool(flags & 1) for _, _, flags, _ in events[:4]], [False, True, True, True])
        self.assertTrue(all(call.args[1] == 0 for call in self.map_key.call_args_list))
        legacy.assert_not_called()

    def test_partial_send_input_cleans_up_keys_and_raises(self):
        batches = []
        def send(count, inputs, size):
            batches.append([(i.ki.wVk, i.ki.wScan, i.ki.dwFlags) for i in inputs])
            return 1 if len(batches) == 1 else count
        with patch.object(injector.user32, "GetAsyncKeyState", side_effect=lambda key: 0x8000 if key == 0xA0 else 0), \
             patch.object(injector.user32, "SendInput", side_effect=send):
            with self.assertRaises(OSError):
                injector._send_ctrl_shortcut(injector.VK_V)
        self.assertEqual(batches[-1], [(0, 0x2F, 10), (0, 0x1D, 10), (0, 0x2A, 8)])

    def test_zero_send_fallback_retains_virtual_keys_scans_and_extended_flags(self):
        events = [(0xA3, 0), (injector.VK_C, injector.KEYEVENTF_KEYUP)]
        with patch.object(injector.user32, "SendInput", return_value=0), \
             patch.object(injector.user32, "keybd_event") as legacy:
            injector._send_input_events(events)
        self.assertEqual([call.args for call in legacy.call_args_list], [
            (0xA3, 0x1D, 1, injector.TRANSFORM_INPUT_MARKER),
            (injector.VK_C, 0x2E, 2, injector.TRANSFORM_INPUT_MARKER),
        ])

    def test_unmappable_key_rejects_entire_batch_before_sending(self):
        with patch.object(injector.user32, "SendInput") as send, \
             patch.object(injector.user32, "keybd_event") as legacy:
            with self.assertRaises(OSError):
                injector._send_input_events([(injector.VK_C, 0), (0xFF, 0)])
        send.assert_not_called()
        legacy.assert_not_called()

    def test_only_own_injected_events_are_identified(self):
        self.assertTrue(injector.is_own_input(SimpleNamespace(flags=0x10, dwExtraInfo=injector.TRANSFORM_INPUT_MARKER)))
        self.assertFalse(injector.is_own_input(SimpleNamespace(flags=0, dwExtraInfo=injector.TRANSFORM_INPUT_MARKER)))
        self.assertFalse(injector.is_own_input(SimpleNamespace(flags=0x10, dwExtraInfo=0)))
        self.assertFalse(injector.is_own_input(SimpleNamespace(flags=0x10, dwExtraInfo=None)))


class NativeClipboardTests(unittest.TestCase):
    def test_clipboard_origin_accepts_hidden_window_from_target_process(self):
        def process_id(hwnd, pid):
            ctypes.cast(pid, ctypes.POINTER(injector.wintypes.DWORD)).contents.value = 999
            return 1
        with patch.object(injector.user32, "GetClipboardOwner", return_value=20), \
             patch.object(injector.user32, "GetWindowThreadProcessId", side_effect=process_id) as lookup:
            self.assertTrue(injector._clipboard_belongs_to_target(10))
        self.assertEqual([call.args[0] for call in lookup.call_args_list], [20, 10])

    def test_clipboard_origin_rejects_another_process(self):
        def process_id(hwnd, pid):
            ctypes.cast(pid, ctypes.POINTER(injector.wintypes.DWORD)).contents.value = hwnd
            return 1
        with patch.object(injector.user32, "GetClipboardOwner", return_value=20), \
             patch.object(injector.user32, "GetWindowThreadProcessId", side_effect=process_id):
            self.assertFalse(injector._clipboard_belongs_to_target(10))

    def test_clipboard_origin_without_owner_or_pid_is_rejected(self):
        with patch.object(injector.user32, "GetClipboardOwner", return_value=0), \
             patch.object(injector.user32, "GetWindowThreadProcessId") as lookup:
            self.assertFalse(injector._clipboard_belongs_to_target(10))
            lookup.assert_not_called()
        with patch.object(injector.user32, "GetClipboardOwner", return_value=20), \
             patch.object(injector.user32, "GetWindowThreadProcessId", return_value=0):
            self.assertFalse(injector._clipboard_belongs_to_target(10))

    def test_conditional_replace_checks_sequence_while_open_before_any_mutation(self):
        state = {"open": False}
        @contextmanager
        def opened(hwnd):
            state["open"] = True
            try:
                yield
            finally:
                state["open"] = False
        def sequence():
            self.assertTrue(state["open"])
            return 200
        with patch.object(injector, "_open_transform_clipboard", side_effect=opened), \
             patch.object(injector.user32, "GetClipboardSequenceNumber", side_effect=sequence), \
             patch.object(injector.win32clipboard, "EmptyClipboard") as empty, \
             patch.object(injector, "_exclude_clipboard_history") as history, \
             patch.object(injector, "_set_clipboard_bytes") as write:
            self.assertFalse(injector._replace_transform_clipboard(
                1, [(TEXT, encoded("old"))], expected_sequence=100))
        empty.assert_not_called()
        history.assert_not_called()
        write.assert_not_called()
        self.assertFalse(state["open"])

    def test_conditional_replace_writes_when_sequence_still_matches(self):
        payload = encoded("old")
        with patch.object(injector, "_open_transform_clipboard", return_value=nullcontext()), \
             patch.object(injector.user32, "GetClipboardSequenceNumber", return_value=100), \
             patch.object(injector.win32clipboard, "EmptyClipboard") as empty, \
             patch.object(injector, "_exclude_clipboard_history"), \
             patch.object(injector, "_set_clipboard_bytes") as write:
            self.assertTrue(injector._replace_transform_clipboard(
                1, [(TEXT, payload)], expected_sequence=100))
        empty.assert_called_once_with()
        write.assert_called_once_with(TEXT, payload)

    def test_partial_replace_reports_its_new_sequence_for_safe_retry(self):
        state = {"open": False, "sequence": 100}
        @contextmanager
        def opened(hwnd):
            state["open"] = True
            try:
                yield
            finally:
                state["open"] = False
                state["sequence"] += 1
        def sequence():
            if state["sequence"] == 101:
                self.assertFalse(state["open"], "Sample the failed write only after CloseClipboard")
            return state["sequence"]
        with patch.object(injector, "_open_transform_clipboard", side_effect=opened), \
             patch.object(injector.user32, "GetClipboardSequenceNumber", side_effect=sequence), \
             patch.object(injector.user32, "GetClipboardOwner", return_value=1), \
             patch.object(injector.win32clipboard, "EmptyClipboard"), \
             patch.object(injector, "_exclude_clipboard_history"), \
             patch.object(injector, "_set_clipboard_bytes", side_effect=OSError("partial write")):
            with self.assertRaises(OSError) as raised:
                injector._replace_transform_clipboard(1, [(TEXT, b"old")], expected_sequence=100)
        self.assertEqual(raised.exception.clipboard_sequence, 101)

    def test_partial_restore_retries_sequence_published_only_on_close(self):
        state = {"sequence": 100, "owner": 10, "empty_count": 0, "open": False}
        @contextmanager
        def opened(hwnd):
            state["open"] = True
            try:
                yield
            finally:
                state["open"] = False
                state["sequence"] += 1
        def empty():
            self.assertTrue(state["open"])
            state["empty_count"] += 1
            state["owner"] = 1
        def sleep(seconds):
            self.assertFalse(state["open"])
        with patch.object(injector, "_open_transform_clipboard", side_effect=opened), \
             patch.object(injector.user32, "GetClipboardSequenceNumber", side_effect=lambda: state["sequence"]), \
             patch.object(injector.user32, "GetClipboardOwner", side_effect=lambda: state["owner"]), \
             patch.object(injector.win32clipboard, "EmptyClipboard", side_effect=empty), \
             patch.object(injector, "_exclude_clipboard_history"), \
             patch.object(injector, "_set_clipboard_bytes", side_effect=[OSError("partial write"), None]) as write, \
             patch.object(injector.time, "sleep", side_effect=sleep):
            self.assertTrue(injector._restore_transform_clipboard(
                1, [(TEXT, encoded("original"))], expected_sequence=100))
        self.assertEqual(state["empty_count"], 2)
        self.assertEqual(write.call_count, 2)
        self.assertEqual(state["sequence"], 102)

    def test_foreign_copy_survives_partial_restore_around_close_and_retry(self):
        for timing in ("on_close", "before_owner_check", "during_retry"):
            with self.subTest(timing=timing):
                state = {"sequence": 100, "owner": 10, "open": False,
                         "empty_count": 0, "close_count": 0, "foreign": False,
                         "data": {TEXT: encoded("original")}}
                foreign = {TEXT: encoded("cópia concorrente")}
                def publish_foreign():
                    self.assertFalse(state["open"])
                    state["owner"] = 20
                    state["sequence"] += 1
                    state["data"] = dict(foreign)
                    state["foreign"] = True
                @contextmanager
                def opened(hwnd):
                    state["open"] = True
                    try:
                        yield
                    finally:
                        state["open"] = False
                        state["close_count"] += 1
                        if state["close_count"] == 1:
                            state["sequence"] += 1
                            if timing == "on_close":
                                publish_foreign()
                def empty():
                    self.assertTrue(state["open"])
                    state["empty_count"] += 1
                    state["owner"] = 1
                    state["data"] = {}
                def sequence():
                    current = state["sequence"]
                    if (timing == "before_owner_check" and not state["open"]
                            and state["close_count"] == 1 and not state["foreign"]):
                        publish_foreign()
                    return current
                def sleep(seconds):
                    self.assertFalse(state["open"])
                    if timing == "during_retry" and not state["foreign"]:
                        publish_foreign()
                with patch.object(injector, "_open_transform_clipboard", side_effect=opened), \
                     patch.object(injector.user32, "GetClipboardSequenceNumber", side_effect=sequence), \
                     patch.object(injector.user32, "GetClipboardOwner", side_effect=lambda: state["owner"]), \
                     patch.object(injector.win32clipboard, "EmptyClipboard", side_effect=empty), \
                     patch.object(injector, "_exclude_clipboard_history"), \
                     patch.object(injector, "_set_clipboard_bytes", side_effect=OSError("partial write")) as write, \
                     patch.object(injector.time, "sleep", side_effect=sleep):
                    self.assertFalse(injector._restore_transform_clipboard(
                        1, [(TEXT, encoded("original"))], expected_sequence=100))
                self.assertEqual(state["data"], foreign)
                self.assertEqual(state["empty_count"], 1)
                self.assertEqual(write.call_count, 1)

    def test_conditional_restore_repairs_own_partial_write_with_new_sequence(self):
        error = OSError("partial write")
        error.clipboard_sequence = 101
        snapshot = [(TEXT, encoded("old"))]
        with patch.object(injector, "_replace_transform_clipboard", side_effect=[error, True]) as replace, \
             patch.object(injector.time, "sleep"):
            self.assertTrue(injector._restore_transform_clipboard(1, snapshot, expected_sequence=100))
        self.assertEqual([call.kwargs["expected_sequence"] for call in replace.call_args_list], [100, 101])

    def test_conditional_restore_stops_when_another_copy_wins_during_retry(self):
        error = OSError("partial write")
        error.clipboard_sequence = 101
        with patch.object(injector, "_replace_transform_clipboard", side_effect=[error, False]) as replace, \
             patch.object(injector.time, "sleep") as sleep:
            self.assertFalse(injector._restore_transform_clipboard(1, [], expected_sequence=100))
        self.assertEqual([call.kwargs["expected_sequence"] for call in replace.call_args_list], [100, 101])
        sleep.assert_called_once_with(0.02)

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

    def test_snapshot_sequence_is_sampled_after_rendering_under_same_clipboard_lock(self):
        payload = encoded("original")
        buffer = ctypes.create_string_buffer(payload, len(payload))
        state = {"open": False, "sequence": 100}
        @contextmanager
        def opened(hwnd):
            state["open"] = True
            try:
                yield
            finally:
                state["open"] = False
        def rendered(handle):
            self.assertTrue(state["open"])
            state["sequence"] += 1
        def sequence():
            self.assertTrue(state["open"], "Snapshot and baseline must share the clipboard lock")
            return state["sequence"]
        with patch.object(injector, "_open_transform_clipboard", side_effect=opened), \
             patch.object(injector.win32clipboard, "EnumClipboardFormats", side_effect=[TEXT, 0]), \
             patch.object(injector.user32, "GetClipboardData", return_value=123), \
             patch.object(injector.user32, "GetClipboardSequenceNumber", side_effect=sequence), \
             patch.object(injector.kernel32, "GlobalSize", return_value=len(payload)), \
             patch.object(injector.kernel32, "GlobalLock", return_value=ctypes.addressof(buffer)), \
             patch.object(injector.kernel32, "GlobalUnlock", side_effect=rendered):
            self.assertEqual(injector._snapshot_clipboard(1, with_sequence=True), ([(TEXT, payload)], 101))
        self.assertFalse(state["open"])

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
