"""Fábrica de dados no formato do TSE para testes (BU/vsc sintéticos com cadeia válida)."""

import hashlib
import json

import httpx

from tse_coleta.codigos import Caminhos, IdSecao
from tse_coleta.integridade import codificar_hash_tse

CAM = Caminhos("ele2026", "3220")


def prefixo(s: IdSecao) -> str:
    return f"o03220{s.uf}{s.municipio}{s.zona}{s.secao}"


def versao(s: IdSecao, bu: bytes, status="Totalizado"):
    vsc = b"VSC" + hashlib.sha512(bu).digest() + b"FIM"
    h = codificar_hash_tse(hashlib.sha256(vsc).digest())
    p = prefixo(s)
    entrada = {
        "hash": h, "dr": "04/10/2026", "hr": "17:58:39", "st": status,
        "arq": [{"nm": f"{p}-vota.vsc", "tp": "vota"}, {"nm": f"{p}-bu.dat", "tp": "bu"}],
    }
    arquivos = {
        CAM.arquivo_urna(s, h, f"{p}-vota.vsc"): vsc,
        CAM.arquivo_urna(s, h, f"{p}-bu.dat"): bu,
    }
    return entrada, arquivos


def aux(st: str, *entradas) -> bytes:
    return json.dumps({"dg": "04/10/2026", "hg": "21:09:52", "st": st, "hashes": list(entradas)}).encode()


def lista(uf: str, municipios: dict, hg="22:47:53") -> bytes:
    """municipios = {mun: {zona: [secao_dict, ...]}}"""
    return json.dumps({
        "dg": "04/10/2026", "hg": hg, "cdp": "3220",
        "abr": [{"cd": uf, "mu": [
            {"cd": m, "zon": [{"cd": z, "sec": secs} for z, secs in zonas.items()]}
            for m, zonas in municipios.items()
        ]}],
    }).encode()


class ServidorFalso:
    def __init__(self, rotas: dict[str, bytes] | None = None, falhas: dict[str, int] | None = None):
        self.rotas = dict(rotas or {})
        self.falhas = dict(falhas or {})  # rel -> status forçado
        self.pedidos: list[str] = []

    def __call__(self, req: httpx.Request):
        rel = req.url.path.removeprefix("/oficial/")
        self.pedidos.append(rel)
        if rel in self.falhas:
            return httpx.Response(self.falhas[rel])
        if rel in self.rotas:
            return httpx.Response(200, content=self.rotas[rel])
        return httpx.Response(404)


async def sem_espera(_):
    return None
