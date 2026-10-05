"""Cliente HTTP para resultados.tse.jus.br com cortesia e resiliência.

- No máximo `concorrencia` requisições simultâneas.
- 404 → None (ainda não publicado).
- Erro de rede / 5xx → novas tentativas com backoff exponencial.
- 403/429/503 → pausa GLOBAL (todas as tarefas esperam) e tenta de novo; respeita Retry-After.
- TLS sempre verificado; sem redirecionamentos (3xx é tratado como erro).
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://resultados.tse.jus.br/oficial/"
USER_AGENT = "tse-coleta/0.1 (preservacao de dados publicos; contato via repositorio)"
STATUS_BLOQUEIO = {403, 429, 503}


class ErroDownload(RuntimeError):
    pass


class ClienteTSE:
    def __init__(
        self,
        base_url: str = BASE_URL,
        *,
        concorrencia: int = 8,
        max_tentativas: int = 6,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
        pausa_bloqueio: float = 120.0,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
            timeout=timeout,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=concorrencia, max_keepalive_connections=concorrencia),
            transport=transport,
        )
        self._sem = asyncio.Semaphore(concorrencia)
        self._pausa = asyncio.Lock()
        self._max = max_tentativas
        self._base = backoff_base
        self._teto = backoff_max
        self._pausa_bloqueio = pausa_bloqueio
        self._dormir = dormir
        self.estatisticas: Counter[str] = Counter()

    async def __aenter__(self) -> "ClienteTSE":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._http.aclose()

    async def obter(self, rel: str) -> bytes | None:
        """Baixa `rel` (relativo à base). None se 404."""
        ultimo_erro = "?"
        for tentativa in range(1, self._max + 1):
            async with self._pausa:  # se alguém está em pausa de bloqueio, espera aqui
                pass
            async with self._sem:
                try:
                    r = await self._http.get(rel)
                except httpx.TransportError as e:
                    ultimo_erro = f"{type(e).__name__}: {e}"
                    self.estatisticas["erro_rede"] += 1
                    r = None
            if r is not None:
                if r.status_code == 200:
                    self.estatisticas["ok"] += 1
                    self.estatisticas["bytes"] += len(r.content)
                    return r.content
                if r.status_code == 404:
                    self.estatisticas["404"] += 1
                    return None
                ultimo_erro = f"HTTP {r.status_code}"
                if r.status_code in STATUS_BLOQUEIO:
                    self.estatisticas["bloqueio"] += 1
                    await self._pausar(r)
                    continue
                self.estatisticas[f"http_{r.status_code}"] += 1
            espera = min(self._teto, self._base * 2 ** (tentativa - 1))
            log.debug("tentativa %d falhou (%s) em %s; aguardando %.1fs", tentativa, ultimo_erro, rel, espera)
            await self._dormir(espera)
        self.estatisticas["desistiu"] += 1
        raise ErroDownload(f"{rel}: {ultimo_erro} após {self._max} tentativas")

    async def _pausar(self, r: httpx.Response) -> None:
        espera = self._pausa_bloqueio
        ra = r.headers.get("Retry-After", "")
        if ra.isdigit():
            espera = min(max(float(ra), 1.0), 15 * 60.0)
        if self._pausa.locked():  # outra tarefa já está pausando; só espera ela
            async with self._pausa:
                return
        async with self._pausa:
            log.warning("TSE respondeu %s; pausando todas as requisições por %.0fs", r.status_code, espera)
            await self._dormir(espera)
