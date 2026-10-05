# PRD — Coleta dos arquivos de urna e resultados do 1º turno 2026

Status: **aprovado** em 2026-10-04 23:01 (BRT). Consolida `docs/brainstorming/coleta_urnas_1t_2026/v1…v6`.

## 1. Objetivo
Montar um acervo local, íntegro e verificável, dos dados públicos das urnas do 1º turno de 2026:
1. Preservar o retrato da apuração ("lista das urnas apuradas") em snapshots imutáveis e datados.
2. Baixar incrementalmente os arquivos de cada urna até que todas as seções estejam em estado final.

Fora de escopo agora: decodificação do BU, banco de dados, análises/insights, Portal de Dados Abertos (fase 2), RDV, log, IMGBU, fotos.

## 2. Fontes (resultados.tse.jus.br/oficial)
| Item | Caminho |
|---|---|
| Config geral | `comum/config/ele-c.json` → ciclo `ele2026`, pleito `3220` |
| Lista de seções por UF (27 + `zz`) | `ele2026/arquivo-urna/3220/config/<uf>/<uf>-p003220-cs.json` |
| JSON auxiliar da seção | `ele2026/arquivo-urna/3220/dados/<uf>/<mun>/<zona>/<secao>/p003220-<uf>-m<mun>-z<zona>-s<secao>-aux.json` |
| Arquivos da urna | `…/<secao>/<hash>/<nome>` (`-bu.dat`, `-vota.vsc`) |
| Config de municípios | `ele2026/<eleicao>/config/mun-e<eleicao6>-cm.json` |
| Agregados UF/BR | `ele2026/<eleicao>/dados/<uf>/<uf>-c<cargo4>-e<eleicao6>-u.json` |
| Agregados município | `ele2026/<eleicao>/dados/<uf>/<uf><mun>-c<cargo4>-e<eleicao6>-u.json` |

Eleições e cargos: `6257` Presidente (c0001) · `6259` Governador (0003), Senador (0005), Dep. Federal (0006), Dep. Estadual (0007), Dep. Distrital (0008) · `6261` Conselheiro Distrital (0025).

Códigos são descobertos de `ele-c.json` em tempo de execução (não hardcoded); aborta com mensagem clara se não encontrar.

## 3. Regras de negócio
- **Seção agregada** (`nsp` na lista): não tem urna própria; não é baixada, mas aparece no manifesto apontando para a principal.
- **Urna apurada** = seção com arquivo publicado (`da`/`ha` na lista; status TSE "Recebida" ou "Totalizada").
- **Estado final**: "Totalizada" (ou outro status terminal que o TSE venha a publicar, ex.: não instalada/anulada).
- **Conclusão**: quando não houver seção pendente nem "Recebida" → varredura final completa → fim.

## 4. Integridade e segurança
1. `hash` do aux (hex → base64 com `-` no lugar de `/`) **deve** ser igual ao SHA-256 do `vota.vsc`.
2. O `vota.vsc` **deve** conter o SHA-512 do `bu.dat`.
3. Arquivo só recebe o nome final após validar (escrita em `.part` + rename atômico). Falhou → descarta e tenta de novo depois; nunca fica arquivo inválido com nome final.
4. Somente HTTPS com verificação TLS ligada; sem credenciais; caminhos montados apenas a partir de códigos validados por regex (`uf`=2 letras, `mun`=5 dígitos, `zona`/`secao`=4 dígitos, `hash`=hex) — bloqueia path traversal vindo de JSON.
5. Dados nunca vão para o Git.

## 5. Armazenamento (`/Volumes/240/TSE`, APFS, ~100 GiB livres; uso estimado ~36 GB)
- `espelho/` — cópia exata do caminho do TSE (a partir de `ele2026/…`).
- `snapshots/<AAAA-MM-DDTHH-MM-SS>/` — listas por UF, manifesto (`manifesto.jsonl.gz`: uma linha por seção com status, `da`/`ha`, hash, se baixado/validado), agregados BR/UF do ciclo, `SHA256SUMS`. Somente-leitura após gravado. Gravado só se algo mudou.
- Versões: se o hash de um BU/vsc mudar, a nova versão fica em seu próprio diretório `<hash>/` (o caminho do TSE já separa por hash) — o original nunca é tocado.
- Arquivos que mudam no mesmo endereço do TSE (JSON auxiliar, listas, agregados) são gravados como `<nome>@<sha256[:16]>.json` — uma cópia por conteúdo distinto, nunca sobrescrita.
- Gravação: arquivo temporário + `fsync` + `link` (falha se o destino existir → impossível sobrescrever, mesmo em corrida).
- `logs/` — execução e erros.
- Sem banco de dados: "já baixado" = arquivo existe no espelho e valida.

## 6. Ciclo de coleta
1. Baixa as 28 listas de seções (~3 MB) → calcula diferenças vs. snapshot anterior.
2. Para seções novas/alteradas (`da`/`ha` mudou) → busca o aux → baixa `vota.vsc` + `bu.dat` → valida.
3. Seções "Recebida": reconsulta o aux em ritmo moderado até "Totalizada"; rebaixa só se o hash mudar.
4. Agregados: BR/UF de todos os cargos a cada ciclo; município uma vez ao fechar 100% e de novo na varredura final.
5. Grava snapshot se algo mudou.
6. Intervalo: 10 min enquanto houver progresso → 1 h após 24 h sem novidade → 6 h após mais 24 h.
- Concorrência máx. **64** conexões + teto rígido de **200 req/s** (~10% do `x-ratelimit-limit: 2000` informado pelo TSE) — decisão do usuário em 2026-10-04 23:20. Medido em RR: 151 req/s, 1.519 urnas em 30 s, 0 bloqueios → 1ª passada nacional estimada em ~2h45. User-Agent identificado, retry com backoff exponencial, pausa automática em 403/429/503.
- Retomável: Ctrl+C a qualquer momento; ao reiniciar continua de onde parou. Roda local com `caffeinate`.

## 7. Stack
Python 3.13 (Homebrew), httpx assíncrono, pytest. Venv local no projeto.

## 8. Testes (obrigatórios, sem rede, com fixtures)
Parse das listas por UF (inclui agregadas) · decodificação do hash TSE · validação da cadeia vsc→BU (aceita/rejeita) · gravação atômica · retomada · versionamento por hash · diff de snapshots e "só grava se mudou" · backoff em 403/429/503 · intervalo adaptativo · rejeição de códigos inválidos (path traversal).

## 9. Entrega por etapas (cada uma: implementar → testar → aprovar)
1. Esqueleto do projeto + descoberta de códigos + parse das listas + testes.
2. Cliente HTTP + integridade + gravação atômica + testes.
3. Ciclo/snapshot/diff + testes.
4. Agregados + testes.
5. Loop adaptativo + CLI + logs.
6. Rodada real em RR → aprovação → Brasil inteiro.

## 10. Marcos já realizados
- 2026-10-04 ~22:50: sondagem dos endpoints (v5).
- 2026-10-04 23:01: snapshot bootstrap manual (`scripts/snapshot_bootstrap.sh`) em `/Volumes/240/TSE/snapshots/`.
