import ctypes
from PyQt5 import QtCore, QtGui, QtWidgets
from ui_components import VoiceBars, palette

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008


class FloatingHUD(QtWidgets.QWidget):
    def __init__(self, bottom_offset=350, theme="dark", translation_target="original"):
        super().__init__()
        self.bottom_offset = bottom_offset
        self.theme = theme
        self.translation_target = (translation_target or "original").lower()
        self.current_state = "idle"
        self.volume_level = 0.0
        self._notice_timer = QtCore.QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._hide_notice)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint |
                            QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(22, 8, 22, 8)
        layout.setSpacing(10)
        self.bars = VoiceBars(self, theme)
        self.label = QtWidgets.QLabel()
        layout.addWidget(self.bars, 0, QtCore.Qt.AlignCenter)
        layout.addWidget(self.label)
        self._apply_win32_noactivate()
        self.set_theme(theme)

    def _apply_win32_noactivate(self):
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                             ex_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)

    def set_translation_target(self, target):
        self.translation_target = (target or "original").lower()
        if self.current_state == "processing":
            self.set_processing()

    def set_theme(self, theme):
        self.theme = theme
        self.bars.theme = theme
        self.bars.update()
        self.label.setStyleSheet(f"color: {palette(theme)['text']}; background: transparent; "
                                 "font-family: 'Segoe UI'; font-size: 13px;")
        self._update_mode_layout()
        self.update()

    def _update_mode_layout(self):
        capturing = self.current_state in ("recording", "transform", "idle")
        self.bars.setVisible(capturing)
        self.label.setVisible(not capturing)
        self.label.ensurePolished()
        self.setFixedSize(160 if capturing else max(160, self.label.sizeHint().width() + 48), 48)
        self.layout().activate()
        if self.isVisible():
            self.reposition()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = palette(self.theme)
        p.setBrush(QtGui.QColor(c["card"]))
        p.setPen(QtGui.QPen(QtGui.QColor(c["border"]), 1))
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1), 24, 24)

    def reposition(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.x() + (area.width() - self.width()) // 2
        y = max(area.top(), min(area.bottom() - self.height() + 1,
                                screen.geometry().bottom() + 1 - self.bottom_offset))
        self.move(x, y)

    def _show_state(self, state, text=""):
        self._notice_timer.stop()
        self.current_state = state
        self.label.setText(text)
        if text:
            self.setAccessibleName(text)
        self.bars.reset()
        self.volume_level = 0.0
        self._update_mode_layout()
        self.reposition()
        self.show()

    def set_recording(self):
        self.setAccessibleName("Ouvindo...")
        self._show_state("recording")

    @QtCore.pyqtSlot()
    def set_transform(self):
        self.setAccessibleName("Transformar texto: ouvindo instrução")
        self._show_state("transform")

    def update_volume(self, volume):
        if self.current_state in ("recording", "transform"):
            self.volume_level = max(0.0, float(volume))
            self.bars.set_level(self.volume_level)

    def set_processing(self):
        text = ("Estilizando..." if self.translation_target == "custom" else
                "Traduzindo..." if self.translation_target not in ("original", "none", "") else
                "Digitando...")
        self._show_state("processing", text)

    @QtCore.pyqtSlot()
    def set_transform_processing(self):
        self._show_state("transform_processing", "Reescrevendo...")

    @QtCore.pyqtSlot()
    def show_no_selection(self):
        self._show_state("no_selection", "Selecione um texto primeiro")
        self._notice_timer.start(1500)

    def _hide_notice(self):
        if self.current_state == "no_selection":
            self.hide_hud()

    def update_preview_text(self, *args, **kwargs):
        pass

    def hide_hud(self):
        self._notice_timer.stop()
        self.current_state = "idle"
        self.volume_level = 0.0
        self.bars.reset()
        self.hide()
