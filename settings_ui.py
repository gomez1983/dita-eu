import os
import sys
import sounddevice as sd
from PyQt5 import QtCore, QtGui, QtWidgets
from pynput import keyboard

import config_manager

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
        if self.theme == "light":
            self.setStyleSheet("""
                QDialog {
                    background-color: #f8fafc;
                    border: 1px solid #cbd5e1;
                }
                QLabel#DialogInstruction {
                    font-size: 13px;
                    color: #475569;
                    font-family: 'Segoe UI', sans-serif;
                }
                QLabel#ComboDisplay {
                    font-size: 18px;
                    font-weight: bold;
                    color: #0f172a;
                    background-color: #ffffff;
                    border: 1px dashed #94a3b8;
                    border-radius: 8px;
                    padding: 12px;
                }
                QPushButton#PrimaryBtn {
                    background-color: #0f172a;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: 600;
                }
                QPushButton#PrimaryBtn:hover {
                    background-color: #1e293b;
                }
                QPushButton#PrimaryBtn:disabled {
                    background-color: #e2e8f0;
                    color: #94a3b8;
                }
                QPushButton#SecondaryBtn {
                    background-color: #f1f5f9;
                    color: #0f172a;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: 600;
                }
                QPushButton#SecondaryBtn:hover {
                    background-color: #e2e8f0;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #121214;
                    border: 1px solid #27272a;
                }
                QLabel#DialogInstruction {
                    font-size: 13px;
                    color: #a1a1aa;
                    font-family: 'Segoe UI', sans-serif;
                }
                QLabel#ComboDisplay {
                    font-size: 18px;
                    font-weight: bold;
                    color: #ffffff;
                    background-color: #18181b;
                    border: 1px dashed #52525b;
                    border-radius: 8px;
                    padding: 12px;
                }
                QPushButton#PrimaryBtn {
                    background-color: #ffffff;
                    color: #09090b;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: 600;
                }
                QPushButton#PrimaryBtn:hover {
                    background-color: #e4e4e7;
                }
                QPushButton#PrimaryBtn:disabled {
                    background-color: #27272a;
                    color: #71717a;
                }
                QPushButton#SecondaryBtn {
                    background-color: #27272a;
                    color: #ffffff;
                    border: 1px solid #3f3f46;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: 600;
                }
                QPushButton#SecondaryBtn:hover {
                    background-color: #3f3f46;
                }
            """)

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


class SettingsWindow(QtWidgets.QWidget):
    config_saved = QtCore.pyqtSignal(dict)

    def __init__(self, config: dict, icon_path: str = None):
        super().__init__()
        self.config = config.copy()
        self.icon_path = icon_path
        self.current_theme = self.config.get("theme", "dark")

        self.setWindowTitle("Dita-eu — Configurações")
        self.setMinimumSize(520, 620)
        self.resize(550, 700)

        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        self._apply_theme(self.current_theme)
        self._setup_ui()

    def _apply_theme(self, theme: str):
        self.current_theme = theme
        if theme == "light":
            # Modo Claro com critérios rígidos de contraste (WCAG AAA / AA)
            self.setStyleSheet("""
                QWidget {
                    background-color: #f8fafc;
                    color: #0f172a;
                    font-family: 'Segoe UI', -apple-system, sans-serif;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background: #f1f5f9;
                    width: 8px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical {
                    background: #cbd5e1;
                    border-radius: 4px;
                    min-height: 20px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #94a3b8;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QLabel {
                    font-size: 13px;
                    color: #1e293b;
                    font-weight: 600;
                }
                QLabel#TitleLabel {
                    font-size: 20px;
                    font-weight: bold;
                    color: #0f172a;
                }
                QLabel#SubtitleLabel {
                    font-size: 12px;
                    color: #475569;
                    font-weight: 400;
                }
                QLabel#CardTitle {
                    font-size: 13px;
                    font-weight: bold;
                    color: #0f172a;
                }
                QLabel#CardBadge {
                    font-size: 13px;
                    font-weight: 700;
                    color: #047857;
                }
                QLabel#CardDesc {
                    font-size: 12px;
                    color: #334155;
                    font-weight: 400;
                    line-height: 1.4;
                }
                QLabel#HintLabel {
                    font-size: 11px;
                    color: #475569;
                    font-weight: 400;
                }
                QWidget#CardBox {
                    background-color: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 8px;
                    padding: 12px;
                }
                QLineEdit, QComboBox, QSpinBox {
                    background-color: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 9px 12px;
                    color: #0f172a;
                    font-size: 13px;
                    font-weight: 500;
                }
                QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                    border: 1px solid #0f172a;
                }
                QComboBox::drop-down {
                    border: none;
                    padding-right: 8px;
                }
                QComboBox QAbstractItemView {
                    background-color: #ffffff;
                    color: #0f172a;
                    selection-background-color: #e2e8f0;
                    selection-color: #0f172a;
                    border: 1px solid #cbd5e1;
                    outline: none;
                }
                QCheckBox {
                    font-size: 13px;
                    color: #1e293b;
                    font-weight: 500;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 4px;
                    border: 1px solid #94a3b8;
                    background-color: #ffffff;
                }
                QCheckBox::indicator:checked {
                    background-color: #0f172a;
                    border: 1px solid #0f172a;
                }
                QPushButton {
                    background-color: #0f172a;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 11px 20px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #1e293b;
                }
                QPushButton#SecondaryBtn {
                    background-color: #f1f5f9;
                    color: #0f172a;
                    border: 1px solid #cbd5e1;
                    padding: 9px 16px;
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton#SecondaryBtn:hover {
                    background-color: #e2e8f0;
                }
            """)
        else:
            # Modo Escuro com contraste rigoroso (Preto/Zinco profundo + Branco)
            self.setStyleSheet("""
                QWidget {
                    background-color: #09090b;
                    color: #f4f4f5;
                    font-family: 'Segoe UI', -apple-system, sans-serif;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background: #121214;
                    width: 8px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical {
                    background: #27272a;
                    border-radius: 4px;
                    min-height: 20px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #3f3f46;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QLabel {
                    font-size: 13px;
                    color: #e4e4e7;
                    font-weight: 500;
                }
                QLabel#TitleLabel {
                    font-size: 20px;
                    font-weight: bold;
                    color: #ffffff;
                }
                QLabel#SubtitleLabel {
                    font-size: 12px;
                    color: #a1a1aa;
                    font-weight: 400;
                }
                QLabel#CardTitle {
                    font-size: 13px;
                    font-weight: bold;
                    color: #ffffff;
                }
                QLabel#CardBadge {
                    font-size: 13px;
                    font-weight: 700;
                    color: #34d399;
                }
                QLabel#CardDesc {
                    font-size: 12px;
                    color: #a1a1aa;
                    font-weight: 400;
                    line-height: 1.4;
                }
                QLabel#HintLabel {
                    font-size: 11px;
                    color: #71717a;
                    font-weight: 400;
                }
                QWidget#CardBox {
                    background-color: #141417;
                    border: 1px solid #27272a;
                    border-radius: 8px;
                    padding: 12px;
                }
                QLineEdit, QComboBox, QSpinBox {
                    background-color: #18181b;
                    border: 1px solid #3f3f46;
                    border-radius: 6px;
                    padding: 9px 12px;
                    color: #ffffff;
                    font-size: 13px;
                }
                QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                    border: 1px solid #ffffff;
                }
                QComboBox::drop-down {
                    border: none;
                    padding-right: 8px;
                }
                QComboBox QAbstractItemView {
                    background-color: #18181b;
                    color: #ffffff;
                    selection-background-color: #27272a;
                    selection-color: #ffffff;
                    border: 1px solid #3f3f46;
                    outline: none;
                }
                QCheckBox {
                    font-size: 13px;
                    color: #e4e4e7;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 4px;
                    border: 1px solid #3f3f46;
                    background-color: #18181b;
                }
                QCheckBox::indicator:checked {
                    background-color: #ffffff;
                    border: 1px solid #ffffff;
                }
                QPushButton {
                    background-color: #ffffff;
                    color: #09090b;
                    border: none;
                    border-radius: 6px;
                    padding: 11px 20px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #e4e4e7;
                }
                QPushButton#SecondaryBtn {
                    background-color: #27272a;
                    color: #ffffff;
                    border: 1px solid #3f3f46;
                    padding: 9px 16px;
                    font-size: 13px;
                }
                QPushButton#SecondaryBtn:hover {
                    background-color: #3f3f46;
                }
            """)

    def _setup_ui(self):
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(content_widget)
        main_layout.setContentsMargins(32, 24, 32, 24)
        main_layout.setSpacing(18)

        # Cabeçalho
        header_layout = QtWidgets.QHBoxLayout()
        if self.icon_path and os.path.exists(self.icon_path):
            icon_lbl = QtWidgets.QLabel()
            pix = QtGui.QPixmap(self.icon_path).scaled(34, 34, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
            icon_lbl.setPixmap(pix)
            header_layout.addWidget(icon_lbl)

        title_lbl = QtWidgets.QLabel("Dita-eu")
        title_lbl.setObjectName("TitleLabel")
        subtitle_lbl = QtWidgets.QLabel("Ditado por Voz com Injeção Direta")
        subtitle_lbl.setObjectName("SubtitleLabel")

        title_vbox = QtWidgets.QVBoxLayout()
        title_vbox.setSpacing(2)
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(subtitle_lbl)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        # Seletor de Tema no cabeçalho
        theme_vbox = QtWidgets.QVBoxLayout()
        theme_vbox.setSpacing(4)
        theme_lbl = QtWidgets.QLabel("Tema:")
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItem("🌙 Modo Escuro", "dark")
        self.theme_combo.addItem("☀️ Modo Claro", "light")
        self.theme_combo.setCurrentIndex(0 if self.current_theme == "dark" else 1)
        self.theme_combo.setMinimumWidth(130)
        theme_vbox.addWidget(theme_lbl)
        theme_vbox.addWidget(self.theme_combo)
        header_layout.addLayout(theme_vbox)

        main_layout.addLayout(header_layout)

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #3f3f46; max-height: 1px;")
        main_layout.addWidget(line)

        # 1. Seletor de Motor
        engine_layout = QtWidgets.QVBoxLayout()
        engine_layout.setSpacing(6)
        engine_lbl = QtWidgets.QLabel("Motor de Transcrição:")
        self.engine_combo = QtWidgets.QComboBox()
        self.engine_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.engine_combo.addItem("⚡ Groq Whisper (Ultra-Rápido ~300ms)", "groq")
        self.engine_combo.addItem("✨ Google Gemini (Flash Multimodal)", "gemini")
        
        current_eng = self.config.get("engine", "groq")
        self.engine_combo.setCurrentIndex(0 if current_eng == "groq" else 1)

        engine_layout.addWidget(engine_lbl)
        engine_layout.addWidget(self.engine_combo)
        main_layout.addLayout(engine_layout)

        # 2. Chave Groq
        self.groq_box = QtWidgets.QWidget()
        groq_vbox = QtWidgets.QVBoxLayout(self.groq_box)
        groq_vbox.setContentsMargins(0, 0, 0, 0)
        groq_vbox.setSpacing(6)
        groq_lbl = QtWidgets.QLabel("Chave de API da Groq (GROQ_API_KEY):")
        self.groq_input = QtWidgets.QLineEdit(self.config.get("groq_api_key", ""))
        self.groq_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.groq_input.setPlaceholderText("gsk_...")
        groq_vbox.addWidget(groq_lbl)
        groq_vbox.addWidget(self.groq_input)
        main_layout.addWidget(self.groq_box)

        # 3. Chave Gemini
        self.gemini_box = QtWidgets.QWidget()
        gemini_vbox = QtWidgets.QVBoxLayout(self.gemini_box)
        gemini_vbox.setContentsMargins(0, 0, 0, 0)
        gemini_vbox.setSpacing(6)
        gemini_lbl = QtWidgets.QLabel("Chave de API do Google Gemini (GEMINI_API_KEY):")
        self.gemini_input = QtWidgets.QLineEdit(self.config.get("gemini_api_key", ""))
        self.gemini_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.gemini_input.setPlaceholderText("Cole sua chave Gemini...")
        gemini_vbox.addWidget(gemini_lbl)
        gemini_vbox.addWidget(self.gemini_input)
        main_layout.addWidget(self.gemini_box)

        # 4. Modo de Funcionamento (EXCLUSIVAMENTE a Opção 1 mantida no Front-end)
        mode_card = QtWidgets.QWidget()
        mode_card.setObjectName("CardBox")
        mode_card_layout = QtWidgets.QVBoxLayout(mode_card)
        mode_card_layout.setContentsMargins(14, 12, 14, 12)
        mode_card_layout.setSpacing(6)

        mode_title = QtWidgets.QLabel("Modo de Funcionamento:")
        mode_title.setObjectName("CardTitle")
        
        mode_badge = QtWidgets.QLabel("✓ Colar tudo no final (Padrão / Mais Rápido)")
        mode_badge.setObjectName("CardBadge")

        mode_desc = QtWidgets.QLabel(
            "Segure a tecla de atalho, fale normalmente e, ao soltar, o texto completo, formatado e pontuado é colado de uma vez só onde seu cursor estiver."
        )
        mode_desc.setObjectName("CardDesc")
        mode_desc.setWordWrap(True)

        mode_card_layout.addWidget(mode_title)
        mode_card_layout.addWidget(mode_badge)
        mode_card_layout.addWidget(mode_desc)
        main_layout.addWidget(mode_card)

        # 5. Tecla de Atalho Push-to-Talk
        shortcut_layout = QtWidgets.QVBoxLayout()
        shortcut_layout.setSpacing(6)
        shortcut_lbl = QtWidgets.QLabel("Atalho Push-to-Talk (Manter pressionado para falar):")
        
        shortcut_row = QtWidgets.QHBoxLayout()
        shortcut_row.setSpacing(8)
        current_combo = " + ".join([k.upper() for k in self.config.get("trigger_keys", ["f8"])])
        self.shortcut_input = QtWidgets.QLineEdit(current_combo)
        self.shortcut_input.setReadOnly(True)
        self.shortcut_input.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

        self.btn_record_key = QtWidgets.QPushButton("Detectar Tecla")
        self.btn_record_key.setObjectName("SecondaryBtn")
        self.btn_record_key.clicked.connect(self._record_key)

        shortcut_row.addWidget(self.shortcut_input)
        shortcut_row.addWidget(self.btn_record_key)

        shortcut_hint = QtWidgets.QLabel("Segure a tecla configurada para falar. Ao soltar, a transcrição é colada onde seu cursor estiver.")
        shortcut_hint.setObjectName("HintLabel")
        shortcut_hint.setWordWrap(True)

        shortcut_layout.addWidget(shortcut_lbl)
        shortcut_layout.addLayout(shortcut_row)
        shortcut_layout.addWidget(shortcut_hint)
        main_layout.addLayout(shortcut_layout)

        # 6. Microfone de Entrada
        mic_layout = QtWidgets.QVBoxLayout()
        mic_layout.setSpacing(6)
        mic_lbl = QtWidgets.QLabel("Microfone de Entrada:")
        self.mic_combo = QtWidgets.QComboBox()
        self.mic_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self._populate_microphones()
        mic_layout.addWidget(mic_lbl)
        mic_layout.addWidget(self.mic_combo)
        main_layout.addLayout(mic_layout)

        # 7. Altura da Pílula HUD na tela
        hud_layout = QtWidgets.QHBoxLayout()
        hud_lbl = QtWidgets.QLabel("Distância da base da tela (Pílula em pixels):")
        self.hud_spin = QtWidgets.QSpinBox()
        self.hud_spin.setRange(50, 1000)
        self.hud_spin.setValue(self.config.get("hud_bottom_offset", 350))
        self.hud_spin.setSuffix(" px")
        self.hud_spin.setMinimumWidth(110)
        hud_layout.addWidget(hud_lbl)
        hud_layout.addStretch()
        hud_layout.addWidget(self.hud_spin)
        main_layout.addLayout(hud_layout)

        # 8. Iniciar com o Windows
        self.autostart_chk = QtWidgets.QCheckBox("Iniciar com o Windows (ao ligar o computador)")
        self.autostart_chk.setChecked(self.config.get("autostart", False))
        main_layout.addWidget(self.autostart_chk)

        main_layout.addSpacing(6)

        # Botão Salvar
        self.btn_save = QtWidgets.QPushButton("Salvar Configurações")
        self.btn_save.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.btn_save.clicked.connect(self._manual_save_clicked)
        main_layout.addWidget(self.btn_save)

        self._toggle_engine_fields()

        # Conexão de sinais APÓS os campos estarem todos montados
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.engine_combo.currentIndexChanged.connect(self._on_field_changed)
        self.groq_input.textChanged.connect(self._on_field_changed)
        self.gemini_input.textChanged.connect(self._on_field_changed)
        self.mic_combo.currentIndexChanged.connect(self._on_field_changed)
        self.hud_spin.valueChanged.connect(self._on_field_changed)
        self.autostart_chk.toggled.connect(self._on_field_changed)

        scroll_area.setWidget(content_widget)
        root_layout.addWidget(scroll_area)

    def _on_theme_changed(self):
        new_theme = self.theme_combo.currentData()
        self.config["theme"] = new_theme
        self._apply_theme(new_theme)
        self._save_settings(feedback=False)

    def _toggle_engine_fields(self):
        engine = self.engine_combo.currentData()
        if engine == "groq":
            self.groq_box.show()
            self.gemini_box.hide()
        else:
            self.groq_box.hide()
            self.gemini_box.show()

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
                self._save_settings(feedback=False)

    def _on_field_changed(self):
        self._toggle_engine_fields()
        self._save_settings(feedback=False)

    def _manual_save_clicked(self):
        self._save_settings(feedback=True)

    def _save_settings(self, feedback: bool = False):
        self.config["theme"] = self.theme_combo.currentData()
        self.config["engine"] = self.engine_combo.currentData()
        self.config["groq_api_key"] = self.groq_input.text().strip()
        self.config["gemini_api_key"] = self.gemini_input.text().strip()
        self.config["microphone_index"] = self.mic_combo.currentData()
        self.config["hud_bottom_offset"] = self.hud_spin.value()
        self.config["autostart"] = self.autostart_chk.isChecked()

        config_manager.save_config(self.config)
        config_manager.set_windows_autostart(self.config["autostart"])

        self.config_saved.emit(self.config)

        if feedback:
            self.btn_save.setText("✓ Configurações Salvas!")
            QtCore.QTimer.singleShot(1500, lambda: self.btn_save.setText("Salvar Configurações"))

    def closeEvent(self, event):
        event.ignore()
        self.hide()
