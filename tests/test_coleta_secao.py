import hashlib
import json

import httpx
import pytest

from tse_coleta.cliente import ClienteTSE
from tse_coleta.codigos import Caminhos, IdSecao
from tse_coleta.coleta_secao import coletar_secao
from tse_coleta.espelho import Espelho
from tse_coleta.integridade import codificar_hash_tse

CAM = Caminhos("ele2026", "3220")
SEC = IdSecao("rr", "03085", "0008", "0001")
PREF = "o03220rr0308500080001"


def montar_versao(bu: bytes, status="Totalizado"):
    vsc = b"VSC" + hashlib.sha512(bu).digest() + b"FIM"
    h = codificar_hash_tse(hashlib.sha256(vsc).digest())
    entrada = {
        "hash": h, "dr": "04/10/2026", "hr": "17:58:39", "st": status,
        "arq": [
            {"nm": f"{PREF}-vota.vsc", "tp": "vota"},
            {"nm": f"{PREF}-rdv.dat", "tp": "rdv"},
            {"nm": f"{PREF}-bu.dat", "tp": "bu"},
            {"nm": f"{PREF}-log.jez", "tp": "log"},
        ],
    }
    arquivos = {
        CAM.arquivo_urna(SEC, h, f"{PREF}-vota.vsc"): vsc,
        CAM.arquivo_urna(SEC, h, f"{PREF}-bu.dat"): bu,
    }
    return h, entrada, arquivos


class ServidorFalso:
    def __init__(self, rotas: dict[str, bytes]):
        self.rotas = rotas
        self.pedidos: list[str] = []

    def __call__(self, req: httpx.Request):
        rel = req.url.path.removeprefix("/oficial/")
        self.pedidos.append(rel)
        if rel in self.rotas:
            return httpx.Response(200, content=self.rotas[rel])
        return httpx.Response(404)


async def _sem_espera(_):
    return None


def cliente(serv):
    return ClienteTSE("https://t.test/oficial/", transport=httpx.MockTransport(serv), dormir=_sem_espera)


def aux_doc(st, *entradas):
    return json.dumps({"dg": "04/10/2026", "hg": "21:09:52", "st": st, "hashes": list(entradas)}).encode()


async def test_coleta_completa_e_valida(tmp_path):
    h, ent, arqs = montar_versao(b"BU-1")
    serv = ServidorFalso({CAM.aux_secao(SEC): aux_doc("Totalizada", ent), **arqs})
    esp = Espelho(tmp_path)
    async with cliente(serv) as c:
        r = await coletar_secao(c, esp, CAM, SEC)
    assert r.completa and r.status_tse == "Totalizada"
    assert r.versoes[0]["gravados"] == ["vota", "bu"]
    for rel, conteudo in arqs.items():
        assert esp.ler(rel) == conteudo
    assert esp.ler(r.aux_rel) is not None
    # não baixa rdv/log
    assert not any(p.endswith(("rdv.dat", "log.jez")) for p in serv.pedidos)


async def test_aux_inexistente_e_pendente(tmp_path):
    async with cliente(ServidorFalso({})) as c:
        r = await coletar_secao(c, Espelho(tmp_path), CAM, SEC)
    assert r.status_tse is None and r.erro is None and not r.completa
    assert not any(tmp_path.iterdir())


async def test_retomada_nao_baixa_de_novo(tmp_path):
    h, ent, arqs = montar_versao(b"BU-1")
    serv = ServidorFalso({CAM.aux_secao(SEC): aux_doc("Totalizada", ent), **arqs})
    esp = Espelho(tmp_path)
    async with cliente(serv) as c:
        await coletar_secao(c, esp, CAM, SEC)
        serv.pedidos.clear()
        r = await coletar_secao(c, esp, CAM, SEC)
    assert r.completa and r.versoes[0]["gravados"] == []
    assert serv.pedidos == [CAM.aux_secao(SEC)]  # só reconsultou o aux


async def test_bu_adulterado_nao_e_gravado(tmp_path):
    h, ent, arqs = montar_versao(b"BU-1")
    rel_bu = next(k for k in arqs if k.endswith("bu.dat"))
    arqs[rel_bu] = b"BU-ADULTERADO"
    serv = ServidorFalso({CAM.aux_secao(SEC): aux_doc("Totalizada", ent), **arqs})
    esp = Espelho(tmp_path)
    async with cliente(serv) as c:
        r = await coletar_secao(c, esp, CAM, SEC)
    assert not r.completa
    assert r.versoes[0]["motivo"] == "bu.dat não confere com o vota.vsc"
    assert esp.ler(rel_bu) is None
    assert all(esp.ler(k) is None for k in arqs)  # nem o vsc é gravado sem o BU validar


async def test_vsc_que_nao_confere_com_hash_nao_e_gravado(tmp_path):
    h, ent, arqs = montar_versao(b"BU-1")
    rel_vsc = next(k for k in arqs if k.endswith("vota.vsc"))
    arqs[rel_vsc] = b"OUTRO"
    serv = ServidorFalso({CAM.aux_secao(SEC): aux_doc("Totalizada", ent), **arqs})
    esp = Espelho(tmp_path)
    async with cliente(serv) as c:
        r = await coletar_secao(c, esp, CAM, SEC)
    assert r.versoes[0]["motivo"] == "vota.vsc não confere com o hash do aux"
    assert esp.ler(rel_vsc) is None


async def test_nova_versao_preserva_original(tmp_path):
    h1, e1, a1 = montar_versao(b"BU-v1", "Recebido")
    h2, e2, a2 = montar_versao(b"BU-v2", "Totalizado")
    esp = Espelho(tmp_path)
    serv = ServidorFalso({CAM.aux_secao(SEC): aux_doc("Recebida", e1), **a1})
    async with cliente(serv) as c:
        await coletar_secao(c, esp, CAM, SEC)
    serv = ServidorFalso({CAM.aux_secao(SEC): aux_doc("Totalizada", e1, e2), **a1, **a2})
    async with cliente(serv) as c:
        r = await coletar_secao(c, esp, CAM, SEC)
    assert r.completa and len(r.versoes) == 2
    for rel, conteudo in {**a1, **a2}.items():
        assert esp.ler(rel) == conteudo
    # dois aux versionados preservados
    dir_sec = tmp_path / CAM.dir_secao(SEC)
    assert len(list(dir_sec.glob("*-aux@*.json"))) == 2


async def test_aux_com_nome_malicioso_e_rejeitado(tmp_path):
    h, ent, arqs = montar_versao(b"BU-1")
    ent["arq"][2]["nm"] = "../../../../evil.dat"
    serv = ServidorFalso({CAM.aux_secao(SEC): aux_doc("Totalizada", ent), **arqs})
    esp = Espelho(tmp_path)
    async with cliente(serv) as c:
        r = await coletar_secao(c, esp, CAM, SEC)
    assert r.erro and "CodigoInvalido" in r.erro
    assert not (tmp_path.parent / "evil.dat").exists()


async def test_aux_sem_bu(tmp_path):
    h, ent, arqs = montar_versao(b"BU-1")
    ent["arq"] = [a for a in ent["arq"] if a["tp"] != "bu"]
    serv = ServidorFalso({CAM.aux_secao(SEC): aux_doc("Recebida", ent), **arqs})
    async with cliente(serv) as c:
        r = await coletar_secao(c, Espelho(tmp_path), CAM, SEC)
    assert not r.completa and "bu" in r.versoes[0]["motivo"]


async def test_aux_json_invalido(tmp_path):
    serv = ServidorFalso({CAM.aux_secao(SEC): b"<html>erro</html>"})
    async with cliente(serv) as c:
        r = await coletar_secao(c, Espelho(tmp_path), CAM, SEC)
    assert r.erro is not None
