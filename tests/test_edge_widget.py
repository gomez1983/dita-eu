"""Automated tests for left-edge half-moon widget, persistence, blur guards, and Dark André theme."""
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5 import QtGui, QtWidgets

import config_manager
from edge_widget import (
    EdgeWidgetService,
    OPENING_GRACE_SECONDS,
    WindowBounds,
    WorkArea,
    compute_half_moon_rect_physical,
)
from overlay import FloatingHUD
from settings_ui import SettingsWindow
from ui_components import palette


class _MockWindowAdapter:
    def __init__(self):
        self.bounds = WindowBounds(180, 90, 640, 720)
        self.min_size = (600, 570)
        self.maximized = False
        self.on_top = False
        self.visible = False
        self.focused = False
        self.active = False

    def hwnd(self):
        return 12345

    def get_bounds(self):
        return self.bounds

    def set_bounds(self, bounds: WindowBounds):
        self.bounds = bounds

    def get_minimum_size(self):
        return self.min_size

    def set_minimum_size(self, width: int, height: int):
        self.min_size = (width, height)

    def is_maximized(self):
        return self.maximized

    def unmaximize(self):
        self.maximized = False

    def maximize(self):
        self.maximized = True

    def is_always_on_top(self):
        return self.on_top

    def set_always_on_top(self, enabled: bool):
        self.on_top = bool(enabled)

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def focus(self):
        self.focused = True
        self.active = True

    def is_active(self):
        return self.active


class _FakeNativeEdge:
    def __init__(self, work_area=None):
        self.work_area = work_area or WorkArea(0, 0, 1920, 1032)
        self.foreground_owned = False
        self.mouse_state = (False, True)
        self.enabled = False
        self.position = "middle"
        self.theme = "dark"
        self.active = True
        self.main_expanded = False
        self.shutdown_called = False

    def configure(self, enabled, position, theme, active=True, main_expanded=None):
        self.enabled = enabled
        self.position = position
        self.theme = theme
        self.active = active
        if main_expanded is not None:
            self.main_expanded = main_expanded

    def set_main_expanded(self, expanded):
        self.main_expanded = expanded

    def get_work_area(self):
        return self.work_area

    def is_foreground_owned_by_app(self):
        return self.foreground_owned

    def get_mouse_outside_state(self):
        return self.mouse_state

    def shutdown(self):
        self.shutdown_called = True


class EdgeWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf"):
            path = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", name)
            if os.path.exists(path):
                QtGui.QFontDatabase.addApplicationFont(path)

    def test_config_persistence_for_edge_widget_and_dark_andre_theme(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "config.json")
            with patch.object(config_manager, "CONFIG_FILE", cfg_path), \
                 patch.object(config_manager, "ENV_FILE", os.path.join(tmpdir, ".env")), \
                 patch.object(config_manager, "is_windows_autostart_enabled", return_value=False):
                initial = config_manager.load_config()
                self.assertFalse(initial["edge_widget_enabled"])
                self.assertEqual(initial["edge_widget_position"], "middle")
                self.assertEqual(initial["theme"], "dark")

                initial["edge_widget_enabled"] = True
                initial["edge_widget_position"] = "bottom"
                initial["theme"] = "dark_andre"
                config_manager.save_config(initial)

                reloaded = config_manager.load_config()
                self.assertTrue(reloaded["edge_widget_enabled"])
                self.assertEqual(reloaded["edge_widget_position"], "bottom")
                self.assertEqual(reloaded["theme"], "dark_andre")

                with open(cfg_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self.assertTrue(raw["edge_widget_enabled"])
                self.assertEqual(raw["edge_widget_position"], "bottom")
                self.assertEqual(raw["theme"], "dark_andre")

    def test_half_moon_vertical_offset_avoids_sixf_overlap_across_positions(self):
        work = (0, 0, 2560, 1032)
        for scale in (1.0, 1.5):
            win_h = int(round(88.0 * scale))
            margin_y = int(round(28.0 * scale))
            work_h = work[3] - work[1]
            sixf_ranges = {
                "top": (margin_y, margin_y + win_h),
                "middle": ((work_h - win_h) // 2, (work_h - win_h) // 2 + win_h),
                "bottom": (work[3] - win_h - margin_y, work[3] - margin_y),
            }
            for pos, (s_top, s_bottom) in sixf_ranges.items():
                dx, dy, dw, dh = compute_half_moon_rect_physical(work, pos, scale)
                self.assertEqual(dx, 0)
                self.assertGreaterEqual(dy, work[1])
                self.assertLessEqual(dy + dh, work[3])
                # Não pode haver interseção com o retângulo equivalente do SixF
                overlaps = not (dy + dh <= s_top or dy >= s_bottom)
                self.assertFalse(overlaps, f"Overlap at pos={pos}, scale={scale}: dita={(dy, dy+dh)}, sixf={(s_top, s_bottom)}")

    def test_expand_full_height_collapse_and_blur_protections(self):
        now = [100.0]
        win = _MockWindowAdapter()
        win.maximized = True
        native = _FakeNativeEdge(WorkArea(0, 0, 1920, 1032))
        service = EdgeWidgetService(win, native_edge=native, clock=lambda: now[0])
        service.configure(True, "middle", "dark_andre")

        service.open_expanded_from_edge()
        self.assertTrue(service.is_expanded_from_edge)
        self.assertFalse(win.maximized)
        self.assertTrue(win.on_top)
        self.assertTrue(win.visible)
        self.assertTrue(win.focused)
        self.assertEqual(win.bounds, WindowBounds(0, 0, 440, 1032))
        self.assertTrue(native.main_expanded)

        # Proteção 1: dentro da janela de tolerância de 450 ms após abrir, não recolhe
        now[0] = 100.2
        service.handle_window_blur()
        self.assertTrue(win.visible)
        self.assertTrue(service.is_expanded_from_edge)

        # Proteção 2: mesmo após 450 ms, se o foco pertence ao mesmo processo, não recolhe
        now[0] = 100.0 + OPENING_GRACE_SECONDS + 0.1
        native.foreground_owned = True
        service.handle_window_blur()
        self.assertTrue(win.visible)
        self.assertTrue(service.is_expanded_from_edge)

        # Foco foi para fora do processo após tolerância -> recolhe para a borda
        native.foreground_owned = False
        service.handle_window_blur()
        self.assertFalse(win.visible)
        self.assertFalse(service.is_expanded_from_edge)
        self.assertFalse(native.main_expanded)

    def test_outside_click_and_foreground_loss_collapse_even_without_qt_blur(self):
        now = [200.0]
        expanded_events = []
        win = _MockWindowAdapter()
        native = _FakeNativeEdge(WorkArea(0, 0, 1920, 1032))
        service = EdgeWidgetService(
            win,
            native_edge=native,
            clock=lambda: now[0],
            on_expanded_changed=lambda flag: expanded_events.append(flag),
        )
        service.configure(True, "middle", "dark_andre")

        # Abre mesmo quando Windows não transferiu foreground inicial para o app
        native.foreground_owned = False
        service.open_expanded_from_edge()
        self.assertEqual(expanded_events[-1], True)

        # Durante tolerância inicial, clique fora ainda não recolhe
        now[0] = 200.2
        native.mouse_state = (True, False)
        service.check_outside_interaction()
        self.assertTrue(win.visible)

        # Solta o mouse e passa a janela de tolerância
        now[0] = 200.0 + OPENING_GRACE_SECONDS + 0.1
        native.mouse_state = (False, True)
        service.check_outside_interaction()
        self.assertTrue(win.visible)

        # Clicar dentro do próprio app (ou em popup do mesmo PID) mantém aberto
        native.mouse_state = (True, True)
        service.check_outside_interaction()
        self.assertTrue(win.visible)
        native.mouse_state = (False, True)
        service.check_outside_interaction()

        # Clicar em qualquer lugar fora do app recolhe imediatamente
        native.mouse_state = (True, False)
        service.check_outside_interaction()
        self.assertFalse(win.visible)
        self.assertFalse(service.is_expanded_from_edge)
        self.assertEqual(expanded_events[-1], False)

        # Reabre com foreground no app, depois outro app toma foreground (ex: Alt+Tab) -> recolhe
        native.foreground_owned = True
        native.mouse_state = (False, True)
        now[0] = 300.0
        service.open_expanded_from_edge()
        now[0] = 300.6
        service.check_outside_interaction()
        self.assertTrue(win.visible)
        native.foreground_owned = False
        service.check_outside_interaction()
        self.assertFalse(win.visible)
        self.assertFalse(service.is_expanded_from_edge)

    def test_restores_normal_geometry_and_always_on_top_when_disabled(self):
        win = _MockWindowAdapter()
        win.bounds = WindowBounds(220, 65, 700, 820)
        win.min_size = (600, 570)
        win.on_top = False
        win.maximized = False
        native = _FakeNativeEdge(WorkArea(0, 0, 1920, 1040))
        service = EdgeWidgetService(win, native_edge=native)
        service.configure(True, "top", "dark")

        service.open_expanded_from_edge()
        self.assertEqual(win.bounds, WindowBounds(0, 0, 440, 1040))
        self.assertTrue(win.on_top)

        service.configure(False, "top", "dark")
        self.assertFalse(service.is_expanded_from_edge)
        self.assertFalse(win.on_top)
        self.assertEqual(win.min_size, (600, 570))
        self.assertEqual(win.bounds, WindowBounds(220, 65, 700, 820))
        self.assertFalse(native.enabled)

    def test_settings_ui_edge_options_theme_combo_and_collapse_button(self):
        with patch("settings_ui.config_manager.save_config"), \
             patch("settings_ui.config_manager.set_windows_autostart"), \
             patch("settings_ui.sd.query_devices", return_value=[]):
            cfg = copy.deepcopy(config_manager.DEFAULT_CONFIG)
            window = SettingsWindow(cfg, is_windows=True)
            window.show()
            self.app.processEvents()

            emitted = []
            collapse_clicks = []
            window.config_saved.connect(lambda c: emitted.append(c.copy()))
            window.collapse_to_edge_requested.connect(lambda: collapse_clicks.append(True))

            # Padrão: meia-lua desativada, seletor de posição e botão de recolher ocultos
            self.assertIsNotNone(window.edge_widget_switch)
            self.assertFalse(window.edge_widget_switch.isChecked())
            self.assertTrue(window.edge_pos_container.isHidden())
            self.assertTrue(window.btn_collapse_edge.isHidden())

            # Ativar meia-lua -> exibe posição e botão no cabeçalho
            window.edge_widget_switch.click()
            self.app.processEvents()
            self.assertTrue(window.edge_widget_switch.isChecked())
            self.assertFalse(window.edge_pos_container.isHidden())
            self.assertFalse(window.btn_collapse_edge.isHidden())
            self.assertTrue(emitted[-1]["edge_widget_enabled"])
            self.assertEqual(emitted[-1]["edge_widget_position"], "middle")

            # Trocar posição para Inferior
            window.edge_pos_buttons["bottom"].click()
            self.app.processEvents()
            self.assertEqual(emitted[-1]["edge_widget_position"], "bottom")

            # Clicar no botão discreto de recolher no cabeçalho
            window.btn_collapse_edge.click()
            self.assertEqual(len(collapse_clicks), 1)

            # Gavetinha Tema: selecionar Dark André e validar paleta SixF
            idx_andre = window.theme_combo.findData("dark_andre")
            self.assertGreaterEqual(idx_andre, 0)
            window.theme_combo.setCurrentIndex(idx_andre)
            self.app.processEvents()
            self.assertEqual(window.current_theme, "dark_andre")
            self.assertTrue(window.theme_switch.isChecked())
            self.assertEqual(emitted[-1]["theme"], "dark_andre")
            self.assertEqual(palette("dark_andre")["bg"], "#0F0F0F")
            self.assertEqual(palette("dark_andre")["status_fg"], "#38BC37")

            # FloatingHUD aceita o tema dark_andre sem erros
            hud = FloatingHUD(theme="dark_andre")
            hud.set_theme("dark_andre")
            hud.hide_hud()
            hud.deleteLater()

            window.hide()
            window.deleteLater()
            self.app.processEvents()

            # Em plataforma não-Windows, opções da meia-lua não são exibidas
            non_win = SettingsWindow(cfg, is_windows=False)
            self.assertIsNone(non_win.edge_widget_switch)
            self.assertTrue(non_win.btn_collapse_edge.isHidden())
            non_win.deleteLater()
            self.app.processEvents()

    def test_tray_activation_expands_on_edge_when_enabled(self):
        import main as app_main

        fake_edge = MagicMock()
        fake_edge.is_enabled = True
        fake_settings = MagicMock()

        dummy = app_main.DictationApp.__new__(app_main.DictationApp)
        dummy.edge_widget = fake_edge
        dummy.settings_window = fake_settings

        dummy._on_tray_activated(QtWidgets.QSystemTrayIcon.ActivationReason.Trigger)
        fake_edge.open_expanded_from_edge.assert_called_once()
        fake_settings.show.assert_not_called()

        fake_edge.is_enabled = False
        dummy._on_tray_activated(QtWidgets.QSystemTrayIcon.ActivationReason.Trigger)
        fake_settings.show.assert_called_once()


if __name__ == "__main__":
    unittest.main()
