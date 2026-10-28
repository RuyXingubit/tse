# Auditoria Matemática e Forense de Dados Públicos do TSE — Eleições Gerais 2026

**Autor:** Ruy França  
**Fonte Primária Exclusiva dos Dados:** Tribunal Superior Eleitoral (TSE) — Repositório Oficial de Dados Brutos de Urna e Resultados (`https://resultados.tse.jus.br/oficial/ele2026/`) — Pleitos `3220` (1º Turno, 04/10/2026) e `3221` (2º Turno, 25/10/2026).

---

## 1. Propósito e Princípios Metodológicos

Este repositório público disponibiliza o código-fonte aberto, os decodificadores binários, a suíte de testes automatizados e os relatórios consolidados de comparação seção por seção entre o **1º Turno (`04/10/2026`)** e o **2º Turno (`25/10/2026`)** das Eleições Gerais de 2026.

O projeto segue quatro diretrizes inegociáveis:

1. **Base Estrita em Dados Públicos Oficiais:** Nenhum dado é estimado, interpolado ou simulado. Todo número, tabela ou gráfico decorre exclusivamente da decodificação direta dos arquivos oficiais assinados digitalmente pelo TSE para cada seção eleitoral:
   - **`-vota.vsc` (Tabela de Hashes Assinada):** validada via hash **SHA-256** contra o índice oficial `-aux.json`.
   - **`-bu.dat` (Boletim de Urna Digital em ASN.1 BER):** validado via hash **SHA-512** contra o pacote `-vota.vsc` antes da extração de eleitores aptos, comparecimento, habilitações biométricas vs. manuais por código e votos nominais/brancos/nulos.
   - **`-log.jez` (Log Oficial da Urna Eletrônica compactado em 7z/LZMA):** validado via hash **SHA-512** contra o pacote `-vota.vsc` antes da leitura linha a linha do arquivo `logd.dat` (e de eventuais pacotes `.jez` internos oriundos de substituição por urna de contingência).
2. **Fatos Objetivos, Sem Opinião Subjetiva:** Os relatórios e scripts não emitem juízos de valor. O objetivo é extrair, cruzar e apresentar **exatamente o que os dados públicos mostram**, permitindo que auditores, peritos, juristas, pesquisadores e cidadãos verifiquem cada métrica de forma independente.
3. **Transparência Total e Código 100% Aberto:** Todos os algoritmos de download, verificação de integridade, decodificação ASN.1 BER, leitura de logs de urna e geração dos relatórios HTML/XHTML/PDF estão publicados em [`src/tse_coleta/`](src/tse_coleta/) sem dependências obscuras.
4. **Reprodutibilidade Determinística:** Qualquer pessoa pode clonar este repositório, executar os testes de verificação ou apontar a ferramenta diretamente para o servidor público do TSE e obter **exatamente os mesmos números, hashes e relatórios**.

---

## 2. Relatórios Públicos Disponíveis (`docs/relatorios/`)

Os relatórios finais consolidados de **todas as 27 Unidades da Federação, Exterior (`ZZ`) e o Agregado Geral Nacional (`BR`)** estão versionados e organizados por pasta na estrutura [`docs/relatorios/<uf>/`](docs/relatorios/) deste repositório (enquanto os arquivos intermediários pesados de gigabytes permanecem em armazenamento externo local):

### Agregado Geral Nacional (`BR` — 499.248 Seções Eleitorais Auditadas)
- **[`docs/relatorios/br/relatorio_br_1t_2t.html`](docs/relatorios/br/relatorio_br_1t_2t.html)** — **Relatório Forense Consolidado Nacional (Brasil + Exterior):**
  - Consolidação matemática das **499.248 urnas** (`158.745.079` eleitores aptos; `125.275.835` votantes no 1ºT e `128.236.074` no 2ºT);
  - 10 gráficos vetoriais SVG com legendas completas e suporte nativo a impressão / exportação em PDF (`Imprimir / Salvar em PDF`);
  - Radiografia das **383.412 seções** do país que aumentaram o comparecimento entre o 1º e o 2º turno;
  - Análise da explosão de votos na janela da manhã (`08h00` às `10h59`, que saltou de `40.004.465` no 1ºT para `60.759.511` no 2ºT, **`+20.755.046` votos / `+51,88%`**) e dos votos após as `17h00` (`3.726.177` no 1ºT vs. `34.560` no 2ºT);
  - Auditoria nacional de biometria vs. habilitação manual por código pelo mesário, incluindo o ranking nacional de identificadores de mesários no `logd.dat` (`Mesário <12_dígitos> habilitou o eleitor`) e os `1.470.651` alertas de digital não associada em `235.838` seções;
  - Demonstração de soma zero nacional (`aptos_1t = aptos_2t = 158.745.079`) nas **55.722 seções** com variação de eleitores aptos por Transferência Temporária de Eleitores (TTE).
- **[`docs/relatorios/br/prioridade_fiscais_br.csv`](docs/relatorios/br/prioridade_fiscais_br.csv)** — **Catálogo Nacional de Prioridade de Seções para Fiscalização (CSV ordenado decrescentemente por `aptos_2t`).**
- **[`docs/relatorios/br/auditoria_mesarios_biometria.json`](docs/relatorios/br/auditoria_mesarios_biometria.json)** — **Dossiê Nacional (JSON) da Janela da Manhã e Mesários.**
- **[`docs/relatorios/br/analise_consolidada.json`](docs/relatorios/br/analise_consolidada.json)** — **Consolidação Estatística Nacional (JSON).**

### Relatórios Individuais por Estado (`docs/relatorios/<uf>/`)
Cada uma das 28 pastas abaixo contém o respectivo `relatorio_<uf>_1t_2t.html`, `prioridade_fiscais_<uf>.csv`, `auditoria_mesarios_biometria.json` e `analise_consolidada.json`:

| UF | Unidade da Federação | Relatório HTML / PDF | Catálogo de Fiscais (CSV) |
| :---: | :--- | :--- | :--- |
| **AC** | Acre (2.270 seções) | [`relatorio_ac_1t_2t.html`](docs/relatorios/ac/relatorio_ac_1t_2t.html) | [`prioridade_fiscais_ac.csv`](docs/relatorios/ac/prioridade_fiscais_ac.csv) |
| **AL** | Alagoas (7.101 seções) | [`relatorio_al_1t_2t.html`](docs/relatorios/al/relatorio_al_1t_2t.html) | [`prioridade_fiscais_al.csv`](docs/relatorios/al/prioridade_fiscais_al.csv) |
| **AM** | Amazonas (8.157 seções) | [`relatorio_am_1t_2t.html`](docs/relatorios/am/relatorio_am_1t_2t.html) | [`prioridade_fiscais_am.csv`](docs/relatorios/am/prioridade_fiscais_am.csv) |
| **AP** | Amapá (1.914 seções) | [`relatorio_ap_1t_2t.html`](docs/relatorios/ap/relatorio_ap_1t_2t.html) | [`prioridade_fiscais_ap.csv`](docs/relatorios/ap/prioridade_fiscais_ap.csv) |
| **BA** | Bahia (35.476 seções) | [`relatorio_ba_1t_2t.html`](docs/relatorios/ba/relatorio_ba_1t_2t.html) | [`prioridade_fiscais_ba.csv`](docs/relatorios/ba/prioridade_fiscais_ba.csv) |
| **CE** | Ceará (23.765 seções) | [`relatorio_ce_1t_2t.html`](docs/relatorios/ce/relatorio_ce_1t_2t.html) | [`prioridade_fiscais_ce.csv`](docs/relatorios/ce/prioridade_fiscais_ce.csv) |
| **DF** | Distrito Federal (6.969 seções) | [`relatorio_df_1t_2t.html`](docs/relatorios/df/relatorio_df_1t_2t.html) | [`prioridade_fiscais_df.csv`](docs/relatorios/df/prioridade_fiscais_df.csv) |
| **ES** | Espírito Santo (9.844 seções) | [`relatorio_es_1t_2t.html`](docs/relatorios/es/relatorio_es_1t_2t.html) | [`prioridade_fiscais_es.csv`](docs/relatorios/es/prioridade_fiscais_es.csv) |
| **GO** | Goiás (15.686 seções) | [`relatorio_go_1t_2t.html`](docs/relatorios/go/relatorio_go_1t_2t.html) | [`prioridade_fiscais_go.csv`](docs/relatorios/go/prioridade_fiscais_go.csv) |
| **MA** | Maranhão (18.093 seções) | [`relatorio_ma_1t_2t.html`](docs/relatorios/ma/relatorio_ma_1t_2t.html) | [`prioridade_fiscais_ma.csv`](docs/relatorios/ma/prioridade_fiscais_ma.csv) |
| **MG** | Minas Gerais (52.062 seções) | [`relatorio_mg_1t_2t.html`](docs/relatorios/mg/relatorio_mg_1t_2t.html) | [`prioridade_fiscais_mg.csv`](docs/relatorios/mg/prioridade_fiscais_mg.csv) |
| **MS** | Mato Grosso do Sul (7.106 seções) | [`relatorio_ms_1t_2t.html`](docs/relatorios/ms/relatorio_ms_1t_2t.html) | [`prioridade_fiscais_ms.csv`](docs/relatorios/ms/prioridade_fiscais_ms.csv) |
| **MT** | Mato Grosso (8.287 seções) | [`relatorio_mt_1t_2t.html`](docs/relatorios/mt/relatorio_mt_1t_2t.html) | [`prioridade_fiscais_mt.csv`](docs/relatorios/mt/prioridade_fiscais_mt.csv) |
| **PA** | Pará (20.827 seções) | [`relatorio_pa_1t_2t_v2.html`](docs/relatorios/pa/relatorio_pa_1t_2t_v2.html) ([`v1`](docs/relatorios/pa/relatorio_pa_1t_2t.html)) | [`prioridade_fiscais_pa.csv`](docs/relatorios/pa/prioridade_fiscais_pa.csv) |
| **PB** | Paraíba (10.712 seções) | [`relatorio_pb_1t_2t.html`](docs/relatorios/pb/relatorio_pb_1t_2t.html) | [`prioridade_fiscais_pb.csv`](docs/relatorios/pb/prioridade_fiscais_pb.csv) |
| **PE** | Pernambuco (21.418 seções) | [`relatorio_pe_1t_2t.html`](docs/relatorios/pe/relatorio_pe_1t_2t.html) | [`prioridade_fiscais_pe.csv`](docs/relatorios/pe/prioridade_fiscais_pe.csv) |
| **PI** | Piauí (10.225 seções) | [`relatorio_pi_1t_2t.html`](docs/relatorios/pi/relatorio_pi_1t_2t.html) | [`prioridade_fiscais_pi.csv`](docs/relatorios/pi/prioridade_fiscais_pi.csv) |
| **PR** | Paraná (27.142 seções) | [`relatorio_pr_1t_2t.html`](docs/relatorios/pr/relatorio_pr_1t_2t.html) | [`prioridade_fiscais_pr.csv`](docs/relatorios/pr/prioridade_fiscais_pr.csv) |
| **RJ** | Rio de Janeiro (37.675 seções) | [`relatorio_rj_1t_2t.html`](docs/relatorios/rj/relatorio_rj_1t_2t.html) | [`prioridade_fiscais_rj.csv`](docs/relatorios/rj/prioridade_fiscais_rj.csv) |
| **RN** | Rio Grande do Norte (8.115 seções) | [`relatorio_rn_1t_2t.html`](docs/relatorios/rn/relatorio_rn_1t_2t.html) | [`prioridade_fiscais_rn.csv`](docs/relatorios/rn/prioridade_fiscais_rn.csv) |
| **RO** | Rondônia (4.698 seções) | [`relatorio_ro_1t_2t.html`](docs/relatorios/ro/relatorio_ro_1t_2t.html) | [`prioridade_fiscais_ro.csv`](docs/relatorios/ro/prioridade_fiscais_ro.csv) |
| **RR** | Roraima (1.519 seções) | [`relatorio_rr_1t_2t.html`](docs/relatorios/rr/relatorio_rr_1t_2t.html) | [`prioridade_fiscais_rr.csv`](docs/relatorios/rr/prioridade_fiscais_rr.csv) |
| **RS** | Rio Grande do Sul (27.547 seções) | [`relatorio_rs_1t_2t.html`](docs/relatorios/rs/relatorio_rs_1t_2t.html) | [`prioridade_fiscais_rs.csv`](docs/relatorios/rs/prioridade_fiscais_rs.csv) |
| **SC** | Santa Catarina (17.326 seções) | [`relatorio_sc_1t_2t.html`](docs/relatorios/sc/relatorio_sc_1t_2t.html) | [`prioridade_fiscais_sc.csv`](docs/relatorios/sc/prioridade_fiscais_sc.csv) |
| **SE** | Sergipe (5.923 seções) | [`relatorio_se_1t_2t.html`](docs/relatorios/se/relatorio_se_1t_2t.html) | [`prioridade_fiscais_se.csv`](docs/relatorios/se/prioridade_fiscais_se.csv) |
| **SP** | São Paulo (103.656 seções) | [`relatorio_sp_1t_2t.html`](docs/relatorios/sp/relatorio_sp_1t_2t.html) | [`prioridade_fiscais_sp.csv`](docs/relatorios/sp/prioridade_fiscais_sp.csv) |
| **TO** | Tocantins (4.384 seções) | [`relatorio_to_1t_2t.html`](docs/relatorios/to/relatorio_to_1t_2t.html) | [`prioridade_fiscais_to.csv`](docs/relatorios/to/prioridade_fiscais_to.csv) |
| **ZZ** | Exterior (1.351 seções) | [`relatorio_zz_1t_2t.html`](docs/relatorios/zz/relatorio_zz_1t_2t.html) | [`prioridade_fiscais_zz.csv`](docs/relatorios/zz/prioridade_fiscais_zz.csv) |

> **Como visualizar e gerar PDF:** Basta abrir o arquivo `.html` em qualquer navegador moderno (Chrome, Safari, Firefox, Edge) e clicar no botão **"Imprimir / Salvar em PDF"** no canto superior direito.

---

## 3. O Que É Verificado em Cada Seção Eleitoral

Para cada seção eleitoral $s$ de uma Unidade da Federação, o pipeline baixa em memória RAM os pacotes do 1º turno (`pleito 3220`) e do 2º turno (`pleito 3221`), valida a cadeia criptográfica SHA-256/SHA-512 e extrai:

| Dimensão Auditada | Fonte Primária no Pacote TSE | Métrica Extraída e Comparada (1ºT vs. 2ºT) |
| :--- | :--- | :--- |
| **Integridade Criptográfica** | `-aux.json` + `-vota.vsc` | Validação do SHA-256 do `.vsc`, SHA-512 do `-bu.dat` e SHA-512 do `-log.jez`, além do confronto do hash do 1º turno contra o snapshot histórico colhido em `05/10/2026`. |
| **Comparecimento e Aptos** | `-bu.dat` (ASN.1 BER) | `aptos_1t`, `aptos_2t`, `delta_aptos`, `comp_1t`, `comp_2t`, `% comparecimento` e variação em pontos percentuais (`delta_comp_pp`). |
| **Votação Nominal, Brancos e Nulos** | `-bu.dat` (ASN.1 BER) | Votos nominais por candidato (Presidente e Governador), brancos, nulos, variação líquida entre turnos e batimento de soma contra o JSON agregado oficial do TSE. |
| **Biometria vs. Liberação Manual** | `-bu.dat` + `-log.jez` (`logd.dat`) | Quantidade de eleitores identificados por biometria (`bio`) vs. liberados manualmente por código pelo mesário (`sem_bio`), eventos `Foto do eleitor apresentada`, `Solicitação de dado pessoal do eleitor para habilitação manual` por hora, identificador de 12 dígitos do mesário (`Mesário <ID> habilitou o eleitor`) e alertas de digital. |
| **Curva Horária e Votos Pós-17h** | `-log.jez` (`logd.dat`) | Contagem exata de eventos `O voto do eleitor foi computado` por hora (`08h` às `20h+`) e minuto a minuto após as `17h00` (normalizado pelo fuso horário oficial de cada município/UF). |
| **Cadência e Hardware da Urna** | `-bu.dat` + `-log.jez` | Número de série da urna (`numeroInternoUrna`), trocas de urna entre turnos ou durante a votação (contingência), reinicializações, regressões de relógio e mediana de intervalo em segundos entre votos consecutivos. |

---

## 4. Arquitetura do Código-Fonte

```text
.
├── docs/
│   ├── PRD_auditoria_1t_vs_2t.md           # Especificação técnica da auditoria comparativa 1T vs 2T
│   ├── PRD_coleta_urnas_1t_2026.md         # Especificação da coleta e preservação do 1º turno
│   ├── brainstorming/                      # Histórico versionado das análises e decisões técnicas
│   └── relatorios/
│       └── pa/                             # Relatórios HTML/XHTML, CSV e JSON publicados (Pará)
├── src/tse_coleta/
│   ├── analisador_log.py                   # Descompactador 7z/LZMA (.jez) e parser forense de logd.dat
│   ├── auditoria_uf.py                     # Pipeline streaming 1T vs 2T, consolidação e enriquecimento
│   ├── ciclo.py                            # Orquestrador de coleta por UF e controle de concorrência
│   ├── cli.py                              # Comandos de linha (`tse-coleta` e `tse-auditoria`)
│   ├── cliente.py                          # Cliente HTTP/2 assíncrono com rate-limit adaptativo e TLS
│   ├── codigos.py                          # Validação estrita de códigos e caminhos oficiais do TSE
│   ├── decodificador_bu.py                 # Decodificador ASN.1 BER nativo para Boletins de Urna (-bu.dat)
│   ├── descoberta.py                       # Descoberta automática de pleitos e eleições via ele-c.json
│   ├── integridade.py                      # Verificação criptográfica SHA-256 (.vsc) e SHA-512 (.bu/.log)
│   ├── manifesto.py                        # Diário append-only JSONL e controle de layout em disco
│   └── relatorio_html.py                   # Gerador de relatórios HTML5/XHTML com gráficos SVG e PDF
└── tests/                                  # 127 testes unitários e de integração automatizados (pytest)
```

---

## 5. Como Executar e Reproduzir por Conta Própria

### 5.1. Pré-requisitos
- **Python 3.13+**
- Utilitário `7z` ou `7zz` instalado no sistema (para descompactação de arquivos `-log.jez` do TSE; no macOS: `brew install sevenzip`, no Ubuntu/Debian: `sudo apt install p7zip-full`).

### 5.2. Instalação e Execução dos Testes Automatizados
```bash
# 1. Clone o repositório
git clone <URL_DO_REPOSITORIO>
cd tse

# 2. Crie um ambiente virtual e instale o pacote e dependências de teste
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 3. Execute os 127 testes unitários (decodificador ASN.1, parser de log, integridade SHA-512, relatórios XHTML)
.venv/bin/pytest -q
```

### 5.3. Reproduzindo a Auditoria Completa de uma UF em Streaming
O comando `tse-auditoria` baixa os pacotes do 1º e do 2º turno de cada seção eleitoral em memória RAM, confere os hashes criptográficos, grava apenas o resumo compacto (`.jsonl.gz`) na pasta de dados indicada em `--raiz` (ex.: um disco externo) e publica automaticamente os relatórios HTML e CSV em `docs/relatorios/<uf>/`:

```bash
# Auditar todas as seções do Pará (PA) diretamente dos servidores públicos do TSE:
.venv/bin/tse-auditoria --raiz /Volumes/240/TSE --uf pa --max-req 60

# Regenerar apenas o relatório HTML e o CSV a partir do resumo já processado:
.venv/bin/tse-auditoria --raiz /Volumes/240/TSE --uf pa --apenas-relatorio
```

---

## 6. Verificação Independente de Qualquer Seção no Site Oficial do TSE

Qualquer seção listada nos relatórios ou no arquivo CSV pode ser conferida manualmente no portal oficial do TSE ou via URL direta da API pública de arquivos de urna:

- **1º Turno (`pleito 3220`):**  
  `https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3220/dados/<uf>/<municipio_5_digitos>/<zona_4_digitos>/<secao_4_digitos>/p003220-<uf>-m<municipio>-z<zona>-s<secao>-aux.json`
- **2º Turno (`pleito 3221`):**  
  `https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/dados/<uf>/<municipio_5_digitos>/<zona_4_digitos>/<secao_4_digitos>/p003221-<uf>-m<municipio>-z<zona>-s<secao>-aux.json`
