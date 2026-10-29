"""Small native Qt drawing primitives for the amber desktop theme."""
import math
from PyQt5 import QtCore, QtGui, QtWidgets, QtSvg


def palette(theme):
    if theme == "light":
        return dict(bg="#f7f6f4", card="#ffffff", field="#faf9f7", text="#202327",
                    muted="#62666b", border="#dededb", accent="#a83d00", bright="#c74c00",
                    hover="#fff0e4", button_text="#ffffff")
    return dict(bg="#141719", card="#1c2022", field="#191d1f", text="#f5f5f4",
                muted="#b0b4b7", border="#383e41", accent="#ff9b32", bright="#ff851b",
                hover="#30261f", button_text="#16191b")


def stylesheet(theme):
    c = palette(theme)
    return f"""
        QWidget {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 13px; }}
        QWidget#SettingsRoot, QDialog {{ background: {c['bg']}; }}
        QWidget#Content {{ background: {c['bg']}; }}
        QLabel {{ background: transparent; border: none; }}
        QLabel#TitleLabel {{ font-size: 28px; font-weight: 700; }}
        QLabel#SubtitleLabel, QLabel#HintLabel, QLabel#CardDesc {{
            color: {c['muted']}; font-size: 12px; font-weight: 400;
        }}
        QLabel#SectionTitle {{ font-size: 16px; font-weight: 650; }}
        QLabel#CardTitle {{ font-size: 13px; font-weight: 600; }}
        QLabel#CardBadge {{ color: {c['accent']}; font-weight: 600; }}
        QWidget#CardBox {{ background: {c['card']}; border: 1px solid {c['border']};
            border-radius: 12px; }}
        QWidget#CardBox QWidget {{ background: transparent; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: {c['bg']}; width: 7px; margin: 3px 0; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 3px; min-height: 24px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QFrame#Divider, QWidget#CardBox QFrame#Divider {{ background: {c['border']}; border: none; max-height: 1px; }}
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QWidget#CardBox QComboBox,
        QWidget#CardBox QLineEdit, QWidget#CardBox QSpinBox, QWidget#CardBox QPlainTextEdit {{
            background: {c['field']}; border: 1px solid {c['border']};
            border-radius: 8px; padding: 8px 10px; color: {c['text']}; selection-background-color: {c['accent']};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
        QComboBox {{ padding-right: 24px; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow {{ width: 0px; height: 0px; }}
        QComboBox QAbstractItemView {{ background: {c['card']}; color: {c['text']};
            selection-background-color: {c['hover']}; selection-color: {c['accent']};
            border: 1px solid {c['border']}; outline: none; }}
        QPushButton {{ background: {c['bright']}; color: {c['button_text']};
            border: 1px solid {c['bright']}; border-radius: 9px;
            padding: 11px 18px; font-size: 14px; font-weight: 600; }}
        QPushButton:hover {{ background: {c['accent']}; }}
        QPushButton:focus {{ border: 2px solid {c['text']}; }}
        QPushButton#SecondaryBtn {{ background: {c['field']}; color: {c['text']};
            border: 1px solid {c['border']}; padding: 8px 14px; font-size: 12px; }}
        QPushButton#SecondaryBtn:hover {{ background: {c['hover']}; border-color: {c['accent']}; }}
        QPushButton:disabled {{ color: {c['muted']}; background: {c['border']}; }}
        QSlider::groove:horizontal {{ height: 5px; background: {c['border']}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {c['bright']}; border-radius: 2px; }}
        QSlider::handle:horizontal {{ background: {c['text']}; border: 2px solid {c['bright']};
            width: 13px; height: 13px; margin: -6px 0; border-radius: 8px; }}
        QSlider:focus {{ border: 1px solid {c['accent']}; border-radius: 4px; }}
        QLabel#ComboDisplay {{ background: {c['card']}; border: 1px dashed {c['accent']};
            border-radius: 9px; padding: 14px; font-size: 18px; font-weight: 600; }}
        QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; }}
    """


class ComboBox(QtWidgets.QComboBox):
    """A consistent chevron, including when Qt uses a non-native platform style."""
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(self.palette().color(QtGui.QPalette.Text), 1.4,
                            QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        x, y = self.width() - 17, self.height() / 2
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(x - 4, y - 2),
                                       QtCore.QPointF(x, y + 2), QtCore.QPointF(x + 4, y - 2)]))


_PATHS = {
    "mic": '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
    "engine": '<path d="m12 2 2 3 4-1 1 4 3 2-2 3 1 4-4 1-2 3-3-2-4 1-1-4-3-2 2-3-1-4 4-1Z"/><circle cx="12" cy="12" r="3"/>',
    "language": '<path d="M2 5h13M8 2v3M5 5c1 6 4 9 9 11M12 5c-1 5-4 9-10 12M14 22l4-11 4 11M16 18h4"/>',
    "document": '<path d="M14 2H5v20h14V7ZM14 2v6h5M8 12h8M8 16h8"/>',
    "keyboard": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M5 9h1m3 0h1m3 0h1m3 0h1M5 12h1m3 0h1m3 0h1m3 0h1M7 16h10"/>',
    "screen": '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M12 17v4M7 21h10"/>',
    "windows": '<path d="M3 5l8-1v8H3ZM14 3l8-1v10h-8ZM3 14h8v7l-8-1ZM14 14h8v10l-8-2Z"/>',
}


class LineIcon(QtWidgets.QWidget):
    def __init__(self, name, size=24, parent=None):
        super().__init__(parent)
        self.name = name
        self.theme = "dark"
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        color = palette(self.theme)["accent"]
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
               f'fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" '
               f'stroke-linejoin="round">{_PATHS[self.name]}</svg>')
        painter = QtGui.QPainter(self)
        QtSvg.QSvgRenderer(svg.encode()).render(painter)


class ThemeSelector(QtWidgets.QAbstractButton):
    def __init__(self, checked=False, theme="dark"):
        super().__init__()
        self.setCheckable(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setChecked(checked)
        self.theme = theme
        self.setFixedSize(88, 36)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setAccessibleName("Tema escuro")
        self.setToolTip("Alternar entre tema claro e escuro")
        self.toggled.connect(lambda _: self.update())

    def set_theme(self, theme):
        self.theme = theme
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = palette(self.theme)
        p.setPen(QtGui.QPen(QtGui.QColor(c["accent"] if self.hasFocus() else c["border"])))
        p.setBrush(QtGui.QColor(c["field"]))
        p.drawRoundedRect(QtCore.QRectF(1, 1, 86, 34), 11, 11)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(c["bright"]))
        p.drawRoundedRect(QtCore.QRectF(44 if self.isChecked() else 3, 3, 41, 30), 9, 9)
        p.setFont(QtGui.QFont("Segoe UI Symbol", 16))
        for i, symbol in enumerate(("☼", "☾")):
            selected = bool(i) == self.isChecked()
            p.setPen(QtGui.QColor(c["button_text"] if selected else c["muted"]))
            p.drawText(QtCore.QRect(i * 43 + 1, 0, 43, 36), QtCore.Qt.AlignCenter, symbol)


class VoiceBars(QtWidgets.QWidget):
    """Seventeen bars with smoothed RMS amplitude, updated only while visible."""
    def __init__(self, parent=None, theme="dark"):
        super().__init__(parent)
        self.theme = theme
        self.target = self.level = 0.0
        self.phase = 0.0
        self.setFixedSize(112, 30)
        self.setAccessibleName("Nível do microfone")
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)

    def set_level(self, rms):
        # RMS is already calculated by AudioRecorder; never open a second stream.
        self.target = min(1.0, max(0.0, float(rms)) * 12.0)

    def reset(self):
        self.target = self.level = self.phase = 0.0
        self.update()

    def _tick(self):
        speed = 0.55 if self.target > self.level else 0.18
        self.level += (self.target - self.level) * speed
        self.phase += 0.24
        self.update()

    def showEvent(self, event):
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def bar_heights(self):
        return [3.0 + self.level * 23.0 * (0.30 + 0.70 * abs(
            math.sin(i * 0.91 + self.phase) * math.cos(i * 0.37 - self.phase * 0.7)))
                for i in range(17)]

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        gradient = QtGui.QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QtGui.QColor(palette(self.theme)["accent"]))
        gradient.setColorAt(1, QtGui.QColor(palette(self.theme)["bright"]))
        p.setBrush(gradient)
        start = (self.width() - (17 * 3 + 16 * 3)) / 2
        for i, height in enumerate(self.bar_heights()):
            p.drawRoundedRect(QtCore.QRectF(start + i * 6, (self.height() - height) / 2,
                                           3, height), 1.5, 1.5)


class ReadyVisual(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = "dark"
        self.setFixedSize(64, 64)
        self.icon = LineIcon("mic", 27, self)
        self.icon.move(19, 18)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        color = QtGui.QColor(palette(self.theme)["accent"])
        fill = QtGui.QColor(color)
        fill.setAlpha(18)
        p.setBrush(fill)
        p.setPen(QtGui.QPen(color, 1.4))
        p.drawEllipse(QtCore.QRectF(3, 3, 58, 58))
