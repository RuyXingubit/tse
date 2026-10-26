# PRD — Auditoria Comparativa 1º vs. 2º Turno por UF (Streaming + Resumo + Relatório HTML/PDF)

Status: **aprovado** em 2026-10-26 10:03 (BRT). Consolida `docs/brainstorming/auditoria_1t_vs_2t/v1…v3`.

## 1. Objetivo
Comparar seção por seção o 1º turno (`pleito 3220`, 04/10/2026) com o 2º turno (`pleito 3221`, 25/10/2026) de uma UF (iniciando pelo **Pará — `pa`**, com ~20.827 urnas, expansível para todas as UFs), identificando inconsistências estatísticas, temporais, biométricas e operacionais, sem encher o disco com arquivos brutos.

## 2. Arquitetura "Baixar → Validar → Comparar → Resumir → Descartar"
1. **Leitura de referência do 1º turno:** carrega os hashes originais congelados em `/Volumes/240/TSE/snapshots/2026-10-05T11-48-08/manifesto.jsonl.gz` (quando disponível).
2. **Coleta em memória por seção:**
   - 1º turno (`3220`): `aux.json`, `vota.vsc`, `bu.dat`.
   - 2º turno (`3221`): `aux.json`, `vota.vsc`, `bu.dat`, `log.jez` (que já contém o histórico de `04/10/2026` e `25/10/2026` quando a urna física é a mesma; caso contrário, baixa também o `1T log.jez`).
3. **Validação criptográfica obrigatória antes de processar:**
   - `vsc_confere(vsc, hash_hex)` (SHA-256) e `arquivo_confere_com_vsc(arq, vsc)` (SHA-512) para todos os `bu.dat` e `log.jez`.
4. **Persistência enxuta e retomável:**
   - Grava 1 linha JSON (~1 KB) por seção em `auditoria/<uf>/resumo_secoes.jsonl` (e compacta em `resumo_secoes.jsonl.gz`), descartando da RAM os binários brutos.
   - Em caso de interrupção (`Ctrl+C`), retoma exatamente das seções já gravadas no `.jsonl`.

## 3. Frentes de Auditoria e Gráficos no Relatório HTML/XHTML (com Impressão/PDF)
1. **Comparecimento 1T vs. 2T:** scatter plot `% 1T vs. % 2T`, histograma de $\Delta\text{Comparecimento}$, seções com salto extremo (ex.: $\le 85\% \rightarrow \ge 98\%$), seções com 100% de presença e seções com $\text{Comparecimento} > \text{Aptos}$.
2. **Votos Registrados Após as 17h00 (`log.jez`) e Encerramento (`bu.dat`):** curva/histograma minuto a minuto de votos computados após as 17h00 no 1T e no 2T, comparando o perfil de votos das urnas que fecharam após as 17h com as que fecharam até as 17h.
3. **Velocidade / Cadência de Votação (`log.jez`):** distribuição do intervalo em segundos entre eleitores consecutivos, destacando urnas com votos em $<8\text{s}$ ou $<12\text{s}$ e divergências entre o total de votos no log e no BU.
4. **Biometria vs. Liberação Manual por Código:** cruzamento da `% de eleitores sem biometria` com comparecimento e votação nos dois turnos.
5. **Migração de Votos e Perda Líquida Absoluta (1T $\rightarrow$ 2T):** scatter plot $\Delta\text{Cand 13}$ vs. $\Delta\text{Cand 22}$, destacando seções onde um candidato perdeu votos absolutos entre 1T e 2T, urnas unânimes (0 votos para um candidato) e saltos de brancos/nulos.
6. **Divergência Intralocal (Mesma Escola / `local`):** detecção de seções que destoam $>3\sigma$ (ou $>15\text{ p.p.}$) das demais seções do mesmo prédio escolar.
7. **Integridade do Cadastro (`qtdEleitoresAptos`) e Malha de Seções:** variações de eleitores aptos entre 1T e 2T e seções ausentes/novas.
8. **Hardware, Troca de Urna e Relógio:** mudança de `numeroInternoUrna` entre 1T e 2T, contingência, reinicializações durante a votação e regressões de relógio no log.
9. **Imutabilidade do 1º Turno (05/10 vs. Hoje):** comparação dos hashes atuais do 1T contra o snapshot imutável de 05/10/2026.
10. **Batimento Soma dos BUs vs. Resultado Oficial (`-u.json`):** conferência matemática voto a voto contra o JSON agregado oficial do TSE.
