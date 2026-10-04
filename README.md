<div align="center">

# 🎙️ Dita-eu

**Ditado por voz ultrarrápido, inteligente e nativo para Windows (Push-to-Talk).**  
Injeção direta no cursor ativo via simulação Win32, preservação do histórico da área de transferência (`Win + V`) e pílula HUD flutuante inspirada no *Wispr Flow* e na experiência do *Antigravity*.

[![Windows](https://img.shields.io/badge/Plataforma-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](#)
[![PyQt5](https://img.shields.io/badge/UI-PyQt5-41CD52?logo=qt&logoColor=white)](#)
[![Groq](https://img.shields.io/badge/IA-Groq%20Whisper%20Turbo-F55036)](#)
[![Gemini](https://img.shields.io/badge/IA-Google%20Gemini%20Flash-8E75B2?logo=google&logoColor=white)](#)
[![License](https://img.shields.io/badge/Licen%C3%A7a-MIT-blue)](#)

</div>

---

## ⚡ Por que o Dita-eu?

Muitas ferramentas de ditado são lentas, exigem navegadores abertos, colam dados bagunçados ou poluem o histórico de cópia do sistema. O **Dita-eu** foi desenhado com 5 princípios inegociáveis:

1. **Push-to-Talk Instantâneo**: Segure a tecla configurada (ex: `F8`, `F6`, ou combos como `Shift + F4`) $\rightarrow$ fale $\rightarrow$ solte. O texto é transcrito e colado onde quer que esteja o cursor.
2. **Preservação de Clipboard (`Win + V`)**: Não polui seu histórico nem apaga textos fixados. O que você tinha copiado antes é preservado e restaurado.
3. **Não Rouba Foco (`WS_EX_NOACTIVATE`)**: A pílula na tela nunca rouba o foco do app onde você está digitando (VS Code, Notion, WhatsApp, Word, Slack, Terminais, etc.).
4. **Duplo Motor de IA com Fallback**:
   - **⚡ Groq Whisper (`whisper-large-v3-turbo`)**: Velocidade extrema de **~250ms a 350ms**.
   - **✨ Google Gemini (`gemini-flash-latest`)**: Compreensão semântica profunda e pontuação expressiva.
5. **Modo Claro & Escuro com Alto Contraste**: Padrão visual baseado nas diretrizes de acessibilidade **WCAG AAA / AA**, mantendo leitura perfeita em qualquer condição de luz.

---

## 🖥️ Como Funciona o Fluxo

```text
[Atalho Push-to-Talk Pressionado]
               │
               ▼
     [Pílula HUD Flutuante]   <── Não rouba foco da janela ativa
               │
               ▼
       [Gravação de Áudio]    <── Captura 100% em memória RAM (PCM 16kHz)
               │
       [Soltura do Atalho]
               │
               ▼
      [Motor de Transcrição]  <── Groq Whisper (~300ms) ou Gemini Flash
               │
               ▼
       [Injeção de Texto]     <── Simulação Win32 Ctrl+V + restaura Clipboard
               │
               ▼
        [HUD Ocultado]
```

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem**: Python 3.10+
- **Interface Gráfica**: PyQt5 (com temas customizados Dark/Light)
- **Captura de Áudio**: `sounddevice`, `numpy`, `scipy` (PCM 16kHz em memória, sem I/O de disco)
- **Hooks de Teclado**: `pynput` (escuta global de atalhos e combos)
- **Automação Win32**: `pywin32` (`keybd_event`, manipulação nativa de clipboard e flags de janela)
- **APIs de IA**: Groq Cloud SDK / Requests e Google GenAI SDK

---

## 📦 Como Instalar e Rodar Localmente

### 1. Pré-requisitos
- Windows 10 ou 11 (64-bit)
- Python 3.10 ou superior
- Git instalado

### 2. Clonar o Repositório
```powershell
git clone https://github.com/SEU-USUARIO/dita-eu.git
cd dita-eu
```

### 3. Criar e Ativar Ambiente Virtual
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 4. Instalar Dependências
```powershell
pip install -r requirements.txt
```

### 5. Configurar Chaves de API
Copie o arquivo de exemplo e insira suas credenciais:
```powershell
copy .env.example .env
```

> **Dica**: Você também pode colar sua chave da Groq ou do Gemini diretamente na interface visual do Dita-eu, que ela será salva localmente em `config.json`.

### 6. Executar o Aplicativo
```powershell
python main.py
```

O ícone do microfone surgirá na bandeja do sistema (ao lado do relógio do Windows). Dê duplo clique nele a qualquer momento para abrir as configurações.

---

## 🚀 Como Gerar o Executável Standalone (.exe)

O Dita-eu pode ser compilado para um executável único que não exige Python instalado na máquina:

```powershell
pip install pyinstaller

# Compilar com ícone embutido e sem tela preta de terminal:
pyinstaller --noconsole --onefile --clean `
    --name "Dita-eu" `
    --icon "icon.ico" `
    --add-data "icon.ico;." `
    --add-data "icon_white.png;." `
    --add-data "radio-mic.svg;." `
    --paths "." `
    --hidden-import config_manager `
    --hidden-import settings_ui `
    --hidden-import audio_recorder `
    --hidden-import transcriber `
    --hidden-import injector `
    --hidden-import overlay `
    main.py
```

O arquivo gerado estará disponível na pasta `dist/Dita-eu.exe`.

---

## 🎨 Acessibilidade & Critérios de Contraste

O Dita-eu possui seletor em tempo real entre **Modo Escuro** e **Modo Claro**, projetado sob critérios rígidos de contraste:

| Modo | Fundo Principal | Texto Principal | Contraste (Ratio) | Norma |
|---|---|---|---|---|
| **🌙 Modo Escuro** | `#09090b` (Obsidian) | `#ffffff` (Branco Puro) | **21.0 : 1** | WCAG AAA |
| **☀️ Modo Claro** | `#f8fafc` (Slate Claro) | `#0f172a` (Ardósia Escura) | **18.2 : 1** | WCAG AAA |

---

## 📂 Estrutura de Arquivos

```text
dita-eu/
├── audio_recorder.py     # Captura de áudio em buffer de memória com cálculo RMS de volume
├── config_manager.py     # Gerenciamento de preferências persistentes e inicialização do Windows
├── injector.py           # Injeção via SendInput (Ctrl+V) e restauração de clipboard
├── main.py               # Ponto de entrada, listener de atalhos e System Tray
├── overlay.py            # Pílula flutuante minimalista (220x52px) com feedback de pulso
├── settings_ui.py        # Interface gráfica com detector de atalhos e seletor de tema
├── transcriber.py        # Clientes Groq Whisper Turbo e Google Gemini Flash com fallback
├── icon.ico              # Ícone para executável e barra de tarefas do Windows
├── icon_white.png        # Ícone para UI
├── radio-mic.svg         # Vetor original
├── requirements.txt      # Dependências mínimas de produção
├── .env.example          # Modelo de variáveis de ambiente
├── .gitignore            # Proteção contra vazamento de chaves e builds
└── README.md             # Esta documentação
```

---

## 🛡️ Segurança & Privacidade
- **Zero Vazamento**: Arquivos `.env`, `config.json` e chaves de API estão incluídos no `.gitignore` para proteção das credenciais.
- **Áudio em Memória**: O áudio capturado pelo microfone nunca é gravado como arquivo temporário em disco; ele trafega exclusivamente na memória RAM e é descartado após o envio.

---

## 📄 Licença

Distribuído sob a licença **MIT**. Veja `LICENSE` para mais detalhes.
