"""Tokens, tipografia, componentes de escolha e layout responsivo da UI (Qt offscreen)."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5 import QtGui, QtWidgets

import config_manager
import edge_widget
import overlay
import ui_components
from settings_ui import SettingsWindow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES = ("dark", "dark_andre", "light")
HAS_BUNDLED_FONTS = os.path.isfile(os.path.join(ROOT, "fonts", "Inter-Regular.ttf"))


class QtTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf"):
            path = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", name)
            if os.path.exists(path):
                QtGui.QFontDatabase.addApplicationFont(path)


class PaletteTests(unittest.TestCase):
    def test_every_theme_exposes_the_same_valid_tokens(self):
        reference = set(ui_components.palette("dark"))
        for theme in THEMES:
            colors = ui_components.palette(theme)
            self.assertEqual(set(colors), reference, theme)
            for key, value in colors.items():
                self.assertTrue(QtGui.QColor(value).isValid(), f"{theme}.{key}={value}")

    def test_dark_andre_keeps_its_existing_tokens(self):
        colors = ui_components.palette("dark_andre")
        self.assertEqual(colors["bg"], "#0F0F0F")
        self.assertEqual(colors["card"], "#1E1E1D")
        self.assertEqual(colors["text"], "#F2F2EF")
        self.assertEqual(colors["accent"], "#EFEFEC")
        self.assertEqual(colors["status_fg"], "#38BC37")

    def test_default_and_light_follow_the_stitch_design_systems(self):
        dark, light = ui_components.palette("dark"), ui_components.palette("light")
        self.assertEqual((dark["bg"], dark["card"], dark["bright"]), ("#0f131c", "#181c24", "#38bdf8"))
        self.assertEqual((light["bg"], light["card"], light["accent"]), ("#f8f9fa", "#ffffff", "#2563eb"))

    def test_unknown_theme_falls_back_to_dark_and_copies_are_independent(self):
        self.assertEqual(ui_components.palette("nope"), ui_components.palette("dark"))
        ui_components.palette("dark")["bg"] = "#000000"
        self.assertEqual(ui_components.palette("dark")["bg"], "#0f131c")

    def test_css_rgba_uses_integer_alpha_for_style_sheets(self):
        self.assertEqual(ui_components.css_rgba("#38bdf8", 0.16), "rgba(56, 189, 248, 41)")


class FontTests(QtTestCase):
    @unittest.skipUnless(HAS_BUNDLED_FONTS, "fonts/ não está presente")
    def test_bundled_fonts_are_registered_and_used(self):
        self.assertEqual(ui_components.font_family("body"), "Inter")
        self.assertEqual(ui_components.font_family("mono"), "JetBrains Mono")
        self.assertIn(ui_components.font_family("head"), ("Plus Jakarta Sans", "Inter"))
        self.assertIn("font-family: 'Inter'", ui_components.stylesheet("dark"))

    @unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "fonts", "PlusJakartaSans-Bold.ttf")),
                         "Plus Jakarta Sans não está em fonts/")
    def test_plus_jakarta_sans_drives_the_headings_when_bundled(self):
        self.assertEqual(ui_components.font_family("head"), "Plus Jakarta Sans")
        for theme in THEMES:
            self.assertIn("font-family: 'Plus Jakarta Sans'", ui_components.stylesheet(theme))

    def test_font_family_falls_back_to_the_last_entry_of_the_chain(self):
        chains = {"body": ("Nope One", "Nope Two", "Segoe UI")}
        with patch.dict(ui_components._FONT_CHAINS, chains):
            ui_components._family_cache.pop("body", None)
            self.assertEqual(ui_components.font_family("body"), "Segoe UI")
        ui_components._family_cache.pop("body", None)


class ComponentTests(QtTestCase):
    def test_choice_group_mirrors_the_combo_in_both_directions(self):
        combo = QtWidgets.QComboBox()
        options = (("A", "a"), ("B", "b"), ("C", "c"))
        for label, data in options:
            combo.addItem(label, data)
        group = ui_components.ChoiceGroup(combo)
        buttons = {}
        for label, data in options:
            buttons[data] = QtWidgets.QPushButton(label)
            group.add(buttons[data], data, mark=" ✓")
        group.sync()
        self.assertTrue(buttons["a"].isChecked())
        self.assertEqual(buttons["a"].text(), "A ✓")

        buttons["b"].click()
        self.assertEqual(combo.currentData(), "b")
        self.assertTrue(buttons["b"].isChecked())
        self.assertEqual(buttons["a"].text(), "A")

        combo.blockSignals(True)
        combo.setCurrentIndex(2)
        combo.blockSignals(False)
        group.sync()
        self.assertTrue(buttons["c"].isChecked())

        buttons["c"].click()  # escolher de novo não desmarca nem muda o combo
        self.assertTrue(buttons["c"].isChecked())
        self.assertEqual(combo.currentData(), "c")

    def test_flow_layout_wraps_chips_when_the_width_shrinks(self):
        host = QtWidgets.QWidget()
        flow = ui_components.FlowLayout(host, 8, 8)
        for index in range(6):
            chip = QtWidgets.QPushButton(f"Chip {index}")
            chip.setFixedSize(100, 30)
            flow.addWidget(chip)
        self.assertEqual(flow.heightForWidth(700), 30)
        self.assertEqual(flow.heightForWidth(230), 3 * 30 + 2 * 8)

    def test_adaptive_grid_changes_columns_and_stretches_the_last_item(self):
        grid = ui_components.AdaptiveGrid(min_cell=100, max_cols=4, spacing=8)
        buttons = [QtWidgets.QPushButton(str(index)) for index in range(6)]
        for button in buttons:
            grid.add(button)
        free = QtWidgets.QPushButton("livre")
        grid.add(free, fill_row=True)
        grid.show()
        grid.resize(250, 300)
        self.app.processEvents()
        self.assertEqual(grid.columns(), 2)
        self.assertGreaterEqual(free.width(), 240)
        grid.resize(700, 300)
        self.app.processEvents()
        self.assertEqual(grid.columns(), 4)
        self.assertGreater(free.width(), buttons[0].width() * 1.5)
        grid.hide()

    def test_option_card_paints_in_every_theme_and_state(self):
        card = ui_components.OptionCard("Base · rápido", "~145 MB")
        card.resize(200, 84)
        for theme in THEMES:
            card.theme = theme
            for ready in (True, False):
                for checked in (True, False):
                    card.set_state("Instalado" if ready else "Não baixado", ready)
                    card.setChecked(checked)
                    self.assertFalse(card.grab().isNull())


class HalfMoonPaletteTests(unittest.TestCase):
    def test_half_moon_palette_has_a_complete_set_of_colors_per_theme(self):
        for theme in THEMES + ("desconhecido",):
            colors = edge_widget.half_moon_palette(theme, 0.5)
            self.assertEqual(set(colors), {"body", "border", "border_alpha", "ink", "text"})
            for key in ("body", "border", "ink", "text"):
                self.assertEqual(len(colors[key]), 3)
                self.assertTrue(all(0 <= channel <= 255 for channel in colors[key]), (theme, key))

    def test_dark_andre_keeps_the_previous_look_and_hover_follows_the_theme(self):
        self.assertEqual(edge_widget.half_moon_palette("dark_andre", 0.0)["body"], (26, 26, 25))
        self.assertEqual(edge_widget.half_moon_palette("dark_andre", 1.0)["body"], (48, 48, 47))
        body = lambda theme, hover: sum(edge_widget.half_moon_palette(theme, hover)["body"])  # noqa: E731
        self.assertGreater(body("dark", 1.0), body("dark", 0.0))
        self.assertLess(body("light", 1.0), body("light", 0.0))
        self.assertEqual(edge_widget.half_moon_palette("x", 0.0), edge_widget.half_moon_palette("dark", 0.0))


class HudThemeTests(QtTestCase):
    def test_pill_is_painted_with_the_theme_surface(self):
        reds = {}
        for theme in THEMES:
            with patch.object(overlay.FloatingHUD, "_apply_win32_noactivate"):
                hud = overlay.FloatingHUD(theme=theme)
            hud.set_recording()
            self.app.processEvents()
            image = hud.grab().toImage()
            reds[theme] = image.pixelColor(14, 24).red()
            hud.set_processing()
            self.assertFalse(hud.grab().isNull())
            hud.hide_hud()
            hud.deleteLater()
        self.assertGreater(reds["light"], 200)
        self.assertLess(reds["dark"], 40)
        self.assertLess(reds["dark_andre"], 60)


class SettingsLayoutTests(QtTestCase):
    def setUp(self):
        for target in ("settings_ui.config_manager.save_config",
                       "settings_ui.config_manager.set_windows_autostart"):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_window(self, theme="dark", width=740, height=1400, **overrides):
        config = copy.deepcopy(config_manager.DEFAULT_CONFIG)
        config.update({"theme": theme, "engine": "local", "translation_target": "custom",
                       "edge_widget_enabled": True, "trigger_keys": ["ctrl", "shift", "f12"]})
        config.update(overrides)
        with patch("settings_ui.sd.query_devices", return_value=[]):
            window = SettingsWindow(config, is_windows=True)
        window.setMinimumSize(420, 570)  # a meia-lua reduz o mínimo ao expandir
        window.resize(width, height)
        window.show()
        self.app.processEvents()
        self.app.processEvents()
        self.addCleanup(self._dispose, window)
        return window

    def _dispose(self, window):
        window.hide()
        window.deleteLater()
        self.app.processEvents()

    def test_nothing_overflows_horizontally_at_any_width_or_theme(self):
        for theme in THEMES:
            for width in (420, 440, 560, 600, 740, 980, 1280):
                with self.subTest(theme=theme, width=width):
                    window = self.make_window(theme, width)
                    viewport = window.scroll_area.viewport().width()
                    content = window.scroll_area.widget()
                    self.assertLessEqual(content.minimumSizeHint().width(), viewport)
                    self.assertEqual(window.scroll_area.horizontalScrollBar().maximum(), 0)
                    for child in content.findChildren(QtWidgets.QWidget):
                        if child.isVisible():
                            right = child.mapTo(content, child.rect().topRight()).x()
                            self.assertLessEqual(right, viewport + 1, child.objectName() or child)

    def test_two_columns_only_in_wide_windows(self):
        narrow = self.make_window(width=740)
        self.assertTrue(narrow.col_right_w.isHidden())
        for card in narrow._cards:
            self.assertIs(card.parentWidget(), narrow.col_left_w)

        wide = self.make_window(width=1280)
        self.assertFalse(wide.col_right_w.isHidden())
        self.assertIs(wide.engine_card.parentWidget(), wide.col_left_w)
        self.assertIs(wide.mic_card.parentWidget(), wide.col_left_w)
        self.assertIs(wide.trans_card.parentWidget(), wide.col_right_w)
        self.assertIs(wide.input_card.parentWidget(), wide.col_right_w)

        wide.resize(740, 1400)  # voltar a estreito reorganiza de novo
        self.app.processEvents()
        self.assertTrue(wide.col_right_w.isHidden())
        self.assertIs(wide.input_card.parentWidget(), wide.col_left_w)

    def test_compact_mode_below_560_px(self):
        edge = self.make_window(width=440)
        self.assertTrue(edge.footer_status_w.isHidden())
        self.assertEqual(edge.btn_collapse_edge.text(), "«")
        self.assertEqual(edge.model_cards_layout.direction(), edge.model_cards_layout.TopToBottom)
        roomy = self.make_window(width=740)
        self.assertFalse(roomy.footer_status_w.isHidden())
        self.assertIn("Recolher", roomy.btn_collapse_edge.text())
        self.assertEqual(roomy.model_cards_layout.direction(), roomy.model_cards_layout.LeftToRight)

    def test_language_chips_drive_the_translation_combo(self):
        window = self.make_window()
        self.assertTrue(window.trans_group.buttons["custom"].isChecked())
        window.trans_group.buttons["en"].click()
        self.assertEqual(window.trans_combo.currentData(), "en")
        self.assertEqual(window.config["translation_target"], "en")
        self.assertTrue(window.custom_prompt_box.isHidden())
        window.trans_group.buttons["custom"].click()
        self.assertTrue(window.custom_prompt_box.isVisible())
        window.set_translation_target("fr")  # troca feita pelo menu da bandeja
        self.assertTrue(window.trans_group.buttons["fr"].isChecked())
        self.assertFalse(window.trans_group.buttons["custom"].isChecked())

    def test_preset_chips_load_the_prompt_and_mark_the_choice(self):
        window = self.make_window()
        chips = window.preset_group.buttons
        self.assertEqual(len(chips), 9)
        self.assertEqual(window.preset_count_badge.text(), "9 perfis")
        chips["dota"].click()
        self.assertEqual(window.preset_combo.currentData(), "dota")
        self.assertEqual(window.custom_prompt_edit.toPlainText(),
                         config_manager.PRESET_PROMPTS["dota"])
        self.assertTrue(chips["dota"].text().endswith("✓"))
        self.assertFalse(chips["email_prytter"].text().endswith("✓"))
        self.assertNotIn("🎮", chips["dota"].text())

    def test_offline_model_cards_choose_the_model_and_show_install_state(self):
        with patch("settings_ui.local_transcriber.is_available", return_value=True), \
             patch("settings_ui.local_transcriber.is_model_downloaded",
                   side_effect=lambda size: size == "base"):
            window = self.make_window()
            self.assertTrue(window.model_cards["base"].isChecked())
            self.assertEqual(window.model_cards["base"].status, "Instalado")
            self.assertEqual(window.model_cards["small"].status, "Não baixado")
            window.model_cards["small"].click()
            self.assertEqual(window.local_model_combo.currentData(), "small")
            self.assertEqual(window.config["local_model_size"], "small")
            self.assertTrue(window.local_download_btn.isEnabled())
            self.assertEqual(window.local_download_btn.text(), "Baixar modelo")

    def test_hero_badges_and_shortcut_field_follow_the_configured_keys(self):
        window = self.make_window()
        self.assertEqual(window.hero_ptt_kbd.text(), "CTRL + SHIFT + F12")
        self.assertEqual(window.hero_transform_kbd.text(), "SHIFT + F8")
        self.assertEqual(window.transform_kbd.text(), "SHIFT + F8")
        self.assertGreater(window.shortcut_input.minimumWidth(), 96)
        window.config["trigger_keys"] = ["f8"]
        window.shortcut_input.setText("F8")
        window._fit_shortcut_input()
        window._update_shortcut_hint()
        self.assertEqual(window.hero_ptt_kbd.text(), "F8")
        self.assertEqual(window.shortcut_input.minimumWidth(), 96)

    def test_every_theme_applies_and_renders(self):
        window = self.make_window(width=740, height=900)
        for theme in THEMES:
            window._apply_theme(theme)
            self.app.processEvents()
            self.assertEqual(window.current_theme, theme)
            self.assertIn(ui_components.palette(theme)["card"], window.styleSheet())
            self.assertFalse(window.grab().isNull())
            self.assertEqual(window.hero_card.theme, theme)
            self.assertEqual(window.model_cards["base"].theme, theme)
            self.assertEqual(window.autostart_switch.theme, theme)


if __name__ == "__main__":
    unittest.main()
