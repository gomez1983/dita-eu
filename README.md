<div align="center">

# 🎙️ Dita-eu

**Ditado por voz ultrarrápido, reescrita inteligente por comando de voz (Voice Transform) e injeção nativa para Windows (Push-to-Talk).**  
Injeção direta no cursor ativo via simulação Win32, preservação total do histórico da área de transferência (`Win + V`) e pílula HUD flutuante inspirada no *Wispr Flow* e na experiência do *Antigravity*.

[![Windows](https://img.shields.io/badge/Plataforma-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](#)
[![PyQt5](https://img.shields.io/badge/UI-PyQt5-41CD52?logo=qt&logoColor=white)](#)
[![Groq](https://img.shields.io/badge/IA-Groq%20Whisper%20Turbo-F55036)](#)
[![Gemini](https://img.shields.io/badge/IA-Google%20Gemini%20Flash-8E75B2?logo=google&logoColor=white)](#)
[![License](https://img.shields.io/badge/Licen%C3%A7a-MIT-blue)](#)

</div>

---

## ⚡ Por que o Dita-eu?

Muitas ferramentas de ditado são lentas, exigem navegadores abertos, colam dados bagunçados ou poluem o histórico de cópia do sistema. O **Dita-eu** foi desenhado com princípios inegociáveis:

1. **Dois Modos de Ação Instantânea**:
   * **Ditado Contínuo (`F8`)**: Segure a tecla configurada $\rightarrow$ fale $\rightarrow$ solte. O texto é transcrito e digitado diretamente onde quer que esteja o cursor.
   * **Voice Transform (`Shift + F8`)**: Selecione qualquer texto já existente na tela $\rightarrow$ segure `Shift + F8` $\rightarrow$ fale uma instrução em voz natural (*"deixe mais formal"*, *"resuma em tópicos"*, *"reescreva em tom persuasivo"*, *"traduza para espanhol"*) $\rightarrow$ o texto selecionado é substituído cirurgicamente pelo resultado transformado pela IA.
2. **Preservação de Clipboard (`Win + V`)**: Não polui seu histórico nem apaga textos fixados. O que você tinha copiado antes é preservado e restaurado com delay de segurança de 350ms.
3. **Não Rouba Foco (`WS_EX_NOACTIVATE`)**: A pílula na tela nunca rouba o foco do app onde você está digitando (VS Code, Notion, WhatsApp, Word, Slack, Terminais, etc.).
4. **🌐 Modo Tradução Coloquial Instantânea**: Traduz a fala em tempo real para **Inglês (`EN`)**, **Espanhol (`ES`)**, **Francês (`FR`)**, **Alemão (`DE`)** ou **Italiano (`IT`)**, preservando rigorosamente o tom natural, casual e coloquial da fala humana nativa (sem soar como tradutor robótico). Alternável em 1 clique pelo menu da bandeja do sistema (System Tray).
5. **Duplo Motor de IA com Fallback Automático**:
   * **⚡ Groq Cloud (`whisper-large-v3-turbo` + LLMs `llama-3.3-70b` / `qwen/qwen3.8-27b`)**: Velocidade extrema de **~250ms a 400ms** com generosa cota gratuita diária.
   * **✨ Google Gemini (`gemini-flash-lite-latest`)**: Compreensão semântica profunda, latência ultrabaixa e redundância transparente.
6. **Modo Claro & Escuro com Alto Contraste**: Padrão visual baseado nas diretrizes de acessibilidade **WCAG AAA / AA**, com alternância dinâmica de logotipo e controles em Toggle Switch estilo Windows 11.

---

## 🖥️ Como Funcionam os Fluxos de Execução

### 1. Fluxo de Ditado Push-to-Talk (`F8`)
```text
[Atalho Push-to-Talk Pressionado: F8]
               │
               ▼
     [Pílula HUD Flutuante]   <── "Ouvindo..." (Não rouba foco)
               │
               ▼
       [Gravação de Áudio]    <── Captura 100% em memória RAM (PCM 16kHz)
               │
       [Soltura do Atalho]
               │
               ▼
      [Motor de Transcrição]  <── Groq Whisper (~250ms) ou Gemini Flash Lite
               │
               ▼
       [Injeção de Texto]     <── Simulação Win32 Ctrl+V + restaura Clipboard
               │
               ▼
        [HUD Ocultado]
```

### 2. Fluxo do Voice Transform (`Shift + F8`)
```text
[Usuário seleciona texto existente na tela]
               │
               ▼
[Pressiona e SEGURA 'Shift + F8']
               │
               ├─► Captura a seleção via Win32 (preserva histórico de clipboard)
               ├─► HUD exibe "✨ Transformar" com pulso dinâmico de voz
               └─► Microfone grava a instrução falada em memória RAM
               │
[Usuário fala o comando (ex: "deixe mais conciso e formal")]
               │
               ▼
[Usuário SOLTA o atalho 'Shift + F8']
               │
               ├─► HUD muda para "Reescrevendo..."
               ├─► IA processa [Texto Selecionado + Comando de Voz]
               ├─► Injeção direta: substitui a seleção original pelo novo texto
               └─► Restaura o clipboard anterior do usuário com segurança
               │
               ▼
        [HUD Ocultado]
```

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem**: Python 3.10+
- **Interface Gráfica**: PyQt5 (com suporte nativo a temas Dark/Light e animações em Toggle Switch)
- **Captura de Áudio**: `sounddevice`, `numpy`, `scipy` (PCM 16kHz em memória, zero I/O de disco)
- **Hooks Globais de Teclado**: `pynput` (captura não-bloqueante de atalhos e combos simultâneos)
- **Automação Win32**: `pywin32` (`keybd_event`, manipulação nativa de clipboard e flags de janela `WS_EX_NOACTIVATE`)
- **APIs de IA**: Groq Cloud SDK / Requests e Google GenAI SDK

---

## 📦 Como Instalar e Rodar Localmente

### 1. Pré-requisitos
- Windows 10 ou 11 (64-bit)
- Python 3.10 ou superior
- Git instalado

### 2. Clonar o Repositório
```powershell
git clone https://github.com/gomez1983/dita-eu.git
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

> **Dica**: O aplicativo localiza suas chaves tanto no arquivo `.env` quanto no arquivo `config.json`, sem risco de sobrescrita.

### 6. Executar o Aplicativo
```powershell
python main.py
```

O ícone do microfone surgirá na bandeja do sistema (ao lado do relógio do Windows). Dê duplo clique nele a qualquer momento para abrir as configurações.

### 7. Executar os Testes Unitários
O projeto inclui uma suíte completa de testes cobrindo engines, HUD, injeção e Voice Transform:
```powershell
python -m unittest discover tests
```

---

## 🚀 Como Gerar o Executável Standalone (.exe)

O Dita-eu pode ser compilado para um executável único que não exige Python instalado na máquina:

```powershell
pip install pyinstaller

# Compilar com ícones embutidos e sem tela preta de terminal:
pyinstaller --clean Dita-eu.spec
```

O arquivo gerado estará disponível na pasta `dist/Dita-eu.exe`.

---

## 🎨 Acessibilidade & Critérios de Contraste

O Dita-eu possui seletor em tempo real entre **Modo Escuro** e **Modo Claro**, projetado sob critérios rígidos de contraste:

| Modo | Fundo Principal | Texto Principal | Contraste (Ratio) | Norma |
|---|---|---|---|---|
| **🌙 Modo Escuro** | `#09090b` (Obsidian) | `#ffffff` (Branco Puro) | **21.0 : 1** | WCAG AAA |
| **☀️ Modo Claro** | `#f8fafc` (Slate Claro) | `#0f172a` (Ardósia Escura) | **18.2 : 1** | WCAG AAA |

O logotipo alterna dinamicamente entre branco (`icon_white.png`) e escuro (`icon.png`) conforme o tema ativo, garantindo visibilidade perfeita.

---

## 📂 Estrutura de Arquivos

```text
dita-eu/
├── audio_recorder.py          # Captura de áudio em buffer de memória com cálculo RMS de volume
├── config_manager.py          # Gerenciamento de preferências persistentes e inicialização do Windows
├── injector.py                # Injeção via SendInput, captura de seleção e restauração de clipboard
├── main.py                    # Ponto de entrada, listeners de atalhos (F8 e Shift+F8) e System Tray
├── overlay.py                 # Pílula flutuante minimalista com feedback de pulso e badges de estado
├── settings_ui.py             # Interface gráfica com Toggle Switches modernos e seletores
├── transcriber.py             # Clientes Groq e Gemini com pipeline de ditado, tradução e Voice Transform
├── icon.ico                   # Ícone para executável e barra de tarefas do Windows
├── icon.png                   # Logotipo escuro para Modo Claro
├── icon_white.png             # Logotipo claro para Modo Escuro
├── radio-mic.svg              # Vetor original
├── FEATURE_VOICE_TRANSFORM.md # Especificação técnica detalhada da funcionalidade Voice Transform
├── tests/                     # Suíte de testes unitários automatizados (engines, hotkeys, HUD, injector)
├── requirements.txt           # Dependências mínimas de produção
├── .env.example               # Modelo de variáveis de ambiente
├── .gitignore                 # Proteção contra vazamento de chaves e builds
└── README.md                  # Esta documentação
```

---

## 🛡️ Segurança & Privacidade
- **Zero Vazamento**: Arquivos `.env`, `config.json` e chaves de API estão incluídos no `.gitignore` para proteção das credenciais.
- **Áudio e Texto 100% em Memória RAM**: O áudio capturado e os trechos de texto selecionados nunca são gravados como arquivos temporários em disco; eles trafegam exclusivamente na memória e são descartados imediatamente após o envio.

---

## 📊 Como Funcionam os Limites, Tokens e Custos (Explicado de Forma Simples)

O **Dita-eu** opera sob o nível gratuito da **Groq Cloud** e do **Google Gemini**, cujo custo é **zero** e funciona como uma **torneira com fluxo contínuo** (que se renova automaticamente):

### 1. Quando os Limites Zeram?
- **14.400 Requisições por Dia (Groq)**: Cada vez que você segura o atalho, dita ou transforma e solta conta como 1 requisição. Esse limite **zera todo dia às 21:00** (horário de Brasília).
- **Apertadas por Minuto**: Você pode acionar de **30 a 60 vezes a cada 60 segundos** (renova a cada minuto).
- **Gemini Flash Lite (Fallback)**: Oferece **1.500 requisições diárias gratuitas** adicionais para cobrir qualquer oscilação.

### 2. Consumo de Tokens
- **Modo Normal (Transcrição em Português)**: **Zero tokens de LLM**. O Whisper processa áudio diretamente (direito a até 1 hora de fala contínua por hora, sem custos).
- **Modo Tradução / Voice Transform**: Consome cerca de **150 a 300 tokens** por reescrita/tradução. Com as franquias gratuitas diárias, dá para transformar milhares de parágrafos por dia.

Um usuário comum trabalhando o dia inteiro consome menos de **2%** da franquia gratuita diária.

---

## 🗺️ Roadmap do Projeto

### ✅ Concluído (v1.0 até v1.2)
- [x] **Push-to-Talk nativo com atalhos globais personalizáveis** (`F8`, `F6`, combos como `Shift + F4`).
- [x] **Voice Transform (`Shift + F8`)**: Reescrita cirúrgica de texto selecionado na tela via comando de voz em linguagem natural.
- [x] **Preservação de histórico da área de transferência (`Win + V`)** com delay de segurança de 350ms.
- [x] **Pílula HUD flutuante moderna** sem roubo de foco (`WS_EX_NOACTIVATE`) e com pulso dinâmico de volume.
- [x] **Suporte a Modo Claro e Modo Escuro** sob critérios rigorosos de contraste **WCAG AAA**.
- [x] **Toggle Switches modernos** estilo Windows 11 para alternância de tema e autoinicialização com o Windows.
- [x] **Modo Tradução Coloquial Instantânea** para 5 idiomas (`EN`, `ES`, `FR`, `DE`, `IT`) com tom 100% natural e casual.
- [x] **Submenu dinâmico na bandeja do sistema (System Tray)** para alternar o idioma de tradução instantaneamente.
- [x] **Badge visual no HUD** indicando o idioma de tradução ativo (ex.: `🌐 EN`) e estado de transformação (`✨ Transformar`).
- [x] **Arquitetura híbrida de IA com redundância**:
  - Groq Whisper Turbo (~250ms) + LLM Groq (~250ms) com ~7.200 reqs/dia gratuitas.
  - Google Gemini Flash Lite com ~1.500 reqs/dia gratuitas e fallback automático.
- [x] **Watchdog de segurança contra congelamento de interface** e persistência protegida de credenciais para compilação `.exe`.
- [x] **Suíte de testes automatizados** com cobertura de 89 casos de teste unitários.

### 📌 Próximos Passos (Futuro)
- [ ] **Detecção Automática do Idioma de Entrada**: Falar em qualquer língua e o motor identificar o idioma sem configuração manual.
- [ ] **Dicionário e Substituições Personalizadas**: Capacidade de cadastrar jargões técnicos específicos, siglas e nomes de projetos personalizados.
- [ ] **Histórico Local Opcional de Transcrições**: Painel retrátil seguro com busca local para consultar o que foi falado recentemente.
- [ ] **Suporte a Botões do Mouse na Interface**: Detecção nativa dos botões laterais (Mouse 4 e Mouse 5) no seletor de atalhos.
- [ ] **Suporte Multiplataforma**: Portabilidade da lógica para macOS e Linux.

---

## 📄 Licença

Distribuído sob a licença **MIT**. Veja `LICENSE` para mais detalhes.
