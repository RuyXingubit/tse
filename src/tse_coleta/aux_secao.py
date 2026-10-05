"""Leitura do JSON auxiliar da seção (status + versões de arquivos publicadas)."""

from __future__ import annotations

from dataclasses import dataclass

from .codigos import Caminhos, CodigoInvalido, IdSecao, validar


@dataclass(frozen=True, slots=True)
class VersaoArquivos:
    hash_hex: str
    data_hora: str
    status: str
    arquivos: dict[str, str]  # tipo ("bu", "vota", ...) -> nome do arquivo


@dataclass(frozen=True, slots=True)
class AuxSecao:
    status: str
    gerado_em: str
    versoes: tuple[VersaoArquivos, ...]


def ler_aux(doc: dict, caminhos: Caminhos, secao: IdSecao) -> AuxSecao:
    versoes = []
    for h in doc.get("hashes", []):
        hash_hex = validar("hash_hex", h.get("hash", ""))
        arquivos: dict[str, str] = {}
        for a in h.get("arq", []):
            tp, nm = a.get("tp", ""), a.get("nm", "")
            caminhos.arquivo_urna(secao, hash_hex, nm)  # valida nome (levanta se inesperado)
            if not tp.isalpha():
                raise CodigoInvalido(f"tipo de arquivo inesperado: {tp!r}")
            arquivos[tp] = nm
        versoes.append(
            VersaoArquivos(
                hash_hex=hash_hex,
                data_hora=f"{h.get('dr', '')} {h.get('hr', '')}".strip(),
                status=h.get("st", ""),
                arquivos=arquivos,
            )
        )
    return AuxSecao(
        status=doc.get("st", ""),
        gerado_em=f"{doc.get('dg', '')} {doc.get('hg', '')}".strip(),
        versoes=tuple(versoes),
    )
