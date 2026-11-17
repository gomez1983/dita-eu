"""Primitivas de desenho Qt e tokens do tema desktop do Dita-eu.

Os tokens vêm do projeto Stitch "Transcritor de Voz": Obsidian Whisper (tema
Padrão), Fluent Clarity (Claro) e a paleta Dark André que o app já usava.
Sem as fontes embutidas em ``fonts/``, a interface cai no Segoe UI.
"""
import math
import os
import sys

from PyQt5 import QtCore, QtGui, QtWidgets, QtSvg


# --- Tipografia -------------------------------------------------------------

_FONT_CHAINS = {
    "head": ("Plus Jakarta Sans", "Inter", "Segoe UI"),
    "body": ("Inter", "Segoe UI"),
    "mono": ("JetBrains Mono", "Consolas", "Courier New"),
}
_fonts_loaded = False
_family_cache = {}


def _font_dirs():
    dirs = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        dirs.append(os.path.join(bundle, "fonts"))
    dirs.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"))
    return dirs


def load_fonts():
    """Registra as fontes de ``fonts/`` uma única vez; sem elas, usa o Segoe UI."""
    global _fonts_loaded
    if _fonts_loaded or QtGui.QGuiApplication.instance() is None:
        return
    _fonts_loaded = True
    _family_cache.clear()
    for folder in _font_dirs():
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith((".ttf", ".otf")):
                QtGui.QFontDatabase.addApplicationFont(os.path.join(folder, name))
        break


def font_family(role="body"):
    """Primeira família disponível da cadeia do papel: head, body ou mono."""
    load_fonts()
    if role in _family_cache:
        return _family_cache[role]
    chain = _FONT_CHAINS.get(role, _FONT_CHAINS["body"])
    if QtGui.QGuiApplication.instance() is None:
        return chain[-1]
    available = set(QtGui.QFontDatabase().families())
    for family in chain:
        if family in available:
            _family_cache[role] = family
            return family
    _family_cache[role] = chain[-1]
    return chain[-1]


# --- Cores ------------------------------------------------------------------

_PALETTES = {
    # Obsidian Whisper (Stitch): camadas tonais azul-petróleo, primário ciano.
    "dark": dict(
        bg="#0f131c", card="#181c24", card_alt="#1c2028", field="#262a33", field_hi="#31353e",
        text="#dfe2ee", muted="#bdc8d1", border="#232931", field_border="#262a33",
        accent="#8ed5ff", bright="#38bdf8", hover="#2c313b",
        button_text="#001e2c", button_hover="#7bd0ff",
        status_bg="#16303d", status_fg="#8ed5ff", status_border="#21495f",
        track_off="#31353e", thumb_on="#ffffff",
        bar="#0a0e16", tile="#262a33", chip_on_bg="#c5c9ff", chip_on_fg="#131e8c",
    ),
    # Fluent Clarity (Stitch): fundo claro, cards brancos, primário azul.
    "light": dict(
        bg="#f8f9fa", card="#ffffff", card_alt="#f8fafc", field="#f1f5f9", field_hi="#e2e8f0",
        text="#0f172a", muted="#64748b", border="#e2e8f0", field_border="#e2e8f0",
        accent="#2563eb", bright="#2563eb", hover="#e8eef7",
        button_text="#ffffff", button_hover="#1d4ed8",
        status_bg="#e9f7ef", status_fg="#1b7a46", status_border="#ccebd9",
        track_off="#cbd5e1", thumb_on="#ffffff",
        bar="#ffffff", tile="#e8f0fe", chip_on_bg="#2563eb", chip_on_fg="#ffffff",
    ),
    # André Dark Minimal: neutros quentes e verde de status (já existia no app).
    "dark_andre": dict(
        bg="#0F0F0F", card="#1E1E1D", field="#262625", text="#F2F2EF",
        muted="#B4B4AF", border="#2E2E2D", accent="#EFEFEC", bright="#EFEFEC",
        hover="#2C2C2B", button_text="#141414", button_hover="#D6D6D2",
        status_bg="#132613", status_fg="#38BC37", status_border="#244A24",
        track_off="#262625", thumb_on="#141414",
        card_alt="#181817", field_hi="#323231", field_border="#2E2E2D",
        bar="#0B0B0B", tile="#262625", chip_on_bg="#EFEFEC", chip_on_fg="#141414",
    ),
}

_EFFECTS = {
    "dark": dict(glow1=(56, 189, 248, 30), glow2=(99, 102, 241, 46), shadow=(0, 0, 0, 70)),
    "light": dict(glow1=(37, 99, 235, 26), glow2=(2, 132, 199, 22), shadow=(28, 45, 74, 22)),
    "dark_andre": dict(glow1=(255, 255, 255, 14), glow2=(56, 188, 55, 18), shadow=(0, 0, 0, 70)),
}


def palette(theme):
    return dict(_PALETTES.get(theme, _PALETTES["dark"]))


def effects(theme):
    """Brilhos do hero e sombra dos cards como QColor."""
    data = _EFFECTS.get(theme, _EFFECTS["dark"])
    return {name: QtGui.QColor(*rgba) for name, rgba in data.items()}


def css_rgba(color, alpha):
    """'#rrggbb' e alpha 0..1 viram 'rgba(r, g, b, a)' com alpha inteiro (0-255)."""
    q = QtGui.QColor(color)
    return f"rgba({q.red()}, {q.green()}, {q.blue()}, {int(round(alpha * 255))})"


def mix(color_a, color_b, t):
    """Mistura duas cores (t=0 devolve a, t=1 devolve b)."""
    a, b = QtGui.QColor(color_a), QtGui.QColor(color_b)
    return QtGui.QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def stylesheet(theme):
    c = palette(theme)
    body, head, mono = font_family("body"), font_family("head"), font_family("mono")
    selected = css_rgba(c["accent"], 0.16)
    status_pill = (
        f"background: {c['status_bg']}; color: {c['status_fg']}; "
        f"border: 1px solid {c['status_border']}; "
        "border-radius: 10px; padding: 2px 10px; font-size: 11px; font-weight: 600;"
    )
    return f"""
        QWidget {{ color: {c['text']}; font-family: '{body}'; font-size: 13px; }}
        QWidget#SettingsRoot, QWidget#Content {{ background: transparent; }}
        QDialog {{ background: {c['bg']}; }}
        QLabel {{ background: transparent; border: none; }}
        QLabel#TitleLabel {{ font-family: '{head}'; font-size: 18px; font-weight: 700; }}
        QLabel#HeroTitle {{ font-family: '{head}'; font-size: 22px; font-weight: 700; }}
        QLabel#SectionTitle {{ font-family: '{head}'; font-size: 15px; font-weight: 700; }}
        QLabel#CardHeading {{ font-family: '{head}'; font-size: 16px; font-weight: 700; }}
        QLabel#CardTitle {{ font-size: 13px; font-weight: 600; }}
        QLabel#BadgeText {{ font-size: 12px; font-weight: 500; }}
        QLabel#SubtitleLabel, QLabel#HintLabel, QLabel#CardDesc {{
            color: {c['muted']}; font-size: 12px; font-weight: 400;
        }}
        QLabel#FieldLabel {{ color: {c['muted']}; font-size: 11px; font-weight: 600; }}
        QLabel#RangeLabel {{ color: {c['muted']}; font-family: '{mono}'; font-size: 11px; }}
        QLabel#CardBadge {{ color: {c['accent']}; font-weight: 600; }}
        QLabel#MonoBadge {{ background: {c['card']}; color: {c['accent']}; border-radius: 5px;
            padding: 2px 8px; font-family: '{mono}'; font-size: 11px; font-weight: 500; }}
        QLabel#Kbd {{ background: {c['field_hi']}; color: {c['accent']}; border-radius: 6px;
            padding: 3px 9px; font-family: '{mono}'; font-size: 12px; font-weight: 700; }}
        QLabel#StatusPill {{ {status_pill} }}
        QLabel#FooterStatus {{ color: {c['muted']}; font-family: '{mono}'; font-size: 11px; }}
        QLabel#StatusDot {{ background: {c['status_fg']}; border-radius: 4px;
            min-width: 8px; max-width: 8px; min-height: 8px; max-height: 8px; }}
        QWidget#HeaderBar {{ background: {c['bar']}; border-bottom: 1px solid {c['border']}; }}
        QWidget#FooterBar {{ background: {c['bar']}; border-top: 1px solid {c['border']}; }}
        QWidget#CardBox {{ background: {c['card']}; border: 1px solid {c['border']};
            border-radius: 12px; }}
        QWidget#InnerCard {{ background: {c['card_alt']}; border: 1px solid {c['border']};
            border-radius: 10px; }}
        QWidget#SegmentBox {{ background: {c['field']}; border: none; border-radius: 8px; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 3px 0; }}
        QScrollBar::handle:vertical {{ background: {c['field_hi']}; border-radius: 4px; min-height: 28px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QFrame#Divider {{ background: {c['border']}; border: none; max-height: 1px; }}
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
            background: {c['field']}; border: 1px solid {c['field_border']};
            border-radius: 8px; padding: 8px 12px; color: {c['text']};
            selection-background-color: {c['accent']}; selection-color: {c['button_text']};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
        QComboBox {{ padding-right: 28px; }}
        QComboBox::drop-down {{ border: none; width: 26px; }}
        QComboBox::down-arrow {{ width: 0px; height: 0px; }}
        QComboBox QAbstractItemView {{ background: {c['card']}; color: {c['text']};
            selection-background-color: {c['hover']}; selection-color: {c['accent']};
            border: 1px solid {c['border']}; outline: none; padding: 4px; }}
        QLineEdit#KbdInput {{ background: {c['field_hi']}; color: {c['accent']};
            border: 1px solid transparent; border-radius: 6px; padding: 5px 8px;
            font-family: '{mono}'; font-size: 12px; font-weight: 700; }}
        QSpinBox#PositionSpin {{ background: {c['card']}; color: {c['accent']};
            border: 1px solid transparent; border-radius: 6px; padding: 3px 8px;
            font-family: '{mono}'; font-size: 12px; font-weight: 600; }}
        QPlainTextEdit#PromptEdit {{ background: {c['field_hi']}; border: 1px solid transparent;
            font-family: '{mono}'; font-size: 12px; padding: 10px 12px; }}
        QPlainTextEdit#PromptEdit:focus {{ border-color: {c['accent']}; }}
        QPushButton {{ background: {c['bright']}; color: {c['button_text']};
            border: 2px solid transparent; border-radius: 8px;
            padding: 9px 20px; font-size: 13px; font-weight: 700; }}
        QPushButton:hover {{ background: {c['button_hover']}; }}
        QPushButton:focus {{ border-color: {c['text']}; }}
        QPushButton:disabled {{ color: {c['muted']}; background: {c['field_hi']}; }}
        QPushButton#SecondaryBtn {{ background: {c['field']}; color: {c['text']};
            border: 1px solid {c['field_border']}; border-radius: 8px; padding: 6px 14px;
            font-size: 12px; font-weight: 600; }}
        QPushButton#SecondaryBtn:hover {{ background: {c['hover']}; border-color: {c['accent']}; }}
        QPushButton#SecondaryBtn:focus {{ border: 1px solid {c['accent']}; }}
        QPushButton#SecondaryBtn:disabled {{ color: {c['muted']}; background: {c['field']}; }}
        QPushButton#CollapseEdgeBtn {{ background: {c['field']}; color: {c['text']};
            border: 1px solid {c['field_border']}; border-radius: 8px;
            padding: 0px 12px; font-size: 13px; font-weight: 600; }}
        QPushButton#CollapseEdgeBtn:hover {{ background: {c['hover']}; border-color: {c['accent']}; }}
        QPushButton#Chip {{ background: {c['field']}; color: {c['muted']};
            border: 1px solid {c['field_border']}; border-radius: 15px;
            padding: 5px 13px; font-size: 12px; font-weight: 600; }}
        QPushButton#Chip:hover {{ background: {c['hover']}; color: {c['text']}; }}
        QPushButton#Chip:checked {{ background: {c['chip_on_bg']}; color: {c['chip_on_fg']};
            border-color: {c['chip_on_bg']}; }}
        QPushButton#OptionBtn {{ background: {c['field']}; color: {c['muted']};
            border: 1px solid {c['field_border']}; border-radius: 8px;
            padding: 9px 12px; text-align: left; font-size: 12px; font-weight: 600; }}
        QPushButton#OptionBtn:hover {{ background: {c['hover']}; color: {c['text']}; }}
        QPushButton#OptionBtn:checked {{ background: {selected}; color: {c['text']};
            border: 1px solid {c['accent']}; }}
        QPushButton#OptionBtn[free="true"]:checked {{ background: {c['chip_on_bg']};
            color: {c['chip_on_fg']}; border-color: {c['chip_on_bg']}; }}
        QPushButton#SegmentedBtn {{ background: transparent; color: {c['muted']};
            border: 1px solid transparent; border-radius: 6px; padding: 5px 12px;
            font-size: 12px; font-weight: 600; }}
        QPushButton#SegmentedBtn:hover {{ color: {c['text']}; }}
        QPushButton#SegmentedBtn:checked {{ background: {c['field_hi']}; color: {c['accent']};
            font-weight: 700; }}
        QSlider::groove:horizontal {{ height: 6px; background: {c['field_hi']}; border-radius: 3px; }}
        QSlider::sub-page:horizontal {{ background: {c['bright']}; border-radius: 3px; }}
        QSlider::handle:horizontal {{ background: {c['bright']}; border: 3px solid {c['card_alt']};
            width: 14px; height: 14px; margin: -7px 0; border-radius: 10px; }}
        QSlider:focus {{ border: 1px solid {c['accent']}; border-radius: 4px; }}
        QLabel#ComboDisplay {{ background: {c['card_alt']}; border: 1px dashed {c['accent']};
            border-radius: 10px; padding: 14px; font-family: '{mono}'; font-size: 18px; font-weight: 700; }}
        QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; }}
    """


# --- Ícones -------------------------------------------------------------------

_PATHS = {
    "mic": '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
    "engine": '<path d="m12 2 2 3 4-1 1 4 3 2-2 3 1 4-4 1-2 3-3-2-4 1-1-4-3-2 2-3-1-4 4-1Z"/><circle cx="12" cy="12" r="3"/>',
    "language": '<path d="M2 5h13M8 2v3M5 5c1 6 4 9 9 11M12 5c-1 5-4 9-10 12M14 22l4-11 4 11M16 18h4"/>',
    "document": '<path d="M14 2H5v20h14V7ZM14 2v6h5M8 12h8M8 16h8"/>',
    "keyboard": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M5 9h1m3 0h1m3 0h1m3 0h1M5 12h1m3 0h1m3 0h1m3 0h1M7 16h10"/>',
    "screen": '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M12 17v4M7 21h10"/>',
    "windows": '<path d="M3 5l8-1v8H3ZM14 3l8-1v10h-8ZM3 14h8v7l-8-1ZM14 14h8v10l-8-2Z"/>',
    "palette": '<circle cx="12" cy="12" r="9"/><circle cx="9" cy="10" r="1.2"/><circle cx="13" cy="8.5" r="1.2"/><circle cx="15.5" cy="12" r="1.2"/>',
    "dock": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M13 10l2 2-2 2"/>',
    "disk": '<rect x="3" y="14" width="18" height="7" rx="2"/><path d="M5 14 7.5 4h9L19 14M7 17.5h.01M10.5 17.5h.01"/>',
    "check_circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 3 3 5-6"/>',
    "download": '<path d="M12 3v12M7 11l5 5 5-5M5 21h14"/>',
}
_svg_cache = {}


def render_icon(painter, name, rect, color, width=1.7):
    """Desenha um dos ícones de linha em ``rect`` com a cor e a espessura pedidas."""
    key = (name, str(color), width)
    renderer = _svg_cache.get(key)
    if renderer is None:
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
               f'fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
               f'stroke-linejoin="round">{_PATHS[name]}</svg>')
        renderer = QtSvg.QSvgRenderer(svg.encode())
        _svg_cache[key] = renderer
    renderer.render(painter, rect)


# --- Layouts e agrupamentos ----------------------------------------------------

class FlowLayout(QtWidgets.QLayout):
    """Distribui os itens em linhas, quebrando quando falta largura (chips)."""

    def __init__(self, parent=None, hspacing=8, vspacing=8):
        super().__init__(parent)
        self._items = []
        self._hspacing = hspacing
        self._vspacing = vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        # Primeiro agrupa os itens em linhas; depois posiciona, centralizando na linha.
        lines, line, x, line_height = [], [], 0, 0
        for item in self._items:
            hint = item.sizeHint()
            width = min(hint.width(), max(1, area.width()))
            if line and x + width > area.width():
                lines.append((line, line_height))
                line, x, line_height = [], 0, 0
            line.append((item, width, hint.height()))
            x += width + self._hspacing
            line_height = max(line_height, hint.height())
        if line:
            lines.append((line, line_height))
        y = area.y()
        for line, height in lines:
            x = area.x()
            for item, width, item_height in line:
                if not test_only:
                    item.setGeometry(QtCore.QRect(x, y + (height - item_height) // 2, width, item_height))
                x += width + self._hspacing
            y += height + self._vspacing
        used = (y - self._vspacing) if lines else area.y()
        return used - rect.y() + margins.bottom()


class AdaptiveGrid(QtWidgets.QWidget):
    """Grade de botões que ajusta o número de colunas à largura disponível."""

    def __init__(self, parent=None, min_cell=120, max_cols=4, spacing=8):
        super().__init__(parent)
        self._min_cell = min_cell
        self._max_cols = max_cols
        self._spacing = spacing
        self._items = []
        self._cols = 0
        self._grid = QtWidgets.QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)

    def add(self, widget, fill_row=False):
        """``fill_row`` faz o item ocupar o resto da linha (ou a linha toda)."""
        widget.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._items.append((widget, fill_row))
        self._relayout(force=True)

    def columns(self):
        return self._cols

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self, force=False):
        cols = (self.width() + self._spacing) // (self._min_cell + self._spacing)
        cols = max(2, min(self._max_cols, cols))
        if cols == self._cols and not force:
            return
        self._cols = cols
        while self._grid.count():
            self._grid.takeAt(0)
        row = col = 0
        for widget, fill_row in self._items:
            span = (cols - col if col else cols) if fill_row else 1
            self._grid.addWidget(widget, row, col, 1, span)
            col += span
            if col >= cols:
                row += 1
                col = 0
        for index in range(self._max_cols):
            self._grid.setColumnStretch(index, 1 if index < cols else 0)
        self.updateGeometry()


class ChoiceGroup(QtCore.QObject):
    """Mantém botões exclusivos (chips, cartões) em sincronia com um QComboBox.

    O combo continua sendo a fonte da verdade: configuração, bandeja e testes
    seguem usando ``currentData()``; os botões apenas o refletem.
    """

    def __init__(self, combo, parent=None):
        super().__init__(parent)
        self.combo = combo
        self.buttons = {}
        self._labels = {}
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        combo.currentIndexChanged.connect(self.sync)

    def add(self, button, data, mark=None):
        """``mark`` é um sufixo exibido no botão escolhido (ex.: ' ✓')."""
        button.setCheckable(True)
        self._group.addButton(button)
        self.buttons[data] = button
        self._labels[data] = (button.text(), mark)
        button.clicked.connect(lambda _checked=False, value=data: self.choose(value))

    def choose(self, data):
        index = self.combo.findData(data)
        if index >= 0 and index != self.combo.currentIndex():
            self.combo.setCurrentIndex(index)
        else:
            self.sync()

    def sync(self, *_args):
        current = self.combo.currentData()
        for data, button in self.buttons.items():
            base, mark = self._labels[data]
            checked = data == current
            button.setChecked(checked)
            if mark:
                button.setText(base + (mark if checked else ""))


# --- Widgets ------------------------------------------------------------------

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


class LineIcon(QtWidgets.QWidget):
    """Ícone de linha; com ``tile`` (px) é desenhado sobre um quadrado arredondado."""
    _themed = True

    def __init__(self, name, size=20, parent=None, circle=None, tile=0):
        super().__init__(parent)
        self.name = name
        self.theme = "dark"
        self.icon_size = size
        self.tile = int(tile) if tile else (36 if circle else 0)
        box = self.tile or size
        self.setFixedSize(box, box)

    def paintEvent(self, event):
        c = palette(self.theme)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        if self.tile:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(c["tile"]))
            painter.drawRoundedRect(QtCore.QRectF(self.rect()), 9, 9)
            draw = min(20, self.icon_size)
            target = QtCore.QRectF((self.width() - draw) / 2.0, (self.height() - draw) / 2.0, draw, draw)
        else:
            target = QtCore.QRectF(0, 0, self.width(), self.height())
        render_icon(painter, self.name, target, c["accent"], 1.7)


class ThemeSelector(QtWidgets.QAbstractButton):
    _themed = True

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
        p.setPen(QtGui.QPen(QtGui.QColor(c["accent"] if self.hasFocus() else c["field_border"]), 1))
        p.setBrush(QtGui.QColor(c["field"]))
        p.drawRoundedRect(QtCore.QRectF(0.5, 0.5, 87, 35), 10, 10)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(c["bright"]))
        p.drawRoundedRect(QtCore.QRectF(44 if self.isChecked() else 3, 3.5, 41, 29), 8, 8)
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
        if self.theme == "light":
            top_color, bottom_color = ("#60a5fa", "#2563eb")
        elif self.theme == "dark_andre":
            top_color, bottom_color = ("#EFEFEC", "#8E8E89")
        else:
            top_color, bottom_color = ("#8ed5ff", "#38bdf8")
        gradient = QtGui.QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QtGui.QColor(top_color))
        gradient.setColorAt(1, QtGui.QColor(bottom_color))
        p.setBrush(gradient)
        start = (self.width() - (17 * 3 + 16 * 3)) / 2
        for i, height in enumerate(self.bar_heights()):
            p.drawRoundedRect(QtCore.QRectF(start + i * 6, (self.height() - height) / 2,
                                           3, height), 1.5, 1.5)


class ReadyVisual(QtWidgets.QWidget):
    _themed = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = "dark"
        self.setFixedSize(56, 56)
        self.icon = LineIcon("mic", 26, self)
        self.icon.move(15, 15)

    def paintEvent(self, event):
        self.icon.theme = self.theme
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = palette(self.theme)
        p.setBrush(QtGui.QColor(c["tile"]))
        p.setPen(QtCore.Qt.NoPen)
        p.drawRoundedRect(QtCore.QRectF(2, 2, 52, 52), 14, 14)
        p.setBrush(QtGui.QColor(c["bright"] if self.theme != "dark_andre" else c["status_fg"]))
        p.setPen(QtGui.QPen(QtGui.QColor(c["card"]), 2.0))
        p.drawEllipse(QtCore.QRectF(42, 1, 12, 12))


class HeroCard(QtWidgets.QWidget):
    """Card de destaque: fundo do card com dois brilhos suaves nos cantos."""
    _themed = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = "dark"
        self.setObjectName("HeroCard")

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = palette(self.theme)
        fx = effects(self.theme)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        p.fillPath(path, QtGui.QColor(c["card"]))
        p.setClipPath(path)
        for color, cx, cy, radius in (
            (fx["glow1"], rect.right() - 30, rect.top() + 6, rect.width() * 0.42),
            (fx["glow2"], rect.left() + 26, rect.bottom() - 4, rect.width() * 0.38),
        ):
            gradient = QtGui.QRadialGradient(cx, cy, radius)
            gradient.setColorAt(0.0, color)
            faded = QtGui.QColor(color)
            faded.setAlpha(0)
            gradient.setColorAt(1.0, faded)
            p.fillRect(rect, QtGui.QBrush(gradient))
        p.setClipping(False)
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor(c["border"]), 1.0))
        p.drawPath(path)


class OptionCard(QtWidgets.QAbstractButton):
    """Cartão de escolha exclusiva (ex.: modelo offline), pintado nativamente."""
    _themed = True

    def __init__(self, title, size_text="", parent=None):
        super().__init__(parent)
        self.theme = "dark"
        self.title = title
        self.size_text = size_text
        self.status = ""
        self.ready = False
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.setFixedHeight(84)
        self.setAccessibleName(title)

    def set_state(self, status, ready):
        self.status = status
        self.ready = bool(ready)
        self.setAccessibleDescription(status)
        self.update()

    def sizeHint(self):
        return QtCore.QSize(190, 84)

    def minimumSizeHint(self):
        return QtCore.QSize(120, 84)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        c = palette(self.theme)
        checked = self.isChecked()
        width, height = float(self.width()), float(self.height())
        rect = QtCore.QRectF(0.75, 0.75, width - 1.5, height - 1.5)
        fill = mix(c["field"], c["accent"], 0.10) if checked else QtGui.QColor(c["field"])
        border = QtGui.QColor(c["accent"] if checked else c["field_border"])
        p.setBrush(fill)
        p.setPen(QtGui.QPen(border, 1.5 if checked else 1.0))
        p.drawRoundedRect(rect, 10, 10)
        if self.hasFocus():
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(c["text"]), 1.0, QtCore.Qt.DotLine))
            p.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 8, 8)

        pad = 14.0
        title_font = QtGui.QFont(font_family("body"))
        title_font.setPixelSize(13)
        title_font.setWeight(QtGui.QFont.DemiBold)
        p.setFont(title_font)
        p.setPen(QtGui.QColor(c["text"]))
        title = QtGui.QFontMetrics(title_font).elidedText(
            self.title, QtCore.Qt.ElideRight, int(width - 2 * pad))
        p.drawText(QtCore.QRectF(pad, 11, width - 2 * pad, 18),
                   QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, title)

        status_font = QtGui.QFont(font_family("body"))
        status_font.setPixelSize(12)
        p.setFont(status_font)
        p.setPen(QtGui.QColor(c["muted"]))
        p.drawText(QtCore.QRectF(pad, 30, width - 2 * pad, 16),
                   QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, self.status)

        mono_font = QtGui.QFont(font_family("mono"))
        mono_font.setPixelSize(11)
        p.setFont(mono_font)
        p.setPen(QtGui.QColor(c["accent"] if checked else c["muted"]))
        p.drawText(QtCore.QRectF(pad, height - 29, width / 2.0, 16),
                   QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, self.size_text)

        render_icon(p, "check_circle" if self.ready else "download",
                    QtCore.QRectF(width - pad - 18, height - 31, 18, 18),
                    c["accent"] if self.ready else c["muted"], 1.8)
