"""Linha de comando: `tse-coleta --raiz /Volumes/240/TSE`.

Proteções:
- A raiz PRECISA já existir (se o disco externo não estiver montado, aborta em vez de criar
  pastas no disco interno).
- Uma única instância por raiz (trava com flock em estado/.trava).
- Aborta se o espaço livre ficar abaixo de --min-livre-gb.
- No macOS, se reexecuta sob `caffeinate` para o Mac não dormir durante a coleta.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import logging
import os
import shutil
import signal
import sys
from datetime import datetime
from pathlib import Path

from .auditoria_uf import (
    consolidar_agregado_nacional,
    consolidar_analise_uf,
    executar_auditoria_uf,
    exportar_csv_prioridade_fiscais,
)
from .ciclo import UFS, ConfigCiclo
from .cliente import MAX_REQ_PADRAO, ClienteTSE
from .codigos import Caminhos, validar
from .descoberta import descobrir_pleito
from .laco import rodar
from .manifesto import Layout
from .relatorio_html import gerar_relatorio_html

log = logging.getLogger("tse_coleta")

ENV_CAFEINA = "TSE_COLETA_CAFFEINATE"


class ErroDeAmbiente(RuntimeError):
    pass


def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tse-coleta", description="Coleta e preserva arquivos de urna e resultados do TSE.")
    p.add_argument("--raiz", required=True, type=Path, help="pasta de dados (precisa existir), ex.: /Volumes/240/TSE")
    p.add_argument("--ciclo", default="ele2026")
    p.add_argument("--data", default="04/10/2026", help="data do pleito (dd/mm/aaaa)")
    p.add_argument("--ufs", default=",".join(UFS), help="UFs separadas por vírgula (padrão: todas + zz)")
    p.add_argument("--uma-vez", action="store_true", help="executa um único ciclo e sai")
    p.add_argument("--varredura-completa", action="store_true", help="reconsulta todas as seções publicadas")
    p.add_argument("--conexoes", type=int, default=64)
    p.add_argument("--max-req", type=float, default=MAX_REQ_PADRAO,
                   help=f"teto de requisições por segundo (padrão {MAX_REQ_PADRAO:.0f})")
    p.add_argument("--min-livre-gb", type=float, default=5.0)
    p.add_argument("--sem-caffeinate", action="store_true")
    a = p.parse_args(argv)
    a.ufs = tuple(validar("uf", u.strip()) for u in a.ufs.split(",") if u.strip())
    if not 1 <= a.conexoes <= 256:
        p.error("--conexoes deve estar entre 1 e 256")
    if not 0 < a.max_req <= 1000:
        p.error("--max-req deve estar entre 0 e 1000")
    return a


def verificar_raiz(raiz: Path, min_livre_gb: float) -> None:
    if not raiz.is_dir():
        raise ErroDeAmbiente(f"raiz {raiz} não existe — o disco externo está montado?")
    if not os.access(raiz, os.W_OK):
        raise ErroDeAmbiente(f"sem permissão de escrita em {raiz}")
    livre = shutil.disk_usage(raiz).free / 1024**3
    if livre < min_livre_gb:
        raise ErroDeAmbiente(f"apenas {livre:.1f} GB livres em {raiz} (mínimo {min_livre_gb} GB)")


def travar(layout: Layout):
    """Retorna o arquivo travado (mantenha a referência viva enquanto o processo roda)."""
    layout.estado.mkdir(parents=True, exist_ok=True)
    f = open(layout.estado / ".trava", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        raise ErroDeAmbiente(f"já existe uma coleta rodando em {layout.raiz}") from None
    f.write(str(os.getpid()))
    f.flush()
    return f


def configurar_log(layout: Layout) -> Path:
    layout.logs.mkdir(parents=True, exist_ok=True)
    arq = layout.logs / f"coleta-{datetime.now():%Y-%m-%dT%H-%M-%S}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    for h in (logging.FileHandler(arq, encoding="utf-8"), logging.StreamHandler(sys.stderr)):
        h.setFormatter(fmt)
        raiz.addHandler(h)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return arq


def _cafeinar(argv: list[str]) -> None:
    """No macOS, reexecuta sob caffeinate (-i ocioso, -m disco, -s sistema na tomada)."""
    if sys.platform != "darwin" or os.environ.get(ENV_CAFEINA) or not shutil.which("caffeinate"):
        return
    env = dict(os.environ, **{ENV_CAFEINA: "1"})
    os.execvpe("caffeinate", ["caffeinate", "-ims", sys.executable, "-m", "tse_coleta.cli", *argv], env)


async def principal(a: argparse.Namespace) -> int:
    layout = Layout(a.raiz)
    verificar_raiz(a.raiz, a.min_livre_gb)
    trava = travar(layout)  # noqa: F841 — mantém a trava até o fim
    layout.criar()
    arq_log = configurar_log(layout)
    log.info("início: raiz=%s ufs=%d conexoes=%d max_req=%.0f/s log=%s",
             a.raiz, len(a.ufs), a.conexoes, a.max_req, arq_log)

    parar = asyncio.Event()
    loop = asyncio.get_running_loop()
    tarefa = asyncio.current_task()

    def ao_sinal():
        if not parar.is_set():
            log.warning("interrupção recebida: encerrando (o progresso fica salvo no diário)")
            parar.set()
            tarefa.cancel()

    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, ao_sinal)

    async with ClienteTSE(concorrencia=a.conexoes, max_req_por_s=a.max_req) as c:
        bruto = await c.obter("comum/config/ele-c.json")
        if bruto is None:
            raise ErroDeAmbiente("comum/config/ele-c.json indisponível")
        pleito = descobrir_pleito(json.loads(bruto), a.ciclo, a.data)
        log.info("pleito %s (%s): eleições %s", pleito.codigo, pleito.data,
                 ", ".join(f"{e.codigo}[{'/'.join(c.codigo for c in e.cargos)}]" for e in pleito.eleicoes))
        caminhos = Caminhos(a.ciclo, pleito.codigo)
        cfg = ConfigCiclo(ufs=a.ufs, varredura_completa=a.varredura_completa,
                          trabalhadores=max(160, a.conexoes * 3))
        inicio = datetime.now()

        def progresso(feitos: int, total: int) -> None:
            dt = (datetime.now() - inicio).total_seconds() or 1
            taxa = f"{c.taxa_atual:.0f}" if c.taxa_atual else "sem teto"
            log.info("  %d/%d seções (%.0f%%) — %.0f req/s acumulado; teto vigente %s req/s; pausas %d",
                     feitos, total, 100 * feitos / total, c.estatisticas["ok"] / dt, taxa,
                     c.estatisticas["pausas"])
            verificar_raiz(a.raiz, a.min_livre_gb)  # disco desmontado/cheio no meio → aborta

        try:
            await rodar(c, layout, caminhos, pleito, cfg, parar=parar,
                        max_ciclos=1 if a.uma_vez else None, progresso=progresso)
        except asyncio.CancelledError:
            log.warning("coleta interrompida; ao reiniciar, continua de onde parou")
            return 130
    log.info("fim. estatísticas HTTP: %s", dict(c.estatisticas))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    a = argumentos(argv)
    if not a.sem_caffeinate:
        _cafeinar(argv)
    try:
        return asyncio.run(principal(a))
    except ErroDeAmbiente as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


UFS_POR_TAMANHO = (
    "zz", "rr", "ap", "ac", "to", "ro", "se", "df", "al", "ms", "rn", "am", "mt", "es",
    "pi", "pb", "go", "sc", "ma", "pa", "pe", "ce", "pr", "rs", "ba", "rj", "mg", "sp",
)


def argumentos_auditoria(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="tse-auditoria",
        description="Auditoria comparativa 1º vs 2º turno por UF em streaming com geração de resumo e relatório HTML/PDF.",
    )
    p.add_argument("--raiz", required=True, type=Path, help="pasta de dados (ex.: /Volumes/240/TSE)")
    p.add_argument(
        "--uf",
        required=True,
        help="sigla da UF (ex.: pa), lista separada por vírgulas (ex.: rr,ap,ac) ou 'todas'",
    )
    p.add_argument("--conexoes", type=int, default=64)
    p.add_argument(
        "--max-req",
        type=float,
        default=MAX_REQ_PADRAO,
        help=f"teto de requisições por segundo (padrão {MAX_REQ_PADRAO:.0f})",
    )
    p.add_argument("--min-livre-gb", type=float, default=2.0)
    p.add_argument(
        "--apenas-relatorio",
        action="store_true",
        help="regenera a consolidação e o relatório HTML a partir de resumo_secoes.jsonl já salvo",
    )
    p.add_argument(
        "--agregado-nacional",
        action="store_true",
        help="ao finalizar as UFs solicitadas, gera o relatório consolidado nacional (br)",
    )
    p.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("docs/relatorios"),
        help="pasta pública no repositório Git onde os relatórios HTML/CSV serão espelhados (padrão: docs/relatorios)",
    )
    p.add_argument("--sem-caffeinate", action="store_true")
    a = p.parse_args(argv)
    uf_arg = a.uf.strip().lower()
    if uf_arg in ("todas", "all", "br"):
        a.ufs_auditoria = UFS_POR_TAMANHO
        a.uf = a.ufs_auditoria[0]
        a.agregado_nacional = True
    else:
        partes = [validar("uf", u.strip().lower()) for u in uf_arg.split(",") if u.strip()]
        if not partes:
            p.error("--uf inválida")
        a.ufs_auditoria = tuple(partes)
        a.uf = a.ufs_auditoria[0]
    if not 1 <= a.conexoes <= 256:
        p.error("--conexoes deve estar entre 1 e 256")
    if not 0 < a.max_req <= 1000:
        p.error("--max-req deve estar entre 0 e 1000")
    return a


def _publicar_artefatos_uf(pasta_uf: Path, uf: str, analise_doc: dict, docs_dir: Path | None) -> Path:
    arq_analise = pasta_uf / "analise_consolidada.json"
    arq_html = pasta_uf / f"relatorio_{uf}_1t_2t.html"
    arq_csv = pasta_uf / f"prioridade_fiscais_{uf}.csv"
    arq_mes = pasta_uf / "auditoria_mesarios_biometria.json"

    lista_csv = (analise_doc.get("prioridade_fiscais") or {}).pop(
        "_lista_completa_csv",
        (analise_doc.get("prioridade_fiscais") or {}).get("lista_ordenada_por_tamanho", []),
    )
    if lista_csv and not arq_csv.is_file():
        exportar_csv_prioridade_fiscais(lista_csv, arq_csv)
    if not arq_mes.is_file() and "janela_manha_e_mesarios" in analise_doc:
        arq_mes.write_text(
            json.dumps(analise_doc["janela_manha_e_mesarios"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    gerar_relatorio_html(analise_doc, arq_html)
    if docs_dir:
        pasta_docs_uf = docs_dir / uf
        pasta_docs_uf.mkdir(parents=True, exist_ok=True)
        for arq in (arq_html, arq_analise, arq_csv, arq_mes):
            if arq.is_file():
                shutil.copy2(arq, pasta_docs_uf / arq.name)
        log.info("relatórios de %s espelhados em %s", uf.upper(), pasta_docs_uf)
    return arq_html


async def principal_auditoria(a: argparse.Namespace) -> int:
    layout = Layout(a.raiz)
    verificar_raiz(a.raiz, a.min_livre_gb)
    trava = travar(layout)  # noqa: F841
    arq_log = configurar_log(layout)
    ufs_alvo: tuple[str, ...] = getattr(a, "ufs_auditoria", (a.uf,))
    log.info(
        "início auditoria 1T vs 2T: raiz=%s ufs=%s conexoes=%d max_req=%.0f/s log=%s",
        a.raiz,
        ",".join(u.upper() for u in ufs_alvo),
        a.conexoes,
        a.max_req,
        arq_log,
    )

    if a.apenas_relatorio:
        for uf_atual in ufs_alvo:
            pasta_uf = a.raiz / "auditoria" / uf_atual
            arq_analise = pasta_uf / "analise_consolidada.json"
            if arq_analise.is_file():
                analise = json.loads(arq_analise.read_text(encoding="utf-8"))
                arq_html = _publicar_artefatos_uf(pasta_uf, uf_atual, analise, a.docs_dir)
                log.info("relatório regenerado: %s", arq_html)
        return 0

    parar = asyncio.Event()
    loop = asyncio.get_running_loop()
    tarefa = asyncio.current_task()

    def ao_sinal():
        if not parar.is_set():
            log.warning("interrupção recebida: encerrando (o progresso em resumo_secoes está salvo)")
            parar.set()
            if tarefa:
                tarefa.cancel()

    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, ao_sinal)

    async with ClienteTSE(concorrencia=a.conexoes, max_req_por_s=a.max_req) as c:
        for idx_uf, uf_atual in enumerate(ufs_alvo, start=1):
            pasta_uf = a.raiz / "auditoria" / uf_atual
            arq_gz = pasta_uf / "resumo_secoes.jsonl.gz"
            arq_an_existente = pasta_uf / "analise_consolidada.json"
            # Se a UF já está 100% concluída com resumo_secoes.jsonl.gz e analise_consolidada.json (ex.: PA), pula
            if len(ufs_alvo) > 1 and arq_gz.is_file() and arq_an_existente.is_file() and not (pasta_uf / "resumo_secoes.jsonl").is_file():
                if a.docs_dir and (a.docs_dir / uf_atual / f"relatorio_{uf_atual}_1t_2t.html").is_file():
                    log.info("[%d/%d] UF %s já concluída e publicada em docs/; pulando", idx_uf, len(ufs_alvo), uf_atual.upper())
                    continue
                log.info("[%d/%d] UF %s já concluída em disco; espelhando em docs/", idx_uf, len(ufs_alvo), uf_atual.upper())
                analise_ex = json.loads(arq_an_existente.read_text(encoding="utf-8"))
                _publicar_artefatos_uf(pasta_uf, uf_atual, analise_ex, a.docs_dir)
                continue

            inicio_uf = datetime.now()
            ok_inicio = c.estatisticas["ok"]

            def progresso(feitos: int, total: int, _uf: str = uf_atual, _ini: datetime = inicio_uf, _ok0: int = ok_inicio) -> None:
                dt = (datetime.now() - _ini).total_seconds() or 1
                taxa = f"{c.taxa_atual:.0f}" if c.taxa_atual else "sem teto"
                log.info(
                    "  [%s %d/%d] %d/%d seções (%.1f%%) — %.0f req/s na UF; teto vigente %s req/s; pausas %d",
                    _uf.upper(),
                    idx_uf,
                    len(ufs_alvo),
                    feitos,
                    total,
                    100 * feitos / total,
                    (c.estatisticas["ok"] - _ok0) / dt,
                    taxa,
                    c.estatisticas["pausas"],
                )
                verificar_raiz(a.raiz, a.min_livre_gb)

            try:
                arq_gz, arq_an = await executar_auditoria_uf(
                    c,
                    a.raiz,
                    uf_atual,
                    trabalhadores=max(160, a.conexoes * 3),
                    progresso=progresso,
                )
            except asyncio.CancelledError:
                log.warning("auditoria interrompida em %s; ao reiniciar, continua exatamente de onde parou", uf_atual.upper())
                return 130

            analise = json.loads(arq_an.read_text(encoding="utf-8"))
            arq_html = _publicar_artefatos_uf(pasta_uf, uf_atual, analise, a.docs_dir)
            log.info("[%d/%d] UF %s concluída: resumo=%s relatorio=%s", idx_uf, len(ufs_alvo), uf_atual.upper(), arq_gz, arq_html)

        if getattr(a, "agregado_nacional", False):
            log.info("iniciando consolidação do Agregado Geral Nacional (BR)...")
            arq_an_br, _ = await consolidar_agregado_nacional(c, a.raiz, UFS_POR_TAMANHO)
            pasta_br = a.raiz / "auditoria" / "br"
            analise_br = json.loads(arq_an_br.read_text(encoding="utf-8"))
            arq_html_br = _publicar_artefatos_uf(pasta_br, "br", analise_br, a.docs_dir)
            log.info("Agregado Geral Nacional (BR) concluído: %s", arq_html_br)

    log.info("fim. estatísticas HTTP: %s", dict(c.estatisticas))
    return 0


def main_auditoria(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    a = argumentos_auditoria(argv)
    if not a.sem_caffeinate and sys.platform == "darwin" and not os.environ.get(ENV_CAFEINA) and shutil.which("caffeinate"):
        env = dict(os.environ, **{ENV_CAFEINA: "1"})
        os.execvpe(
            "caffeinate",
            ["caffeinate", "-ims", sys.executable, "-c", "import sys; from tse_coleta.cli import main_auditoria; sys.exit(main_auditoria())", *argv],
            env,
        )
    try:
        return asyncio.run(principal_auditoria(a))
    except ErroDeAmbiente as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
