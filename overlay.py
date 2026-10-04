import sys
import ctypes
from PyQt5 import QtCore, QtGui, QtWidgets

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

class FloatingHUD(QtWidgets.QWidget):
    def __init__(self, bottom_offset: int = 350, theme: str = "dark", translation_target: str = "original"):
        super().__init__()
        self.bottom_offset = bottom_offset
        self.theme = theme
        self.translation_target = (translation_target or "original").lower()
        self.current_state = "idle"
        self.volume_level = 0.0

        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.WindowStaysOnTopHint |
            QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._setup_ui()
        self._apply_win32_noactivate()
        self.set_translation_target(self.translation_target)
        self.set_theme(self.theme)

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        self.dot = QtWidgets.QLabel()
        self.dot.setFixedSize(14, 14)
        self.dot.setStyleSheet("border-radius: 7px; background-color: #ef4444;")

        self.lang_badge = QtWidgets.QLabel()
        self.lang_badge.setObjectName("LangBadge")
        self.lang_badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lang_badge.hide()

        self.label = QtWidgets.QLabel("Ouvindo...")
        
        layout.addWidget(self.dot)
        layout.addWidget(self.lang_badge)
        layout.addWidget(self.label)
        layout.addStretch()

    def set_translation_target(self, target: str):
        self.translation_target = (target or "original").lower()
        if self.translation_target not in ("original", "none", ""):
            code = self.translation_target.upper()
            self.lang_badge.setText(f"🌐 {code}")
            self.lang_badge.show()
            self.setFixedSize(260, 52)
        else:
            self.lang_badge.hide()
            self.setFixedSize(220, 52)
        self._apply_theme_styles()

    def set_theme(self, theme: str):
        self.theme = theme
        self._apply_theme_styles()
        self.update()

    def _apply_theme_styles(self):
        if self.theme == "light":
            self.label.setStyleSheet(
                "color: #0f172a; font-family: 'Segoe UI', -apple-system, sans-serif; font-size: 14px; font-weight: 700;"
            )
            self.lang_badge.setStyleSheet(
                "background-color: #dbeafe; color: #1e40af; border: 1px solid #93c5fd; "
                "border-radius: 5px; padding: 2px 7px; font-size: 11px; font-weight: 700; "
                "font-family: 'Segoe UI', sans-serif;"
            )
        else:
            self.label.setStyleSheet(
                "color: #f3f4f6; font-family: 'Segoe UI', -apple-system, sans-serif; font-size: 14px; font-weight: 600;"
            )
            self.lang_badge.setStyleSheet(
                "background-color: #27272a; color: #93c5fd; border: 1px solid #3b82f6; "
                "border-radius: 5px; padding: 2px 7px; font-size: 11px; font-weight: 700; "
                "font-family: 'Segoe UI', sans-serif;"
            )

    def _apply_win32_noactivate(self):
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        if self.theme == "light":
            brush = QtGui.QBrush(QtGui.QColor(255, 255, 255, 245))
            pen = QtGui.QPen(QtGui.QColor(203, 213, 225, 220))
        else:
            brush = QtGui.QBrush(QtGui.QColor(18, 18, 20, 240))
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 30))

        painter.setBrush(brush)
        pen.setWidth(1)
        painter.setPen(pen)

        rect = QtCore.QRectF(self.rect())
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 25, 25)

    def reposition(self):
        screen = QtGui.QGuiApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.bottom_offset
        self.move(x, y)

    def set_recording(self):
        self.current_state = "recording"
        self.label.setText("Ouvindo...")
        self.dot.setStyleSheet("border-radius: 7px; background-color: #ef4444;")
        self.reposition()
        self.show()

    def update_volume(self, volume: float):
        if self.current_state == "recording":
            size = int(10 + min(volume * 80, 8))
            radius = size // 2
            self.dot.setFixedSize(size, size)
            self.dot.setStyleSheet(f"border-radius: {radius}px; background-color: #ef4444;")

    def set_processing(self):
        self.current_state = "processing"
        is_translating = self.translation_target not in ("original", "none", "")
        self.label.setText("Traduzindo..." if is_translating else "Digitando...")
        self.dot.setFixedSize(14, 14)
        dot_color = "#2563eb" if self.theme == "light" else "#3b82f6"
        self.dot.setStyleSheet(f"border-radius: 7px; background-color: {dot_color};")
        self.reposition()
        self.show()

    def update_preview_text(self, *args, **kwargs):
        """Método stub defensivo: previne qualquer AttributeError caso sinais legados tentem emitir texto de prévia."""
        pass

    def hide_hud(self):
        self.current_state = "idle"
        self.hide()
