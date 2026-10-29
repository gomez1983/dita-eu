"""Render native Qt previews using safe sample settings, without starting dictation.

Run from the repository root: venv\Scripts\python tools/preview_ui.py
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


def main():
    app = QtWidgets.QApplication([])
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if path.exists():
            QtGui.QFontDatabase.addApplicationFont(str(path))
    app.setFont(QtGui.QFont("Segoe UI", 10))
    folder = ROOT / "output" / "ui-preview"
    folder.mkdir(parents=True, exist_ok=True)
    with patch("settings_ui.sd.query_devices", return_value=[]):
        window = SettingsWindow(copy.deepcopy(config_manager.DEFAULT_CONFIG))
    window.resize(740, 850)
    window.show()
    for theme in ("dark", "light"):
        window._apply_theme(theme)
        app.processEvents()
        window.grab().save(str(folder / f"settings-{theme}.png"))
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
    window.hide()
    print(f"Previews: {folder}")


if __name__ == "__main__":
    main()
