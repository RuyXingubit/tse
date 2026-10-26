# v6 — Legendas em Todos os Gráficos SVG, Publicação dos Relatórios em `docs/` e `README.md` de Transparência Pública

**Data/Hora:** 2026-10-26 19:13 (BRT)

## 1. Solicitações do Usuário
1. **Legendas em todos os gráficos SVG:**
   - Todos os gráficos (dispersão/scatter, barras simples e barras duplas) devem ter barra de legenda vetorial no topo dentro do próprio `<svg>`, explicando com clareza todas as cores, séries e linhas tracejadas de referência, além de títulos explícitos nos eixos X e Y.
2. **Relatórios publicados dentro de `docs/` (repositório público no GitHub):**
   - Os dados brutos e intermediários pesados (`resumo_secoes.jsonl`, snapshots, etc.) permanecem no HD externo (`/Volumes/240/TSE/`).
   - Os relatórios finais (`relatorio_pa_1t_2t.html`, `relatorio_pa_1t_2t_v2.html`, `prioridade_fiscais_pa.csv`, `auditoria_mesarios_biometria.json`, `analise_consolidada_v2.json`) devem ficar salvos também em `docs/relatorios/pa/` para versionamento e acesso público imediato no GitHub.
3. **`README.md` completo, técnico e focado em fatos objetivos e reprodutibilidade:**
   - Explicar o propósito estritamente técnico e científico do projeto: extrair e auditar exclusivamente os **fatos matemáticos e registros forenses contidos nos arquivos públicos oficiais do TSE** (`resultados.tse.jus.br`), sem opiniões subjetivas.
   - Detalhar a validação criptográfica (`SHA-256` e `SHA-512`), a arquitetura dos pacotes oficiais (`-bu.dat`, `-log.jez`, `-vota.vsc`), como qualquer pessoa pode auditar o código-fonte, rodar a suíte de testes unitários e reproduzir integralmente os relatórios.
