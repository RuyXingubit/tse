# v2 — Escopo, arquivos, integridade e estratégia de snapshot

Continuação de `v1_conceito_inicial.md` (preservado).

## Nota de esclarecimento
- IMGBU = "imagem do boletim de urna": versão em texto legível do BU impresso e afixado na seção. O BU (.bu) é o arquivo binário assinado (ASN.1), fonte autoritativa.

## Decisões tomadas
1. **Escopo das fontes**: (A) arquivos de urna por seção + (B) resultados agregados em JSON agora. (C) Portal de Dados Abertos (CSVs) fica para fase 2.
2. **Arquivos por seção**: somente **BU** (sem IMGBU, RDV, log).
3. **Integridade** (decisão de segurança): BU + **assinatura (.vscmr)**, validando o **hash de cada arquivo** com o JSON auxiliar do TSE. Usuário optou por NÃO abrir mão da assinatura.
4. **Snapshot / conclusão**:
   - Cada ciclo de varredura grava snapshot **imutável e datado** do status de todas as seções (histórico da apuração; nunca sobrescreve).
   - Baixa apenas seções que viraram totalizadas desde o ciclo anterior.
   - Se o hash de um BU mudar, guarda nova versão **sem apagar** a antiga.
   - Para quando todas as seções estiverem em **estado final** (totalizada, não instalada, anulada etc.).

## Pendentes
- [ ] Stack
- [ ] Armazenamento (layout em disco / catálogo)
- [ ] Execução (onde roda, intervalo, politeness com o TSE)
- [ ] Parte B: quais JSONs agregados
- [ ] Testes
