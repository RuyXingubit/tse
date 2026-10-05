"""Laço de coleta: repete ciclos até tudo estar em estado final, faz a varredura final e para."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime

from .ciclo import ConfigCiclo, ListaIndisponivel, ResultadoCiclo, executar_ciclo
from .cliente import ClienteTSE, ErroDownload
from .codigos import Caminhos
from .descoberta import Pleito
from .intervalo import PoliticaIntervalo
from .manifesto import Layout

log = logging.getLogger(__name__)


async def _esperar(parar: asyncio.Event, segundos: float) -> None:
    try:
        await asyncio.wait_for(parar.wait(), timeout=segundos)
    except TimeoutError:
        pass


async def rodar(
    cliente: ClienteTSE,
    layout: Layout,
    caminhos: Caminhos,
    pleito: Pleito | None,
    cfg: ConfigCiclo = ConfigCiclo(),
    politica: PoliticaIntervalo = PoliticaIntervalo(),
    agora: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    parar: asyncio.Event | None = None,
    esperar: Callable[[asyncio.Event, float], Awaitable[None]] = _esperar,
    max_ciclos: int | None = None,
    progresso: Callable[[int, int], None] | None = None,
) -> list[ResultadoCiclo]:
    """Retorna os resultados de cada ciclo executado (útil para testes e para o resumo final)."""
    parar = parar or asyncio.Event()
    resultados: list[ResultadoCiclo] = []
    ultimo_progresso = agora()
    n = 0
    while not parar.is_set() and (max_ciclos is None or n < max_ciclos):
        n += 1
        try:
            res = await executar_ciclo(cliente, layout, caminhos, cfg, agora, progresso, pleito)
        except (ListaIndisponivel, ErroDownload) as e:
            log.warning("ciclo %d abortado: %s — nova tentativa em %s", n, e, politica.apos_erro)
            await esperar(parar, politica.apos_erro.total_seconds())
            continue
        resultados.append(res)
        r = res.resumo
        log.info(
            "ciclo %d: %d/%d urnas publicadas, %d completas, %d finais, %d coletadas, snapshot=%s",
            n, r["publicadas"], r["urnas"], r["completas"], r["finais"], r["coletadas_neste_ciclo"],
            res.snapshot.name if res.snapshot else "-",
        )
        if res.mudou:
            ultimo_progresso = agora()

        if res.terminado:
            if cfg.varredura_completa:
                log.info("varredura final concluída e tudo em estado final — coleta encerrada")
                break
            log.info("todas as urnas em estado final — iniciando varredura final completa")
            cfg = replace(cfg, varredura_completa=True)
            continue
        if cfg.varredura_completa:  # varredura final achou algo pendente: volta ao modo normal
            cfg = replace(cfg, varredura_completa=False)

        espera = politica.proximo(ultimo_progresso, agora())
        log.info("próximo ciclo em %s", espera)
        await esperar(parar, espera.total_seconds())
    return resultados
