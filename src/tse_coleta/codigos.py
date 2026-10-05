"""Validação dos códigos que vêm dos JSONs do TSE e montagem de caminhos.

Todo caminho (URL ou disco) é montado SOMENTE a partir de códigos validados aqui.
Isso impede que um valor inesperado num JSON (ex.: "../../") escape da pasta de dados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RE = {
    "uf": re.compile(r"[a-z]{2}"),
    "municipio": re.compile(r"\d{5}"),
    "zona": re.compile(r"\d{4}"),
    "secao": re.compile(r"\d{4}"),
    "pleito": re.compile(r"\d{1,6}"),
    "eleicao": re.compile(r"\d{1,6}"),
    "cargo": re.compile(r"\d{1,4}"),
    "ciclo": re.compile(r"ele\d{4}"),
    "hash_hex": re.compile(r"(?:[0-9a-f]{2}){16,128}"),
}


class CodigoInvalido(ValueError):
    """Valor vindo do TSE não tem o formato esperado; nunca usar em caminhos."""


def validar(tipo: str, valor: str) -> str:
    padrao = _RE[tipo]
    if not isinstance(valor, str) or not padrao.fullmatch(valor):
        raise CodigoInvalido(f"{tipo} inválido: {valor!r}")
    return valor


@dataclass(frozen=True, slots=True)
class IdSecao:
    uf: str
    municipio: str
    zona: str
    secao: str

    def __post_init__(self) -> None:
        validar("uf", self.uf)
        validar("municipio", self.municipio)
        validar("zona", self.zona)
        validar("secao", self.secao)

    @property
    def chave(self) -> str:
        return f"{self.uf}-{self.municipio}-{self.zona}-{self.secao}"


@dataclass(frozen=True, slots=True)
class Caminhos:
    """Caminhos relativos no padrão do TSE (servem para URL e para o espelho em disco)."""

    ciclo: str
    pleito: str

    def __post_init__(self) -> None:
        validar("ciclo", self.ciclo)
        validar("pleito", self.pleito)

    @property
    def _p6(self) -> str:
        return self.pleito.zfill(6)

    def lista_secoes(self, uf: str) -> str:
        validar("uf", uf)
        return f"{self.ciclo}/arquivo-urna/{self.pleito}/config/{uf}/{uf}-p{self._p6}-cs.json"

    def dir_secao(self, s: IdSecao) -> str:
        return f"{self.ciclo}/arquivo-urna/{self.pleito}/dados/{s.uf}/{s.municipio}/{s.zona}/{s.secao}"

    def aux_secao(self, s: IdSecao) -> str:
        nome = f"p{self._p6}-{s.uf}-m{s.municipio}-z{s.zona}-s{s.secao}-aux.json"
        return f"{self.dir_secao(s)}/{nome}"

    def arquivo_urna(self, s: IdSecao, hash_hex: str, nome: str) -> str:
        validar("hash_hex", hash_hex)
        esperado = re.compile(
            rf"o{self.pleito.zfill(5)}{s.uf}{s.municipio}{s.zona}{s.secao}-[a-z]+\.[a-z]{{3}}"
        )
        if not esperado.fullmatch(nome):
            raise CodigoInvalido(f"nome de arquivo de urna inesperado: {nome!r}")
        return f"{self.dir_secao(s)}/{hash_hex}/{nome}"

    def config_municipios(self, eleicao: str) -> str:
        validar("eleicao", eleicao)
        return f"{self.ciclo}/{eleicao}/config/mun-e{eleicao.zfill(6)}-cm.json"

    def agregado(self, eleicao: str, cargo: str, uf: str, municipio: str | None = None) -> str:
        validar("eleicao", eleicao)
        validar("cargo", cargo)
        if uf != "br":
            validar("uf", uf)
        abr = uf if municipio is None else f"{uf}{validar('municipio', municipio)}"
        return (
            f"{self.ciclo}/{eleicao}/dados/{uf}/"
            f"{abr}-c{cargo.zfill(4)}-e{eleicao.zfill(6)}-u.json"
        )
