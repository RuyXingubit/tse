# v2 — Arquitetura Streaming (Baixar, Validar, Comparar, Resumir e Descartar) + Relatório HTML/PDF

Data: 2026-10-26
Continuação de `v1_conceito_inicial.md` (preservado).

## 1. Diagnóstico do Disco (`/Volumes/240/TSE`) e dos Endpoints do 2º Turno
- **Arquivos apagados:** em `/Volumes/240/TSE`, as pastas `espelho/`, `estado/` e `logs/` foram removidas em 07/10/2026.
- **Arquivos preservados:** a pasta `/Volumes/240/TSE/snapshots/` (somente-leitura) permaneceu 100% íntegra com os 17 snapshots do 1º turno (1,1 GB), incluindo `2026-10-05T11-48-08/manifesto.jsonl.gz` com os hashes originais de 498.815 urnas coletadas em 05/10/2026.
- **2º Turno no TSE (`ele-c.json`):**
  - Ciclo `ele2026`, **pleito `3221`** (data `25/10/2026`).
  - Eleição **`6258`**: Presidente (2º turno, nacional — candidatos `13` e `22`).
  - Eleição **`6260`**: Governador (2º turno em 6 UFs: `ac`, `am`, `df`, `es`, `rn`, `to`).
- **Descoberta técnica nos arquivos binários:**
  1. `bu.dat` é um envelope ASN.1 BER (`EntidadeEnvelopeGenerico` → `EntidadeBoletimUrna`) decodificável em Python puro (sem dependências nativas externas), trazendo: código do local de votação (`local` = escola), código interno da urna física (`numeroInternoUrna`), horários de abertura/encerramento, aptos, comparecimento, detalhamento de biometria (`[biométrica, liberados_por_codigo]`) e votos por candidato/branco/nulo.
  2. `log.jez` é um arquivo ZIP padrão (`PK\x03\x04`) contendo `logd.dat` (texto Latin-1 tabulado) e seu SHA-512 também consta assinado dentro do `vota.vsc`.
  3. **Otimização crítica:** o `log.jez` do 2º turno (`3221`) **já contém o log completo do 1º turno (`04/10/2026`) e do 2º turno (`25/10/2026`)** quando a seção usou a mesma urna física. Só é necessário baixar o `log.jez` do 1º turno (`3220`) quando a urna física da seção mudou entre os turnos (ou não contém eventos de 04/10/2026).

## 2. Fluxo "Baixar → Validar → Comparar → Resumir → Descartar" (Sem Encher o HD)
Para cada seção eleitoral da UF escolhida:
1. Baixa em memória (RAM) do 1º turno (`3220`): `aux.json`, `vota.vsc`, `bu.dat`.
2. Baixa em memória (RAM) do 2º turno (`3221`): `aux.json`, `vota.vsc`, `bu.dat`, `log.jez` (e `1T log.jez` apenas se o log do 2T não contiver os eventos de 04/10/2026).
3. **Validação criptográfica completa em memória:**
   - Confere `hash` do `aux.json` == SHA-256(`vota.vsc`) e SHA-512(`bu.dat` / `log.jez`) dentro do `vota.vsc` em ambos os turnos.
   - Compara o `hash` do 1º turno atual com o `hash` que salvamos em `05/10/2026` no `manifesto.jsonl.gz` (detecta qualquer republicação tardia do 1º turno).
4. **Extração e comparação em memória:**
   - Decodifica `1T bu.dat` e `2T bu.dat`.
   - Processa `logd.dat` separando os eventos de `04/10/2026` (1T) e `25/10/2026` (2T): conta votos minuto a minuto, votos após as 17h00 (horário local da urna), calcula tempos entre eleitores (mínimo, p5, p10, mediana, quantidade de votos em $<8\text{s}$ e $<12\text{s}$), reinicializações, alertas de bateria/relógio e tentativas de biometria.
5. **Persistência enxuta e descarte:**
   - Grava apenas **um registro JSON compacto (~1 KB por seção)** no arquivo `resumo_secoes_<uf>.jsonl.gz` (uma UF inteira ocupa de **2 MB a 40 MB** no disco, em vez de dezenas de gigabytes) e um diário incremental para retomada (`Ctrl+C`).
   - Descarta imediatamente da memória os bytes brutos de `bu.dat`, `vota.vsc` e `log.jez`.

## 3. Escopo Completo de Auditorias, Gráficos e Explicações no Relatório HTML/XHTML (com PDF)
O gerador produzirá um relatório `relatorio_<uf>_1t_vs_2t.html` (compatível com XHTML/HTML5, com botão **"Imprimir / Baixar em PDF"** e CSS `@media print` otimizado para A4/paisagem) contendo:
1. **Resumo Executivo e Auditoria de Integridade:** total de urnas, batimento matemático soma dos BUs vs. JSON oficial do TSE, verificação das assinaturas `.vsc` e verificação contra o snapshot de 05/10/2026.
2. **Comparecimento 1T vs. 2T:**
   - Gráfico de dispersão (% 1T vs. % 2T) e distribuição de $\Delta\text{Comparecimento}$.
   - Lista e explicação das seções com salto extremo (ex.: $\le 85\%$ no 1T para $\ge 98\%$ no 2T, ou $> +15\text{ p.p.}$), seções com 100% de comparecimento e seções com $\text{Comparecimento} > \text{Aptos}$.
3. **Cadastro de Eleitores Aptos (1T vs. 2T):**
   - Verificação de seções onde `qtdEleitoresAptos` mudou entre o 1º e o 2º turno, ou seções que desapareceram/surgiram.
4. **Votos Registrados Após as 17h00 (1T vs. 2T):**
   - Gráfico minuto a minuto dos votos computados após as 17h00 (horário local da urna) no 1º e no 2º turno, mais histograma do horário de encerramento das urnas.
   - Cruzamento: quem ganhou mais votos nas urnas que encerraram tarde e quantas pessoas votaram após as 17h em cada turno.
5. **Cadência e Velocidade Física de Votação (`log.jez`):**
   - Distribuição do tempo entre um voto e o seguinte; destaque para urnas com votos em intervalo curto ($<8\text{s}$ ou $<10\text{s}$) ou mediana de tempo atípica.
6. **Biometria vs. Liberação Manual pelo Mesário (1T vs. 2T):**
   - Gráfico cruzando `% de eleitores liberados sem biometria` com `% de comparecimento` e `% de votos por candidato`, e variação da falha biométrica entre 1T e 2T na mesma seção.
7. **Migração de Votos e Perda Líquida (1T $\rightarrow$ 2T):**
   - Gráfico $\Delta\text{Candidato 13}$ vs. $\Delta\text{Candidato 22}$ (e Governador, quando houver 2º turno estadual), destacando seções onde um candidato perdeu votos absolutos entre 1T e 2T mesmo com aumento de comparecimento, urnas unânimes (0 votos para um candidato) e variações bruscas de brancos/nulos.
8. **Anomalias Intralocal (Mesma Escola / Local de Votação):**
   - Comparação de cada seção com a média das outras seções do **mesmo prédio escolar** (`local`), apontando salas que divergem fortemente ($>3\sigma$ ou $>20\text{ p.p.}$) das salas vizinhas em comparecimento, votos ou biometria.
9. **Auditoria de Hardware e Operação (1T vs. 2T):**
   - Seções que trocaram de urna física (`numeroInternoUrna`) entre 1T e 2T, urnas de contingência, reinicializações durante o horário de votação e anomalias de relógio.
10. **Dossiê Ranqueado das Seções Mais Atípicas:**
    - Score composto de atipicidade e ficha explicativa em linguagem clara para cada seção sinalizada.
