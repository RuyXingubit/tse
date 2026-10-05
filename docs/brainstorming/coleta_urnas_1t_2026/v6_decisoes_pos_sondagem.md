# v6 — Decisões pós-sondagem

Continuação de `v5_sondagem_endpoints.md` (preservado).

## Decisões tomadas
13. **Definição de "apurada"**: seção com arquivo publicado (status TSE "Recebida" ou "Totalizada").
    - Baixa BU + vota.vsc assim que publicado.
    - O snapshot registra o status TSE de cada seção.
    - Seções "Recebida" têm o JSON auxiliar reconsultado em ritmo moderado até virarem "Totalizada"; BU só é baixado de novo se o hash mudar (nova versão gravada ao lado, original intocado).
14. **Eleição 6261 (Conselheiro Distrital)**: incluída nos agregados (junto com 6257 e 6259).

## Ajuste da decisão 8 (ritmo), por causa da sondagem
- Status de todas as seções por ciclo vem das **28 listas de seções por UF** (~3 MB), não de 499 mil JSONs auxiliares.
- JSON auxiliar é consultado: (a) uma vez quando a seção aparece com `da`/`ha`; (b) de novo se `da`/`ha` mudar; (c) periodicamente enquanto status = "Recebida".

## Estimativas atualizadas
- BU + vota.vsc ≈ 35 GB; ~1 milhão de arquivos + ~500 mil JSONs auxiliares.

## Próximo passo proposto
Consolidar em `docs/PRD_coleta_urnas_1t_2026.md` e iniciar a implementação (passo 1 do plano da v4), após aprovação explícita.
