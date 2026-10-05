"""Cliente HTTP para resultados.tse.jus.br com cortesia e resiliência.

- No máximo `concorrencia` requisições simultâneas e teto rígido de `max_req_por_s`
  (padrão 60/s). Na noite da eleição o Akamai do TSE bloqueou o IP (429 por IP, sem
  Retry-After) após ~1 min a ~170 req/s; por isso o padrão é conservador.
- Taxa adaptativa (AIMD): cada episódio de bloqueio corta a taxa pela metade (piso
  `min_req_por_s`); a cada `aumentar_a_cada` sucessos seguidos sobe 10%, nunca acima do teto.
- 404 → None (ainda não publicado).
- Erro de rede / 5xx → novas tentativas com backoff exponencial.
- 403/429/503 → pausa GLOBAL (nenhuma requisição sai durante a pausa). Ao fim da pausa,
  UMA requisição de sonda verifica se o bloqueio acabou; se ainda bloqueado, a pausa dobra
  (`pausa_bloqueio` → … → `pausa_max`). Episódios seguidos só "esquecem" após
  `aumentar_a_cada` sucessos. Respeita Retry-After. Bloqueios de requisições enviadas antes
  do fim da última pausa não disparam nova pausa (são respostas atrasadas do mesmo episódio).
- TLS sempre verificado; sem redirecionamentos (3xx é tratado como erro).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://resultados.tse.jus.br/oficial/"
USER_AGENT = "tse-coleta/0.1 (preservacao de dados publicos; contato via repositorio)"
STATUS_BLOQUEIO = {403, 429, 503}
CABECALHOS_DIAGNOSTICO = ("retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
                          "akamai-grn", "cdn-cache-status")
MAX_REQ_PADRAO = 60.0


class ErroDownload(RuntimeError):
    pass


class ClienteTSE:
    def __init__(
        self,
        base_url: str = BASE_URL,
        *,
        concorrencia: int = 64,
        max_req_por_s: float | None = MAX_REQ_PADRAO,
        min_req_por_s: float = 10.0,
        aumentar_a_cada: int = 2000,
        max_tentativas: int = 6,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
        pausa_bloqueio: float = 120.0,
        pausa_max: float = 15 * 60.0,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
        relogio: Callable[[], float] = time.monotonic,
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
        self._taxa = asyncio.Lock()
        self._teto_taxa = max_req_por_s
        self._piso_taxa = min(min_req_por_s, max_req_por_s) if max_req_por_s else None
        self._taxa_atual = max_req_por_s
        self._intervalo = (1.0 / max_req_por_s) if max_req_por_s else 0.0
        self._aumentar_a_cada = aumentar_a_cada
        self._sucessos_seguidos = 0
        self._episodios_seguidos = 0  # bloqueios sem um período saudável entre eles
        self._geracao = 0  # incrementa ao fim de cada pausa de bloqueio
        self._proximo = 0.0
        self._relogio = relogio
        self._max = max_tentativas
        self._base = backoff_base
        self._teto = backoff_max
        self._pausa_bloqueio = pausa_bloqueio
        self._pausa_max = pausa_max
        self._dormir = dormir
        self.estatisticas: Counter[str] = Counter()

    async def __aenter__(self) -> "ClienteTSE":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._http.aclose()

    @property
    def taxa_atual(self) -> float | None:
        """Taxa máxima vigente (req/s) após o ajuste adaptativo; None = sem teto."""
        return self._taxa_atual

    def _definir_taxa(self, nova: float) -> None:
        self._taxa_atual = nova
        self._intervalo = 1.0 / nova

    async def _liberar_envio(self) -> int:
        """Espera pausa de bloqueio e o espaçamento da taxa. Devolve a geração vigente.

        A espera pela pausa fica DENTRO do lock da taxa: assim nada sai durante a pausa e,
        ao retomar, as requisições continuam espaçadas (sem rajada).
        """
        async with self._taxa:
            async with self._pausa:
                pass
            if self._intervalo:
                agora = self._relogio()
                if self._proximo > agora:
                    await self._dormir(self._proximo - agora)
                    agora = self._proximo
                self._proximo = agora + self._intervalo
            return self._geracao

    def _registrar_sucesso(self) -> None:
        self._sucessos_seguidos += 1
        if self._sucessos_seguidos < self._aumentar_a_cada:
            return
        self._sucessos_seguidos = 0
        self._episodios_seguidos = 0  # período saudável: a próxima pausa volta ao tamanho base
        if self._teto_taxa and self._taxa_atual < self._teto_taxa:
            self._definir_taxa(min(self._teto_taxa, self._taxa_atual * 1.1))
            log.info("taxa adaptativa subiu para %.0f req/s", self._taxa_atual)

    async def obter(self, rel: str) -> bytes | None:
        """Baixa `rel` (relativo à base). None se 404."""
        ultimo_erro = "?"
        for tentativa in range(1, self._max + 1):
            async with self._pausa:  # se alguém está em pausa de bloqueio, espera aqui
                pass
            async with self._sem:
                geracao = await self._liberar_envio()
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
                    self._registrar_sucesso()
                    return r.content
                if r.status_code == 404:
                    self.estatisticas["404"] += 1
                    self._registrar_sucesso()
                    return None
                ultimo_erro = f"HTTP {r.status_code}"
                if r.status_code in STATUS_BLOQUEIO:
                    self.estatisticas["bloqueio"] += 1
                    await self._pausar(r, rel, geracao)
                    continue
                self.estatisticas[f"http_{r.status_code}"] += 1
            espera = min(self._teto, self._base * 2 ** (tentativa - 1))
            log.debug("tentativa %d falhou (%s) em %s; aguardando %.1fs", tentativa, ultimo_erro, rel, espera)
            await self._dormir(espera)
        self.estatisticas["desistiu"] += 1
        raise ErroDownload(f"{rel}: {ultimo_erro} após {self._max} tentativas")

    def _duracao_pausa(self, r: httpx.Response) -> float:
        ra = r.headers.get("Retry-After", "")
        if ra.isdigit():
            return min(max(float(ra), 1.0), self._pausa_max)
        return min(self._pausa_max, self._pausa_bloqueio * 2 ** (self._episodios_seguidos - 1))

    async def _pausar(self, r: httpx.Response, rel: str, geracao: int) -> None:
        if self._pausa.locked() or geracao < self._geracao:
            # episódio já em pausa, ou resposta atrasada de requisição enviada antes do fim
            # da última pausa: apenas espera a pausa vigente (se houver) e tenta de novo.
            async with self._pausa:
                return
        async with self._pausa:
            try:
                self._sucessos_seguidos = 0
                if self._taxa_atual:
                    self._definir_taxa(max(self._piso_taxa, self._taxa_atual / 2))
                self.estatisticas["pausas"] += 1
                while True:
                    self._episodios_seguidos += 1
                    espera = self._duracao_pausa(r)
                    diag = {k: r.headers[k] for k in CABECALHOS_DIAGNOSTICO if k in r.headers}
                    log.warning("TSE respondeu %s %s; pausando todas as requisições por %.0fs "
                                "(bloqueio seguido nº %d); taxa agora %s req/s",
                                r.status_code, diag, espera, self._episodios_seguidos,
                                f"{self._taxa_atual:.0f}" if self._taxa_atual else "sem teto")
                    await self._dormir(espera)
                    # sonda: uma única requisição verifica se o bloqueio acabou
                    self.estatisticas["sondas"] += 1
                    try:
                        sonda = await self._http.get(rel)
                    except httpx.TransportError:
                        break  # não é bloqueio; os retries normais cuidam do erro de rede
                    finally:
                        if self._intervalo:
                            self._proximo = self._relogio() + self._intervalo
                    if sonda.status_code not in STATUS_BLOQUEIO:
                        log.info("sonda respondeu %s: retomando a coleta", sonda.status_code)
                        break
                    self.estatisticas["sondas_bloqueadas"] += 1
                    r = sonda
            finally:
                self._geracao += 1
