# v1 — Conceito Inicial: Auditoria e Comparação 1º Turno vs 2º Turno (Por Estado)

Data: 2026-10-26
Status: Em discussão (brainstorming inicial)

## 1. Objetivo
Selecionar um estado (UF) e comparar seção por seção o 1º turno (04/10/2026) com o 2º turno (25/10/2026), buscando inconsistências estatísticas, temporais e operacionais, apresentando os achados em gráficos e textos explicativos baseados exclusivamente nos dados reais das urnas.

## 2. O que já temos no disco vs. o que precisamos baixar
- **Já no disco (`/Volumes/240/TSE`):**
  - 1º turno nacional (`pleito 3220`): `aux.json`, `vota.vsc` e `bu.dat` de 498.815 urnas (99,91%), mais agregados JSON.
- **Necessário para a comparação 1T vs 2T do estado escolhido:**
  1. **Coleta do 2º turno da UF escolhida (`bu.dat` + `vota.vsc` + `aux.json` + agregados):** essencial para comparar comparecimento, votos, horários de encerramento e aptos entre os dois turnos.
  2. **Coleta de `log.jez` (Log da Urna) da UF escolhida (1º e 2º turno) — Decisão em aberto:**
     - O `bu.dat` contém o **horário de abertura e de encerramento da urna**, mas **não** o horário individual de cada voto.
     - Para saber **exatamente quantos votos foram registrados após as 17h00** (e medir intervalo em segundos entre eleitores), precisamos do arquivo `-log.jez` de cada seção, cujo hash SHA-512 também é assinado e validado pelo `vota.vsc`.

## 3. Catálogo de Inconsistências e Auditorias Propostas

### A. Comparecimento e Cadastro Eleitoral (1T vs 2T — via `bu.dat`)
1. **Salto anômalo de comparecimento ($\Delta$ 1T $\rightarrow$ 2T):** seções que saíram de ex. 75%–80% no 1º turno para ~98%–100% no 2º turno, destoar da variação média do próprio município/local de votação.
2. **Comparecimento de 100% (abstenção zero) ou Comparecimento > Eleitores Aptos:** verificação absoluta em ambos os turnos.
3. **Variação no número de Eleitores Aptos (`qtdEleitoresAptos`):** como o cadastro fecha em maio, o número de aptos na seção deve ser idêntico entre 1º e 2º turno (salvo transferências temporárias documentadas).
4. **Seções desaparecidas ou criadas entre turnos:** comparação da malha de seções e agregações (`nsp`/`nsa`) entre 1T e 2T.

### B. Horário de Votação e Votos Após as 17h (via `bu.dat` e `log.jez`)
5. **Urnas encerradas após as 17h00 (horário local da UF):** distribuição do horário de encerramento (`dataHoraEncerramento` do BU) no 1T e no 2T, respeitando o fuso horário oficial de cada UF.
6. **Contagem exata de votos registrados após as 17h00 (requer `log.jez`):** leitura dos timestamps de cada voto confirmado no log da urna após 17h00m00s no 1T e no 2T, comparando o volume e os candidatos mais votados nessas urnas.
7. **Cadência / Velocidade de votação (requer `log.jez`):** detecção de sequências de votos com intervalo humano improvável (ex.: múltiplos eleitores seguidos votando em menos de 5–8 segundos) ou lacunas de inatividade seguidas de rajadas.

### C. Comportamento dos Votos e Outliers Estatísticos (via `bu.dat`)
8. **Divergência Intralocal (mesma escola/local de votação):** comparação de cada seção com as demais seções da **mesma escola** (onde o perfil demográfico é homogêneo). Sinalizar seções com mais de 3 desvios-padrão ($>3\sigma$) na proporção de votos ou comparecimento.
9. **Perda líquida de votos absolutos de candidato entre 1T e 2T:** seções onde um candidato do 2º turno teve *menos* votos no 2T do que no 1T enquanto o comparecimento da seção subiu.
10. **Urnas unânimes (0 votos para um candidato) ou variações extremas de Brancos/Nulos:** comparação 1T vs 2T.
11. **Batimento Soma dos BUs vs. JSON Agregado Oficial do TSE:** conferência matemática para garantir que nenhuma seção foi omitida ou alterada na totalização oficial.

### D. Biometria e Operação da Urna (via `bu.dat` e `log.jez`)
12. **Taxa de liberação sem biometria:** no `bu.dat` consta a lista de eleitores habilitados por ano de nascimento (quando a biometria não é usada/reconhecida). Cruzar seções com alta taxa de liberação manual pelo mesário com saltos de comparecimento ou votação pós-17h.
13. **Troca de urna (contingência), reinicializações e alertas de hardware (via `log.jez`):** urnas que sofreram reboot ou substituição durante o expediente.

## 4. Visualizações e Formato de Entrega Propostos
- Relatório visual interativo (HTML local autocontido + resumo em Markdown) com:
  - Scatter plot: % Comparecimento 1T vs % Comparecimento 2T por seção (destacando outliers).
  - Histograma / Curva acumulada: Horário de encerramento das urnas e votos registrados após as 17h (1T vs 2T).
  - Scatter plot: Variação de votos ($\Delta$ Cand A vs $\Delta$ Cand B) entre 1T e 2T.
  - Gráfico de anomalias intralocal (seção vs média da escola).
  - Cruzamento: % Sem Biometria vs % Comparecimento.
  - Tabelas ranqueadas das seções mais atípicas com texto explicativo individualizado.

## 5. Decisões em aberto para alinhar com o usuário
1. Qual **estado (UF)** será analisado primeiro (e qual cargo: Presidente, Governador ou ambos)?
2. Vamos baixar apenas o `bu.dat` do 2º turno dessa UF ou incluir também o **`log.jez` (1º e 2º turno)** para ter a contagem exata de votos individuais após as 17h e o tempo entre eleitores?
3. Formato preferido dos gráficos e explicações (relatório HTML interativo no navegador, notebooks, ou imagens estáticas + Markdown)?
