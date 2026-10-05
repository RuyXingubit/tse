"""Um ciclo de coleta.

1. Baixa as 28 listas de seções (27 UFs + exterior). Se alguma falhar, aborta o ciclo
   (nunca grava snapshot parcial).
2. Decide, seção a seção, o que precisa ser coletado:
   - publicada e nunca coletada / incompleta / com data-hora alterada na lista;
   - "Recebida" cuja última verificação passou de `reverificar_recebidas_apos`;
   - tudo que está publicado, se for varredura completa.
3. Coleta com um pool de trabalhadores (o cliente HTTP limita a concorrência real) e anota
   cada resultado no diário — se cair, o próximo ciclo retoma de onde parou.
4. Monta o manifesto e grava snapshot somente se algo mudou.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from .cliente import ClienteTSE, ErroDownload
from .codigos import Caminhos
from .coleta_secao import ResultadoSecao, coletar_secao
from .espelho import Espelho
from .manifesto import (
    STATUS_FINAL,
    Diario,
    Layout,
    Registro,
    carregar_estado,
    gravar_estado_atual,
    gravar_snapshot,
    mudou,
)
from .secoes import Secao, ler_lista_secoes

log = logging.getLogger(__name__)

UFS = (
    "ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt", "pa",
    "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to", "zz",
)


class ListaIndisponivel(RuntimeError):
    pass


@dataclass(frozen=True)
class ConfigCiclo:
    ufs: tuple[str, ...] = UFS
    reverificar_recebidas_apos: timedelta = timedelta(minutes=30)
    trabalhadores: int = 32
    varredura_completa: bool = False


@dataclass
class ResultadoCiclo:
    snapshot: Path | None
    mudou: bool
    terminado: bool
    resumo: dict


def _agora_local() -> datetime:
    return datetime.now().astimezone()


async def executar_ciclo(
    cliente: ClienteTSE,
    layout: Layout,
    caminhos: Caminhos,
    cfg: ConfigCiclo = ConfigCiclo(),
    agora: Callable[[], datetime] = _agora_local,
    progresso: Callable[[int, int], None] | None = None,
) -> ResultadoCiclo:
    inicio = agora()
    layout.criar()
    anterior, historico = carregar_estado(layout)

    brutas = await _baixar_listas(cliente, caminhos, cfg.ufs)
    listas = {uf: ler_lista_secoes(json.loads(b), uf) for uf, b in brutas.items()}

    diario = Diario(layout.diario)
    do_diario = diario.carregar()
    espelho = Espelho(layout.espelho)

    registros: dict[str, Registro] = {}
    fila: list[tuple[Secao, Registro | None]] = []
    for lista in listas.values():
        for s in lista.secoes:
            chave = s.id.chave
            j = do_diario.get(chave)
            if j is not None and j.completa and j.data_hora_lista == s.data_hora:
                registros[chave] = j  # já coletada neste ciclo antes de uma queda
                continue
            prev = (anterior or {}).get(chave)
            if _precisa_coletar(s, prev, inicio, cfg):
                fila.append((s, prev))
            else:
                registros[chave] = _da_lista(s, prev)

    log.info("ciclo: %d seções, %d a coletar (diário: %d)", len(registros) + len(fila), len(fila), len(do_diario))
    try:
        coletadas = await _coletar(cliente, espelho, caminhos, fila, registros, diario, cfg, agora, progresso)
    finally:
        diario.fechar()  # se interrompido, o diário fica no disco para retomar

    resumo = _resumo(registros, listas, coletadas, cliente, inicio, agora(), cfg)
    houve_mudanca = mudou(historico, registros)
    snap = None
    if houve_mudanca:
        snap = gravar_snapshot(layout, inicio.strftime("%Y-%m-%dT%H-%M-%S"), brutas, registros, resumo)
        log.info("snapshot gravado: %s", snap)
    else:
        log.info("nada mudou; snapshot não gravado")
    gravar_estado_atual(layout, registros)  # antes de apagar o diário
    diario.encerrar()
    return ResultadoCiclo(snap, houve_mudanca, resumo["terminado"], resumo)


async def _baixar_listas(cliente: ClienteTSE, caminhos: Caminhos, ufs) -> dict[str, bytes]:
    async def uma(uf: str) -> tuple[str, bytes]:
        b = await cliente.obter(caminhos.lista_secoes(uf))
        if b is None:
            raise ListaIndisponivel(f"lista de seções de {uf} não encontrada (404)")
        return uf, b

    try:
        return dict(await asyncio.gather(*(uma(uf) for uf in ufs)))
    except ErroDownload as e:
        raise ListaIndisponivel(str(e)) from e


def _precisa_coletar(s: Secao, prev: Registro | None, agora: datetime, cfg: ConfigCiclo) -> bool:
    if not (s.tem_urna and s.publicada):
        return False
    if prev is None or not prev.completa or prev.data_hora_lista != s.data_hora:
        return True
    if cfg.varredura_completa:
        return True
    if prev.status_tse != STATUS_FINAL:
        if prev.verificado_em is None:
            return True
        return agora - datetime.fromisoformat(prev.verificado_em) >= cfg.reverificar_recebidas_apos
    return False


def _da_lista(s: Secao, prev: Registro | None) -> Registro:
    """Registro sem nova coleta: atualiza os campos vindos da lista e herda o resto."""
    base = prev or Registro(
        chave=s.id.chave, uf=s.id.uf, municipio=s.id.municipio, zona=s.id.zona, secao=s.id.secao,
        tem_urna=s.tem_urna,
    )
    return replace(base, tem_urna=s.tem_urna, agregada_a=s.agregada_a, publicada=s.publicada,
                   data_hora_lista=s.data_hora)


def _de_resultado(s: Secao, prev: Registro | None, res: ResultadoSecao, quando: datetime) -> Registro:
    # Falha transitória numa reverificação não "rebaixa" uma seção que já estava completa.
    if res.erro and prev is not None and prev.completa and prev.data_hora_lista == s.data_hora:
        return replace(_da_lista(s, prev), motivo=f"reverificação falhou: {res.erro}")
    motivo = res.erro or next((v["motivo"] for v in res.versoes if v["motivo"]), None)
    if res.status_tse is None and not res.erro:
        motivo = "aux ainda não disponível"
    return replace(
        _da_lista(s, None),
        status_tse=res.status_tse,
        hashes=[v["hash"] for v in res.versoes],
        completa=res.completa,
        motivo=motivo,
        aux_rel=res.aux_rel,
        verificado_em=quando.isoformat(timespec="seconds"),
    )


async def _coletar(cliente, espelho, caminhos, fila, registros, diario, cfg, agora, progresso) -> int:
    total = len(fila)
    feitos = 0
    it = iter(fila)

    async def trabalhador():
        nonlocal feitos
        for s, prev in it:  # iterador compartilhado: cada item vai para um único trabalhador
            res = await coletar_secao(cliente, espelho, caminhos, s.id)
            reg = _de_resultado(s, prev, res, agora())
            registros[reg.chave] = reg
            diario.anotar(reg)
            feitos += 1
            if progresso and (feitos % 500 == 0 or feitos == total):
                progresso(feitos, total)

    await asyncio.gather(*(trabalhador() for _ in range(max(1, min(cfg.trabalhadores, total)))))
    return feitos


def _resumo(registros, listas, coletadas, cliente, inicio, fim, cfg) -> dict:
    urnas = [r for r in registros.values() if r.tem_urna]
    status = Counter(r.status_tse or "sem_aux" for r in urnas if r.publicada)
    motivos = Counter(r.motivo for r in urnas if r.publicada and not r.completa)
    return {
        "inicio": inicio.isoformat(timespec="seconds"),
        "fim": fim.isoformat(timespec="seconds"),
        "varredura_completa": cfg.varredura_completa,
        "listas_geradas_em": {uf: l.gerado_em for uf, l in sorted(listas.items())},
        "secoes": len(registros),
        "agregadas": len(registros) - len(urnas),
        "urnas": len(urnas),
        "publicadas": sum(r.publicada for r in urnas),
        "pendentes": sum(not r.publicada for r in urnas),
        "completas": sum(r.completa for r in urnas),
        "status_tse": dict(status),
        "incompletas_por_motivo": dict(motivos.most_common(20)),
        "finais": sum(r.final for r in urnas),
        "terminado": all(r.final for r in urnas),
        "coletadas_neste_ciclo": coletadas,
        "http": dict(cliente.estatisticas),
    }
