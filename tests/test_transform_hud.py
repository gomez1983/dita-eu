"""HUD state tests using Qt's offscreen platform; no desktop interaction."""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5 import QtCore, QtTest, QtWidgets

import overlay


class TransformHUDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        # Windows offscreen Qt has no system font database.
        from PyQt5 import QtGui
        for name in ("segoeui.ttf", "segoeuib.ttf"):
            path = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", name)
            if os.path.exists(path):
                QtGui.QFontDatabase.addApplicationFont(path)

    def setUp(self):
        with patch.object(overlay.FloatingHUD, "_apply_win32_noactivate"):
            self.hud = overlay.FloatingHUD(translation_target="en")

    def tearDown(self):
        self.hud.hide_hud()
        self.hud.deleteLater()
        self.app.processEvents()

    def test_capture_is_minimal_and_bars_follow_volume_in_both_modes(self):
        for method in (self.hud.set_recording, self.hud.set_transform):
            method()
            self.app.processEvents()
            self.assertTrue(self.hud.isVisible())
            self.assertTrue(self.hud.label.isHidden())
            self.assertTrue(self.hud.bars.isVisible())
            self.assertEqual(self.hud.width(), 160)
            silence = max(self.hud.bars.bar_heights())
            self.hud.update_volume(0.1)
            for _ in range(10):
                self.hud.bars._tick()
            self.assertGreater(max(self.hud.bars.bar_heights()), silence + 5)
            self.hud.update_volume(0.0)
            for _ in range(60):
                self.hud.bars._tick()
            self.assertLess(max(self.hud.bars.bar_heights()), 3.1)

    def test_processing_messages_fit_in_both_themes(self):
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                self.hud.set_theme(theme)
                self.hud.set_transform_processing()
                self.app.processEvents()
                self.assertEqual(self.hud.current_state, "transform_processing")
                self.assertEqual(self.hud.label.text(), "Reescrevendo...")
                self.assertTrue(self.hud.bars.isHidden())
                self.assertTrue(self.hud.label.isVisible())
                self.assertGreaterEqual(self.hud.label.width(), self.hud.label.sizeHint().width())
                self.hud.update_volume(0.1)
                self.assertEqual(self.hud.volume_level, 0.0)

    def test_translation_keeps_capture_minimal_and_processing_informative(self):
        for target, text in (("en", "Traduzindo..."), ("original", "Digitando..."),
                             ("custom", "Estilizando...")):
            self.hud.set_translation_target(target)
            self.hud.set_recording()
            self.assertTrue(self.hud.label.isHidden())
            self.assertEqual(self.hud.width(), 160)
            self.hud.set_processing()
            self.assertEqual(self.hud.label.text(), text)
            self.assertTrue(self.hud.bars.isHidden())

    def test_theme_and_language_changes_preserve_active_capture(self):
        self.hud.set_transform()
        self.hud.set_translation_target("pt")
        self.hud.set_theme("light")
        self.assertEqual(self.hud.current_state, "transform")
        self.assertTrue(self.hud.label.isHidden())
        self.assertEqual(self.hud.bars.theme, "light")
        self.assertTrue(self.hud.isVisible())

    def test_hidden_hud_stops_animation_and_resets_audio(self):
        self.hud.set_recording()
        self.app.processEvents()
        self.assertTrue(self.hud.bars.timer.isActive())
        self.hud.update_volume(0.1)
        self.hud.hide_hud()
        self.assertFalse(self.hud.bars.timer.isActive())
        self.assertEqual(self.hud.bars.level, 0.0)
        self.assertEqual(self.hud.bars.target, 0.0)

    def test_no_selection_notice_expires_after_1500_ms(self):
        self.hud.show_no_selection()
        self.assertEqual(self.hud.label.text(), "Selecione um texto primeiro")
        self.assertTrue(self.hud.bars.isHidden())
        self.assertEqual(self.hud._notice_timer.interval(), 1500)
        self.assertTrue(self.hud._notice_timer.isSingleShot())
        QtTest.QTest.qWait(1700)
        self.assertEqual(self.hud.current_state, "idle")
        self.assertFalse(self.hud.isVisible())

    def test_old_notice_never_hides_subsequent_work(self):
        for next_state in ("set_recording", "set_transform", "set_processing", "set_transform_processing"):
            with self.subTest(next_state=next_state):
                self.hud.show_no_selection()
                getattr(self.hud, next_state)()
                self.assertFalse(self.hud._notice_timer.isActive())
                self.hud._notice_timer.timeout.emit()
                self.assertTrue(self.hud.isVisible())
                self.assertNotEqual(self.hud.current_state, "idle")

    def test_noactivate_style_and_qt_attribute_are_preserved(self):
        self.assertTrue(self.hud.testAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating))
        fake_windll = MagicMock()
        fake_windll.user32.GetWindowLongW.return_value = 0x100
        with patch.object(overlay.ctypes, "windll", fake_windll, create=True), patch.object(self.hud, "winId", return_value=42):
            self.hud._apply_win32_noactivate()
        fake_windll.user32.SetWindowLongW.assert_called_once_with(
            42, overlay.GWL_EXSTYLE,
            0x100 | overlay.WS_EX_NOACTIVATE | overlay.WS_EX_TOOLWINDOW | overlay.WS_EX_TOPMOST,
        )


if __name__ == "__main__":
    unittest.main()
