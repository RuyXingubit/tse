# v7 — Análise de Migração de Votos da 3ª Via e Teto Matemático por Seção (Caso Altamira - PA)

**Data/Hora:** 2026-10-28 17:50 (BRT)

## 1. Hipótese e Observação Inicial do Usuário (Seção 0031, Zona 0018 — Altamira/PA)

Na análise da seção `0031` (Zona `0018`, Local `1066`, Altamira/PA):
- **1º Turno (`Eleição 6257`):**
  - Candidato `22`: `168` votos
  - Candidato `13`: `66` votos
  - Candidato `14`: `6` votos
  - Candidato `70`: `5` votos
  - Candidato `55`: `3` votos
  - Brancos: `1` | Nulos: `9` (Soma `B+N = 10`) | Comparecimento: `258` (`248` votos válidos)
- **2º Turno (`Eleição 6258`):**
  - Candidato `22`: `171` votos (**`+3` votos**)
  - Candidato `13`: `77` votos (**`+11` votos**)
  - Brancos: `0` | Nulos: `5` (Soma `B+N = 5`, queda de `-5`) | Comparecimento: `253` (queda de `-5`, mantendo exatamente `248` votos válidos)
- **Constatação na Seção `0031`:**
  - Os `3` votos do candidato `55` (cujo perfil de eleitor dificilmente migraria para o `13`) equivalem exatamente ao crescimento de `+3` votos do candidato `22` (`168 -> 171`).
  - Os `11` votos somados dos candidatos `14` (`6` votos) e `70` (`5` votos) equivalem exatamente ao crescimento de `+11` votos do candidato `13` (`66 -> 77`).
  - Portanto, na seção `0031`, a variação nominal é **100% explicada pela migração orgânica dos candidatos de 3ª via**, sem perda de votos dos finalistas e sem distorções.

---

## 2. Modelagem Matemática da Migração em Qualquer Seção Eleitoral

Para testar onde essa migração orgânica se sustenta e onde uma urna **extrapola** o comportamento esperado, toda seção eleitoral obedece à identidade contábil exata entre 1º e 2º turno:

$$\Delta V_{13} + \Delta V_{22} = V_{\text{3ª via}, 1T} + (BN_{1T} - BN_{2T}) + (C_{2T} - C_{1T})$$

Onde:
- $V_{\text{compat\_13}, 1T} = V_{14} + V_{70} + V_{\text{outros (exceto 55 e 30)}}$: estoque de votos de 3ª via com potencial de migração para o `13` (ou divisão entre `13` e `22`).
- $V_{\text{compat\_22}, 1T} = V_{55} + V_{30}$: estoque de votos de direita/centro-direita com tendência de migração para o `22`.
- $\Delta BN_{\text{disp}} = \max(0, BN_{1T} - BN_{2T})$: eleitores que votaram branco/nulo no 1ºT e passaram a votar nominalmente no 2ºT.
- $\Delta C^+ = \max(0, C_{2T} - C_{1T})$: novos eleitores que abstiveram no 1ºT e compareceram no 2ºT.

Isso define **3 níveis (filtros) de auditoria para identificar urnas que fogem do padrão da Seção 0031**:

1. **Nível 1 — Excesso sobre a 3ª Via Compatível ($\Delta V_{13} > V_{14} + V_{70} + V_{\text{outros}}$):**
   - O candidato `13` cresceu mais do que a soma de todos os votos de `14`, `70` e demais candidatos (excluindo `55` e `30`).
2. **Nível 2 — Excesso sobre o Teto Orgânico sem Virada ($\Delta V_{13} > V_{\text{compat\_13}, 1T} + \Delta BN_{\text{disp}} + \Delta C^+$):**
   - Mesmo somando **100% dos votos de `14 + 70 + outros`**, **100% da redução de brancos/nulos** e **100% do aumento de comparecimento**, ainda faltam votos para explicar o salto do `13`. Matematicamente, nessa seção, o crescimento do `13` precisou sair dos votos de `55/30` ou diretamente da redução dos votos do `22`.
3. **Nível 3 — Erosão Direta / Inversão ($\Delta V_{22} < 0$ combinado com $\Delta V_{13} > V_{\text{3ª via}}$):**
   - Seções em que o candidato `22` não apenas deixou de receber os votos do `55/30`, como **perdeu votos absolutos** que já tinha no 1º turno, enquanto o `13` subiu além da 3ª via.

---

## 3. Radiografia Completa de Altamira/PA (`315` Seções — Zona `0018`)

### 3.1. Consolidado Municipal de Altamira (`315` seções)
- **Comparecimento:** `67.458` (1ºT) -> `67.484` (2ºT) (**`+26`** eleitores no total do município).
- **1º Turno (Nominais):**
  - Candidato `22`: `41.004`
  - Candidato `13`: `20.416`
  - Candidato `70`: `1.378` | Candidato `14`: `1.250` | Outros (`80, 27, 16, 21, 29, 35, 28`): `102` -> **Subtotal `14 + 70 + outros`: `2.730` votos**
  - Candidato `55`: `648` | Candidato `30`: `34` -> **Subtotal `55 + 30`: `682` votos**
  - **Total de toda a 3ª via:** `3.412` votos
- **Brancos e Nulos em Altamira:**
  - Brancos: `758` (1ºT) -> `497` (2ºT) (`-261`)
  - Nulos: `1.868` (1ºT) -> `880` (2ºT) (`-988`)
  - **Redução total de Brancos + Nulos:** **`-1.249` votos** (que se converteram em votos nominais no 2ºT).
- **2º Turno (Nominais) em Altamira:**
  - Candidato `13`: `23.942` (**`+3.526` votos**)
  - Candidato `22`: `42.165` (**`+1.161` votos**)
- **Conclusão Macro em Altamira:**
  - O candidato `13` cresceu `+3.526` votos, o que supera em **`+796` votos** a soma inteira de `14 + 70 + outros` (`2.730` votos), e supera até mesmo toda a 3ª via somada incluindo `55` e `30` (`3.412` votos). Isso só fecha contabilmente no município porque houve a queda de `-1.249` votos brancos/nulos.

### 3.2. Classificação das 315 Seções de Altamira pelos Patamares de Migração
- **122 seções (`38,7%`):** Comportamento igual ou dentro do limite da Seção `0031` ($\Delta V_{13} \le V_{14} + V_{70} + V_{\text{outros}}$).
- **193 seções (`61,3%`):** O crescimento do `13` ultrapassou a soma de `14 + 70 + outros`.
- **152 seções (`48,3%`):** O crescimento do `13` ultrapassou **toda a 3ª via somada** (incluindo `55` e `30`).
- **68 seções (`21,6%`):** O candidato `22` **perdeu votos absolutos** entre o 1º e o 2º turno ($\Delta V_{22} < 0$).
- **60 seções (`19,0%`):** O crescimento do `13` ultrapassou até mesmo a soma de (`14 + 70 + outros` + `queda de Brancos/Nulos` + `aumento de comparecimento`).
