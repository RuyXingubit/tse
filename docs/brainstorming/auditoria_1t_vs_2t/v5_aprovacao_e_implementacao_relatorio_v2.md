# Brainstorming v5 — Aprovação e Especificação da Versão 2 (`v2`) do Relatório do Pará

**Data:** 2026-10-26  
**Autor:** Ruy França  
**Status:** Aprovado pelo usuário ("avança") — Execução da `v2` preservando integralmente a `v1`

---

## 1. Diretriz de Preservação da `v1`
- O arquivo `/Volumes/240/TSE/auditoria/pa/relatorio_pa_1t_2t.html` (`v1`) e `/Volumes/240/TSE/auditoria/pa/analise_consolidada.json` (`v1`) permanecem **100% intocados**.
- A nova entrega será gravada em:
  - `/Volumes/240/TSE/auditoria/pa/auditoria_mesarios_biometria.json`
  - `/Volumes/240/TSE/auditoria/pa/analise_consolidada_v2.json`
  - `/Volumes/240/TSE/auditoria/pa/relatorio_pa_1t_2t_v2.html`
  - `/Volumes/240/TSE/auditoria/pa/prioridade_fiscais_pa.csv`

---

## 2. Escopo dos 4 Novos Módulos da `v2`

1. **Módulo 1 — Seções que Subiram o Comparecimento no 2º Turno (7.055 seções):**
   - Gráfico SVG por faixas de aumento de comparecimento (`0 a +2 p.p.`, `+2 a +5 p.p.`, `+5 a +10 p.p.`, `+10 a +15 p.p.`, `>= +15 p.p.`) comparando a variação líquida de votos do Cand. 13 (`+139.025`) vs. Cand. 22 (`+44.259`).
   - Tabela expandida com as seções que mais subiram em pontos percentuais e em votos absolutos.
2. **Módulo 2 — Catálogo de Prioridade para Fiscais no Próximo Pleito (Ordenado por `aptos_2t` Decrescente):**
   - Tabela ordenada de forma decrescente pelo tamanho da seção (`aptos_2t`) para priorizar as maiores urnas com anomalias (alta liberação sem biometria, salto de comparecimento, presença $\ge 92\%$, perda líquida de votos ou outlier na mesma escola), acompanhada do CSV completo `prioridade_fiscais_pa.csv`.
3. **Módulo 3 — Explosão de Votos na Manhã (08h–11h), Auditoria Forense Nominal de Mesários (`log.jez`) e Guia Jurídico/Pericial (PL):**
   - Extração nos `log.jez` das 306 seções críticas ($\ge 30\%$ sem biometria) de:
     - `Foto do eleitor apresentada`;
     - `Solicitação de dado pessoal do eleitor para habilitação manual` por hora (`08h..17h`);
     - `Mesário <12_digitos> habilitou o eleitor` (ranking de títulos de mesários por seção e no estado);
     - Alertas `Digital coletada bate com uma digital gravada após o registro inicial de mesário. Não é possível associar a habilitação a um mesário`;
     - Emissão do relatório físico `[ELEITORES HABILITADOS BIOGRAFICAMENTE]`.
   - Explicação jurídica e roteiro prático de peticionamento e amostragem (Caderno de Votação + Fita de Habilitados Biograficamente + Sistema ELO).
4. **Módulo 4 — Detalhamento Técnico e Estatístico das 1.488 Seções com Mudança de Eleitores Aptos (`aptos_1t != aptos_2t`):**
   - Gráfico SVG da distribuição das diferenças de aptos (`-21` a `+4`), explicação técnica (TTE vs. cancelamentos ELO) e tabela das maiores variações por seção.
