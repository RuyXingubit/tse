"""Coleta de uma seção: aux → vota.vsc → bu.dat, com validação antes de gravar."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .aux_secao import VersaoArquivos, ler_aux
from .cliente import ClienteTSE, ErroDownload
from .codigos import Caminhos, CodigoInvalido, IdSecao
from .espelho import ConflitoDeConteudo, Espelho
from .integridade import HashInvalido, arquivo_confere_com_vsc, vsc_confere

log = logging.getLogger(__name__)

TIPOS_BAIXADOS = ("vota", "bu")  # decisão do PRD: só BU + assinatura


@dataclass
class ResultadoSecao:
    secao: IdSecao
    status_tse: str | None = None          # "Recebida", "Totalizada"… (None = aux ainda não existe)
    aux_rel: str | None = None             # caminho do aux versionado no espelho
    versoes: list[dict] = field(default_factory=list)  # por hash: arquivos gravados/validados
    erro: str | None = None

    @property
    def completa(self) -> bool:
        return self.erro is None and bool(self.versoes) and all(v["ok"] for v in self.versoes)


async def coletar_secao(
    cliente: ClienteTSE, espelho: Espelho, caminhos: Caminhos, secao: IdSecao
) -> ResultadoSecao:
    res = ResultadoSecao(secao)
    try:
        bruto = await cliente.obter(caminhos.aux_secao(secao))
        if bruto is None:
            return res  # ainda não publicado
        aux = ler_aux(json.loads(bruto), caminhos, secao)
        res.status_tse = aux.status
        res.aux_rel, _ = espelho.gravar_versionado(caminhos.aux_secao(secao), bruto)
        for versao in aux.versoes:  # todas as versões publicadas (preserva histórico)
            res.versoes.append(await _coletar_versao(cliente, espelho, caminhos, secao, versao))
    except (ErroDownload, CodigoInvalido, HashInvalido, ConflitoDeConteudo, ValueError) as e:
        res.erro = f"{type(e).__name__}: {e}"
        log.warning("seção %s: %s", secao.chave, res.erro)
    return res


async def _coletar_versao(
    cliente: ClienteTSE, espelho: Espelho, caminhos: Caminhos, secao: IdSecao, v: VersaoArquivos
) -> dict:
    info = {"hash": v.hash_hex, "status": v.status, "data_hora": v.data_hora, "ok": False, "gravados": [], "motivo": None}
    faltando = [t for t in TIPOS_BAIXADOS if t not in v.arquivos]
    if faltando:
        info["motivo"] = f"aux sem arquivo(s): {','.join(faltando)}"
        return info

    rel_vsc = caminhos.arquivo_urna(secao, v.hash_hex, v.arquivos["vota"])
    rel_bu = caminhos.arquivo_urna(secao, v.hash_hex, v.arquivos["bu"])

    # Retomada: se ambos já estão no disco e validam, não baixa de novo.
    vsc = espelho.ler(rel_vsc)
    bu = espelho.ler(rel_bu)
    if vsc is not None and bu is not None and vsc_confere(vsc, v.hash_hex) and arquivo_confere_com_vsc(bu, vsc):
        info["ok"] = True
        return info

    if vsc is None or not vsc_confere(vsc, v.hash_hex):
        vsc = await cliente.obter(rel_vsc)
        if vsc is None:
            info["motivo"] = "vota.vsc 404"
            return info
        if not vsc_confere(vsc, v.hash_hex):
            info["motivo"] = "vota.vsc não confere com o hash do aux"
            return info
    if bu is None or not arquivo_confere_com_vsc(bu, vsc):
        bu = await cliente.obter(rel_bu)
        if bu is None:
            info["motivo"] = "bu.dat 404"
            return info
        if not arquivo_confere_com_vsc(bu, vsc):
            info["motivo"] = "bu.dat não confere com o vota.vsc"
            return info

    # Só grava depois que a cadeia inteira validou.
    if espelho.gravar_imutavel(rel_vsc, vsc):
        info["gravados"].append("vota")
    if espelho.gravar_imutavel(rel_bu, bu):
        info["gravados"].append("bu")
    info["ok"] = True
    return info
