# v3 — Stack, armazenamento, execução, ritmo, agregados e layout

Continuação de `v2_escopo_integridade_snapshot.md` (preservado).

## Decisões tomadas
5. **Stack**: Python 3.13, httpx assíncrono. (asn1tools para BU fica para a fase de insights.)
6. **Armazenamento**: **somente arquivos brutos em disco**, espelhando o caminho do TSE (uf/município/zona/seção). Sem banco de dados por enquanto. Estado de "já baixado" = arquivo existe no disco com hash válido.
7. **Onde roda**: local no Mac (caffeinate, retomável). Dados em **`/Volumes/240/TSE`** (disco externo APFS, ~100 GiB livres). Código em `/Users/ruy/Code/tse`. Dados nunca no Git.
   - Obs.: o sandbox do agente não tem permissão em `/Volumes/240/TSE`; a execução real precisará de autorização do usuário.
8. **Ritmo**: varredura completa inicial → snapshot #1 (a "lista das 100%") → ciclos a cada ~10 min só nas pendentes (snapshot = manifesto completo: finais herdadas + pendentes reconsultadas) → varredura final completa para detectar hash alterado. 8 conexões simultâneas, User-Agent identificado, retry com backoff exponencial, pausa automática em 403/429/503.
9. **Agregados (parte B)**: todos os cargos (Presidente, Governador, Senador, Dep. Federal, Dep. Estadual/Distrital); BR + UFs a cada ciclo; cada município uma vez ao fechar 100% e de novo na varredura final; JSONs de configuração (seções por UF, candidatos/partidos). **Sem fotos.**
10. **Layout em `/Volumes/240/TSE`**:
    - `espelho/` — cópia exata do caminho do TSE (`.bu`, `.vscmr`, JSON auxiliar; agregados em `<eleicao>/dados/<uf>/`).
    - `snapshots/<AAAA-MM-DDTHH-MM-SS>/` — manifesto do ciclo (`.jsonl.gz`) + agregados BR/UF do ciclo. Imutável.
    - `logs/` — execução e erros.
    - Gravação atômica: `.part` → rename somente após hash validado.
11. **Versões de BU**: usuário cogitou manter só a mais recente, mas **voltou atrás**: se o hash mudar, o original fica intocado e a nova versão é gravada ao lado com o hash no nome (mantém decisão 4 da v2).

## Pendentes
- [ ] Comportamento com seções que ficam pendentes por muito tempo
- [ ] Testes (obrigatório por regra: testes unitários com fixtures, sem rede)
- [ ] Descoberta automática dos códigos de pleito/eleição de 2026 (via `comum/config/ele-c.json`)
