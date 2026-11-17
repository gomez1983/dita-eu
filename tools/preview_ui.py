"""Render native Qt previews using safe sample settings, without starting dictation.

Run from the repository root: venv\Scripts\python tools/preview_ui.py

Gera em output/ui-preview o painel de configurações nos três temas (janela normal,
janela estreita da meia-lua e janela larga de duas colunas) e a pílula em cada estado.
"""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PyQt5 import QtGui, QtWidgets
import config_manager
from overlay import FloatingHUD
from settings_ui import SettingsWindow

THEMES = ("dark", "dark_andre", "light")
# Alturas generosas para capturar a página inteira, sem rolagem.
SIZES = {"default": (740, 2700), "edge": (440, 3400), "wide": (1280, 1400)}


def main():
    app = QtWidgets.QApplication([])
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if path.exists():
            QtGui.QFontDatabase.addApplicationFont(str(path))
    app.setFont(QtGui.QFont("Segoe UI", 10))
    folder = ROOT / "output" / "ui-preview"
    folder.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        sample = copy.deepcopy(config_manager.DEFAULT_CONFIG)
        # Exibe tudo: card do motor offline, modo livre com prompt e opções da meia-lua.
        sample.update({"theme": theme, "engine": "local", "translation_target": "custom",
                       "edge_widget_enabled": True})
        for label, (width, height) in SIZES.items():
            with patch("settings_ui.sd.query_devices", return_value=[]):
                window = SettingsWindow(copy.deepcopy(sample), is_windows=True)
            window.setMinimumSize(420, 570)  # a meia-lua reduz o mínimo ao expandir
            window.resize(width, height)
            window.show()
            app.processEvents()
            window.grab().save(str(folder / f"settings-{theme}-{label}.png"))
            window.hide()
            window.deleteLater()
            app.processEvents()
        hud = FloatingHUD(theme=theme)
        hud.set_recording()
        hud.update_volume(0.06)
        for _ in range(10):
            hud.bars._tick()
        app.processEvents()
        hud.grab().save(str(folder / f"pill-{theme}.png"))
        hud.set_transform_processing()
        app.processEvents()
        hud.grab().save(str(folder / f"pill-processing-{theme}.png"))
        hud.hide_hud()
    print(f"Previews: {folder}")


if __name__ == "__main__":
    main()
