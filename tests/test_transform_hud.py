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

    def setUp(self):
        with patch.object(overlay.FloatingHUD, "_apply_win32_noactivate"):
            self.hud = overlay.FloatingHUD(translation_target="en")

    def tearDown(self):
        self.hud.hide_hud()
        self.hud.deleteLater()
        self.app.processEvents()

    def test_transform_hides_translation_badge_and_animates_volume(self):
        self.hud.set_transform()
        self.assertEqual(self.hud.current_state, "transform")
        self.assertEqual(self.hud.label.text(), "✨ Transformar")
        self.assertTrue(self.hud.lang_badge.isHidden())
        self.assertTrue(self.hud.isVisible())
        self.hud.update_volume(0.1)
        self.assertEqual(self.hud.dot.width(), 18)
        self.assertIn("#a855f7", self.hud.dot.styleSheet())

    def test_transform_processing_label_fits_in_both_themes(self):
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                self.hud.set_theme(theme)
                self.hud.set_transform_processing()
                self.app.processEvents()
                self.assertEqual(self.hud.current_state, "transform_processing")
                self.assertEqual(self.hud.label.text(), "Processando transformação...")
                self.assertTrue(self.hud.lang_badge.isHidden())
                self.assertGreaterEqual(self.hud.label.width(), self.hud.label.sizeHint().width())
                self.hud.update_volume(0.1)
                self.assertEqual(self.hud.dot.width(), 14)

    def test_normal_dictation_restores_badge_and_existing_labels(self):
        self.hud.set_transform()
        self.hud.set_recording()
        self.assertEqual(self.hud.current_state, "recording")
        self.assertEqual(self.hud.label.text(), "Ouvindo...")
        self.assertFalse(self.hud.lang_badge.isHidden())
        self.assertEqual(self.hud.lang_badge.text(), "🌐 EN")
        self.assertEqual(self.hud.width(), 260)
        self.hud.update_volume(0.1)
        self.assertIn("#ef4444", self.hud.dot.styleSheet())
        self.hud.set_processing()
        self.assertEqual(self.hud.label.text(), "Traduzindo...")
        self.hud.set_translation_target("original")
        self.hud.set_processing()
        self.assertEqual(self.hud.label.text(), "Digitando...")
        self.assertTrue(self.hud.lang_badge.isHidden())
        self.assertEqual(self.hud.width(), 220)

    def test_translation_change_during_transform_does_not_reveal_badge(self):
        self.hud.set_transform()
        self.hud.set_translation_target("pt")
        self.assertTrue(self.hud.lang_badge.isHidden())
        self.hud.set_recording()
        self.assertEqual(self.hud.lang_badge.text(), "🌐 PT")
        self.assertFalse(self.hud.lang_badge.isHidden())

    def test_no_selection_notice_expires_after_1500_ms(self):
        self.hud.show_no_selection()
        self.assertEqual(self.hud.label.text(), "Selecione um texto primeiro")
        self.assertTrue(self.hud.lang_badge.isHidden())
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
