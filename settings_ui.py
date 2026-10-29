import os
import sys
import sounddevice as sd
from PyQt5 import QtCore, QtGui, QtWidgets
from pynput import keyboard

import config_manager
import local_transcriber
from ui_components import ComboBox, LineIcon, ReadyVisual, ThemeSelector, palette, stylesheet

class ToggleSwitch(QtWidgets.QAbstractButton):
    """Toggle switch moderno e minimalista estilo iOS / Windows 11 Settings"""
    def __init__(self, parent=None, checked=False, theme: str = "dark"):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setChecked(checked)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 24)
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

    def set_theme(self, theme: str):
        self.theme = theme
        self.update()

    def hitButton(self, pos: QtCore.QPoint):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # Trilha arredondada
        if self._offset > 0.0:
            track_color = QtGui.QColor(palette(self.theme)["bright"])  # Azul vibrante de ativação
        else:
            track_color = QtGui.QColor("#3f3f46") if self.theme == "dark" else QtGui.QColor("#cbd5e1")

        painter.setBrush(QtGui.QBrush(track_color))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 46, 24, 12, 12)

        # Círculo deslizante (Thumb)
        thumb_diameter = 18
        x = 3 + self._offset * (46 - thumb_diameter - 6)
        y = 3
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#ffffff")))
        if self._offset == 0.0 and self.theme == "light":
            painter.setPen(QtGui.QPen(QtGui.QColor("#94a3b8"), 1))
        else:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(QtCore.QRectF(x, y, thumb_diameter, thumb_diameter))


class KeyRecorderDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, theme: str = "dark"):
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

    def _normalize_key(self, key) -> str:
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

    def __init__(self, size: str, parent=None):
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

    def __init__(self, config: dict, icon_path: str = None, icon_white_path: str = None, icon_dark_path: str = None):
        super().__init__()
        self.config = config.copy()
        self.icon_white_path = icon_white_path or icon_path
        self.icon_dark_path = icon_dark_path or icon_path
        self.current_theme = self.config.get("theme", "dark")

        self.setWindowTitle("Dita-eu — Configurações")
        self.setObjectName("SettingsRoot")
        self.setMinimumSize(600, 570)
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.resize(min(740, area.width()), min(850, area.height() - 40))

        self._setup_ui()
        self._apply_theme(self.current_theme)

    def _update_logo(self):
        icon_file = self.icon_white_path if self.current_theme == "dark" else self.icon_dark_path
        if icon_file and os.path.exists(icon_file):
            pix = QtGui.QPixmap(icon_file).scaled(
                34, 34,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            self.logo_label.setPixmap(pix)
            self.setWindowIcon(QtGui.QIcon(icon_file))

    def _apply_theme(self, theme: str):
        self.current_theme = theme
        self._update_logo()
        self.theme_switch.set_theme(theme)
        self.theme_switch.blockSignals(True)
        self.theme_switch.setChecked(theme == "dark")
        self.theme_switch.blockSignals(False)
        self.autostart_switch.set_theme(theme)
        self.setStyleSheet(stylesheet(theme))
        for icon in self.findChildren(LineIcon):
            icon.theme = theme
            icon.update()
        self.ready_visual.theme = theme
        self.ready_visual.update()

    @staticmethod
    def _text(text, name="CardTitle"):
        label = QtWidgets.QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label

    def _card(self, parent_layout):
        card = QtWidgets.QWidget()
        card.setObjectName("CardBox")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(16, 5, 16, 5)
        layout.setSpacing(0)
        parent_layout.addWidget(card)
        return layout

    def _row(self, layout, icon, title, control, hint=None):
        if layout.count():
            divider = QtWidgets.QFrame()
            divider.setObjectName("Divider")
            divider.setFixedHeight(1)
            layout.addWidget(divider)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 10, 0, 10)
        row.setSpacing(14)
        row.addWidget(LineIcon(icon, 23))
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(3)
        text.addWidget(self._text(title))
        if hint:
            text.addWidget(self._text(hint, "HintLabel"))
        row.addLayout(text, 1)
        row.addWidget(control)
        layout.addLayout(row)

    def _setup_ui(self):
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area = scroll_area
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        content_widget = QtWidgets.QWidget()
        content_widget.setObjectName("Content")
        main_layout = QtWidgets.QVBoxLayout(content_widget)
        main_layout.setContentsMargins(24, 20, 24, 18)
        main_layout.setSpacing(14)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(14)
        # Keep the original window/tray identity, with an amber in-app microphone.
        self.logo_label = QtWidgets.QLabel()
        self.logo_label.hide()
        header.addWidget(LineIcon("mic", 38))
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(self._text("Dita-eu", "TitleLabel"))
        titles.addWidget(self._text("Sua voz, direto ao texto.", "SubtitleLabel"))
        header.addLayout(titles, 1)
        self.theme_switch = ThemeSelector(self.current_theme == "dark", self.current_theme)
        self.theme_switch.toggled.connect(self._on_theme_switch_toggled)
        header.addWidget(self.theme_switch)
        main_layout.addLayout(header)

        hero = self._card(main_layout)
        hero_row = QtWidgets.QHBoxLayout()
        hero_row.setContentsMargins(0, 9, 0, 9)
        hero_row.setSpacing(18)
        self.ready_visual = ReadyVisual()
        hero_row.addWidget(self.ready_visual)
        hero_text = QtWidgets.QVBoxLayout()
        hero_text.setSpacing(5)
        hero_text.addWidget(self._text("Pronto para ouvir", "SectionTitle"))
        self.ready_hint = self._text("", "HintLabel")
        hero_text.addWidget(self.ready_hint)
        hero_row.addLayout(hero_text, 1)
        hero.addLayout(hero_row)
        self._update_shortcut_hint()

        main_layout.addWidget(self._text("Configurações", "SectionTitle"))
        settings = self._card(main_layout)
        self.engine_combo = ComboBox()
        self.engine_combo.setMinimumWidth(210)
        self.engine_combo.addItem("Groq Whisper", "groq")
        self.engine_combo.addItem("Google Gemini", "gemini")
        self.engine_combo.addItem("Local · offline", "local")
        self.engine_combo.setCurrentIndex(max(0, self.engine_combo.findData(self.config.get("engine", "groq"))))
        self._row(settings, "engine", "Motor de transcrição", self.engine_combo,
                  "Reconhecimento de voz")

        # Modelo offline: só aparece com o motor local e é baixado sob demanda.
        local_layout = self._card(main_layout)
        self.local_card = local_layout.parentWidget()
        self.local_model_combo = ComboBox()
        self.local_model_combo.setMinimumWidth(210)
        for size, mb in local_transcriber.MODEL_SIZES.items():
            label = "Base · rápido" if size == "base" else "Small · mais preciso"
            self.local_model_combo.addItem(f"{label} (~{mb} MB)", size)
        self.local_model_combo.setCurrentIndex(
            max(0, self.local_model_combo.findData(self.config.get("local_model_size", local_transcriber.DEFAULT_MODEL_SIZE))))
        self._row(local_layout, "engine", "Modelo offline", self.local_model_combo,
                  "Processado neste computador, sem internet e sem cota de API")
        self.local_download_btn = QtWidgets.QPushButton()
        self.local_download_btn.setObjectName("SecondaryBtn")
        self.local_download_btn.clicked.connect(self._download_local_model)
        self._row(local_layout, "document", "Download do modelo", self.local_download_btn)
        self.local_status = self._text("", "HintLabel")
        local_layout.addWidget(self.local_status)
        self._download_thread = None
        self._refresh_local_ui()
        self.trans_combo = ComboBox()
        self.trans_combo.setMinimumWidth(210)
        for label, value in [("Original · sem tradução", "original"), ("Inglês", "en"),
                             ("Espanhol", "es"), ("Francês", "fr"), ("Alemão", "de"),
                             ("Italiano", "it"), ("Modo livre", "custom")]:
            self.trans_combo.addItem(label, value)
        current_trans = self.config.get("translation_target", "original")
        index = self.trans_combo.findData(current_trans)
        self.trans_combo.setCurrentIndex(max(0, index))
        self._row(settings, "language", "Tradução", self.trans_combo, "Idioma do texto de saída")
        free_mode = self._card(main_layout)
        self.custom_mode_button = QtWidgets.QPushButton()
        self.custom_mode_button.setObjectName("SecondaryBtn")
        self.custom_mode_button.clicked.connect(self._toggle_custom_mode)
        self._row(free_mode, "document", "Modo livre", self.custom_mode_button,
                  "Personalidades e instruções de escrita")

        self.custom_prompt_box = QtWidgets.QWidget()
        self.custom_prompt_box.setObjectName("CardBox")
        custom_box_layout = QtWidgets.QVBoxLayout(self.custom_prompt_box)
        custom_box_layout.setContentsMargins(14, 12, 14, 12)
        custom_box_layout.setSpacing(8)

        custom_title = QtWidgets.QLabel("Personalidade / Prompt do Modo Livre:")
        custom_title.setObjectName("CardTitle")

        self.preset_combo = ComboBox()
        self.preset_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.preset_combo.addItem("✉️ Email Prytter", "email_prytter")
        self.preset_combo.addItem("🎮 Jogador de Dota 2 estressado", "dota")
        self.preset_combo.addItem("🏴‍☠️ Linguagem Pirata", "pirata")
        self.preset_combo.addItem("💅 Adolescente empolgada (Bestie)", "adolescente")
        self.preset_combo.addItem("💼 Corporativo Formal", "corporativo")
        self.preset_combo.addItem("🧘 Coach Quântico", "coach_quantico")
        self.preset_combo.addItem("🥩 Tiozão do Churrasco", "tiozao_churrasco")
        self.preset_combo.addItem("🎬 Trailer de Cinema Anos 90", "trailer_cinema")
        self.preset_combo.addItem("✍️ Prompt Livre / Customizado", "livre")

        saved_preset = self.config.get("custom_preset", "email_prytter")
        for i in range(self.preset_combo.count()):
            if self.preset_combo.itemData(i) == saved_preset:
                self.preset_combo.setCurrentIndex(i)
                break

        self.custom_prompt_edit = QtWidgets.QPlainTextEdit()
        self.custom_prompt_edit.setPlaceholderText("Escreva a instrução de como o texto ditado deve ser reescrito...")
        self.custom_prompt_edit.setFixedHeight(95)
        saved_prompt = config_manager.get_preset_prompt(self.config, saved_preset)
        self.custom_prompt_edit.setPlainText(saved_prompt)

        # Botões de Ação do Prompt: Salvar Edição e Restaurar Padrão de Fábrica
        prompt_actions_layout = QtWidgets.QHBoxLayout()
        prompt_actions_layout.setSpacing(8)
        self.btn_save_prompt = QtWidgets.QPushButton("Salvar Prompt")
        self.btn_save_prompt.setObjectName("SecondaryBtn")
        self.btn_save_prompt.clicked.connect(self._save_prompt_clicked)

        self.btn_reset_prompt = QtWidgets.QPushButton("Restaurar Padrão")
        self.btn_reset_prompt.setObjectName("SecondaryBtn")
        self.btn_reset_prompt.clicked.connect(self._reset_prompt_clicked)

        prompt_actions_layout.addWidget(self.btn_save_prompt)
        prompt_actions_layout.addWidget(self.btn_reset_prompt)
        prompt_actions_layout.addStretch()

        preset_hint = QtWidgets.QLabel("Escolha uma personalidade pronta ou edite a instrução livremente. O texto ditado no F8 será adaptado conforme esse comando.")
        preset_hint.setObjectName("HintLabel")
        preset_hint.setWordWrap(True)

        custom_box_layout.addWidget(custom_title)
        custom_box_layout.addWidget(self.preset_combo)
        custom_box_layout.addWidget(self.custom_prompt_edit)
        custom_box_layout.addLayout(prompt_actions_layout)
        custom_box_layout.addWidget(preset_hint)

        self.custom_prompt_box.setVisible(current_trans == "custom")
        main_layout.addWidget(self.custom_prompt_box)

        self._update_custom_mode_button()
        main_layout.addWidget(self._text("Entrada e atalhos", "SectionTitle"))
        inputs = self._card(main_layout)
        shortcut_control = QtWidgets.QWidget()
        shortcut_row = QtWidgets.QHBoxLayout(shortcut_control)
        shortcut_row.setContentsMargins(0, 0, 0, 0)
        shortcut_row.setSpacing(8)
        current_combo = " + ".join(k.upper() for k in self.config.get("trigger_keys", ["f8"]))
        self.shortcut_input = QtWidgets.QLineEdit(current_combo)
        self.shortcut_input.setReadOnly(True)
        self.shortcut_input.setFixedWidth(100)
        self.shortcut_input.setAlignment(QtCore.Qt.AlignCenter)
        self.btn_record_key = QtWidgets.QPushButton("Alterar")
        self.btn_record_key.setObjectName("SecondaryBtn")
        self.btn_record_key.clicked.connect(self._record_key)
        shortcut_row.addWidget(self.shortcut_input)
        shortcut_row.addWidget(self.btn_record_key)
        transform_keys = " + ".join(k.upper().replace("+", " + ") for k in
                                    self.config.get("transform_trigger_keys", ["shift+f8"]))
        self._row(inputs, "keyboard", "Atalho de ditado", shortcut_control,
                  "Transformar seleção: " + transform_keys)
        self.mic_combo = ComboBox()
        self.mic_combo.setFixedWidth(240)
        self.mic_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._populate_microphones()
        self._row(inputs, "mic", "Microfone de entrada", self.mic_combo)
        self.hud_spin = QtWidgets.QSpinBox()
        self.hud_spin.setRange(50, 1000)
        self.hud_spin.setValue(self.config.get("hud_bottom_offset", 350))
        self.hud_spin.setSuffix(" px")
        self.hud_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.hud_spin.setFixedWidth(100)
        self.hud_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.hud_slider.setTracking(False)
        self.hud_slider.setRange(50, 1000)
        self.hud_slider.setValue(self.hud_spin.value())
        self.hud_slider.setMinimumWidth(100)
        self.hud_slider.setMaximumWidth(160)
        self.hud_slider.setAccessibleName("Distância da pílula à base da tela")
        self.hud_slider.valueChanged.connect(self.hud_spin.setValue)
        self.hud_spin.valueChanged.connect(self.hud_slider.setValue)
        position = QtWidgets.QWidget()
        position_row = QtWidgets.QHBoxLayout(position)
        position_row.setContentsMargins(0, 0, 0, 0)
        position_row.setSpacing(12)
        position_row.addWidget(self.hud_slider)
        position_row.addWidget(self.hud_spin)
        self._row(inputs, "screen", "Posição da pílula", position)
        self.autostart_switch = ToggleSwitch(self, self.config.get("autostart", False), self.current_theme)
        self.autostart_switch.setAccessibleName("Iniciar com o Windows")
        self._row(inputs, "windows", "Iniciar com o Windows", self.autostart_switch,
                  "Executar em segundo plano ao ligar")
        main_layout.addStretch()
        scroll_area.setWidget(content_widget)
        root_layout.addWidget(scroll_area, 1)
        # The save action remains reachable even with the custom editor expanded.
        footer = QtWidgets.QHBoxLayout()
        footer.setContentsMargins(24, 10, 24, 18)
        self.btn_save = QtWidgets.QPushButton("Salvar configurações")
        self.btn_save.setMinimumHeight(44)
        self.btn_save.clicked.connect(self._manual_save_clicked)
        footer.addWidget(self.btn_save)
        root_layout.addLayout(footer)

        self.engine_combo.currentIndexChanged.connect(self._on_field_changed)
        self.local_model_combo.currentIndexChanged.connect(self._on_field_changed)
        self.trans_combo.currentIndexChanged.connect(self._on_trans_combo_changed)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_combo_changed)
        self.custom_prompt_edit.textChanged.connect(self._on_field_changed)
        self.mic_combo.currentIndexChanged.connect(self._on_field_changed)
        self.hud_spin.valueChanged.connect(self._on_field_changed)
        self.autostart_switch.toggled.connect(self._on_field_changed)
        for widget, name in ((self.engine_combo, "Motor de transcrição"),
                             (self.trans_combo, "Tradução"), (self.mic_combo, "Microfone de entrada"),
                             (self.hud_spin, "Distância da pílula em pixels"),
                             (self.shortcut_input, "Atalho de ditado")):
            widget.setAccessibleName(name)

    def _update_shortcut_hint(self):
        combo = " + ".join(k.upper() for k in self.config.get("trigger_keys", ["f8"]))
        self.ready_hint.setText(f"Segure {combo} para ditar em qualquer aplicativo.")

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

    def _on_theme_switch_toggled(self, is_dark: bool):
        new_theme = "dark" if is_dark else "light"
        self.config["theme"] = new_theme
        self._apply_theme(new_theme)
        self._save_settings(feedback=False)

    def set_translation_target(self, target: str):
        """Atualiza o combobox caso o usuário tenha alterado o idioma pelo menu da bandeja (tray)"""
        target = (target or "original").lower()
        self.trans_combo.blockSignals(True)
        for i in range(self.trans_combo.count()):
            if self.trans_combo.itemData(i) == target:
                self.trans_combo.setCurrentIndex(i)
                break
        self.trans_combo.blockSignals(False)
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
                self._update_shortcut_hint()
                self._save_settings(feedback=False)

    def _on_field_changed(self):
        self._refresh_local_ui()
        self._save_settings(feedback=False)

    def _refresh_local_ui(self):
        """Mostra o card offline só com o motor local e reflete o estado do download."""
        self.local_card.setVisible(self.engine_combo.currentData() == "local")
        size = self.local_model_combo.currentData()
        if self._download_thread is not None and self._download_thread.isRunning():
            return
        if not local_transcriber.is_available():
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

    def _on_model_downloaded(self, ok: bool, size: str):
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

    def _save_settings(self, feedback: bool = False):
        self.config["theme"] = "dark" if self.theme_switch.isChecked() else "light"
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

        config_manager.save_config(self.config)
        config_manager.set_windows_autostart(self.config["autostart"])

        self.config_saved.emit(self.config)

        if feedback:
            self.btn_save.setText("✓ Configurações Salvas!")
            QtCore.QTimer.singleShot(1500, lambda: self.btn_save.setText("Salvar configurações"))

    def closeEvent(self, event):
        event.ignore()
        self.hide()
