"""Resultados agregados (JSON) e configs da eleição.

- Configs (`ele-c.json` e `mun-e<eleicao>-cm.json`) a cada ciclo.
- BR + UF de todos os cargos a cada ciclo.
- Município: uma vez quando todas as urnas dele estão publicadas e completas; de novo na
  varredura completa.
- Tudo gravado no espelho de forma versionada (`<nome>@<sha256[:16]>.json`): cada conteúdo
  distinto é preservado, o que guarda a curva da apuração sem duplicar arquivos iguais.
- 404 = combinação que não existe (ex.: Dep. Distrital fora do DF) → lembrada em
  `inexistentes` para não ser pedida de novo a cada ciclo (reverificada na varredura completa).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from .cliente import ClienteTSE, ErroDownload
from .codigos import Caminhos, CodigoInvalido, validar
from .descoberta import Pleito
from .espelho import ConflitoDeConteudo, Espelho
from .manifesto import Registro

log = logging.getLogger(__name__)

CONFIG_GERAL = "comum/config/ele-c.json"


@dataclass
class EstadoAgregados:
    inexistentes: set[str] = field(default_factory=set)
    municipios_baixados: set[str] = field(default_factory=set)  # "uf-mun"

    def para_json(self) -> str:
        return json.dumps(
            {"inexistentes": sorted(self.inexistentes), "municipios_baixados": sorted(self.municipios_baixados)},
            indent=1,
        )

    @classmethod
    def de_json(cls, s: str) -> "EstadoAgregados":
        d = json.loads(s)
        return cls(set(d.get("inexistentes", [])), set(d.get("municipios_baixados", [])))


def abrangencias(cm: dict) -> dict[str, list[str]]:
    """{uf: [municipios]} de um `mun-e<eleicao>-cm.json`, com códigos validados."""
    out: dict[str, list[str]] = {}
    for abr in cm.get("abr", []):
        uf = validar("uf", abr.get("cd", ""))
        out[uf] = [validar("municipio", m.get("cd", "")) for m in abr.get("mu", [])]
    return out


def alvos_uf(caminhos: Caminhos, pleito: Pleito, abr_por_eleicao: dict[str, dict[str, list[str]]]) -> list[str]:
    alvos = []
    for e in pleito.eleicoes:
        for c in e.cargos:
            alvos.append(caminhos.agregado(e.codigo, c.codigo, "br"))
            for uf in abr_por_eleicao.get(e.codigo, {}):
                alvos.append(caminhos.agregado(e.codigo, c.codigo, uf))
    return alvos


def alvos_municipio(
    caminhos: Caminhos, pleito: Pleito, abr_por_eleicao: dict[str, dict[str, list[str]]], uf: str, mun: str
) -> list[str]:
    alvos = []
    for e in pleito.eleicoes:
        if mun in abr_por_eleicao.get(e.codigo, {}).get(uf, []):
            alvos.extend(caminhos.agregado(e.codigo, c.codigo, uf, mun) for c in e.cargos)
    return alvos


def municipios_fechados(registros: Iterable[Registro]) -> set[str]:
    """Municípios em que TODAS as urnas estão publicadas e com arquivos completos."""
    abertos: set[str] = set()
    todos: set[str] = set()
    for r in registros:
        if not r.tem_urna:
            continue
        k = f"{r.uf}-{r.municipio}"
        todos.add(k)
        if not (r.publicada and r.completa):
            abertos.add(k)
    return todos - abertos


async def baixar_versionados(
    cliente: ClienteTSE, espelho: Espelho, rels: Iterable[str], inexistentes: set[str]
) -> Counter:
    cont: Counter = Counter()

    async def um(rel: str) -> None:
        try:
            b = await cliente.obter(rel)
        except ErroDownload as e:
            cont["erro"] += 1
            log.warning("agregado %s: %s", rel, e)
            return
        if b is None:
            inexistentes.add(rel)
            cont["inexistente"] += 1
            return
        try:
            json.loads(b)  # só preserva JSON válido (evita guardar página de erro)
        except ValueError:
            cont["invalido"] += 1
            return
        try:
            _, gravou = espelho.gravar_versionado(rel, b)
        except ConflitoDeConteudo:  # colisão de prefixo de hash: improvável, mas nunca sobrescreve
            cont["conflito"] += 1
            return
        cont["novo" if gravou else "igual"] += 1

    await asyncio.gather(*(um(r) for r in rels))
    return cont


async def coletar_configs(
    cliente: ClienteTSE, espelho: Espelho, caminhos: Caminhos, pleito: Pleito
) -> dict[str, dict[str, list[str]]]:
    """Baixa/preserva ele-c.json e os cm de cada eleição; devolve {eleicao: {uf: [mun]}}."""
    abr: dict[str, dict[str, list[str]]] = {}
    geral = await cliente.obter(CONFIG_GERAL)
    if geral is not None:
        espelho.gravar_versionado(CONFIG_GERAL, geral)
    for e in pleito.eleicoes:
        rel = caminhos.config_municipios(e.codigo)
        b = await cliente.obter(rel)
        if b is None:
            log.warning("config de municípios da eleição %s indisponível", e.codigo)
            continue
        try:
            abr[e.codigo] = abrangencias(json.loads(b))
        except (ValueError, CodigoInvalido) as ex:
            log.warning("config de municípios da eleição %s inválida: %s", e.codigo, ex)
            continue
        espelho.gravar_versionado(rel, b)
    return abr


async def coletar_agregados(
    cliente: ClienteTSE,
    espelho: Espelho,
    caminhos: Caminhos,
    pleito: Pleito,
    registros: dict[str, Registro],
    estado: EstadoAgregados,
    varredura_completa: bool = False,
) -> dict:
    abr = await coletar_configs(cliente, espelho, caminhos, pleito)
    if varredura_completa:
        estado.inexistentes.clear()

    uf_alvos = [r for r in alvos_uf(caminhos, pleito, abr) if r not in estado.inexistentes]
    cont_uf = await baixar_versionados(cliente, espelho, uf_alvos, estado.inexistentes)

    fechados = municipios_fechados(registros.values())
    pendentes = fechados if varredura_completa else fechados - estado.municipios_baixados
    mun_alvos: list[str] = []
    for k in sorted(pendentes):
        uf, mun = k.split("-")
        mun_alvos.extend(r for r in alvos_municipio(caminhos, pleito, abr, uf, mun) if r not in estado.inexistentes)
    cont_mun = await baixar_versionados(cliente, espelho, mun_alvos, estado.inexistentes)
    if not cont_mun.get("erro"):
        estado.municipios_baixados |= pendentes
    else:  # algum falhou: só marca municípios cujos arquivos todos já existem
        for k in pendentes:
            uf, mun = k.split("-")
            if all(_tem_versao(espelho, r) or r in estado.inexistentes
                   for r in alvos_municipio(caminhos, pleito, abr, uf, mun)):
                estado.municipios_baixados.add(k)

    return {
        "uf_br": dict(cont_uf),
        "municipios": dict(cont_mun),
        "municipios_fechados": len(fechados),
        "municipios_baixados": len(estado.municipios_baixados),
    }


def _tem_versao(espelho: Espelho, rel: str) -> bool:
    p = espelho.caminho(rel)
    return p.parent.is_dir() and any(p.parent.glob(f"{p.stem}@*{p.suffix}"))
