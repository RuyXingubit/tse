"""Leitura da lista de seções por UF (`<uf>-p<pleito>-cs.json`)."""

from __future__ import annotations

from dataclasses import dataclass

from .codigos import CodigoInvalido, IdSecao, validar


@dataclass(frozen=True, slots=True)
class Secao:
    id: IdSecao
    publicada: bool            # tem arquivo de urna publicado (campos da/ha presentes)
    data_hora: str | None      # "dd/mm/aaaa hh:mm:ss" da publicação, se houver
    agregada_a: str | None     # nº da seção principal, se esta for agregada (sem urna própria)
    agregadas: tuple[str, ...]  # seções agregadas a esta (se principal)

    @property
    def tem_urna(self) -> bool:
        return self.agregada_a is None


@dataclass(frozen=True, slots=True)
class ListaSecoes:
    uf: str
    gerado_em: str  # dg + hg do JSON
    secoes: tuple[Secao, ...]

    @property
    def urnas(self) -> tuple[Secao, ...]:
        return tuple(s for s in self.secoes if s.tem_urna)

    @property
    def publicadas(self) -> tuple[Secao, ...]:
        return tuple(s for s in self.urnas if s.publicada)

    @property
    def pendentes(self) -> tuple[Secao, ...]:
        return tuple(s for s in self.urnas if not s.publicada)


def ler_lista_secoes(doc: dict, uf_esperada: str) -> ListaSecoes:
    """Converte o JSON do TSE. Rejeita UF divergente e códigos fora do padrão."""
    validar("uf", uf_esperada)
    secoes: list[Secao] = []
    abrs = doc.get("abr", [])
    if not abrs:
        raise CodigoInvalido(f"lista de seções de {uf_esperada} sem abrangência")
    for abr in abrs:
        if abr.get("cd") != uf_esperada:
            raise CodigoInvalido(f"UF divergente: esperado {uf_esperada}, veio {abr.get('cd')!r}")
        for mu in abr.get("mu", []):
            for zo in mu.get("zon", []):
                for s in zo.get("sec", []):
                    sid = IdSecao(uf_esperada, mu["cd"], zo["cd"], s["ns"])
                    da, ha = s.get("da"), s.get("ha")
                    nsp = s.get("nsp")
                    secoes.append(
                        Secao(
                            id=sid,
                            publicada=bool(da and ha) and nsp is None,
                            data_hora=f"{da} {ha}" if da and ha else None,
                            agregada_a=validar("secao", nsp) if nsp is not None else None,
                            agregadas=tuple(validar("secao", x) for x in s.get("nsa", [])),
                        )
                    )
    return ListaSecoes(
        uf=uf_esperada,
        gerado_em=f"{doc.get('dg', '')} {doc.get('hg', '')}".strip(),
        secoes=tuple(secoes),
    )
