# v4 — Pendências de longa duração, testes e plano de implementação

Continuação de `v3_stack_layout_execucao.md` (preservado).

## Decisões tomadas
12. **Seções pendentes por muito tempo**: intervalo adaptativo — 10 min enquanto houver progresso → 1 h após 24 h sem novidade → 6 h após mais 24 h. Snapshot gravado só quando algo mudou (o log registra todo ciclo). Ctrl+C a qualquer momento; ao religar, retoma de onde parou.

## Itens técnicos (sem decisão do usuário necessária)
- **Descoberta dos códigos 2026**: ler `comum/config/ele-c.json`, escolher o pleito do 1º turno de 2026 e as eleições/cargos dele. Nada hardcoded; se não encontrar, aborta com mensagem clara.
- **Testes (obrigatório)**: pytest com fixtures JSON/binárias locais (sem rede) cobrindo:
  - parse do config de seções por UF;
  - classificação de status (pendente vs. final);
  - validação de hash (aceita correto, rejeita corrompido, não deixa `.part` com nome final);
  - retomada (pula arquivo existente com hash válido);
  - versionamento quando o hash do BU muda (original intocado);
  - montagem do manifesto de snapshot (finais herdadas + pendentes reconsultadas) e "só grava se mudou";
  - backoff em 403/429/503 e intervalo adaptativo.
- **Segurança**: apenas leitura HTTPS de fontes públicas; sem credenciais; sem dados no Git (`.gitignore`); validação de hash antes de aceitar qualquer arquivo; caminhos montados só a partir de códigos validados (evita path traversal vindo do JSON).

## Plano de implementação (após aprovação)
1. Esqueleto do projeto Python 3.13 (`pyproject.toml`, `uv`/venv, `.gitignore`, pytest).
2. Módulo de descoberta (config TSE) + testes.
3. Cliente HTTP com limite de concorrência, retry/backoff + testes.
4. Varredura de seções (aux JSON) → manifesto de snapshot + testes.
5. Download BU + .vscmr com hash e gravação atômica/versionada + testes.
6. Agregados BR/UF/município + configs + testes.
7. Loop com intervalo adaptativo, retomada, logs.
8. Amostragem real em 1 UF pequena (ex.: RR) para medir volume/tempo → aprovação → execução completa em `/Volumes/240/TSE`.
