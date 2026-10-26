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

Os relatórios finais consolidados ficam versionados na pasta [`docs/relatorios/`](docs/relatorios/) deste repositório (enquanto os arquivos intermediários pesados de gigabytes permanecem em armazenamento externo local):

### Estado do Pará (`PA` — 20.827 Seções Eleitorais Auditadas)
- **[`docs/relatorios/pa/relatorio_pa_1t_2t_v2.html`](docs/relatorios/pa/relatorio_pa_1t_2t_v2.html)** — **Relatório Forense Completo (Versão 2):**
  - 10 gráficos vetoriais SVG com legendas completas e suporte nativo a impressão / exportação em PDF (`Imprimir / Salvar em PDF`);
  - Batimento matemático exato entre a soma das 20.827 urnas (`-bu.dat`) e o resultado oficial consolidado pelo TSE (`0` divergência);
  - Radiografia das **7.055 seções** que aumentaram o comparecimento entre o 1º e o 2º turno;
  - Análise da curva horária de votação (foco na janela das **08h00 às 10h59** e nos votos registrados após as **17h00**);
  - Auditoria de biometria vs. habilitação manual por código pelo mesário, incluindo o rastreamento nominal dos identificadores de mesários registrados no `logd.dat` (`Mesário <12_dígitos> habilitou o eleitor`), a contagem de `Foto do eleitor apresentada`, os alertas de segurança de digital não associada e a verificação da emissão da fita `[ELEITORES HABILITADOS BIOGRAFICAMENTE]`;
  - Análise técnica das **1.488 seções** com variação no número de eleitores aptos entre turnos (Transferência Temporária de Eleitores / TTE vs. atualizações cadastrais do Sistema ELO).
- **[`docs/relatorios/pa/relatorio_pa_1t_2t.html`](docs/relatorios/pa/relatorio_pa_1t_2t.html)** — **Relatório Inicial (Versão 1 preservada para histórico).**
- **[`docs/relatorios/pa/prioridade_fiscais_pa.csv`](docs/relatorios/pa/prioridade_fiscais_pa.csv)** — **Catálogo de Prioridade de Seções Eleitorais (CSV):**
  - Lista das **1.303 seções** com alertas estatísticos no Pará, ordenadas de forma **decrescente pelo tamanho do colégio eleitoral da seção (`aptos_2t`)** para priorização objetiva de fiscalização e auditoria amostral.
- **[`docs/relatorios/pa/auditoria_mesarios_biometria.json`](docs/relatorios/pa/auditoria_mesarios_biometria.json)** — **Dados Estruturados (JSON) da Janela da Manhã (08h–11h) e Auditoria de Mesários no `log.jez`.**
- **[`docs/relatorios/pa/analise_consolidada_v2.json`](docs/relatorios/pa/analise_consolidada_v2.json)** — **Consolidação Estatística Completa (JSON) da Versão 2.**

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
