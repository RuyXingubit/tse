import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from fabrica import CAM, ServidorFalso, sem_espera
from test_ciclo import CFG, rotas
from tse_coleta.cli import ErroDeAmbiente, argumentos, travar, verificar_raiz
from tse_coleta.cliente import ClienteTSE
from tse_coleta.intervalo import PoliticaIntervalo
from tse_coleta.laco import rodar
from tse_coleta.manifesto import Layout

BRT = timezone(timedelta(hours=-3))
T0 = datetime(2026, 10, 4, 23, 0, tzinfo=BRT)


# ---------- intervalo ----------

def test_intervalo_adaptativo():
    p = PoliticaIntervalo()
    assert p.proximo(T0, T0 + timedelta(hours=1)) == timedelta(minutes=10)
    assert p.proximo(T0, T0 + timedelta(hours=24)) == timedelta(hours=1)
    assert p.proximo(T0, T0 + timedelta(hours=47)) == timedelta(hours=1)
    assert p.proximo(T0, T0 + timedelta(hours=48)) == timedelta(hours=6)


# ---------- laço ----------

class Relogio:
    def __init__(self):
        self.t = T0
        self.esperas: list[float] = []

    def __call__(self):
        return self.t

    async def esperar(self, parar, s):
        self.esperas.append(s)
        self.t += timedelta(seconds=s)


class ServidorMutavel(ServidorFalso):
    """Troca as rotas a cada ciclo (detectado pelo pedido da lista)."""

    def __init__(self, sequencia):
        super().__init__(sequencia[0])
        self.seq = sequencia
        self.ciclo = 0

    def __call__(self, req):
        rel = req.url.path.removeprefix("/oficial/")
        if rel == CAM.lista_secoes("rr"):
            self.rotas = self.seq[min(self.ciclo, len(self.seq) - 1)]
            self.ciclo += 1
        return super().__call__(req)


async def _rodar(tmp_path, serv, rel, **kw):
    async with ClienteTSE("https://t.test/oficial/", transport=httpx.MockTransport(serv), dormir=sem_espera) as c:
        return await rodar(c, Layout(tmp_path), CAM, None, CFG, agora=rel, esperar=rel.esperar, **kw)


async def test_laco_termina_com_varredura_final(tmp_path):
    rel = Relogio()
    serv = ServidorMutavel([rotas(), rotas("Totalizada", s3_publicada=True)])
    res = await _rodar(tmp_path, serv, rel)
    # Recebida só é reconsultada após 30 min: ciclos em t=0,10,20 ainda pendentes;
    # t=30 vê Totalizada (terminado); em seguida a varredura final → fim
    assert [r.terminado for r in res] == [False, False, False, True, True]
    assert [r.resumo["varredura_completa"] for r in res] == [False, False, False, False, True]
    assert rel.esperas == [600, 600, 600]


async def test_laco_tolera_lista_indisponivel(tmp_path):
    rel = Relogio()
    falhou = {"n": 0}
    base = ServidorFalso(rotas("Totalizada", s3_publicada=True))

    def serv(req):
        if req.url.path.endswith("-cs.json") and falhou["n"] < 1:
            falhou["n"] += 1
            return httpx.Response(404)
        return base(req)

    res = await _rodar(tmp_path, serv, rel)
    assert rel.esperas[0] == 120  # espera de erro
    assert res[-1].terminado


async def test_laco_respeita_max_ciclos_e_parar(tmp_path):
    rel = Relogio()
    res = await _rodar(tmp_path, ServidorFalso(rotas()), rel, max_ciclos=2)
    assert len(res) == 2
    parar = asyncio.Event()
    parar.set()
    res = await _rodar(tmp_path, ServidorFalso(rotas()), rel, parar=parar)
    assert res == []


async def test_intervalo_cresce_sem_progresso(tmp_path):
    rel = Relogio()
    pol = PoliticaIntervalo(normal=timedelta(minutes=10), apos_lento=timedelta(minutes=25),
                            lento=timedelta(hours=1))
    await _rodar(tmp_path, ServidorFalso(rotas()), rel, max_ciclos=5, politica=pol)
    # 1º ciclo é progresso; depois nada muda: 10, 10, 10 (30 min parado ≥ 25) → 1 h
    assert rel.esperas[:4] == [600, 600, 600, 3600]


# ---------- CLI / ambiente ----------

def test_raiz_precisa_existir(tmp_path):
    with pytest.raises(ErroDeAmbiente, match="montado"):
        verificar_raiz(tmp_path / "nao_montado", 0)


def test_espaco_minimo(tmp_path):
    with pytest.raises(ErroDeAmbiente, match="livres"):
        verificar_raiz(tmp_path, 10**9)


def test_instancia_unica(tmp_path):
    lay = Layout(tmp_path)
    t1 = travar(lay)
    with pytest.raises(ErroDeAmbiente, match="já existe"):
        travar(lay)
    t1.close()
    travar(lay).close()  # liberou


def test_argumentos_validam(tmp_path):
    a = argumentos(["--raiz", str(tmp_path), "--ufs", "rr,ac"])
    assert a.ufs == ("rr", "ac") and a.conexoes == 64 and a.max_req == 60
    with pytest.raises(Exception):
        argumentos(["--raiz", str(tmp_path), "--ufs", "../x"])
    with pytest.raises(SystemExit):
        argumentos(["--raiz", str(tmp_path), "--conexoes", "999"])
