# v5 — Resultado da sondagem real dos endpoints do TSE (04/10/2026 ~22:50)

Continuação de `v4_pendencias_testes_plano.md` (preservado). Sem código de projeto escrito; só sondas descartáveis no scratch.

## Códigos de 2026 (de `comum/config/ele-c.json`)
- Ciclo `ele2026`, **pleito 3220** (1º turno, 04/10/2026).
- Eleição **6257**: Presidente (2º turno = 6258).
- Eleição **6259**: Governador, Senador, Dep. Federal, Dep. Estadual, Dep. Distrital (2º turno = 6260).
- Eleição **6261**: "Municipal 2026 – Conselheiro Distrital" (não estava na nossa lista de cargos).

## Lista de seções por UF (`arquivo-urna/3220/config/<uf>/<uf>-p003220-cs.json`)
- 28 arquivos (27 UFs + ZZ/exterior), ~3 MB no total, 28 requisições.
- Cada seção traz `ns`; se tem arquivo publicado, traz `da`/`ha` (data/hora). Seções agregadas trazem `nsp` (apontam para a principal, sem urna própria); principais com agregadas trazem `nsa`.
- Retrato às 22:47: **517.179 seções**, **17.931 agregadas**, **499.248 urnas**, **498.947 com arquivo (99,94%)**, 301 pendentes (ZZ 95,4%; BA 99,67%; demais ≥ 99,8%).
- **Consequência**: o status de todas as seções sai dessas 28 requisições → não precisamos consultar 499 mil JSONs auxiliares por ciclo (muda a decisão 8 para melhor).

## JSON auxiliar por seção (`.../dados/<uf>/<mun>/<zona>/<secao>/p003220-<uf>-m<mun>-z<zona>-s<secao>-aux.json`)
- Campos: `st` (seção: "Totalizada" / "Recebida"), lista `hashes` (cada uma com `hash`, `dr`/`hr`, `st`, `arq` = nomes e tipos).
- Tipos de arquivo: `vota` (.vsc = pacote de assinaturas), `bu`, `rdv`, `log`, às vezes `imgbu` (listado mas 404 num caso testado).
- Arquivos em `.../<secao>/<hash>/<nome>`.
- Amostra aleatória de 40 seções com arquivo: 32 "Recebida", 8 "Totalizada". 5 pendentes: aux provavelmente ainda não existe (erro na requisição).

## Cadeia de integridade (confirmada 40/40)
1. `hash` do aux (hex → texto base64 com `-` no lugar de `/`) = **SHA-256 do `vota.vsc`**.
2. O `vota.vsc` contém o **SHA-512 do `bu.dat`** (e do rdv/log), assinado pela urna.
→ Com BU + vota.vsc temos verificação ponta a ponta.

## Volume
- BU médio 11,6 KB (5–19 KB); vota.vsc ~61 KB (fixo).
- **BU + vota.vsc ≈ 34,6 GB** para 499 mil urnas (não "poucos GB" como estimado antes). Cabe nos ~100 GB livres do disco externo.

## Agregados (parte B) — endpoints que respondem 200
- `ele2026/<eleicao>/config/mun-e<eleicao6>-cm.json` (municípios, ~98 KB)
- `ele2026/<eleicao>/dados/<uf>/<uf>-c<cargo4>-e<eleicao6>-u.json` (UF/BR)
- `ele2026/<eleicao>/dados/<uf>/<uf><mun>-c<cargo4>-e<eleicao6>-u.json` (município)
- Variantes `-r`/`-v` deram 404.

## Ambiente / rede
- Header `x-ratelimit-limit: 2000/s` (Akamai). Ocorreram falhas de rede transitórias (curl 56) → retries obrigatórios.
- Python do Xcode (3.9) sem certificados raiz → **não** desligar verificação TLS; usar Python 3.13 do Homebrew (`/opt/homebrew/bin/python3.13`). `uv` não instalado.

## Decisões em aberto geradas pela sondagem
- [ ] Definição de "apurada": arquivo publicado (Recebida+Totalizada) ou só Totalizada?
- [ ] Incluir eleição 6261 (Conselheiro Distrital)?
