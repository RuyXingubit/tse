# v9 — Decomposição Matemática da Virada (1ºT -> 2ºT no PA e no Brasil) e Arquitetura de Agregação (Seção -> Cidade -> Estado)

**Data/Hora:** 2026-10-28 19:12 (BRT)

## 1. Resposta Matemática à Pergunta: "O que explica o 22 ganhar no 1º turno e perder no 2º? Foi migração da 3ª via ou novos eleitores?"

A análise direta das **499.207 seções eleitorais do Brasil** (com 1ºT e 2ºT válidos) e das **20.827 seções do Pará** demonstra matematicamente que **a migração pura da 3ª via (`14 + 70 + outros`) sozinha NÃO cobria o crescimento do candidato `13`**. A virada decorreu da combinação de **4 fontes contábeis simultâneas**:

### 1.1. Os Números Nacionais (`499.207` Urnas — Brasil + Exterior)
- **1º Turno:**
  - Candidato `22`: `56.104.503` votos (**venceu o 1ºT com `+2.224.965` votos de vantagem**)
  - Candidato `13`: `53.879.538` votos
  - Estoque da 3ª Via Não-Direita (`14 + 70 + nanicos`): **`6.390.357` votos** (`70`: `3.448.569` | `14`: `2.675.887` | outros: `265.901`)
  - Estoque da 3ª Via Direita (`55 + 30`): **`2.931.636` votos** (`55`: `2.605.148` | `30`: `326.488`)
  - Brancos + Nulos (1ºT): `5.969.801` votos
  - Comparecimento Total (1ºT): `125.275.835` eleitores
- **2º Turno:**
  - Candidato `13`: `64.256.232` votos (**crescimento líquido de `+10.376.694` votos**)
  - Candidato `22`: `59.826.041` votos (**crescimento líquido de `+3.721.538` votos**)
  - Brancos + Nulos (2ºT): `4.153.801` votos (**queda de `-1.816.000` votos**, que viraram votos nominais)
  - Comparecimento Total (2ºT): `128.236.074` eleitores (**entrada líquida de `+2.960.239` novos votantes no 2ºT**)

### 1.2. Decomposição Urna por Urna dos `+10.376.694` Novos Votos do `13` no Brasil
Calculando seção por seção (sem mascarar uma urna pela outra):
1. **Migração da 3ª Via Compatível (`14 + 70 + outros` na própria urna):** até **`5.963.828` votos (`57,1%`)**
2. **Entrada de Novos Eleitores no 2º Turno ($\Delta C > 0$ na urna):** **`2.085.553` votos (`20,0%`)**
3. **Conversão de Brancos e Nulos do 1ºT em Voto Nominal no 2ºT ($\Delta BN < 0$):** **`1.708.643` votos (`16,4%`)**
4. **Estouro de Teto Contábil da Seção (`139.308` urnas dos Grupos 5 e 6):** **`677.605` votos (`6,5%`)**, sendo `530.298` dentro da margem do `55+30`/giro de abstenção (`94.423` urnas do Grupo 5) e **`147.307` votos de estouro absoluto com perda direta de votos do `22`** (`44.885` urnas críticas do Grupo 6).

### 1.3. Funil Nacional (`499.207` Urnas) vs. Pará (`20.827` Urnas) vs. Altamira (`315` Urnas)

| Grupo de Diagnóstico (por Seção) | Altamira (`315` urnas) | Pará (`20.827` urnas) | Brasil (`499.207` urnas) |
| :--- | :---: | :---: | :---: |
| **G0 — Padrão Esperado Puro (`13 <= 14+70` e `22 >= 55+30`)** | `95` (`30,2%`) | `4.511` (`21,7%`) | `80.371` (`16,1%`) |
| **G1 — Explicado por Queda de Brancos/Nulos (`22` OK)** | `58` (`18,4%`) | `3.036` (`14,6%`) | `54.580` (`10,9%`) |
| **G2 — Explicado por Novos Eleitores no 2ºT (`22` OK)** | `49` (`15,6%`) | `2.393` (`11,5%`) | `175.304` (`35,1%`) |
| **G3 — Abstenção de Eleitores do `22`/`55` no 2ºT (`13` OK)** | `27` (`8,6%`) | `3.965` (`19,0%`) | `27.696` (`5,5%`) |
| **G4 — Queda de B/N (p/ `13`) + Abstenção no 2ºT (no `22`)** | `26` (`8,3%`) | `2.596` (`12,5%`) | `21.948` (`4,4%`) |
| **G5 — Alerta Moderado (Exige `55/30` ou Giro de Abstenção)** | `31` (`9,8%`) | `2.193` (`10,5%`) | `94.423` (`18,9%`) |
| **G6 — Anomalia Crítica (Estouro Total + Queda Direta do `22`)** | `29` (`9,2%`) | `2.133` (`10,2%`) | `44.885` (`9,0%`) |

---

## 2. Estratégia Técnica: Por Cidade vs. Por Estado (Como Não Mascarar Dados e Não Demorar)

1. **Por que nunca devemos agregar os votos antes de aplicar a regra?**
   - Se somarmos todos os votos de uma cidade ou estado antes de testar o teto, as urnas normais (Grupos 0 a 4) **compensam e mascaram** as urnas críticas (Grupos 5 e 6).
   - Em Altamira, por exemplo, a soma macro da cidade esconderia as `29` urnas críticas.
2. **A solução sem perda de fidelidade e em segundos:**
   - O cálculo de diagnóstico é feito **100% no nível da Seção Eleitoral (urna por urna)**.
   - Depois de classificar cada seção individualmente (`G0` a `G6`), nós **contamos quantas seções de cada grupo existem em cada Cidade e em cada Estado** (soma de anomalias por cidade, sem cancelar positivo com negativo).
   - **Performance comprovada:** Como os resumos `.jsonl.gz` das `499.248` urnas já estão salvos localmente em `/Volumes/240/TSE/auditoria/`, o cálculo completo levou **0,5 segundo para o Pará inteiro (`20.827` seções / `144` cidades)** e **15,1 segundos para o Brasil inteiro (`499.207` seções / `5.570` cidades)**!
   - No Relatório Web de cada Estado (começando pelo Pará), podemos exibir o **Ranking das Cidades daquele Estado** e um **Filtro Interativo por Cidade**, permitindo ver tanto o Estado consolidado quanto abrir qualquer município sem mascarar uma única urna.
