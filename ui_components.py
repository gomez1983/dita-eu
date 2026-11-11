"""Small native Qt drawing primitives for the Payno desktop theme."""
import math
from PyQt5 import QtCore, QtGui, QtWidgets, QtSvg


def palette(theme):
    if theme == "light":
        return dict(bg="#eef2f7", card="#ffffff", field="#f4f7fb", text="#1a2333",
                    muted="#64748b", border="#dce4f0", accent="#253858", bright="#2d4365",
                    hover="#e8eef7", button_text="#ffffff")
    return dict(bg="#0d1424", card="#162034", field="#0f172a", text="#f1f5f9",
                muted="#94a3b8", border="#263552", accent="#60a5fa", bright="#3b66a8",
                hover="#1e2d47", button_text="#ffffff")


def stylesheet(theme):
    c = palette(theme)
    if theme == "light":
        status_pill = ("background: #e9f7ef; color: #1b7a46; border: 1px solid #ccebd9; "
                       "border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 600;")
    else:
        status_pill = ("background: #112e28; color: #34d399; border: 1px solid #1f5245; "
                       "border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 600;")
    return f"""
        QWidget {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 13px; }}
        QWidget#SettingsRoot, QWidget#Content {{ background: transparent; }}
        QDialog {{ background: {c['bg']}; }}
        QLabel {{ background: transparent; border: none; }}
        QLabel#TitleLabel {{ font-size: 24px; font-weight: 700; }}
        QLabel#SubtitleLabel, QLabel#HintLabel, QLabel#CardDesc {{
            color: {c['muted']}; font-size: 12px; font-weight: 400;
        }}
        QLabel#SectionTitle {{ font-size: 15px; font-weight: 700; }}
        QLabel#CardTitle {{ font-size: 13px; font-weight: 600; }}
        QLabel#CardBadge {{ color: {c['accent']}; font-weight: 600; }}
        QLabel#StatusPill {{ {status_pill} }}
        QWidget#CardBox {{ background: {c['card']}; border: 1px solid {c['border']};
            border-radius: 20px; }}
        QFrame#HeroCard {{ background: {c['card']}; border: 1px solid {c['border']};
            border-radius: 22px; }}
        QWidget#CardBox QWidget, QFrame#HeroCard QWidget {{ background: transparent; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 7px; margin: 3px 0; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 3px; min-height: 24px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QFrame#Divider, QWidget#CardBox QFrame#Divider {{ background: {c['border']}; border: none; max-height: 1px; }}
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QWidget#CardBox QComboBox,
        QWidget#CardBox QLineEdit, QWidget#CardBox QSpinBox, QWidget#CardBox QPlainTextEdit {{
            background: {c['field']}; border: 1px solid {c['border']};
            border-radius: 11px; padding: 7px 11px; color: {c['text']}; selection-background-color: {c['accent']};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
        QComboBox {{ padding-right: 24px; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow {{ width: 0px; height: 0px; }}
        QComboBox QAbstractItemView {{ background: {c['card']}; color: {c['text']};
            selection-background-color: {c['hover']}; selection-color: {c['accent']};
            border: 1px solid {c['border']}; outline: none; }}
        QPushButton {{ background: {c['bright']}; color: {c['button_text']};
            border: 1px solid {c['accent']}; border-radius: 21px;
            padding: 11px 20px; font-size: 14px; font-weight: 600; }}
        QPushButton:hover {{ background: {c['accent']}; }}
        QPushButton:focus {{ border: 2px solid {c['text']}; }}
        QPushButton#SecondaryBtn {{ background: {c['field']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 11px; padding: 7px 14px;
            font-size: 12px; font-weight: 600; }}
        QPushButton#SecondaryBtn:hover {{ background: {c['hover']}; border-color: {c['accent']}; }}
        QPushButton:disabled {{ color: {c['muted']}; background: {c['border']}; }}
        QSlider::groove:horizontal {{ height: 5px; background: {c['border']}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {c['bright']}; border-radius: 2px; }}
        QSlider::handle:horizontal {{ background: {c['text']}; border: 2px solid {c['bright']};
            width: 13px; height: 13px; margin: -6px 0; border-radius: 8px; }}
        QSlider:focus {{ border: 1px solid {c['accent']}; border-radius: 4px; }}
        QLabel#ComboDisplay {{ background: {c['card']}; border: 1px dashed {c['accent']};
            border-radius: 11px; padding: 14px; font-size: 18px; font-weight: 600; }}
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
    def __init__(self, name, size=24, parent=None, circle=None):
        super().__init__(parent)
        self.name = name
        self.theme = "dark"
        self.icon_size = size
        self.circle = (size <= 30) if circle is None else bool(circle)
        box_size = max(size, 36) if self.circle else size
        self.setFixedSize(box_size, box_size)

    def paintEvent(self, event):
        c = palette(self.theme)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        if self.circle:
            painter.setBrush(QtGui.QColor(c["field"]))
            painter.setPen(QtGui.QPen(QtGui.QColor(c["border"]), 1.0))
            painter.drawEllipse(QtCore.QRectF(1, 1, self.width() - 2, self.height() - 2))
            draw_size = min(18, self.icon_size)
            offset_x = (self.width() - draw_size) / 2.0
            offset_y = (self.height() - draw_size) / 2.0
            target_rect = QtCore.QRectF(offset_x, offset_y, draw_size, draw_size)
        else:
            target_rect = QtCore.QRectF(0, 0, self.width(), self.height())
        color = c["accent"]
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
               f'fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
               f'stroke-linejoin="round">{_PATHS[self.name]}</svg>')
        QtSvg.QSvgRenderer(svg.encode()).render(painter, target_rect)


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
        p.drawRoundedRect(QtCore.QRectF(1, 1, 86, 34), 17, 17)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(c["bright"]))
        p.drawRoundedRect(QtCore.QRectF(44 if self.isChecked() else 3, 4, 41, 28), 14, 14)
        p.setFont(QtGui.QFont("Segoe UI Symbol", 15))
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
        top_color, bottom_color = (("#253858", "#4f70a4") if self.theme == "light"
                                   else ("#60a5fa", "#3b82f6"))
        gradient = QtGui.QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QtGui.QColor(top_color))
        gradient.setColorAt(1, QtGui.QColor(bottom_color))
        p.setBrush(gradient)
        start = (self.width() - (17 * 3 + 16 * 3)) / 2
        for i, height in enumerate(self.bar_heights()):
            p.drawRoundedRect(QtCore.QRectF(start + i * 6, (self.height() - height) / 2,
                                           3, height), 1.5, 1.5)


class ReadyVisual(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = "dark"
        self.setFixedSize(56, 56)
        self.icon = LineIcon("mic", 24, self, circle=False)
        self.icon.move(16, 16)

    def paintEvent(self, event):
        self.icon.theme = self.theme
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = palette(self.theme)
        p.setBrush(QtGui.QColor(c["field"]))
        p.setPen(QtGui.QPen(QtGui.QColor(c["border"]), 1.0))
        p.drawRoundedRect(QtCore.QRectF(2, 2, 52, 52), 16, 16)
        p.setBrush(QtGui.QColor("#10b981"))
        p.setPen(QtGui.QPen(QtGui.QColor(c["card"]), 2.0))
        p.drawEllipse(QtCore.QRectF(42, 1, 12, 12))
