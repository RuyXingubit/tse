import json

import httpx
import pytest

from fabrica import CAM, ServidorFalso, sem_espera
from tse_coleta.agregados import (
    CONFIG_GERAL,
    EstadoAgregados,
    abrangencias,
    alvos_municipio,
    alvos_uf,
    coletar_agregados,
    municipios_fechados,
)
from tse_coleta.cliente import ClienteTSE
from tse_coleta.codigos import CodigoInvalido
from tse_coleta.descoberta import Cargo, Eleicao, Pleito
from tse_coleta.espelho import Espelho
from tse_coleta.manifesto import Registro

PLEITO = Pleito("ele2026", "3220", "04/10/2026", (
    Eleicao("6257", "Federal", "1", (Cargo("1", "Presidente"),)),
    Eleicao("6259", "Estadual", "1", (Cargo("3", "Governador"), Cargo("8", "Deputado Distrital"))),
    Eleicao("6261", "Municipal", "1", (Cargo("25", "Conselheiro Distrital"),)),
))

CM = {
    "6257": {"abr": [{"cd": "rr", "mu": [{"cd": "03085"}, {"cd": "03123"}]}, {"cd": "zz", "mu": [{"cd": "29999"}]}]},
    "6259": {"abr": [{"cd": "rr", "mu": [{"cd": "03085"}, {"cd": "03123"}]}]},
    "6261": {"abr": [{"cd": "pe", "mu": [{"cd": "30015"}]}]},
}
ABR = {e: abrangencias(d) for e, d in CM.items()}


def reg(uf, mun, sec, publicada=True, completa=True, tem_urna=True):
    return Registro(chave=f"{uf}-{mun}-0001-{sec}", uf=uf, municipio=mun, zona="0001", secao=sec,
                    tem_urna=tem_urna, publicada=publicada, completa=completa)


def test_abrangencias_valida_codigos():
    assert ABR["6257"] == {"rr": ["03085", "03123"], "zz": ["29999"]}
    with pytest.raises(CodigoInvalido):
        abrangencias({"abr": [{"cd": "../", "mu": []}]})


def test_alvos_uf_incluem_br_e_ufs_por_eleicao():
    alvos = alvos_uf(CAM, PLEITO, ABR)
    assert "ele2026/6257/dados/br/br-c0001-e006257-u.json" in alvos
    assert "ele2026/6257/dados/zz/zz-c0001-e006257-u.json" in alvos
    assert "ele2026/6259/dados/rr/rr-c0008-e006259-u.json" in alvos
    assert not any("6259/dados/zz" in a for a in alvos)  # estaduais não têm exterior


def test_alvos_municipio():
    assert alvos_municipio(CAM, PLEITO, ABR, "rr", "03085") == [
        "ele2026/6257/dados/rr/rr03085-c0001-e006257-u.json",
        "ele2026/6259/dados/rr/rr03085-c0003-e006259-u.json",
        "ele2026/6259/dados/rr/rr03085-c0008-e006259-u.json",
    ]
    assert alvos_municipio(CAM, PLEITO, ABR, "pe", "30015") == [
        "ele2026/6261/dados/pe/pe30015-c0025-e006261-u.json"
    ]


def test_municipios_fechados():
    regs = [
        reg("rr", "03085", "0001"), reg("rr", "03085", "0002"),
        reg("rr", "03123", "0001"), reg("rr", "03123", "0002", completa=False),
        reg("rr", "03123", "0120", publicada=False, completa=False, tem_urna=False),  # agregada não conta
    ]
    assert municipios_fechados(regs) == {"rr-03085"}


def test_estado_roundtrip():
    e = EstadoAgregados({"a"}, {"rr-03085"})
    assert EstadoAgregados.de_json(e.para_json()) == e


def _rotas(extra=None):
    r = {CONFIG_GERAL: b'{"pl": []}'}
    r.update({CAM.config_municipios(e): json.dumps(d).encode() for e, d in CM.items()})
    r[CAM.agregado("6257", "1", "br")] = b'{"v": 1}'
    r[CAM.agregado("6257", "1", "rr")] = b'{"v": 1}'
    r[CAM.agregado("6259", "3", "rr")] = b'{"v": 1}'
    r.update(extra or {})
    return r


async def _rodar(tmp_path, serv, regs, estado, completa=False):
    async with ClienteTSE("https://t.test/oficial/", transport=httpx.MockTransport(serv),
                          dormir=sem_espera, max_req_por_s=None) as c:
        return await coletar_agregados(c, Espelho(tmp_path), CAM, PLEITO, {r.chave: r for r in regs}, estado, completa)


async def test_coleta_uf_versiona_e_lembra_inexistentes(tmp_path):
    estado = EstadoAgregados()
    serv = ServidorFalso(_rotas())
    r = await _rodar(tmp_path, serv, [], estado)
    assert r["uf_br"]["novo"] == 3
    assert CAM.agregado("6259", "8", "rr") in estado.inexistentes
    esp = tmp_path / "ele2026/6257/dados/br"
    assert len(list(esp.glob("br-c0001-e006257-u@*.json"))) == 1

    # 2º ciclo: mesmo conteúdo → nada novo; inexistentes não são pedidos de novo
    serv2 = ServidorFalso(_rotas())
    r2 = await _rodar(tmp_path, serv2, [], estado)
    assert r2["uf_br"] == {"igual": 3}
    assert CAM.agregado("6259", "8", "rr") not in serv2.pedidos

    # 3º ciclo: resultado mudou → nova versão, antiga preservada
    serv3 = ServidorFalso(_rotas({CAM.agregado("6257", "1", "br"): b'{"v": 2}'}))
    await _rodar(tmp_path, serv3, [], estado)
    assert len(list(esp.glob("br-c0001-e006257-u@*.json"))) == 2


async def test_municipio_baixado_uma_vez_ao_fechar(tmp_path):
    estado = EstadoAgregados()
    mun = {CAM.agregado("6257", "1", "rr", "03085"): b'{"m": 1}',
           CAM.agregado("6259", "3", "rr", "03085"): b'{"m": 1}',
           CAM.agregado("6259", "8", "rr", "03085"): b'{"m": 1}'}
    regs = [reg("rr", "03085", "0001"), reg("rr", "03123", "0001", completa=False)]
    r = await _rodar(tmp_path, ServidorFalso(_rotas(mun)), regs, estado)
    assert r["municipios"] == {"novo": 3} and estado.municipios_baixados == {"rr-03085"}

    serv = ServidorFalso(_rotas(mun))
    await _rodar(tmp_path, serv, regs, estado)
    assert not any("rr03085" in p for p in serv.pedidos)  # não baixa de novo

    serv = ServidorFalso(_rotas(mun))
    await _rodar(tmp_path, serv, regs, estado, completa=True)  # varredura final rebaixa
    assert any("rr03085" in p for p in serv.pedidos)


async def test_json_invalido_nao_e_preservado(tmp_path):
    estado = EstadoAgregados()
    serv = ServidorFalso(_rotas({CAM.agregado("6257", "1", "br"): b"<html>erro</html>"}))
    r = await _rodar(tmp_path, serv, [], estado)
    assert r["uf_br"]["invalido"] == 1
    assert not (tmp_path / "ele2026/6257/dados/br").exists()


async def test_erro_no_municipio_nao_marca_como_baixado(tmp_path):
    estado = EstadoAgregados()
    rel = CAM.agregado("6257", "1", "rr", "03085")
    serv = ServidorFalso(_rotas(), falhas={rel: 500})
    async with ClienteTSE("https://t.test/oficial/", transport=httpx.MockTransport(serv),
                          dormir=sem_espera, max_req_por_s=None, max_tentativas=1) as c:
        await coletar_agregados(c, Espelho(tmp_path), CAM, PLEITO,
                                {r.chave: r for r in [reg("rr", "03085", "0001")]}, estado)
    assert "rr-03085" not in estado.municipios_baixados


async def test_configs_preservadas(tmp_path):
    await _rodar(tmp_path, ServidorFalso(_rotas()), [], EstadoAgregados())
    assert list((tmp_path / "comum/config").glob("ele-c@*.json"))
    assert list((tmp_path / "ele2026/6261/config").glob("mun-e006261-cm@*.json"))
