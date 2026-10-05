"""Descoberta do pleito/eleições/cargos a partir de `comum/config/ele-c.json`."""

from __future__ import annotations

from dataclasses import dataclass

from .codigos import validar


class PleitoNaoEncontrado(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class Cargo:
    codigo: str
    descricao: str


@dataclass(frozen=True, slots=True)
class Eleicao:
    codigo: str
    nome: str
    turno: str
    cargos: tuple[Cargo, ...]


@dataclass(frozen=True, slots=True)
class Pleito:
    ciclo: str
    codigo: str
    data: str
    eleicoes: tuple[Eleicao, ...]


def descobrir_pleito(config: dict, ciclo: str, data: str) -> Pleito:
    """Retorna o pleito do `ciclo` na `data` (dd/mm/aaaa). Falha se houver 0 ou mais de 1."""
    validar("ciclo", ciclo)
    candidatos = [p for p in config.get("pl", []) if p.get("c") == ciclo and p.get("dt") == data]
    if len(candidatos) != 1:
        raise PleitoNaoEncontrado(
            f"esperado 1 pleito para {ciclo} em {data}, encontrado {len(candidatos)}"
        )
    p = candidatos[0]
    eleicoes = []
    for e in p.get("e", []):
        cargos: dict[str, Cargo] = {}
        for abr in e.get("abr", []):
            for c in abr.get("cp", []):
                cod = validar("cargo", c["cd"])
                cargos.setdefault(cod, Cargo(cod, c["ds"].strip()))
        eleicoes.append(
            Eleicao(
                codigo=validar("eleicao", e["cd"]),
                nome=e.get("nm", ""),
                turno=e.get("t", ""),
                cargos=tuple(sorted(cargos.values(), key=lambda c: int(c.codigo))),
            )
        )
    if not eleicoes:
        raise PleitoNaoEncontrado(f"pleito {p.get('cd')} sem eleições")
    return Pleito(
        ciclo=ciclo,
        codigo=validar("pleito", p["cd"]),
        data=data,
        eleicoes=tuple(eleicoes),
    )
