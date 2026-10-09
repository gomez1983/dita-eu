# Especificação Técnica de Engenharia: Voice Transform (Dita-eu v1.2)

Documento executável de especificação técnica para implementação da funcionalidade **Voice Transform (Reescrita e Polimento de Seleção por Comando de Voz)** no aplicativo desktop **Dita-eu**.

---

## 1. Visão Geral do Recurso

O **Voice Transform** permite ao usuário selecionar qualquer bloco de texto já existente na tela (em editores de texto, e-mails, navegadores, WhatsApp, IDEs, etc.), acionar um atalho de voz secundário (`Shift + F8`), falar uma instrução em linguagem natural (ex.: *"deixe mais formal"*, *"reescreva em tom pirata"*, *"traduza para inglês coloquial"*, *"resuma os pontos principais"*) e ter o texto selecionado **substituído instantaneamente** pelo resultado transformado pela IA, sem perder o foco do cursor.

---

## 2. Princípios de Engenharia e Restrições Inegociáveis

1. **Zero Degradação da Arquitetura Atual:** Não alterar o fluxo principal de Push-to-Talk simples (`F8`). A funcionalidade atual de ditado deve continuar 100% idêntica.
2. **Compatibilidade com Motores Ativos (Groq e Gemini):**
   - Respeitar rigorosamente a preferência do usuário em `config.json` (`"engine": "groq"` ou `"engine": "gemini"`).
   - Se o motor for **Groq**: Usar Whisper Turbo para transcrever a instrução de voz + LLM ultrarrápida da Groq (`llama-3.3-70b-versatile` / `qwen/qwen3.8-27b`) para transformar o texto (~400ms total).
   - Se o motor for **Gemini**: Usar `gemini-flash-lite-latest` via Google GenAI SDK.
3. **100% Efêmero (Sem Persistência de Disco):** Áudios e textos transitam exclusivamente na memória RAM. Não gravar arquivos temporários em disco nem criar históricos locais.
4. **Preservação de Clipboard:** Ao capturar a seleção ou colar o resultado, o clipboard anterior do Windows (`Win + V`) deve ser restaurado de forma limpa.

---

## 3. Fluxo de Execução Passo a Passo

```text
[Usuário seleciona texto na tela]
              │
              ▼
[Usuário pressiona e SEGURA 'Shift + F8']
              │
              ├─► 1. Dita-eu captura o texto selecionado:
              │      - Salva o clipboard anterior.
              │      - Dispara Win32 SendInput (Ctrl + C).
              │      - Aguarda 40ms e lê o texto da seleção do clipboard.
              │
              ├─► 2. Se a seleção estiver vazia:
              │      - HUD exibe aviso rápido "Nenhum texto selecionado" e cancela com segurança.
              │
              ├─► 3. Se houver texto selecionado:
              │      - HUD flutuante abre com indicação visual: "✨ Transformar" (WS_EX_NOACTIVATE).
              │      - Microfone inicia captura de áudio da ordem de voz em memória RAM.
              │
              ▼
[Usuário fala o comando (ex: "reescreva em tom formal para cliente")]
              │
              ▼
[Usuário SOLTA o atalho 'Shift + F8']
              │
              ├─► 1. HUD muda para estado de processamento ("Processando transformação...").
              │
              ├─► 2. Motor de IA:
              │      a) Transcreve o áudio da instrução (Whisper / Gemini).
              │      b) Executa a transformação combinando (Texto Original + Instrução).
              │
              ├─► 3. Injeção direta:
              │      - Coloca o texto transformado no clipboard.
              │      - Dispara Win32 SendInput (Ctrl + V) por cima da seleção original (Substituição Direta).
              │      - Aguarda delay seguro (350ms) e restaura o clipboard anterior original do usuário.
              │
              ▼
[HUD é ocultado silenciosamente]
```

---

## 4. Prompt de Sistema da LLM de Transformação

Ao acionar a LLM para transformação de texto, utilizar rigorosamente o seguinte system prompt:

```text
Você é um assistente de reescrita e transformação cirúrgica de texto integrado diretamente ao cursor do sistema operacional.
Sua missão é pegar o [TEXTO_ORIGINAL] fornecido pelo usuário e reescrevê-lo estritamente de acordo com o [COMANDO_DE_VOZ].

Diretrizes estritas:
1. Retorne EXCLUSIVAMENTE o texto final transformado.
2. NUNCA adicione introduções ("Aqui está a reescrita:"), aspas no início/fim, explicações ou notas de rodapé.
3. Se o comando de voz for de tradução, traduza preservando o sentido e tom.
4. Se o comando de voz pedir um tom específico (formal, casual, pirata, direto, poético), incorpore o tom com maestria sem inventar informações inexistentes no texto original.
5. Mantenha as quebras de linha e estrutura de parágrafos coerentes com o formato do texto original, a menos que o comando peça explicitamente para alterar (ex: "transforme em tópicos").
```

---

## 5. Mapeamento dos Arquivos a Serem Modificados

| Arquivo | Modificações Necessárias |
|---|---|
| `config_manager.py` | Adicionar chave `"transform_trigger_keys": ["shift+f8"]` ao `DEFAULT_CONFIG`. |
| `transcriber.py` | Adicionar método `transform_text(original_text: str, instruction_audio_bytes: bytes) -> str` nas classes `GroqTranscriber`, `GeminiTranscriber` e na fachada `TranscriptionEngine`. |
| `overlay.py` | Adicionar suporte ao estado visual `"transform"` na pílula flutuante (ex.: exibir ícone de estrela/varinha e label "✨ Transformar"). |
| `injector.py` | Adicionar função auxiliar `get_selected_text() -> str` que salva o clipboard, dispara `Ctrl + C`, recupera a string e restaura o clipboard anterior caso a seleção esteja vazia. |
| `main.py` | Adicionar listener global para o atalho de transformação (`Shift + F8`), orquestrando a captura da seleção, gravação da ordem, chamada de transformação e injeção do resultado. |
| `settings_ui.py` | (Opcional/Secundário) Adicionar campo de detecção do atalho secundário de transformação caso desejado. |

---

## 6. Casos Extremos e Tratamento de Erros

- **Usuário aciona `Shift + F8` sem nenhum texto selecionado:**  
  O aplicativo não deve congelar nem capturar áudio em vão. A pílula deve exibir brevemente `"Selecione um texto primeiro"` e sumir após 1,5 segundos.
- **Falha de transcrição da instrução (áudio inaudível):**  
  Se a transcrição da ordem retornar vazia, cancelar a operação sem sobrescrever o texto da tela do usuário.
- **Watchdog Timeout:**  
  Manter o timer de segurança de 15s no HUD para garantir que a janela nunca fique travada na tela em caso de instabilidade na API.
