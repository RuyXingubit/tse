# Brainstorming v4 — Expansão da Auditoria: Janela das 08h–11h, Biometria/Mesários, Mapa de Fiscais e Caminhos Jurídicos

**Data:** 2026-10-26  
**Autor:** Ruy França  
**Status:** Debate técnico e estratégico (sem alteração no relatório v1 existente; preparando especificação da v2 do relatório)

---

## 1. Pontos Levantados pelo Usuário

1. **Seções que saltaram o comparecimento (1T $\rightarrow$ 2T):**
   - Localizar **todas** as seções onde o comparecimento subiu (ou teve salto expressivo) em gráfico e/ou tabela completa, gerando uma **segunda versão (`v2`) do relatório** sem sobrescrever a `v1` que já está pronta.
2. **Catálogo completo em ordem decrescente de tamanho da seção (`aptos` / `comparecimento`):**
   - Listar todas as seções críticas em ordem decrescente de tamanho para priorização prática de **envio de fiscais partidários no próximo pleito** (as maiores seções com anomalia têm maior impacto em votos absolutos).
3. **A grande distorção entre 08h00 e 11h00 da manhã + Liberação Manual pelos Mesários + Prova Física (Caderno de Votação / Assinaturas / Polegar) + Caminhos Jurídicos (PL):**
   - No Gráfico 3.1 (`Curva Horária Completa de Votos Computados`), o volume de votos entre **08h00 e 10h59** no 2º turno (`2.632.224` votos) quase dobrou em relação ao 1º turno (`1.505.249` votos — **+1.126.975 votos na manhã, sendo +128,4% só na faixa das 08h**).
   - Perguntas centrais a responder:
     - Os mesários liberaram para pessoas reais? Eleitores com foto?
     - Registraram assinatura no Caderno de Votação ou colheram impressão digital (polegar com tinta)?
     - Como um partido político (ex.: PL) pode ter acesso legal a esse material físico/digital para fazer amostragem e periciar votos de terceiros?
     - A assinatura no Caderno de Votação pode ser confrontada com a assinatura original do cadastro/título (ou biometria/foto do cadastro ELO)?
     - O que a legislação eleitoral e as Resoluções do TSE dizem nesses casos e quais são os caminhos formais?
     - Quais novos dados podemos extrair **agora mesmo** dos arquivos `bu.dat` e `log.jez` mudando o foco para a janela das **08h às 11h** e para as **habilitações por mesário**?
4. **Explicação aprofundada sobre a mudança no número de eleitores aptos entre o 1º e o 2º turno (`1.488` seções no Pará).**

---

## 2. Descobertas Técnicas Imediatas nos Dados do Pará (`PA`)

### 2.1. O que aconteceu nas seções onde o comparecimento SUBIU no 2º Turno
- Das **20.827** seções do Pará, o comparecimento **subiu** no 2º turno em **7.055 seções** (somando **+38.430 eleitores** a mais nessas urnas).
- Nessas **7.055 seções** onde o comparecimento aumentou:
  - O **Candidato 13 ganhou +139.025 votos** a mais que no 1º turno;
  - O **Candidato 22 ganhou +44.259 votos** a mais que no 1º turno (proporção de **3,14 para 1** pró-13).

### 2.2. O que o `log.jez` (`logd.dat`) grava quando um eleitor vota sem biometria
A inspeção direta das linhas do `logd.dat` revelou que a urna registra **rastro forense nominal do mesário**:
1. **`Foto do eleitor apresentada`**: confirma se o eleitor tinha foto biométrica na tela do terminal do mesário.
2. **`Solicita digital. Tentativa [1] de [4]` ... `Tentativa [4] de [4]`**: registra cada uma das 4 falhas do sensor biométrico, com segundo exato.
3. **`Solicitação de dado pessoal do eleitor para habilitação manual`** $\rightarrow$ **`Dado digitado confere`**: o mesário digita o ano de nascimento do eleitor.
4. **`Solicita digital do mesário`** $\rightarrow$ **`Batimento de digitais retornou o score XX`**: o mesário é obrigado a colocar o **próprio dedo** no leitor biométrico para destravar o voto sem biometria do eleitor.
5. **`Mesário <NÚMERO_DO_TÍTULO_DO_MESÁRIO> habilitou o eleitor`**: o `logd.dat` grava em texto aberto o **número de inscrição eleitoral (12 dígitos) do mesário** que autorizou cada voto sem biometria e o horário exato!
6. **`Digital coletada bate com uma digital gravada após o registro inicial de mesário. Não é possível associar a habilitação a um mesário`**: alerta gravíssimo no log quando a digital usada pelo mesário foi cadastrada fora do rito padrão inicial.
7. **`Gerando relatório [ELEITORES HABILITADOS BIOGRAFICAMENTE] [INÍCIO]`**: ao encerrar a urna às 17h00, além do Boletim de Urna, a urna imprime uma fita em papel listando **todos os eleitores (título/nome) que foram habilitados manualmente sem biometria** naquela seção!
