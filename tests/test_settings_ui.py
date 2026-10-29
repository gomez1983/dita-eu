"""Settings regressions without writing credentials, registry or user config."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5 import QtGui, QtWidgets
import config_manager
from settings_ui import SettingsWindow


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf"):
            path = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", name)
            if os.path.exists(path):
                QtGui.QFontDatabase.addApplicationFont(path)

    def setUp(self):
        self.save_patch = patch("settings_ui.config_manager.save_config")
        self.autostart_patch = patch("settings_ui.config_manager.set_windows_autostart")
        self.save = self.save_patch.start()
        self.autostart_patch.start()
        self.addCleanup(self.save_patch.stop)
        self.addCleanup(self.autostart_patch.stop)
        config = copy.deepcopy(config_manager.DEFAULT_CONFIG)
        config["trigger_keys"] = ["ctrl", "f9"]
        with patch("settings_ui.sd.query_devices", return_value=[]):
            self.window = SettingsWindow(config)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()

    def test_theme_switch_saves_and_emits_without_losing_preferences(self):
        emitted = []
        self.window.config_saved.connect(lambda config: emitted.append(config.copy()))
        self.window.theme_switch.click()
        self.assertEqual(self.window.current_theme, "light")
        self.assertEqual(emitted[-1]["theme"], "light")
        self.assertEqual(emitted[-1]["trigger_keys"], ["ctrl", "f9"])
        self.assertIn("CTRL + F9", self.window.ready_hint.text())
        self.save.assert_called()
        self.window.theme_switch.click()
        self.assertEqual(self.window.current_theme, "dark")

    def test_custom_mode_expands_editor_and_retains_prompt(self):
        self.window.custom_mode_button.click()
        self.assertEqual(self.window.trans_combo.currentData(), "custom")
        self.assertTrue(self.window.custom_prompt_box.isVisible())
        self.window.custom_prompt_edit.setPlainText("Reescreva com clareza.")
        self.assertEqual(self.window.config["custom_prompt"], "Reescreva com clareza.")
        self.window.set_translation_target("en")
        self.assertTrue(self.window.custom_prompt_box.isHidden())
        self.assertIn("Desativado", self.window.custom_mode_button.text())
        self.assertEqual(self.window.custom_prompt_edit.toPlainText(), "Reescreva com clareza.")

    def test_position_controls_are_linked_and_saved(self):
        self.window.hud_slider.setValue(150)
        self.assertEqual(self.window.hud_spin.value(), 150)
        self.assertEqual(self.window.config["hud_bottom_offset"], 150)
        self.window.hud_spin.setValue(550)
        self.assertEqual(self.window.hud_slider.value(), 550)

    def test_save_stays_reachable_at_minimum_size_and_expanded_editor(self):
        self.window.resize(600, 570)
        self.window.custom_mode_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.width(), 600)
        self.assertTrue(self.window.btn_save.isVisible())
        self.assertTrue(self.window.rect().contains(self.window.btn_save.geometry()))
        self.assertGreater(self.window.scroll_area.verticalScrollBar().maximum(), 0)
        self.assertEqual(self.window.scroll_area.horizontalScrollBar().maximum(), 0)


if __name__ == "__main__":
    unittest.main()
