# v3 — Decisão: Estado do Pará (`pa`) Primeiro e Consolidação do Escopo

Data: 2026-10-26
Continuação de `v2_streaming_resumo_e_relatorio_html_pdf.md` (preservado).

## Decisões Aprovadas pelo Usuário
1. **Estado piloto:** **Pará (`pa`)** (~20.827 urnas). Se o resultado for aprovado, o mesmo comando e arquitetura serão usados para os demais estados.
2. **Modo de operação (Zero Acúmulo de Brutos):**
   - Baixar em memória por seção os arquivos do 1º turno (`3220`) e do 2º turno (`3221`), validar criptograficamente (`vota.vsc` SHA-256 + `bu.dat` e `log.jez` SHA-512), comparar os dois turnos, gravar apenas o registro resumido em `auditoria/pa/resumo_secoes.jsonl` (compactado ao final em `.jsonl.gz`) e descartar os arquivos brutos da memória.
   - Preservar intactos os snapshots de `/Volumes/240/TSE/snapshots/` e comparar os hashes de `05/10/2026` do 1º turno com os atuais.
3. **Relatório Visual Completo (`auditoria/pa/relatorio_pa_1t_2t.html`):**
   - Formato HTML/XHTML com opção nativa de **Imprimir / Baixar em PDF** (`window.print()` + CSS `@media print` sem estouro de layout).
   - Todos os gráficos vetoriais (SVG) e textos explicativos das 10 frentes de auditoria.
