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
        assert c.taxa_atual == 200
    finally:
        await c.__aexit__(None, None, None)


# ---------- taxa adaptativa (AIMD) ----------

def cliente_relogio(respostas, **kw):
    rel = RelogioFalso()
    fila = list(respostas)
    inicios: list[tuple[float, int]] = []

    def handler(req):
        st = fila.pop(0)
        inicios.append((rel.t, st))
        return httpx.Response(st, content=b"ok")

    c = ClienteTSE("https://exemplo.test/", transport=httpx.MockTransport(handler),
                   dormir=rel.dormir, relogio=rel, **kw)
    return c, rel, inicios


async def test_bloqueio_corta_taxa_pela_metade_ate_o_piso():
    c, _, _ = cliente_relogio([429, 200, 429, 200, 429, 200, 429, 200],
                              max_req_por_s=200, min_req_por_s=30, pausa_bloqueio=1)
    async with c:
        for i in range(4):
            await c.obter(f"{i}")
    assert c.taxa_atual == 30  # 200 → 100 → 50 → 30 (piso) → 30
    assert c._intervalo == pytest.approx(1 / 30)
    assert c.estatisticas["pausas"] == 4


async def test_taxa_sobe_10pct_a_cada_n_sucessos_sem_passar_do_teto():
    c, _, _ = cliente_relogio([429] + [200] * 40, max_req_por_s=200, aumentar_a_cada=5, pausa_bloqueio=1)
    async with c:
        await c.obter("bloqueado")
        assert c.taxa_atual == 100
        for i in range(3):
            await c.obter(f"{i}")
        assert c.taxa_atual == 100  # 4 sucessos (o retry do 1º conta 1): ainda não chegou a 5
        await c.obter("quinto")
        assert c.taxa_atual == pytest.approx(110)
        for i in range(35):
            await c.obter(f"x{i}")
    assert c.taxa_atual == 200  # nunca ultrapassa o teto configurado


async def test_sem_teto_nao_ha_ajuste():
    c, _, _ = cliente_relogio([429, 200], max_req_por_s=None, pausa_bloqueio=1)
    async with c:
        await c.obter("a")
    assert c.taxa_atual is None and c._intervalo == 0


async def test_nada_sai_durante_a_pausa_e_retomada_e_espacada():
    import asyncio
    c, rel, inicios = cliente_relogio([429] + [200] * 30, max_req_por_s=200, pausa_bloqueio=120, concorrencia=8)
    async with c:
        await asyncio.gather(*(c.obter(f"{i}") for i in range(30)))
    t_bloqueio = inicios[0][0]
    fim_pausa = t_bloqueio + 120
    depois = [t for t, _ in inicios[1:]]
    # nenhuma requisição começou dentro da janela de pausa
    assert not [t for t in depois if t_bloqueio < t < fim_pausa - 1e-9]
    # após a pausa, espaçamento respeita a taxa já reduzida (100/s), sem rajada
    retomada = sorted(t for t in depois if t >= fim_pausa - 1e-9)
    intervalos = [b - a for a, b in zip(retomada, retomada[1:])]
    assert intervalos and min(intervalos) >= 1 / 100 - 1e-9


async def test_bloqueio_atrasado_de_antes_da_pausa_nao_gera_nova_pausa():
    import asyncio
    lento_pode_responder = asyncio.Event()
    respostas = {"lento": [429, 200], "rapido": [429, 200]}

    async def handler(req):
        nome = req.url.path.strip("/")
        st = respostas[nome].pop(0)
        if nome == "lento" and st == 429:
            await lento_pode_responder.wait()  # só responde depois que a pausa acabou
        if nome == "rapido" and st == 200:
            lento_pode_responder.set()
        return httpx.Response(st, content=b"ok")

    esperas: list[float] = []

    async def dormir(s):
        esperas.append(s)
        await asyncio.sleep(0)

    async with ClienteTSE("https://exemplo.test/", transport=httpx.MockTransport(handler), dormir=dormir,
                          max_req_por_s=200, pausa_bloqueio=120, concorrencia=2) as c:
        lento = asyncio.create_task(c.obter("lento"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert await c.obter("rapido") == b"ok"
        assert await lento == b"ok"
    assert [e for e in esperas if e == 120] == [120]  # uma única pausa
    assert c.estatisticas["pausas"] == 1 and c.estatisticas["bloqueio"] == 2
    assert c.taxa_atual == 100  # cortada uma única vez

