import os
import re
import sys
import sounddevice as sd
from PyQt5 import QtCore, QtGui, QtWidgets
from pynput import keyboard

import config_manager
import local_transcriber
from ui_components import (AdaptiveGrid, ChoiceGroup, ComboBox, FlowLayout, HeroCard, LineIcon,
                           OptionCard, ReadyVisual, ThemeSelector, effects, font_family, mix,
                           palette, stylesheet)


class _HeaderLogoBadge(QtWidgets.QWidget):
    """Logotipo do cabeçalho: ladrilho arredondado com barras de áudio."""
    _themed = True

    def __init__(self, theme="dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setFixedSize(38, 38)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        c = palette(self.theme)
        tile = QtGui.QColor(c["bright"])
        tile.setAlpha(46)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(tile)
        painter.drawRoundedRect(QtCore.QRectF(1, 1, 36, 36), 10, 10)
        painter.setBrush(QtGui.QColor(c["accent"]))
        heights = (8, 14, 20, 12, 6)
        start = 19 - (len(heights) * 3 + (len(heights) - 1) * 3) / 2.0
        for i, height in enumerate(heights):
            painter.drawRoundedRect(QtCore.QRectF(start + i * 6, 19 - height / 2.0, 3, height), 1.5, 1.5)


class ToggleSwitch(QtWidgets.QAbstractButton):
    """Toggle switch moderno e minimalista estilo iOS / Windows 11 Settings"""
    _themed = True

    def __init__(self, parent=None, checked=False, theme="dark"):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setChecked(checked)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        self.theme = theme

        self._offset = 1.0 if checked else 0.0
        self._anim = QtCore.QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._start_anim)

    def _get_offset(self):
        return self._offset

    def _set_offset(self, val):
        self._offset = val
        self.update()

    offset = QtCore.pyqtProperty(float, _get_offset, _set_offset)

    def _start_anim(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def set_theme(self, theme):
        self.theme = theme
        self.update()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        c = palette(self.theme)
        # Trilha arredondada: acompanha a animação entre desligado e ligado.
        track_color = mix(c["track_off"], c["bright"], self._offset)
        painter.setBrush(QtGui.QBrush(track_color))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 44, 24, 12, 12)

        # Círculo deslizante (Thumb)
        thumb_diameter = 20
        x = 2 + self._offset * (44 - thumb_diameter - 4)
        y = 2
        thumb_color = c["thumb_on"] if self._offset > 0.5 else "#ffffff"
        painter.setBrush(QtGui.QBrush(QtGui.QColor(thumb_color)))
        if self._offset == 0.0 and self.theme == "light":
            painter.setPen(QtGui.QPen(QtGui.QColor("#94a3b8"), 1))
        else:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(QtCore.QRectF(x, y, thumb_diameter, thumb_diameter))


class KeyRecorderDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, theme="dark"):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle("Detectar Atalho")
        self.setMinimumSize(400, 220)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self._apply_theme()

        self.detected_keys = []
        self._active_keys = set()
        self._combo_history = set()
        self._listener = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.instruction_label = QtWidgets.QLabel("Pressione a tecla ou combinação desejada\n(ex: F8, F6, ou Shift + F4) e clique em Confirmar:")
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setObjectName("DialogInstruction")

        self.combo_display = QtWidgets.QLabel("Aguardando tecla...")
        self.combo_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.combo_display.setObjectName("ComboDisplay")

        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_cancel = QtWidgets.QPushButton("Cancelar")
        self.btn_cancel.setObjectName("SecondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_ok = QtWidgets.QPushButton("Confirmar")
        self.btn_ok.setObjectName("PrimaryBtn")
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)

        layout.addWidget(self.instruction_label)
        layout.addWidget(self.combo_display)
        layout.addLayout(btn_layout)

        self._start_listening()

    def _apply_theme(self):
        self.setStyleSheet(stylesheet(self.theme))

    def _normalize_key(self, key):
        if isinstance(key, keyboard.Key):
            name = key.name.lower()
            if "shift" in name:
                return "shift"
            if "ctrl" in name:
                return "ctrl"
            if "alt" in name:
                return "alt"
            return name
        elif hasattr(key, 'char') and key.char:
            return key.char.lower()
        return str(key).lower().replace("'", "")

    def _start_listening(self):
        def on_press(key):
            k_str = self._normalize_key(key)
            if not self._active_keys:
                self._combo_history = set()
            self._active_keys.add(k_str)
            self._combo_history.add(k_str)

            ordered = []
            for mod in ["ctrl", "shift", "alt"]:
                if mod in self._combo_history:
                    ordered.append(mod)
            for k in sorted(self._combo_history):
                if k not in ordered:
                    ordered.append(k)

            self.detected_keys = ordered
            combo_text = " + ".join([k.upper() for k in ordered])
            QtCore.QMetaObject.invokeMethod(
                self, "_update_display", QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, combo_text)
            )

        def on_release(key):
            k_str = self._normalize_key(key)
            if k_str in self._active_keys:
                self._active_keys.remove(k_str)
            if self.detected_keys:
                QtCore.QMetaObject.invokeMethod(
                    self, "_enable_ok", QtCore.Qt.ConnectionType.QueuedConnection
                )

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    @QtCore.pyqtSlot(str)
    def _update_display(self, text):
        self.combo_display.setText(text)

    @QtCore.pyqtSlot()
    def _enable_ok(self):
        self.btn_ok.setEnabled(True)

    def closeEvent(self, event):
        if self._listener:
            self._listener.stop()
        super().closeEvent(event)


class _ModelDownloadThread(QtCore.QThread):
    """Baixa o modelo offline fora da thread da interface."""
    done = QtCore.pyqtSignal(bool, str)

    def __init__(self, size, parent=None):
        super().__init__(parent)
        self.size = size

    def run(self):
        try:
            local_transcriber.download_model(self.size)
            self.done.emit(local_transcriber.is_model_downloaded(self.size), self.size)
        except Exception as e:
            print(f"[Dita-eu] Falha ao baixar o modelo offline: {type(e).__name__}")
            self.done.emit(False, self.size)


class SettingsWindow(QtWidgets.QWidget):
    config_saved = QtCore.pyqtSignal(dict)
    window_deactivated = QtCore.pyqtSignal()
    window_hidden = QtCore.pyqtSignal()
    collapse_to_edge_requested = QtCore.pyqtSignal()

    # Duas colunas só em janela larga; a meia-lua (420–440 px) usa uma coluna.
    WIDE_BREAKPOINT = 980
    COMPACT_BREAKPOINT = 560
    LANGUAGE_LABELS = {
        "original": "Original", "en": "Inglês", "es": "Espanhol", "fr": "Francês",
        "de": "Alemão", "it": "Italiano", "custom": "✦ Modo livre",
    }

    def __init__(self, config, icon_path=None, icon_white_path=None, icon_dark_path=None, is_windows=None):
        super().__init__()
        self.config = config.copy()
        self.icon_white_path = icon_white_path or icon_path
        self.icon_dark_path = icon_dark_path or icon_path
        self._is_windows_platform = (sys.platform == "win32") if is_windows is None else bool(is_windows)
        self.current_theme = config_manager.normalize_theme(self.config.get("theme", "dark"))
        self._card_shadows = []
        self._wide_layout = False
        self._compact_layout = False
        self._ui_ready = False

        self.setWindowTitle("Dita-eu — Configurações")
        self.setObjectName("SettingsRoot")
        self.setMinimumSize(600, 570)
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.resize(min(740, area.width()), min(850, area.height() - 40))

        self._setup_ui()
        self._apply_theme(self.current_theme)
        self._ui_ready = True
        self._apply_responsive(force=True)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(palette(self.current_theme)["bg"]))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._ui_ready:
            self._apply_responsive()

    def _update_logo(self):
        icon_file = self.icon_dark_path if self.current_theme == "light" else self.icon_white_path
        if icon_file and os.path.exists(icon_file):
            pix = QtGui.QPixmap(icon_file).scaled(
                34, 34,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            self.logo_label.setPixmap(pix)
            self.setWindowIcon(QtGui.QIcon(icon_file))

    def _apply_theme(self, theme):
        theme = config_manager.normalize_theme(theme)
        self.current_theme = theme
        self._update_logo()
        self.theme_switch.blockSignals(True)
        self.theme_switch.setChecked(theme in ("dark", "dark_andre"))
        self.theme_switch.blockSignals(False)
        if hasattr(self, "theme_combo"):
            self.theme_combo.blockSignals(True)
            idx = self.theme_combo.findData(theme)
            if idx >= 0:
                self.theme_combo.setCurrentIndex(idx)
            self.theme_combo.blockSignals(False)
        self.setStyleSheet(stylesheet(theme))
        for widget in self.findChildren(QtWidgets.QWidget):
            if getattr(widget, "_themed", False):
                widget.theme = theme
                widget.update()
        shadow_color = effects(theme)["shadow"]
        for shadow in self._card_shadows:
            shadow.setColor(shadow_color)
        self.update()

    # --- Blocos reutilizáveis ----------------------------------------------

    @staticmethod
    def _text(text, name="CardTitle", wrap=True):
        label = QtWidgets.QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(wrap)
        return label

    def _field_label(self, text):
        return self._text(text.upper(), "FieldLabel", wrap=False)

    def _kbd(self, text):
        label = QtWidgets.QLabel(text)
        label.setObjectName("Kbd")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        return label

    def _add_shadow(self, card):
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        shadow = QtWidgets.QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 5)
        shadow.setColor(effects(self.current_theme)["shadow"])
        card.setGraphicsEffect(shadow)
        self._card_shadows.append(shadow)

    def _make_card(self, title, subtitle, icon):
        """Card com cabeçalho (ícone, título, descrição) e um layout para o corpo."""
        card = QtWidgets.QWidget()
        card.setObjectName("CardBox")
        self._add_shadow(card)
        outer = QtWidgets.QVBoxLayout(card)
        outer.setContentsMargins(20, 18, 20, 20)
        outer.setSpacing(14)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(LineIcon(icon, 20, tile=36), 0, QtCore.Qt.AlignTop)
        texts = QtWidgets.QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self._text(title, "CardHeading"))
        texts.addWidget(self._text(subtitle, "CardDesc"))
        head.addLayout(texts, 1)
        outer.addLayout(head)
        body = QtWidgets.QVBoxLayout()
        body.setSpacing(12)
        outer.addLayout(body)
        return card, body

    def _inner_card(self, margins=(14, 12, 14, 12), spacing=10):
        box = QtWidgets.QWidget()
        box.setObjectName("InnerCard")
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        return box, layout

    def _setting_row(self, icon, title, hint, control, extra=None):
        """Linha de configuração: ícone, título, descrição e controle à direita."""
        box, layout = self._inner_card()
        top = QtWidgets.QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(LineIcon(icon, 20), 0, QtCore.Qt.AlignTop)
        texts = QtWidgets.QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self._text(title, "CardTitle"))
        if hint:
            texts.addWidget(self._text(hint, "HintLabel"))
        top.addLayout(texts, 1)
        top.addWidget(control, 0, QtCore.Qt.AlignVCenter)
        layout.addLayout(top)
        if extra is not None:
            layout.addWidget(extra)
        return box

    def _hotkey_badge(self, label, description, kbd):
        box, layout = self._inner_card((14, 10, 14, 10))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)
        texts = QtWidgets.QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(self._text(label, "HintLabel", wrap=False))
        texts.addWidget(self._text(description, "BadgeText", wrap=False))
        row.addLayout(texts, 1)
        row.addWidget(kbd, 0, QtCore.Qt.AlignVCenter)
        layout.addLayout(row)
        return box

    # --- Montagem da interface ---------------------------------------------

    def _setup_ui(self):
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_header())

        scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area = scroll_area
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll_area.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        content_widget = QtWidgets.QWidget()
        content_widget.setObjectName("Content")
        content_widget.setMaximumWidth(1240)
        main_layout = QtWidgets.QVBoxLayout(content_widget)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        main_layout.addWidget(self._build_hero())

        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(16)
        self.col_left_w = QtWidgets.QWidget()
        self.col_left = QtWidgets.QVBoxLayout(self.col_left_w)
        self.col_right_w = QtWidgets.QWidget()
        self.col_right = QtWidgets.QVBoxLayout(self.col_right_w)
        for layout in (self.col_left, self.col_right):
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(16)
        columns.addWidget(self.col_left_w, 1, QtCore.Qt.AlignTop)
        columns.addWidget(self.col_right_w, 1, QtCore.Qt.AlignTop)
        main_layout.addLayout(columns)
        main_layout.addStretch()

        self.engine_card = self._build_engine_card()
        self.mic_card = self._build_mic_card()
        self.trans_card = self._build_translation_card()
        self.input_card = self._build_input_card()
        self._cards = [self.engine_card, self.mic_card, self.trans_card, self.input_card]

        scroll_area.setWidget(content_widget)
        root_layout.addWidget(scroll_area, 1)
        # A ação de salvar fica sempre alcançável, mesmo com o editor expandido.
        root_layout.addWidget(self._build_footer())

        self._connect_signals()
        self._arrange_columns()
        self._arrange_hero()

    def _build_header(self):
        self.header_bar = QtWidgets.QWidget()
        self.header_bar.setObjectName("HeaderBar")
        self.header_bar.setFixedHeight(64)
        header = QtWidgets.QHBoxLayout(self.header_bar)
        header.setContentsMargins(24, 0, 24, 0)
        header.setSpacing(12)
        self.logo_label = QtWidgets.QLabel(self.header_bar)
        self.logo_label.hide()
        self.header_badge = _HeaderLogoBadge(self.current_theme, self.header_bar)
        header.addWidget(self.header_badge)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(1)
        for label in (self._text("Dita-eu", "TitleLabel", wrap=False),
                      self._text("Sua voz, direto ao texto.", "SubtitleLabel", wrap=False)):
            label.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
            titles.addWidget(label)
        header.addLayout(titles)
        header.setAlignment(titles, QtCore.Qt.AlignVCenter)
        header.addStretch(1)
        self.btn_collapse_edge = QtWidgets.QPushButton("«")
        self.btn_collapse_edge.setObjectName("CollapseEdgeBtn")
        self.btn_collapse_edge.setFixedHeight(36)
        self.btn_collapse_edge.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_collapse_edge.setToolTip("Recolher para a borda")
        self.btn_collapse_edge.setAccessibleName("Recolher para a borda")
        self.btn_collapse_edge.clicked.connect(self.collapse_to_edge_requested.emit)
        self.btn_collapse_edge.setVisible(
            self._is_windows_platform and bool(self.config.get("edge_widget_enabled", False))
        )
        header.addWidget(self.btn_collapse_edge)
        self.theme_switch = ThemeSelector(self.current_theme in ("dark", "dark_andre"), self.current_theme)
        self.theme_switch.toggled.connect(self._on_theme_switch_toggled)
        header.addWidget(self.theme_switch)
        return self.header_bar

    def _build_hero(self):
        self.hero_card = HeroCard()
        self.hero_grid = QtWidgets.QGridLayout(self.hero_card)
        self.hero_grid.setContentsMargins(20, 20, 20, 20)
        self.hero_grid.setHorizontalSpacing(16)
        self.hero_grid.setVerticalSpacing(14)
        self.ready_visual = ReadyVisual()

        self.hero_text_w = QtWidgets.QWidget()
        text = QtWidgets.QVBoxLayout(self.hero_text_w)
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(6)
        # O selo "Ativo" desce para a linha de baixo quando a janela é muito estreita.
        title_row = FlowLayout(hspacing=10, vspacing=4)
        title_row.addWidget(self._text("Pronto para ouvir", "HeroTitle", wrap=False))
        self.status_pill = QtWidgets.QLabel("● Ativo")
        self.status_pill.setObjectName("StatusPill")
        title_row.addWidget(self.status_pill)
        text.addLayout(title_row)
        self.ready_hint = self._text("", "HintLabel")
        text.addWidget(self.ready_hint)

        self.hero_badges_w = QtWidgets.QWidget()
        badges = QtWidgets.QVBoxLayout(self.hero_badges_w)
        badges.setContentsMargins(0, 0, 0, 0)
        badges.setSpacing(8)
        self.hero_ptt_kbd = self._kbd("F8")
        self.hero_transform_kbd = self._kbd("SHIFT + F8")
        badges.addWidget(self._hotkey_badge("Push-to-Talk", "Segurar para ditar", self.hero_ptt_kbd))
        badges.addWidget(self._hotkey_badge("Voice Transform", "Selecionar texto + comando",
                                            self.hero_transform_kbd))
        self._update_shortcut_hint()
        return self.hero_card

    def _build_engine_card(self):
        card, body = self._make_card("Configurações do motor", "Reconhecimento de voz", "engine")
        body.addWidget(self._field_label("Motor de transcrição"))
        self.engine_combo = ComboBox()
        self.engine_combo.addItem("Groq Whisper", "groq")
        self.engine_combo.addItem("Google Gemini", "gemini")
        self.engine_combo.addItem("Local · offline", "local")
        self.engine_combo.setCurrentIndex(max(0, self.engine_combo.findData(self.config.get("engine", "groq"))))
        body.addWidget(self.engine_combo)
        body.addWidget(self._build_local_card())
        return card

    def _build_local_card(self):
        """Modelo offline: só aparece com o motor local e é baixado sob demanda."""
        self.local_card, layout = self._inner_card((16, 14, 16, 16), 12)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(LineIcon("disk", 20))
        head.addWidget(self._text("Modelo offline", "CardTitle", wrap=False))
        head.addStretch()
        layout.addLayout(head)
        layout.addWidget(self._text("Processado neste computador, sem internet e sem cota de API", "HintLabel"))

        # O combo oculto segue como fonte da verdade; os cartões apenas o refletem.
        self.local_model_combo = ComboBox(self)
        self.local_model_combo.hide()
        self.model_cards = {}
        self.model_cards_layout = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight)
        self.model_cards_layout.setSpacing(10)
        self.model_group = ChoiceGroup(self.local_model_combo, self)
        for size, mb in local_transcriber.MODEL_SIZES.items():
            label = "Base · rápido" if size == "base" else "Small · mais preciso"
            self.local_model_combo.addItem(f"{label} (~{mb} MB)", size)
            card = OptionCard(label, f"~{mb} MB")
            self.model_cards[size] = card
            self.model_group.add(card, size)
            self.model_cards_layout.addWidget(card, 1)
        self.local_model_combo.setCurrentIndex(
            max(0, self.local_model_combo.findData(self.config.get("local_model_size", local_transcriber.DEFAULT_MODEL_SIZE))))
        self.model_group.sync()
        layout.addLayout(self.model_cards_layout)

        action = QtWidgets.QHBoxLayout()
        self.local_download_btn = QtWidgets.QPushButton()
        self.local_download_btn.setObjectName("SecondaryBtn")
        self.local_download_btn.clicked.connect(self._download_local_model)
        action.addWidget(self.local_download_btn)
        action.addStretch()
        layout.addLayout(action)
        self.local_status = self._text("", "HintLabel")
        layout.addWidget(self.local_status)
        self._download_thread = None
        self._refresh_local_ui()
        return self.local_card

    def _build_mic_card(self):
        card, body = self._make_card("Microfone de entrada", "Dispositivo de captura do ditado", "mic")
        body.addWidget(self._field_label("Dispositivo de captura"))
        self.mic_combo = ComboBox()
        self.mic_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.mic_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.mic_combo.setMinimumContentsLength(10)
        self._populate_microphones()
        body.addWidget(self.mic_combo)
        return card

    def _build_translation_card(self):
        card, body = self._make_card("Tradução e modo livre", "Idioma do texto de saída e estilos de escrita",
                                     "language")
        body.addWidget(self._field_label("Destino de linguagem"))
        # O combo oculto segue como fonte da verdade (configuração, bandeja, testes).
        self.trans_combo = ComboBox(self)
        self.trans_combo.hide()
        for label, value in [("Original · sem tradução", "original"), ("Inglês", "en"),
                             ("Espanhol", "es"), ("Francês", "fr"), ("Alemão", "de"),
                             ("Italiano", "it"), ("Modo livre", "custom")]:
            self.trans_combo.addItem(label, value)
        current_trans = self.config.get("translation_target", "original")
        self.trans_combo.setCurrentIndex(max(0, self.trans_combo.findData(current_trans)))

        self.trans_group = ChoiceGroup(self.trans_combo, self)
        self.lang_grid = AdaptiveGrid(min_cell=118, max_cols=4)
        for index in range(self.trans_combo.count()):
            value = self.trans_combo.itemData(index)
            full_name = self.trans_combo.itemText(index)
            button = QtWidgets.QPushButton(self.LANGUAGE_LABELS.get(value, full_name))
            button.setObjectName("OptionBtn")
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            button.setToolTip(full_name)
            button.setAccessibleName(full_name)
            if value == "custom":
                button.setProperty("free", True)
            self.trans_group.add(button, value)
            self.lang_grid.add(button, fill_row=(value == "custom"))
        self.trans_group.sync()
        body.addWidget(self.lang_grid)

        # Atalho de compatibilidade: alterna o modo livre como o botão antigo.
        self.custom_mode_button = QtWidgets.QPushButton(self)
        self.custom_mode_button.setObjectName("SecondaryBtn")
        self.custom_mode_button.clicked.connect(self._toggle_custom_mode)
        self.custom_mode_button.hide()

        body.addWidget(self._build_custom_prompt_box(current_trans))
        self._update_custom_mode_button()
        return card

    def _build_custom_prompt_box(self, current_trans):
        self.custom_prompt_box, layout = self._inner_card((16, 14, 16, 16), 12)

        head = QtWidgets.QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(self._text("Presets de personalidade", "CardTitle", wrap=False))
        head.addStretch()
        self.preset_count_badge = QtWidgets.QLabel("")
        self.preset_count_badge.setObjectName("MonoBadge")
        head.addWidget(self.preset_count_badge)
        layout.addLayout(head)

        self.preset_combo = ComboBox(self)
        self.preset_combo.hide()
        self.preset_combo.addItem("✉️ Email Prytter", "email_prytter")
        self.preset_combo.addItem("🎮 Jogador de Dota 2 estressado", "dota")
        self.preset_combo.addItem("🏴‍☠️ Linguagem Pirata", "pirata")
        self.preset_combo.addItem("💅 Adolescente empolgada (Bestie)", "adolescente")
        self.preset_combo.addItem("💼 Corporativo Formal", "corporativo")
        self.preset_combo.addItem("🧘 Coach Quântico", "coach_quantico")
        self.preset_combo.addItem("🥩 Tiozão do Churrasco", "tiozao_churrasco")
        self.preset_combo.addItem("🎬 Trailer de Cinema Anos 90", "trailer_cinema")
        self.preset_combo.addItem("✍️ Prompt Livre / Customizado", "livre")
        self.preset_count_badge.setText(f"{self.preset_combo.count()} perfis")

        saved_preset = self.config.get("custom_preset", "email_prytter")
        for i in range(self.preset_combo.count()):
            if self.preset_combo.itemData(i) == saved_preset:
                self.preset_combo.setCurrentIndex(i)
                break

        self.preset_group = ChoiceGroup(self.preset_combo, self)
        chips = QtWidgets.QWidget()
        flow = FlowLayout(chips, 8, 8)
        for index in range(self.preset_combo.count()):
            # Os chips não repetem o emoji do combo; o nome já identifica a personalidade.
            name = re.sub(r"^[^\w]+", "", self.preset_combo.itemText(index))
            chip = QtWidgets.QPushButton(name)
            chip.setObjectName("Chip")
            chip.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            chip.setAccessibleName(name)
            self.preset_group.add(chip, self.preset_combo.itemData(index), mark="  ✓")
            flow.addWidget(chip)
        self.preset_group.sync()
        layout.addWidget(chips)

        layout.addWidget(self._field_label("Instrução do modo livre"))
        self.custom_prompt_edit = QtWidgets.QPlainTextEdit()
        self.custom_prompt_edit.setObjectName("PromptEdit")
        self.custom_prompt_edit.setPlaceholderText("Escreva a instrução de como o texto ditado deve ser reescrito...")
        self.custom_prompt_edit.setFixedHeight(112)
        self.custom_prompt_edit.setPlainText(config_manager.get_preset_prompt(self.config, saved_preset))
        layout.addWidget(self.custom_prompt_edit)

        # Botões de Ação do Prompt: Salvar Edição e Restaurar Padrão de Fábrica
        prompt_actions_layout = QtWidgets.QHBoxLayout()
        prompt_actions_layout.setSpacing(8)
        self.btn_reset_prompt = QtWidgets.QPushButton("Restaurar Padrão")
        self.btn_reset_prompt.setObjectName("SecondaryBtn")
        self.btn_reset_prompt.clicked.connect(self._reset_prompt_clicked)
        self.btn_save_prompt = QtWidgets.QPushButton("Salvar Prompt")
        self.btn_save_prompt.setObjectName("SecondaryBtn")
        self.btn_save_prompt.clicked.connect(self._save_prompt_clicked)
        prompt_actions_layout.addStretch()
        prompt_actions_layout.addWidget(self.btn_reset_prompt)
        prompt_actions_layout.addWidget(self.btn_save_prompt)
        layout.addLayout(prompt_actions_layout)

        layout.addWidget(self._text(
            "Escolha uma personalidade pronta ou edite a instrução livremente. "
            "O texto ditado no F8 será adaptado conforme esse comando.", "HintLabel"))
        self.custom_prompt_box.setVisible(current_trans == "custom")
        return self.custom_prompt_box

    def _build_input_card(self):
        card, body = self._make_card("Entrada e atalhos", "Atalhos globais, pílula e integração com o Windows",
                                     "keyboard")

        # Atalho de ditado (editável) e Voice Transform (somente leitura).
        dictate, dictate_layout = self._inner_card()
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)
        texts = QtWidgets.QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self._text("Atalho de ditado", "CardTitle"))
        texts.addWidget(self._text("Segure e fale", "HintLabel"))
        row.addLayout(texts, 1)
        current_combo = " + ".join(k.upper() for k in self.config.get("trigger_keys", ["f8"]))
        self.shortcut_input = QtWidgets.QLineEdit(current_combo)
        self.shortcut_input.setObjectName("KbdInput")
        self.shortcut_input.setReadOnly(True)
        self.shortcut_input.setAlignment(QtCore.Qt.AlignCenter)
        self._fit_shortcut_input()
        self.btn_record_key = QtWidgets.QPushButton("Alterar")
        self.btn_record_key.setObjectName("SecondaryBtn")
        self.btn_record_key.clicked.connect(self._record_key)
        row.addWidget(self.shortcut_input)
        row.addWidget(self.btn_record_key)
        dictate_layout.addLayout(row)
        body.addWidget(dictate)

        self.transform_kbd = self._kbd("SHIFT + F8")
        body.addWidget(self._hotkey_badge("Voice Transform", "Reescrever seleção", self.transform_kbd))
        self._update_shortcut_hint()

        # Posição da pílula: valor em px e controle deslizante.
        position, position_layout = self._inner_card((14, 12, 14, 14), 10)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(10)
        head_texts = QtWidgets.QVBoxLayout()
        head_texts.setSpacing(2)
        head_texts.addWidget(self._text("Posição da pílula", "CardTitle"))
        head_texts.addWidget(self._text("Distância vertical em relação à base da tela", "HintLabel"))
        head.addLayout(head_texts, 1)
        self.hud_spin = QtWidgets.QSpinBox()
        self.hud_spin.setObjectName("PositionSpin")
        self.hud_spin.setRange(50, 1000)
        self.hud_spin.setValue(self.config.get("hud_bottom_offset", 350))
        self.hud_spin.setSuffix(" px")
        self.hud_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.hud_spin.setAlignment(QtCore.Qt.AlignCenter)
        self.hud_spin.setFixedWidth(92)
        head.addWidget(self.hud_spin, 0, QtCore.Qt.AlignTop)
        position_layout.addLayout(head)
        self.hud_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.hud_slider.setTracking(False)
        self.hud_slider.setRange(50, 1000)
        self.hud_slider.setValue(self.hud_spin.value())
        self.hud_slider.setMinimumWidth(75)
        self.hud_slider.setAccessibleName("Distância da pílula à base da tela")
        self.hud_slider.valueChanged.connect(self.hud_spin.setValue)
        self.hud_spin.valueChanged.connect(self.hud_slider.setValue)
        slider_row = QtWidgets.QHBoxLayout()
        slider_row.setSpacing(10)
        slider_row.addWidget(self._text("50 px", "RangeLabel", wrap=False))
        slider_row.addWidget(self.hud_slider, 1)
        slider_row.addWidget(self._text("1000 px", "RangeLabel", wrap=False))
        position_layout.addLayout(slider_row)
        body.addWidget(position)

        self.autostart_switch = ToggleSwitch(self, self.config.get("autostart", False), self.current_theme)
        self.autostart_switch.setAccessibleName("Iniciar com o Windows")
        body.addWidget(self._setting_row("windows", "Iniciar com o Windows",
                                         "Executar em segundo plano ao ligar", self.autostart_switch))

        self.edge_widget_switch = None
        self.edge_pos_container = None
        self.edge_pos_group = None
        self.edge_pos_buttons = {}
        if self._is_windows_platform:
            edge_enabled = bool(self.config.get("edge_widget_enabled", False))
            edge_pos = config_manager.normalize_edge_position(
                self.config.get("edge_widget_position", "middle")
            )
            self.edge_widget_switch = ToggleSwitch(self, edge_enabled, self.current_theme)
            self.edge_widget_switch.setAccessibleName("Meia-lua na borda")

            # Rótulo e segmentos ficam lado a lado em janela larga e empilhados em janela estreita.
            self.edge_pos_container = QtWidgets.QWidget()
            self.edge_pos_layout = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight,
                                                        self.edge_pos_container)
            self.edge_pos_layout.setContentsMargins(32, 0, 0, 0)
            self.edge_pos_layout.setSpacing(8)
            self.edge_pos_layout.addWidget(self._text("Posição na borda esquerda", "HintLabel"), 1)
            segments = QtWidgets.QWidget()
            segments.setObjectName("SegmentBox")
            segments_layout = QtWidgets.QHBoxLayout(segments)
            segments_layout.setContentsMargins(3, 3, 3, 3)
            segments_layout.setSpacing(2)
            self.edge_pos_group = QtWidgets.QButtonGroup(self)
            self.edge_pos_group.setExclusive(True)
            for pos_id, pos_title in (("top", "Superior"), ("middle", "Meio"), ("bottom", "Inferior")):
                btn = QtWidgets.QPushButton(pos_title)
                btn.setObjectName("SegmentedBtn")
                btn.setCheckable(True)
                btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
                btn.setChecked(pos_id == edge_pos)
                btn.setProperty("edge_position", pos_id)
                self.edge_pos_group.addButton(btn)
                self.edge_pos_buttons[pos_id] = btn
                segments_layout.addWidget(btn, 1)
            self.edge_pos_layout.addWidget(segments)
            body.addWidget(self._setting_row(
                "dock", "Meia-lua na borda (Windows)",
                "Mostra ao encostar na borda esquerda e recolhe ao clicar fora",
                self.edge_widget_switch, extra=self.edge_pos_container))
            self.edge_pos_container.setVisible(edge_enabled)
            self.edge_widget_switch.toggled.connect(self._on_edge_widget_toggled)
            self.edge_pos_group.buttonClicked.connect(self._on_field_changed)

        self.theme_combo = ComboBox()
        self.theme_combo.setMinimumWidth(150)
        self.theme_combo.addItem("Padrão", "dark")
        self.theme_combo.addItem("Dark André", "dark_andre")
        self.theme_combo.addItem("Claro", "light")
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.current_theme)))
        body.addWidget(self._setting_row("palette", "Tema", "Aparência da interface", self.theme_combo))
        return card

    def _build_footer(self):
        self.footer_bar = QtWidgets.QWidget()
        self.footer_bar.setObjectName("FooterBar")
        layout = QtWidgets.QHBoxLayout(self.footer_bar)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(14)
        self.footer_status_w = QtWidgets.QWidget()
        status = QtWidgets.QHBoxLayout(self.footer_status_w)
        status.setContentsMargins(0, 0, 0, 0)
        status.setSpacing(8)
        dot = QtWidgets.QLabel()
        dot.setObjectName("StatusDot")
        status.addWidget(dot, 0, QtCore.Qt.AlignVCenter)
        status.addWidget(self._text("Alterações salvas automaticamente", "FooterStatus", wrap=False))
        layout.addWidget(self.footer_status_w)
        layout.addStretch(1)
        self.btn_save = QtWidgets.QPushButton("Salvar configurações")
        self.btn_save.setMinimumHeight(40)
        self.btn_save.setMinimumWidth(190)
        self.btn_save.clicked.connect(self._manual_save_clicked)
        layout.addWidget(self.btn_save)
        return self.footer_bar

    def _connect_signals(self):
        self.engine_combo.currentIndexChanged.connect(self._on_field_changed)
        self.local_model_combo.currentIndexChanged.connect(self._on_field_changed)
        self.trans_combo.currentIndexChanged.connect(self._on_trans_combo_changed)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_combo_changed)
        self.custom_prompt_edit.textChanged.connect(self._on_field_changed)
        self.mic_combo.currentIndexChanged.connect(self._on_field_changed)
        self.hud_spin.valueChanged.connect(self._on_field_changed)
        self.autostart_switch.toggled.connect(self._on_field_changed)
        for widget, name in ((self.engine_combo, "Motor de transcrição"),
                             (self.trans_combo, "Tradução"), (self.theme_combo, "Tema"),
                             (self.mic_combo, "Microfone de entrada"),
                             (self.hud_spin, "Distância da pílula em pixels"),
                             (self.shortcut_input, "Atalho de ditado")):
            widget.setAccessibleName(name)

    # --- Layout responsivo ---------------------------------------------------

    def _arrange_columns(self):
        """Duas colunas em janela larga; uma coluna na janela estreita (meia-lua)."""
        for layout in (self.col_left, self.col_right):
            while layout.count():
                layout.takeAt(0)
        if self._wide_layout:
            left, right = self._cards[:2], self._cards[2:]
        else:
            left, right = self._cards, []
        for card in left:
            self.col_left.addWidget(card)
        for card in right:
            self.col_right.addWidget(card)
        self.col_left.addStretch(1)
        self.col_right.addStretch(1)
        self.col_right_w.setVisible(self._wide_layout)

    def _arrange_hero(self):
        """Atalhos ao lado do texto em janela larga e abaixo dele em janela estreita."""
        for widget in (self.ready_visual, self.hero_text_w, self.hero_badges_w):
            self.hero_grid.removeWidget(widget)
        self.hero_grid.addWidget(self.ready_visual, 0, 0, QtCore.Qt.AlignVCenter)
        self.hero_grid.addWidget(self.hero_text_w, 0, 1, QtCore.Qt.AlignVCenter)
        if self._wide_layout:
            self.hero_grid.addWidget(self.hero_badges_w, 0, 2, QtCore.Qt.AlignVCenter)
            self.hero_grid.setColumnStretch(1, 1)
            self.hero_grid.setColumnStretch(2, 0)
        else:
            self.hero_grid.addWidget(self.hero_badges_w, 1, 0, 1, 2)
            self.hero_grid.setColumnStretch(1, 1)
            self.hero_grid.setColumnStretch(2, 0)

    def _apply_compact(self):
        compact = self._compact_layout
        self.footer_status_w.setVisible(not compact)
        self.footer_bar.layout().setStretchFactor(self.btn_save, 1 if compact else 0)
        if compact:
            self.btn_collapse_edge.setText("«")
            self.btn_collapse_edge.setFixedWidth(36)
        else:
            self.btn_collapse_edge.setText("«  Recolher para borda")
            self.btn_collapse_edge.setMinimumWidth(0)
            self.btn_collapse_edge.setMaximumWidth(16777215)
        direction = QtWidgets.QBoxLayout.TopToBottom if compact else QtWidgets.QBoxLayout.LeftToRight
        self.model_cards_layout.setDirection(direction)
        if self.edge_pos_container is not None:
            self.edge_pos_layout.setDirection(direction)

    def _apply_responsive(self, force=False):
        wide = self.width() >= self.WIDE_BREAKPOINT
        compact = self.width() < self.COMPACT_BREAKPOINT
        if force or wide != self._wide_layout:
            self._wide_layout = wide
            self._arrange_columns()
            self._arrange_hero()
        if force or compact != self._compact_layout:
            self._compact_layout = compact
            self._apply_compact()

    # --- Comportamento -------------------------------------------------------

    def _update_shortcut_hint(self):
        combo = " + ".join(k.upper() for k in self.config.get("trigger_keys", ["f8"]))
        transform = " + ".join(k.upper().replace("+", " + ") for k in
                               self.config.get("transform_trigger_keys", ["shift+f8"]))
        self.ready_hint.setText(f"Segure {combo} para ditar em qualquer aplicativo.")
        self.hero_ptt_kbd.setText(combo)
        self.hero_transform_kbd.setText(transform)
        if hasattr(self, "transform_kbd"):
            self.transform_kbd.setText(transform)

    def _fit_shortcut_input(self):
        """Ajusta a largura do campo ao texto do atalho (ex.: CTRL + SHIFT + F12)."""
        font = QtGui.QFont(font_family("mono"))
        font.setPixelSize(12)
        font.setBold(True)
        width = QtGui.QFontMetrics(font).horizontalAdvance(self.shortcut_input.text()) + 36
        self.shortcut_input.setFixedWidth(max(96, min(230, width)))

    def _update_custom_mode_button(self):
        self.custom_mode_button.setText("Ativado  ›" if self.trans_combo.currentData() == "custom"
                                        else "Desativado  ›")

    def _toggle_custom_mode(self):
        target = "original" if self.trans_combo.currentData() == "custom" else "custom"
        self.trans_combo.setCurrentIndex(self.trans_combo.findData(target))

    def _on_trans_combo_changed(self):
        is_custom = self.trans_combo.currentData() == "custom"
        self.custom_prompt_box.setVisible(is_custom)
        self._update_custom_mode_button()
        self._on_field_changed()

    def _on_preset_combo_changed(self):
        preset_key = self.preset_combo.currentData()
        prompt = config_manager.get_preset_prompt(self.config, preset_key)
        self.custom_prompt_edit.blockSignals(True)
        self.custom_prompt_edit.setPlainText(prompt)
        self.custom_prompt_edit.blockSignals(False)
        self.config["custom_preset"] = preset_key
        self.config["custom_prompt"] = prompt
        self._on_field_changed()

    def _on_theme_switch_toggled(self, is_dark):
        new_theme = "dark" if is_dark else "light"
        self.config["theme"] = new_theme
        self._apply_theme(new_theme)
        self._save_settings(feedback=False)

    def _on_theme_combo_changed(self):
        new_theme = config_manager.normalize_theme(self.theme_combo.currentData())
        self.config["theme"] = new_theme
        self._apply_theme(new_theme)
        self._save_settings(feedback=False)

    def _on_edge_widget_toggled(self, enabled):
        enabled = bool(enabled)
        if self.edge_pos_container is not None:
            self.edge_pos_container.setVisible(enabled)
        if hasattr(self, "btn_collapse_edge"):
            self.btn_collapse_edge.setVisible(self._is_windows_platform and enabled)
        self._on_field_changed()

    def _selected_edge_position(self) -> str:
        if self.edge_pos_group is not None:
            checked = self.edge_pos_group.checkedButton()
            if checked is not None:
                return config_manager.normalize_edge_position(checked.property("edge_position"))
        return config_manager.normalize_edge_position(self.config.get("edge_widget_position", "middle"))

    def set_translation_target(self, target):
        """Atualiza o combobox caso o usuário tenha alterado o idioma pelo menu da bandeja (tray)"""
        target = (target or "original").lower()
        self.trans_combo.blockSignals(True)
        for i in range(self.trans_combo.count()):
            if self.trans_combo.itemData(i) == target:
                self.trans_combo.setCurrentIndex(i)
                break
        self.trans_combo.blockSignals(False)
        self.trans_group.sync()
        self.custom_prompt_box.setVisible(target == "custom")
        self._update_custom_mode_button()
        self.config["translation_target"] = target

    def _populate_microphones(self):
        self.mic_combo.blockSignals(True)
        self.mic_combo.addItem("Padrão do Sistema", None)
        saved_index = self.config.get("microphone_index")

        try:
            devices = sd.query_devices()
            selected_pos = 0
            curr_pos = 1
            for idx, dev in enumerate(devices):
                if dev.get('max_input_channels', 0) > 0:
                    name = dev.get('name', f"Dispositivo {idx}")
                    self.mic_combo.addItem(f"{name} (#{idx})", idx)
                    if saved_index == idx:
                        selected_pos = curr_pos
                    curr_pos += 1
            self.mic_combo.setCurrentIndex(selected_pos)
        except Exception as e:
            print(f"[Settings] Erro ao listar microfones: {e}")
        self.mic_combo.blockSignals(False)

    def _record_key(self):
        dialog = KeyRecorderDialog(self, theme=self.current_theme)
        if dialog.exec_() == QtWidgets.QDialog.DialogCode.Accepted:
            if dialog.detected_keys:
                self.config["trigger_keys"] = dialog.detected_keys
                combo_text = " + ".join([k.upper() for k in dialog.detected_keys])
                self.shortcut_input.setText(combo_text)
                self._fit_shortcut_input()
                self._update_shortcut_hint()
                self._save_settings(feedback=False)

    def _on_field_changed(self):
        self._refresh_local_ui()
        self._save_settings(feedback=False)

    def _refresh_local_ui(self):
        """Mostra o card offline só com o motor local e reflete o estado do download."""
        self.local_card.setVisible(self.engine_combo.currentData() == "local")
        size = self.local_model_combo.currentData()
        available = local_transcriber.is_available()
        for model_size, card in self.model_cards.items():
            ready = available and local_transcriber.is_model_downloaded(model_size)
            card.set_state("Instalado" if ready else ("Não baixado" if available else "Indisponível"), ready)
        if self._download_thread is not None and self._download_thread.isRunning():
            return
        if not available:
            self.local_download_btn.setEnabled(False)
            self.local_download_btn.setText("Indisponível")
            self.local_status.setText("Esta versão do aplicativo não inclui o motor offline.")
        elif local_transcriber.is_model_downloaded(size):
            self.local_download_btn.setEnabled(False)
            self.local_download_btn.setText("✓ Modelo pronto")
            self.local_status.setText("Ditado offline ativo. Tradução, modo livre e Voice Transform ainda usam a nuvem.")
        else:
            self.local_download_btn.setEnabled(True)
            self.local_download_btn.setText("Baixar modelo")
            self.local_status.setText(
                f"Baixe o modelo (~{local_transcriber.MODEL_SIZES[size]} MB) uma única vez. "
                "Enquanto isso, o ditado usa a nuvem se houver chave configurada.")

    def _download_local_model(self):
        size = self.local_model_combo.currentData()
        self.local_download_btn.setEnabled(False)
        self.local_download_btn.setText("Baixando…")
        self.local_status.setText("Baixando o modelo. Isso acontece só uma vez; pode continuar usando o app.")
        thread = _ModelDownloadThread(size, self)
        thread.done.connect(self._on_model_downloaded)
        self._download_thread = thread
        thread.start()

    def _on_model_downloaded(self, ok, size):
        self._download_thread = None
        self._refresh_local_ui()
        if ok:
            self._save_settings(feedback=False)  # reconstrói o motor e aquece o modelo
        else:
            self.local_download_btn.setText("Tentar novamente")
            self.local_status.setText("Não foi possível baixar o modelo. Verifique a conexão e tente de novo.")

    def _manual_save_clicked(self):
        self._save_settings(feedback=True)

    def _save_prompt_clicked(self):
        preset_key = self.preset_combo.currentData()
        prompt_text = self.custom_prompt_edit.toPlainText().strip()
        if "custom_prompts" not in self.config:
            self.config["custom_prompts"] = {}
        self.config["custom_prompts"][preset_key] = prompt_text
        self.config["custom_prompt"] = prompt_text
        self.config["custom_preset"] = preset_key
        config_manager.save_config(self.config)
        self.config_saved.emit(self.config)
        self.btn_save_prompt.setText("✓ Prompt Salvo!")
        QtCore.QTimer.singleShot(1500, lambda: self.btn_save_prompt.setText("Salvar Prompt"))

    def _reset_prompt_clicked(self):
        preset_key = self.preset_combo.currentData()
        default_prompt = config_manager.PRESET_PROMPTS.get(preset_key, "")
        if "custom_prompts" in self.config and preset_key in self.config["custom_prompts"]:
            del self.config["custom_prompts"][preset_key]
        self.custom_prompt_edit.blockSignals(True)
        self.custom_prompt_edit.setPlainText(default_prompt)
        self.custom_prompt_edit.blockSignals(False)
        self.config["custom_prompt"] = default_prompt
        self.config["custom_preset"] = preset_key
        config_manager.save_config(self.config)
        self.config_saved.emit(self.config)
        self.btn_reset_prompt.setText("✓ Padrão Restaurado!")
        QtCore.QTimer.singleShot(1500, lambda: self.btn_reset_prompt.setText("Restaurar Padrão"))

    def _save_settings(self, feedback=False):
        self.config["theme"] = config_manager.normalize_theme(self.current_theme)
        self.config["engine"] = self.engine_combo.currentData()
        self.config["local_model_size"] = self.local_model_combo.currentData()
        self.config["translation_target"] = self.trans_combo.currentData()
        preset_key = self.preset_combo.currentData()
        self.config["custom_preset"] = preset_key
        prompt_text = self.custom_prompt_edit.toPlainText().strip()
        self.config["custom_prompt"] = prompt_text
        if "custom_prompts" not in self.config:
            self.config["custom_prompts"] = {}
        self.config["custom_prompts"][preset_key] = prompt_text
        self.config["microphone_index"] = self.mic_combo.currentData()
        self.config["hud_bottom_offset"] = self.hud_spin.value()
        self.config["autostart"] = self.autostart_switch.isChecked()
        if self._is_windows_platform and self.edge_widget_switch is not None:
            self.config["edge_widget_enabled"] = self.edge_widget_switch.isChecked()
            self.config["edge_widget_position"] = self._selected_edge_position()

        config_manager.save_config(self.config)
        config_manager.set_windows_autostart(self.config["autostart"])

        self.config_saved.emit(self.config)

        if feedback:
            self.btn_save.setText("✓ Configurações Salvas!")
            QtCore.QTimer.singleShot(1500, lambda: self.btn_save.setText("Salvar configurações"))

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.Type.WindowDeactivate:
            self.window_deactivated.emit()
        super().changeEvent(event)

    def closeEvent(self, event):
        self.window_hidden.emit()
        event.ignore()
        self.hide()
