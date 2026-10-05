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

from .ciclo import UFS, ConfigCiclo
from .cliente import MAX_REQ_PADRAO, ClienteTSE
from .codigos import Caminhos, validar
from .descoberta import descobrir_pleito
from .laco import rodar
from .manifesto import Layout

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


if __name__ == "__main__":
    sys.exit(main())
