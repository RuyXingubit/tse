#!/usr/bin/env bash
# Snapshot bootstrap (manual) — retrato da apuração do 1º turno 2026 antes do coletor existir.
# Somente leitura HTTPS de dados públicos do TSE; grava em pasta nova e datada (nunca sobrescreve).
set -euo pipefail

DEST_ROOT="${1:?uso: snapshot_bootstrap.sh <pasta_snapshots>}"
TS="$(date +%Y-%m-%dT%H-%M-%S)"
DEST="$DEST_ROOT/$TS"
if [ -e "$DEST" ]; then echo "já existe: $DEST" >&2; exit 1; fi
mkdir -p "$DEST/cs" "$DEST/agregados" "$DEST/config"

BASE="https://resultados.tse.jus.br/oficial"
UA="tse-coleta/0.1 (snapshot bootstrap; pesquisa)"
UFS="ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz"
LOG="$DEST/download.log"

baixa() { # url destino
  local code
  code=$(curl -sS --compressed --retry 4 --retry-all-errors -m 60 -A "$UA" -o "$2.part" -w "%{http_code}" "$1" || echo "ERR")
  if [ "$code" = "200" ]; then mv "$2.part" "$2"; else rm -f "$2.part"; fi
  echo "$(date +%H:%M:%S) $code $1" >> "$LOG"
}

baixa "$BASE/comum/config/ele-c.json" "$DEST/config/ele-c.json"
for e in 6257 6259 6261; do
  baixa "$BASE/ele2026/$e/config/mun-e00$e-cm.json" "$DEST/config/mun-e00$e-cm.json"
done

for uf in $UFS; do
  baixa "$BASE/ele2026/arquivo-urna/3220/config/$uf/$uf-p003220-cs.json" "$DEST/cs/$uf-p003220-cs.json"
done

baixa "$BASE/ele2026/6257/dados/br/br-c0001-e006257-u.json" "$DEST/agregados/br-c0001-e006257-u.json"
for uf in $UFS; do
  baixa "$BASE/ele2026/6257/dados/$uf/$uf-c0001-e006257-u.json" "$DEST/agregados/$uf-c0001-e006257-u.json"
  for c in 0003 0005 0006 0007 0008; do
    baixa "$BASE/ele2026/6259/dados/$uf/$uf-c$c-e006259-u.json" "$DEST/agregados/$uf-c$c-e006259-u.json"
  done
  baixa "$BASE/ele2026/6261/dados/$uf/$uf-c0025-e006261-u.json" "$DEST/agregados/$uf-c0025-e006261-u.json"
done

cp "$0" "$DEST/snapshot_bootstrap.sh"
(cd "$DEST" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS)
chmod -R a-w "$DEST"
echo "$DEST"
grep -c " 200 " "$LOG" | sed 's/^/ok: /'
grep -v " 200 " "$LOG" || true
