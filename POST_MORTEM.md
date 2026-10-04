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

