# v1 — Conceito inicial: coleta de dados das urnas (1º turno 2026)

Data: 2026-10-04 22:15 (BRT) — noite do 1º turno.

## Pedido original
- Criar uma lista das urnas (seções) com 100% de apuração do 1º turno.
- Preservar essa lista (snapshot) e ir baixando incrementalmente até todas estarem atualizadas.
- Baixar todos os dados públicos sobre as urnas.
- Fase futura (fora do escopo agora): gerar dados/insights para candidatos.
- Foco imediato: **apenas download/preservação**.

## Fatos levantados (fonte: resultados.tse.jus.br/oficial/comum/config/ele-c.json)
Padrões de diretório públicos expostos pelo TSE:
- `cs`  : `<base>/<ambiente>/<ciclo>/arquivo-urna/<cd_pleito>/config/<uf>` → lista municípios/zonas/seções da UF
- `aux` : `<base>/<ambiente>/<ciclo>/arquivo-urna/<cd_pleito>/dados/<uf>/<municipio>/<zona>/<secao>` → status da seção + hashes + nomes dos arquivos de urna
- `e`/`u`/`ab`: `<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>` → resultados agregados (por cargo/abrangência)
- `cm`  : config da eleição; `ft`: fotos de candidatos

Arquivos de urna por seção (padrão de eleições anteriores): BU, RDV, log da urna, imagem do BU, assinaturas (.vscmr).

Workspace `/Users/ruy/Code/tse` está vazio (projeto do zero).

## Decisões (preenchidas no grill-me)
- [ ] Escopo dos dados
- [ ] Cargos/abrangência
- [ ] Definição de "100% apurada" e snapshot
- [ ] Stack
- [ ] Armazenamento / integridade
- [ ] Execução / agendamento
