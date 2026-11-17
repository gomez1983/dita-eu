# Fontes embutidas

A interface do Dita-eu usa três famílias do projeto de design (Stitch). Todas são
distribuídas sob a **SIL Open Font License 1.1** (https://openfontlicense.org), que
permite uso, cópia e redistribuição, inclusive embutidas em aplicativos.

| Família | Uso | Arquivos | Origem |
| --- | --- | --- | --- |
| Inter | corpo e rótulos | `Inter-Regular/Medium/SemiBold/Bold.ttf` | https://rsms.me/inter |
| JetBrains Mono | atalhos, badges, editor de prompt | `JetBrainsMono-Regular/Medium/SemiBold/Bold.ttf` | https://www.jetbrains.com/lp/mono |
| Plus Jakarta Sans | títulos | `PlusJakartaSans-SemiBold.ttf`, `PlusJakartaSans-Bold.ttf` | https://github.com/tokotype/PlusJakartaSans |

`ui_components.load_fonts()` registra tudo que estiver nesta pasta. Sem Plus Jakarta Sans
os títulos usam Inter; sem nenhuma delas a interface cai no Segoe UI. O `Dita-eu.spec`
empacota a pasta `fonts/` inteira.

Se o aplicativo for distribuído publicamente, inclua junto os arquivos `OFL.txt` oficiais
de cada família.
