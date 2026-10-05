import httpx
import pytest

from tse_coleta.cliente import ClienteTSE, ErroDownload


class Dormidor:
    def __init__(self):
        self.esperas: list[float] = []

    async def __call__(self, s: float) -> None:
        self.esperas.append(s)


def cliente_com(respostas, **kw):
    """`respostas`: lista de status/exceções devolvidos em sequência."""
    fila = list(respostas)
    chamadas = []

    def handler(req: httpx.Request):
        chamadas.append(req)
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        status, corpo, headers = (item + (b"", {}))[:3] if isinstance(item, tuple) else (item, b"ok", {})
        return httpx.Response(status, content=corpo, headers=headers)

    dorm = Dormidor()
    c = ClienteTSE("https://exemplo.test/", transport=httpx.MockTransport(handler), dormir=dorm, **{"max_req_por_s": None, **kw})
    return c, dorm, chamadas


async def test_200():
    c, _, ch = cliente_com([200])
    async with c:
        assert await c.obter("a.json") == b"ok"
    assert ch[0].headers["User-Agent"].startswith("tse-coleta/")


async def test_404_retorna_none_sem_retry():
    c, dorm, ch = cliente_com([404])
    async with c:
        assert await c.obter("a.json") is None
    assert len(ch) == 1 and dorm.esperas == []


async def test_retry_com_backoff_exponencial_em_erro_de_rede_e_5xx():
    c, dorm, _ = cliente_com([httpx.ConnectError("x"), 500, httpx.ReadTimeout("t"), 200], backoff_base=1)
    async with c:
        assert await c.obter("a.json") == b"ok"
    assert dorm.esperas == [1, 2, 4]


async def test_backoff_tem_teto():
    c, dorm, _ = cliente_com([500] * 5 + [200], backoff_base=10, backoff_max=25, max_tentativas=6)
    async with c:
        await c.obter("a")
    assert dorm.esperas == [10, 20, 25, 25, 25]


async def test_desiste_apos_max_tentativas():
    c, _, _ = cliente_com([500, 500, 500], max_tentativas=3)
    async with c:
        with pytest.raises(ErroDownload):
            await c.obter("a")
    assert c.estatisticas["desistiu"] == 1


@pytest.mark.parametrize("status", [403, 429, 503])
async def test_bloqueio_pausa_e_tenta_de_novo(status):
    c, dorm, _ = cliente_com([status, 200], pausa_bloqueio=120)
    async with c:
        assert await c.obter("a") == b"ok"
    assert dorm.esperas == [120]
    assert c.estatisticas["bloqueio"] == 1


async def test_respeita_retry_after():
    c, dorm, _ = cliente_com([(429, b"", {"Retry-After": "30"}), 200])
    async with c:
        await c.obter("a")
    assert dorm.esperas == [30]


async def test_redirecionamento_nao_e_seguido():
    c, _, ch = cliente_com([(302, b"", {"Location": "https://outro.test/"})] * 2, max_tentativas=2)
    async with c:
        with pytest.raises(ErroDownload):
            await c.obter("a")
    assert all(r.url.host == "exemplo.test" for r in ch)


class RelogioFalso:
    """Relógio que só anda quando alguém 'dorme'."""

    def __init__(self):
        self.t = 1000.0
        self.esperas: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def dormir(self, s: float) -> None:
        self.esperas.append(s)
        self.t += s


async def test_teto_de_taxa_espaca_requisicoes():
    rel = RelogioFalso()
    inicios: list[float] = []

    def handler(req):
        inicios.append(rel.t)
        return httpx.Response(200, content=b"ok")

    async with ClienteTSE("https://exemplo.test/", transport=httpx.MockTransport(handler),
                          max_req_por_s=200, dormir=rel.dormir, relogio=rel) as c:
        import asyncio
        await asyncio.gather(*(c.obter(f"{i}") for i in range(50)))
    assert len(inicios) == 50
    # 50 requisições a 200/s ocupam >= 49 * 5 ms
    assert inicios[-1] - inicios[0] == pytest.approx(49 / 200)
    intervalos = [b - a for a, b in zip(inicios, inicios[1:])]
    assert min(intervalos) == pytest.approx(1 / 200)


async def test_padroes_de_producao():
    c = ClienteTSE("https://exemplo.test/")
    try:
        assert c._sem._value == 64
        assert c._intervalo == pytest.approx(1 / 200)
    finally:
        await c.__aexit__(None, None, None)
