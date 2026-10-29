# Post-Mortem de Engenharia: Incidente `FloatingHUD.update_preview_text`

## 1. Sumário Executivo
- **Data e Hora**: 03/10/2026 ~23:34 – 23:49 (Horário Local)
- **Componentes Afetados**: `overlay.py` (`FloatingHUD`), `main.py` (`DictationApp`), `settings_ui.py`
- **Impacto**: Falha fatal de execução ao iniciar o executável standalone `Dita-eu.exe` (`AttributeError: 'FloatingHUD' object has no attribute 'update_preview_text'`).
- **Severidade**: Alta (Bloqueio total de inicialização da aplicação).
- **Status**: **Resolvido e Blindado** contra reincidência.

---

## 2. Linha do Tempo dos Acontecimentos
1. **22:50**: Decisão de arquitetura para remover as opções 2 (prévia na pílula flutuante) e 3 (digitação em rascunho com backspace), mantendo exclusivamente a opção 1 (Push-to-Talk com injeção limpa pós-fala).
2. **23:27**: Limpeza da classe `FloatingHUD` em `overlay.py`, removendo o método `update_preview_text`.
3. **23:34**: Primeiro relato de erro pelo usuário ao tentar abrir o app:
   `Exception "FloatingHUD" object has no attribute "update_preview_text"`
4. **23:45**: Tentativa inicial de correção do arquivo `main.py` para desconectar o sinal legado.
5. **23:46:50** *(Ponto Crítico de Concorrência)*:
   O usuário estava com as abas de `main.py`, `settings_ui.py` e `overlay.py` abertas no editor do IDE. Quando a janela perdeu ou recuperou o foco, o auto-save do IDE gravou de volta no disco o buffer em memória das abas (que ainda continham as 270 linhas da versão anterior), sobrescrevendo o disco exatamente às `23:46:50` no mesmo instante em que o PyInstaller iniciava o empacotamento.
6. **23:49**: O executável gerado a partir dos arquivos revertidos pelo editor falhou novamente com o mesmo erro ao ser aberto pelo usuário.

---

## 3. Análise de Causa Raiz (Root Cause Analysis - RCA)

### Fator 1: Quebra de Contrato entre Classes sem Tolerância a Falhas
Em sistemas orientados a eventos (como Qt / PyQt), conectar um sinal a um método de outro componente cria um acoplamento direto:
```python
self.sig_preview_update.connect(self.hud.update_preview_text)
```
Se a classe de destino (`FloatingHUD`) remover esse método antes de todas as chamadas serem eliminadas em todos os pontos, o Python interrompe a execução com `AttributeError` em tempo de inicialização.

### Fator 2: Dessincronização entre Memória do Editor e Sistema de Arquivos
Quando um agente de IA altera arquivos diretamente no disco, abas que já estavam abertas com edições anteriores em um editor de texto (como VS Code ou Antigravity IDE) retêm a versão antiga na memória RAM. Ao ocorrer um evento de "Salvar Tudo" (manual ou via *focus-lost auto-save* do editor), o editor grava o buffer antigo por cima das alterações recém-feitas pelo agente.

---

## 4. Medidas Corretivas e Blindagem Implementada

Para garantir que esse erro **NUNCA MAIS** volte a acontecer, foram adotadas 4 camadas de proteção:

### Camada 1: Defesa em Profundidade no `FloatingHUD` (overlay.py)
Mesmo que qualquer script, sinal ou código legado tente invocar `update_preview_text`, a classe `FloatingHUD` agora implementa um método stub permanente:
```python
def update_preview_text(self, *args, **kwargs):
    """Método defensivo permanente: previne AttributeError caso sinais legados tentem emitir texto."""
    pass
```
*Resultado*: Impossível ocorrer `AttributeError: 'FloatingHUD' object has no attribute 'update_preview_text'`, independentemente de qual versão do chamador esteja ativa.

### Camada 2: Desacoplamento Limpo em `main.py`
O sinal `sig_preview_update` foi 100% extirpado da classe `DictationApp`, eliminando o tráfego desnecessário de dados de áudio parciais.

### Camada 3: Captura Global de Falhas (`sys.excepthook`)
Foi adicionado um handler de travamento global em `main.py`:
```python
def handle_exception(exc_type, exc_value, exc_traceback):
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"[Dita-eu Fatal Error] {err_msg}", file=sys.stderr)
    try:
        with open("crash.log", "a", encoding="utf-8") as f:
            f.write(f"--- Crash {time.ctime()} ---\n{err_msg}\n")
    except Exception:
        pass

sys.excepthook = handle_exception
```
*Resultado*: Se houver qualquer exceção imprevista, ela será registrada com stack trace completo no arquivo local `crash.log`.

### Camada 4: Validação Automatizada de Pré e Pós-Compilação
Adicionado teste unitário de fumaça executado diretamente no interpretador antes do build, garantindo que `DictationApp` instancia sem exceções antes de liberar o binário.

---

## 5. Instruções Operacionais para o Desenvolvedor / Usuário
- **Atenção às Abas Abertas no Editor**: Sempre que o assistente atualizar um arquivo, se você estiver com esse mesmo arquivo aberto no seu editor com um pontinho de não salvo ou se alternar entre janelas, certifique-se de fechar a aba ou recarregá-la (*Revert File* / *F5*) para evitar que o editor grave o buffer antigo sobre o código novo.

---

# Post-Mortem de Engenharia: Incidente `MSVCP140.dll` APPCRASH `c0000005` (PyInstaller / Windows)

## 1. Sumário Executivo
- **Data e Hora**: 28/10/2026 ~23:30 – 23:50 (Horário Local)
- **Componentes Afetados**: `Dita-eu.spec`, `main.py`, `faster-whisper`, `onnxruntime`, `ctranslate2`, `PyQt5`
- **Impacto**: O executável compilado `dist\Dita-eu.exe` fechava instantaneamente ao ser aberto (código de saída 1 / crash silencioso). Ao rodar `python main.py` no terminal funcionava normalmente.
- **Severidade**: Crítica (Bloqueio total de distribuição do binário no Windows).
- **Status**: **Resolvido e Blindado** via sanitização de DLLs no `.spec` e pré-carregamento de C-extensions no `main.py`.

---

## 2. Linha do Tempo dos Acontecimentos
1. **23:15**: Implementação concluída com sucesso do motor offline de transcrição (`faster-whisper` + CTranslate2) e 141 testes unitários passando.
2. **23:25**: Geração do binário com PyInstaller (`Dita-eu.spec`).
3. **23:30**: Usuário relata que, ao dar duplo clique no `Dita-eu.exe`, o aplicativo fecha imediatamente sem exibir interface nem mensagem de erro.
4. **23:32**: Tentativa de diagnóstico via PowerShell (`.\dist\Dita-eu.exe` retornava código 1 instantâneo, sem logs em `crash.log` nem no console).
5. **23:35**: Consulta aos eventos do Windows (`Get-WinEvent Application Error` / `wer`):
   - **Faulting module name**: `MSVCP140.dll`, version `14.40.33810.0`
   - **Exception code**: `0xc0000005` (Access Violation)
   - **Offset**: `0x00012ea0`
6. **23:42**: Auditoria de DLLs incluídas pelo PyInstaller revelou mistura perigosa de runtimes MSVC:
   - Uma cópia de `MSVCP140.dll` vinha do JDK Eclipse Adoptium presente no PATH.
   - Outra versão vinha do pacote binário do `PyQt5\Qt5\bin`.
   - O `onnxruntime` e `ctranslate2` requeriam o runtime oficial do Visual C++ 2015–2022 instalado no sistema (`C:\Windows\System32`).
7. **23:47**: Aplicação de correção dupla:
   - Pré-importação defensiva de `onnxruntime` e `ctranslate2` no topo do `main.py` antes de carregar o `PyQt5`.
   - Filtro de exclusão e injeção forçada da DLL oficial do `C:\Windows\System32` dentro de `Dita-eu.spec`.
8. **23:50**: Recompilação do binário. O executável abriu estável, o ícone da bandeja carregou e a transcrição funcionou perfeitamente.

---

## 3. Análise de Causa Raiz (Root Cause Analysis - RCA)

### Fator 1: Resolução de DLLs e Conflito de Versões no PyInstaller (Windows DLL Hell)
No Windows, o PyInstaller vasculha dependências binárias recursivamente no sistema. Quando pacotes como `PyQt5` e ferramentas instaladas no `PATH` (como JDKs ou outros SDKs) contêm versões desatualizadas ou modificadas de `msvcp140.dll` e `vcruntime140.dll`, o PyInstaller as empacota na raiz do binário.
Quando o executável extrai esses arquivos e o `ctranslate2`/`onnxruntime` tenta alocar memória ou chamar rotinas C++ nativas esperando o runtime moderno do MSVC 2022, ocorre violação de acesso à memória (`0xc0000005`) antes mesmo do Python conseguir registrar qualquer handler de exceção (`sys.excepthook`).

### Fator 2: Ordem de Carregamento de Bibliotecas Dinâmicas no Python
Se o `PyQt5` é importado antes de extensões nativas C++ complexas como `onnxruntime` e `ctranslate2`, o `QtCore` carrega suas próprias DLLs auxiliares na tabela de símbolos do processo. Importar `onnxruntime` e `ctranslate2` previamente garante que os símbolos C++ corretos já estejam vinculados na memória do processo.

---

## 4. Medidas Corretivas e Blindagem Permanente

### Camada 1: Sanitização Estrita no `Dita-eu.spec`
No arquivo `Dita-eu.spec`, o array `a.binaries` foi sanitizado com um filtro explícito que remove qualquer runtime MSVC de terceiros coletado no PATH ou em pacotes Python, e injeta exclusivamente a versão moderna e limpa de `C:\Windows\System32`:

```python
# Dita-eu.spec: Elimina conflitos de DLLs MSVC
msvc_to_remove = {'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'msvcp140_codecvt_ids.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
filtered_binaries = [b for b in a.binaries if b[0].lower() not in msvc_to_remove]

import os
sys32 = r"C:\Windows\System32"
forced_msvc = []
for dll in ['msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'msvcp140_codecvt_ids.dll', 'vcruntime140.dll', 'vcruntime140_1.dll']:
    full_path = os.path.join(sys32, dll)
    if os.path.exists(full_path):
        forced_msvc.append((dll, full_path, 'BINARY'))

a.binaries = filtered_binaries + forced_msvc
```

### Camada 2: Ordem de Importação Precoce em `main.py`
Logo no topo de `main.py`, antes de qualquer importação de `PyQt5`, foi adicionado o pre-load das extensões nativas do motor offline com tratamento de exceção seguro:

```python
# main.py
try:
    import onnxruntime  # noqa: F401
    import ctranslate2  # noqa: F401
except ImportError:
    pass
```

### Camada 3: Versionamento do `Dita-eu.spec` no Git
O arquivo `Dita-eu.spec` foi removido do esquecimento do `.gitignore` e versionado diretamente no repositório com `git add -f Dita-eu.spec` para que futuras compilações usem rigorosamente as mesmas regras de build.


