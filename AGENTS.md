# Regras do Projeto Dita-eu

Como assistente de IA trabalhando no projeto **Dita-eu**, você DEVE seguir rigorosamente as seguintes diretrizes:

## 1. Consulta Obrigatória ao Post-Mortem
- Antes de propor refatorações arquiteturais, alterar empacotamento com PyInstaller ou modificar o ciclo de vida da UI/Engine, **consulte o arquivo `POST_MORTEM.md` na raiz do projeto**.
- Nunca reintroduza métodos ou padrões de código que já causaram incidentes registrados no `POST_MORTEM.md`.

## 2. Cuidados com a Interface e Sinais (Qt / PyQt5)
- **Incidentes passados**: Conectar sinais a métodos que podem ser removidos causa `AttributeError` em tempo de execução.
- Sempre mantenha métodos defensivos (*stubs*) ou use `hasattr()` antes de emitir sinais legados na UI.
- Nunca remova métodos públicos de componentes como `FloatingHUD` sem verificar todos os `.connect()` em `main.py` e `settings_ui.py`.

## 3. Cuidados com Executável Standalone e Runtimes C++ (Windows)
- O aplicativo usa extensões nativas C++ pesadas (`onnxruntime`, `ctranslate2`, `PyQt5`).
- **Ordem de Importação**: Em `main.py`, as bibliotecas `onnxruntime` e `ctranslate2` DEVEM ser importadas antes de `PyQt5` para evitar conflitos de símbolos na tabela de DLLs do Windows.
- **Compilação PyInstaller**: Sempre utilize e respeite o arquivo `Dita-eu.spec`. O script possui sanitização explícita para evitar que DLLs conflitantes (`MSVCP140.dll` / `VCRUNTIME140.dll`) de JDKs ou ambientes externos causem o crash silencioso `c0000005`.
- **Ativos Obrigatórios**: O diretório `assets` do Silero VAD (`faster_whisper/assets`) deve sempre ser incluído no `.spec`.

## 4. Concorrência com Abas Abertas no Editor
- Quando o usuário estiver com abas abertas no IDE, arquivos editados em disco podem ser sobrescritos pelo buffer do editor se a janela perder/ganhar foco. Tenha cautela ao instruir ou aplicar edits simultâneos em momentos de build.

