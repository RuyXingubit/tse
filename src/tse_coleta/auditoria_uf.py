"""Pipeline de auditoria comparativa 1º vs. 2º turno por UF em modo streaming.

Fluxo por seção:
1. Baixa em memória (RAM) os arquivos do 1º turno (`3220`) e do 2º turno (`3221`).
2. Valida criptograficamente `vota.vsc` (SHA-256 contra o hash da seção) e `bu.dat` / `log.jez`
   (SHA-512 contido no `vota.vsc`).
3. Decodifica `bu.dat` (1T e 2T) e analisa `log.jez` (aproveitando que o `log.jez` do 2T já traz
   os eventos de `04/10/2026` e `25/10/2026` quando a urna física não mudou; se mudou, baixa
   também o `log.jez` do 1T).
4. Grava uma única linha compacta (~1 KB) em `auditoria/<uf>/resumo_secoes.jsonl` e descarta os
   arquivos brutos da memória (não acumula gigabytes no HD).
5. Consolida estatísticas, cruzamentos e anomalias em `auditoria/<uf>/analise_consolidada.json`.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import math
import os
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .analisador_log import ErroAnaliseLog, ResumoLogTurno, analisar_log_por_datas
from .aux_secao import AuxSecao, ler_aux
from .cliente import ClienteTSE
from .codigos import Caminhos, IdSecao, validar
from .decodificador_bu import BoletimUrnaDecodificado, ErroDecodificacaoBU, decodificar_bu
from .integridade import HashInvalido, arquivo_confere_com_vsc, vsc_confere
from .secoes import Secao, ler_lista_secoes

log = logging.getLogger(__name__)

CICLO_2026 = "ele2026"
PLEITO_1T = "3220"
PLEITO_2T = "3221"
DATA_1T = "04/10/2026"
DATA_2T = "25/10/2026"
ELEICAO_PRES_1T = "6257"
ELEICAO_PRES_2T = "6258"
ELEICAO_EST_1T = "6259"
ELEICAO_EST_2T = "6260"


def carregar_hashes_snapshot_1t(raiz: Path, uf: str) -> dict[str, dict]:
    """Lê do último snapshot disponível em `raiz/snapshots/` os hashes do 1º turno da UF."""
    validar("uf", uf)
    pasta_snaps = raiz / "snapshots"
    if not pasta_snaps.is_dir():
        return {}
    candidatos = sorted(
        (p for p in pasta_snaps.iterdir() if p.is_dir() and (p / "manifesto.jsonl.gz").is_file()),
        key=lambda p: p.name,
        reverse=True,
    )
    for snap in candidatos:
        achados: dict[str, dict] = {}
        try:
            with gzip.open(snap / "manifesto.jsonl.gz", "rt", encoding="utf-8") as f:
                for linha in f:
                    r = json.loads(linha)
                    if r.get("uf") == uf and r.get("tem_urna"):
                        achados[r["chave"]] = {
                            "hashes": r.get("hashes") or [],
                            "data_hora_lista": r.get("data_hora_lista") or "",
                            "status_tse": r.get("status_tse") or "",
                            "snapshot": snap.name,
                        }
        except OSError:
            continue
        if achados:
            log.info("carregados %d registros do snapshot 1T %s para %s", len(achados), snap.name, uf)
            return achados
    return {}


async def carregar_mapa_municipios(cliente: ClienteTSE, uf: str) -> dict[str, str]:
    """Retorna `{codigo_municipio_tse: nome_municipio}` para a UF."""
    validar("uf", uf)
    cam = Caminhos(CICLO_2026, PLEITO_2T)
    bruto = await cliente.obter(cam.config_municipios(ELEICAO_PRES_2T))
    if not bruto:
        return {}
    doc = json.loads(bruto)
    for abr in doc.get("abr", []):
        if abr.get("cd", "").lower() == uf.lower():
            return {m["cd"]: m.get("nm", m["cd"]) for m in abr.get("mu", []) if "cd" in m}
    return {}


async def baixar_agregado_oficial(
    cliente: ClienteTSE, eleicao: str, cargo: str, uf: str
) -> dict | None:
    cam = Caminhos(CICLO_2026, PLEITO_2T if eleicao in (ELEICAO_PRES_2T, ELEICAO_EST_2T) else PLEITO_1T)
    bruto = await cliente.obter(cam.agregado(eleicao, cargo, uf))
    if not bruto:
        return None
    return json.loads(bruto)


async def _obter_aux(
    cliente: ClienteTSE, cam: Caminhos, sec: IdSecao
) -> AuxSecao | None:
    bruto = await cliente.obter(cam.aux_secao(sec))
    if not bruto:
        return None
    return ler_aux(json.loads(bruto), cam, sec)


async def _baixar_e_validar_bu(
    cliente: ClienteTSE,
    cam: Caminhos,
    sec: IdSecao,
    hash_hex: str,
    nome_vsc: str,
    nome_bu: str,
) -> tuple[bytes, BoletimUrnaDecodificado] | tuple[None, str]:
    """Baixa `vota.vsc` e `bu.dat` em memória, valida os hashes e decodifica o BU."""
    vsc = await cliente.obter(cam.arquivo_urna(sec, hash_hex, nome_vsc))
    if not vsc:
        return None, "vota.vsc 404"
    try:
        if not vsc_confere(vsc, hash_hex):
            return None, "vota.vsc SHA-256 inválido"
    except HashInvalido as e:
        return None, str(e)

    bu_bytes = await cliente.obter(cam.arquivo_urna(sec, hash_hex, nome_bu))
    if not bu_bytes:
        return None, "bu.dat 404"
    if not arquivo_confere_com_vsc(bu_bytes, vsc):
        return None, "bu.dat SHA-512 ausente no vsc"
    try:
        bu_dec = decodificar_bu(bu_bytes)
    except ErroDecodificacaoBU as e:
        return None, f"erro ASN.1 BU: {e}"
    return vsc, bu_dec


def _resumir_cargo(bu: BoletimUrnaDecodificado | None, cod_cargo: int) -> dict | None:
    if not bu or cod_cargo not in bu.cargos:
        return None
    c = bu.cargos[cod_cargo]
    return {
        "eleicao": c.eleicao,
        "aptos": c.aptos,
        "comparecimento": c.comparecimento,
        "nominais": {str(k): v for k, v in sorted(c.nominais.items())},
        "brancos": c.brancos,
        "nulos": c.nulos,
        "legenda": c.legenda,
        "total": c.total,
    }


async def processar_secao_1t_2t(
    cliente: ClienteTSE,
    sec_1t: Secao | None,
    sec_2t: Secao | None,
    info_snap_1t: dict | None,
    nome_municipio: str,
) -> dict:
    """Baixa em memória 1T e 2T de uma seção, valida, compara, resume e descarta os brutos."""
    sec_id = (sec_2t or sec_1t).id  # type: ignore[union-attr]
    uf = sec_id.uf
    cam_1t = Caminhos(CICLO_2026, PLEITO_1T)
    cam_2t = Caminhos(CICLO_2026, PLEITO_2T)

    erros: list[str] = []
    prefixo_1t = f"o{PLEITO_1T.zfill(5)}{uf}{sec_id.municipio}{sec_id.zona}{sec_id.secao}"

    # --- 1º TURNO ---
    hash_snap_1t = (info_snap_1t or {}).get("hashes", [""])[0] if info_snap_1t else ""
    dh_snap_1t = (info_snap_1t or {}).get("data_hora_lista", "")
    dh_lista_1t = (sec_1t.data_hora or "") if sec_1t else ""

    hash_1t_atual = ""
    status_1t = (info_snap_1t or {}).get("status_tse", "")
    nome_vsc_1t = f"{prefixo_1t}-vota.vsc"
    nome_bu_1t = f"{prefixo_1t}-bu.dat"
    nome_log_1t = f"{prefixo_1t}-log.jez"

    # Se temos o hash validado no snapshot de 05/10 e a data/hora na lista 1T não mudou, usamos direto
    if hash_snap_1t and dh_lista_1t and dh_lista_1t == dh_snap_1t:
        hash_1t_atual = hash_snap_1t
    elif sec_1t and sec_1t.publicada:
        aux_1t = await _obter_aux(cliente, cam_1t, sec_id)
        if aux_1t and aux_1t.versoes:
            v1 = aux_1t.versoes[0]
            hash_1t_atual = v1.hash_hex
            status_1t = aux_1t.status
            nome_vsc_1t = v1.arquivos.get("vota", nome_vsc_1t)
            nome_bu_1t = v1.arquivos.get("bu", nome_bu_1t)
            nome_log_1t = v1.arquivos.get("log", nome_log_1t)
        else:
            erros.append("1T aux indisponível")
    else:
        erros.append("1T não publicada")

    vsc_1t: bytes | None = None
    bu_1t: BoletimUrnaDecodificado | None = None
    if hash_1t_atual:
        res_1t = await _baixar_e_validar_bu(
            cliente, cam_1t, sec_id, hash_1t_atual, nome_vsc_1t, nome_bu_1t
        )
        if res_1t[0] is None:
            # Se falhou usando o atalho do snapshot, consulta o aux_1t real como fallback
            aux_1t = await _obter_aux(cliente, cam_1t, sec_id)
            if aux_1t and aux_1t.versoes:
                v1 = aux_1t.versoes[0]
                hash_1t_atual = v1.hash_hex
                status_1t = aux_1t.status
                res_1t = await _baixar_e_validar_bu(
                    cliente,
                    cam_1t,
                    sec_id,
                    hash_1t_atual,
                    v1.arquivos.get("vota", nome_vsc_1t),
                    v1.arquivos.get("bu", nome_bu_1t),
                )
        if res_1t[0] is None:
            erros.append(f"1T {res_1t[1]}")
        else:
            vsc_1t, bu_1t = res_1t  # type: ignore[assignment]

    # --- 2º TURNO ---
    hash_2t = ""
    status_2t = ""
    vsc_2t: bytes | None = None
    bu_2t: BoletimUrnaDecodificado | None = None
    nome_log_2t = ""

    if sec_2t and sec_2t.publicada:
        aux_2t = await _obter_aux(cliente, cam_2t, sec_id)
        if aux_2t and aux_2t.versoes:
            v2 = aux_2t.versoes[0]
            hash_2t = v2.hash_hex
            status_2t = aux_2t.status
            nome_vsc_2t = v2.arquivos.get("vota", "")
            nome_bu_2t = v2.arquivos.get("bu", "")
            nome_log_2t = v2.arquivos.get("log", "")
            if nome_vsc_2t and nome_bu_2t:
                res_2t = await _baixar_e_validar_bu(
                    cliente, cam_2t, sec_id, hash_2t, nome_vsc_2t, nome_bu_2t
                )
                if res_2t[0] is None:
                    erros.append(f"2T {res_2t[1]}")
                else:
                    vsc_2t, bu_2t = res_2t  # type: ignore[assignment]
            else:
                erros.append("2T aux sem vota/bu")
        else:
            erros.append("2T aux indisponível")
    else:
        erros.append("2T não publicada")

    # --- LOGS DA URNA (2T log.jez já traz 1T + 2T quando a urna física é a mesma) ---
    log_1t = ResumoLogTurno(data=DATA_1T, presente=False)
    log_2t = ResumoLogTurno(data=DATA_2T, presente=False)

    if hash_2t and nome_log_2t and vsc_2t:
        bytes_log_2t = await cliente.obter(cam_2t.arquivo_urna(sec_id, hash_2t, nome_log_2t))
        if bytes_log_2t:
            if arquivo_confere_com_vsc(bytes_log_2t, vsc_2t):
                try:
                    logs = analisar_log_por_datas(bytes_log_2t, (DATA_1T, DATA_2T), uf=uf)
                    log_1t = logs[DATA_1T]
                    log_2t = logs[DATA_2T]
                except ErroAnaliseLog as e:
                    erros.append(f"2T log inválido: {e}")
            else:
                erros.append("2T log.jez SHA-512 ausente no vsc")
        del bytes_log_2t

    # Se o log do 2T não continha todos os votos de 04/10/2026 (ex. urna trocada ou contingência no 1T), baixa o log do 1T
    precisa_log_1t = (
        bu_1t is not None
        and bu_1t.comparecimento_urna > 0
        and log_1t.votos_computados != bu_1t.comparecimento_urna
        and bool(hash_1t_atual)
        and vsc_1t is not None
    )
    if precisa_log_1t and vsc_1t is not None:
        bytes_log_1t = await cliente.obter(cam_1t.arquivo_urna(sec_id, hash_1t_atual, nome_log_1t))
        if bytes_log_1t:
            if arquivo_confere_com_vsc(bytes_log_1t, vsc_1t):
                try:
                    logs_1 = analisar_log_por_datas(bytes_log_1t, (DATA_1T,), uf=uf)
                    log_1t = logs_1[DATA_1T]
                except ErroAnaliseLog as e:
                    erros.append(f"1T log inválido: {e}")
            else:
                erros.append("1T log.jez SHA-512 ausente no vsc")
        del bytes_log_1t

    # Libera referências aos pacotes de assinatura
    del vsc_1t, vsc_2t

    pres_1t = _resumir_cargo(bu_1t, 1)
    pres_2t = _resumir_cargo(bu_2t, 1)
    gov_1t = _resumir_cargo(bu_1t, 3)
    gov_2t = _resumir_cargo(bu_2t, 3)

    aptos_1t = pres_1t["aptos"] if pres_1t else 0
    aptos_2t = pres_2t["aptos"] if pres_2t else 0
    comp_1t = bu_1t.comparecimento_urna if bu_1t else 0
    comp_2t = bu_2t.comparecimento_urna if bu_2t else 0
    pct_comp_1t = round(100.0 * comp_1t / aptos_1t, 2) if aptos_1t > 0 else 0.0
    pct_comp_2t = round(100.0 * comp_2t / aptos_2t, 2) if aptos_2t > 0 else 0.0

    sem_bio_1t = (bu_1t.liberados_codigo + bu_1t.habilitados_outros) if bu_1t else 0
    sem_bio_2t = (bu_2t.liberados_codigo + bu_2t.habilitados_outros) if bu_2t else 0
    pct_sem_bio_1t = round(100.0 * sem_bio_1t / comp_1t, 2) if comp_1t > 0 else 0.0
    pct_sem_bio_2t = round(100.0 * sem_bio_2t / comp_2t, 2) if comp_2t > 0 else 0.0

    urna_1t = bu_1t.numero_interno_urna if bu_1t else 0
    urna_2t = bu_2t.numero_interno_urna if bu_2t else 0
    local = bu_2t.local if bu_2t else (bu_1t.local if bu_1t else 0)

    return {
        "chave": sec_id.chave,
        "uf": uf,
        "municipio": sec_id.municipio,
        "nome_municipio": nome_municipio,
        "zona": sec_id.zona,
        "secao": sec_id.secao,
        "local": local,
        "completa_1t": bu_1t is not None,
        "completa_2t": bu_2t is not None,
        "status_1t": status_1t,
        "status_2t": status_2t,
        "erros": erros,
        "hash_1t_snapshot": hash_snap_1t,
        "hash_1t_atual": hash_1t_atual,
        "hash_1t_mudou_pos_snapshot": bool(
            hash_snap_1t and hash_1t_atual and hash_snap_1t != hash_1t_atual
        ),
        "hash_2t": hash_2t,
        "urna_1t": urna_1t,
        "urna_2t": urna_2t,
        "trocou_urna_entre_turnos": bool(urna_1t and urna_2t and urna_1t != urna_2t),
        "abertura_1t": bu_1t.abertura if bu_1t else "",
        "encerramento_1t": bu_1t.encerramento if bu_1t else "",
        "abertura_2t": bu_2t.abertura if bu_2t else "",
        "encerramento_2t": bu_2t.encerramento if bu_2t else "",
        "aptos_1t": aptos_1t,
        "aptos_2t": aptos_2t,
        "delta_aptos": aptos_2t - aptos_1t if (bu_1t and bu_2t) else 0,
        "comp_1t": comp_1t,
        "comp_2t": comp_2t,
        "pct_comp_1t": pct_comp_1t,
        "pct_comp_2t": pct_comp_2t,
        "delta_comp_abs": comp_2t - comp_1t if (bu_1t and bu_2t) else 0,
        "delta_comp_pp": round(pct_comp_2t - pct_comp_1t, 2) if (bu_1t and bu_2t) else 0.0,
        "bio_1t": bu_1t.habilitados_biometria if bu_1t else 0,
        "sem_bio_1t": sem_bio_1t,
        "pct_sem_bio_1t": pct_sem_bio_1t,
        "bio_2t": bu_2t.habilitados_biometria if bu_2t else 0,
        "sem_bio_2t": sem_bio_2t,
        "pct_sem_bio_2t": pct_sem_bio_2t,
        "delta_sem_bio_pp": round(pct_sem_bio_2t - pct_sem_bio_1t, 2) if (bu_1t and bu_2t) else 0.0,
        "pres_1t": pres_1t,
        "pres_2t": pres_2t,
        "gov_1t": gov_1t,
        "gov_2t": gov_2t,
        "log_1t": log_1t.para_dict(),
        "log_2t": log_2t.para_dict(),
    }


def _carregar_resumos_existentes(arq_jsonl: Path) -> dict[str, dict]:
    existentes: dict[str, dict] = {}
    if not arq_jsonl.is_file():
        return existentes
    with open(arq_jsonl, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                r = json.loads(linha)
                if r.get("completa_1t") and r.get("completa_2t"):
                    existentes[r["chave"]] = r
            except json.JSONDecodeError:
                continue
    return existentes


async def executar_auditoria_uf(
    cliente: ClienteTSE,
    raiz: Path,
    uf: str,
    *,
    trabalhadores: int = 160,
    progresso: Callable[[int, int], None] | None = None,
) -> tuple[Path, Path]:
    """Executa a coleta em streaming, grava o resumo enxuto por seção e consolida a análise."""
    uf = validar("uf", uf.lower())
    pasta_uf = raiz / "auditoria" / uf
    pasta_uf.mkdir(parents=True, exist_ok=True)
    arq_jsonl = pasta_uf / "resumo_secoes.jsonl"
    arq_gz = pasta_uf / "resumo_secoes.jsonl.gz"
    arq_analise = pasta_uf / "analise_consolidada.json"

    hashes_snap = carregar_hashes_snapshot_1t(raiz, uf)
    mapa_mun = await carregar_mapa_municipios(cliente, uf)

    cam_1t = Caminhos(CICLO_2026, PLEITO_1T)
    cam_2t = Caminhos(CICLO_2026, PLEITO_2T)
    bruto_cs1 = await cliente.obter(cam_1t.lista_secoes(uf))
    bruto_cs2 = await cliente.obter(cam_2t.lista_secoes(uf))
    if not bruto_cs1 or not bruto_cs2:
        raise RuntimeError(f"listas de seções indisponíveis para {uf.upper()}")

    lista_1t = ler_lista_secoes(json.loads(bruto_cs1), uf)
    lista_2t = ler_lista_secoes(json.loads(bruto_cs2), uf)

    urnas_1t = {s.id.chave: s for s in lista_1t.secoes if s.tem_urna}
    urnas_2t = {s.id.chave: s for s in lista_2t.secoes if s.tem_urna}
    todas_chaves = sorted(set(urnas_1t) | set(urnas_2t))

    prontas = _carregar_resumos_existentes(arq_jsonl)
    pendentes = [k for k in todas_chaves if k not in prontas]
    log.info(
        "auditoria %s: %d urnas no total, %d já resumidas no disco, %d a processar",
        uf.upper(),
        len(todas_chaves),
        len(prontas),
        len(pendentes),
    )

    if pendentes:
        fila: asyncio.Queue[str] = asyncio.Queue()
        for k in pendentes:
            fila.put_nowait(k)

        feitas = 0
        total = len(pendentes)
        trava_escrita = asyncio.Lock()

        with open(arq_jsonl, "a", encoding="utf-8") as f_out:

            async def trabalhador() -> None:
                nonlocal feitas
                while not fila.empty():
                    try:
                        chave = fila.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    s1 = urnas_1t.get(chave)
                    s2 = urnas_2t.get(chave)
                    mun_cd = (s2 or s1).id.municipio  # type: ignore[union-attr]
                    nome_mun = mapa_mun.get(mun_cd, mun_cd)
                    reg = await processar_secao_1t_2t(
                        cliente, s1, s2, hashes_snap.get(chave), nome_mun
                    )
                    async with trava_escrita:
                        f_out.write(json.dumps(reg, ensure_ascii=False, sort_keys=True) + "\n")
                        prontas[chave] = reg
                        feitas += 1
                        if feitas % 250 == 0 or feitas == total:
                            f_out.flush()
                            if progresso:
                                progresso(feitas, total)

            n_trab = min(trabalhadores, len(pendentes))
            await asyncio.gather(*(trabalhador() for _ in range(n_trab)))

    # Regrava `resumo_secoes.jsonl` limpo/ordenado e gera `resumo_secoes.jsonl.gz`
    registros_ordenados = [prontas[k] for k in sorted(prontas)]
    tmp_jsonl = arq_jsonl.with_suffix(".jsonl.tmp")
    with open(tmp_jsonl, "w", encoding="utf-8") as f_plain, gzip.open(
        arq_gz, "wt", encoding="utf-8"
    ) as f_gz:
        for reg in registros_ordenados:
            linha = json.dumps(reg, ensure_ascii=False, sort_keys=True) + "\n"
            f_plain.write(linha)
            f_gz.write(linha)
    os.replace(tmp_jsonl, arq_jsonl)

    # Baixa agregados oficiais da UF (1T e 2T) para batimento matemático
    ag_pres_1t = await baixar_agregado_oficial(cliente, ELEICAO_PRES_1T, "1", uf)
    ag_pres_2t = await baixar_agregado_oficial(cliente, ELEICAO_PRES_2T, "1", uf)
    ag_gov_1t = await baixar_agregado_oficial(cliente, ELEICAO_EST_1T, "3", uf)
    ag_gov_2t = await baixar_agregado_oficial(cliente, ELEICAO_EST_2T, "3", uf)

    analise = consolidar_analise_uf(
        uf=uf,
        registros=registros_ordenados,
        agregadas_1t=sum(1 for s in lista_1t.secoes if not s.tem_urna),
        agregadas_2t=sum(1 for s in lista_2t.secoes if not s.tem_urna),
        ag_pres_1t=ag_pres_1t,
        ag_pres_2t=ag_pres_2t,
        ag_gov_1t=ag_gov_1t,
        ag_gov_2t=ag_gov_2t,
    )
    with open(arq_analise, "w", encoding="utf-8") as f_an:
        json.dump(analise, f_an, ensure_ascii=False, indent=2, sort_keys=True)

    return arq_gz, arq_analise


def _extrair_totais_agregado_tse(doc: dict | None) -> dict | None:
    if not doc:
        return None
    votos_cand: dict[str, dict] = {}
    for carg in doc.get("carg", []):
        for agr in carg.get("agr", []):
            for par in agr.get("par", []):
                for cand in par.get("cand", []):
                    num = str(cand.get("n", ""))
                    votos_cand[num] = {
                        "nome": cand.get("nm", ""),
                        "votos": int(cand.get("vap", 0)),
                        "pct": cand.get("pvap", ""),
                    }
    s = doc.get("s", {})
    e = doc.get("e", {})
    v = doc.get("v", {})
    return {
        "secoes_totalizadas": int(s.get("st", 0)) if s else 0,
        "eleitores_aptos": int(e.get("te", 0)) if e else 0,
        "comparecimento": int(e.get("c", 0)) if e else 0,
        "abstencao": int(e.get("a", 0)) if e else 0,
        "votos_nominais": int(v.get("tv", 0)) if v else 0,
        "brancos": int(v.get("vb", 0)) if v else 0,
        "nulos": int(v.get("tvn", 0)) if v else 0,
        "candidatos": votos_cand,
    }


def _hms_encerramento(iso: str) -> str:
    if len(iso) >= 15 and "T" in iso:
        t = iso.split("T", 1)[1]
        if len(t) >= 6:
            return f"{t[0:2]}:{t[2:4]}:{t[4:6]}"
    return ""


def consolidar_analise_uf(
    *,
    uf: str,
    registros: list[dict],
    agregadas_1t: int = 0,
    agregadas_2t: int = 0,
    ag_pres_1t: dict | None = None,
    ag_pres_2t: dict | None = None,
    ag_gov_1t: dict | None = None,
    ag_gov_2t: dict | None = None,
) -> dict:
    """Executa as 10 baterias de auditoria estatística, temporal, biométrica e intralocal."""
    total_urnas = len(registros)
    completas_ambos = [r for r in registros if r.get("completa_1t") and r.get("completa_2t")]

    # 1. Somas gerais 1T e 2T (Presidente)
    aptos_1t_tot = sum(r["aptos_1t"] for r in completas_ambos)
    aptos_2t_tot = sum(r["aptos_2t"] for r in completas_ambos)
    comp_1t_tot = sum(r["comp_1t"] for r in completas_ambos)
    comp_2t_tot = sum(r["comp_2t"] for r in completas_ambos)
    sem_bio_1t_tot = sum(r["sem_bio_1t"] for r in completas_ambos)
    sem_bio_2t_tot = sum(r["sem_bio_2t"] for r in completas_ambos)

    soma_pres_1t: Counter[str] = Counter()
    soma_pres_2t: Counter[str] = Counter()
    brancos_1t = nulos_1t = brancos_2t = nulos_2t = 0

    for r in registros:
        p1 = r.get("pres_1t")
        if p1:
            for k, v in p1.get("nominais", {}).items():
                soma_pres_1t[k] += v
            brancos_1t += p1.get("brancos", 0)
            nulos_1t += p1.get("nulos", 0)
        p2 = r.get("pres_2t")
        if p2:
            for k, v in p2.get("nominais", {}).items():
                soma_pres_2t[k] += v
            brancos_2t += p2.get("brancos", 0)
            nulos_2t += p2.get("nulos", 0)

    of_pres_1t = _extrair_totais_agregado_tse(ag_pres_1t)
    of_pres_2t = _extrair_totais_agregado_tse(ag_pres_2t)
    of_gov_1t = _extrair_totais_agregado_tse(ag_gov_1t)
    of_gov_2t = _extrair_totais_agregado_tse(ag_gov_2t)

    # 2. Estatísticas por município (média e desvio-padrão de delta_comp_pp)
    deltas_por_mun: dict[str, list[float]] = defaultdict(list)
    for r in completas_ambos:
        deltas_por_mun[r["municipio"]].append(r["delta_comp_pp"])
    media_delta_mun: dict[str, tuple[float, float]] = {}
    for m, vals in deltas_por_mun.items():
        med = statistics.mean(vals) if vals else 0.0
        dp = statistics.stdev(vals) if len(vals) >= 3 else 3.0
        media_delta_mun[m] = (med, max(dp, 1.5))

    # 3. Agrupamento Intralocal (mesma escola: municipio + zona + local)
    secoes_por_escola: dict[str, list[dict]] = defaultdict(list)
    for r in completas_ambos:
        if r.get("local"):
            chave_esc = f"{r['municipio']}-{r['zona']}-{r['local']}"
            secoes_por_escola[chave_esc].append(r)

    outliers_escola: list[dict] = []
    mapa_desvio_escola: dict[str, dict] = {}
    for chave_esc, salas in secoes_por_escola.items():
        if len(salas) < 3:
            continue
        for idx, s in enumerate(salas):
            vizinhas = [x for j, x in enumerate(salas) if j != idx]
            comp_viz = [x["pct_comp_2t"] for x in vizinhas]
            med_comp_viz = statistics.mean(comp_viz)
            dp_comp_viz = max(statistics.stdev(comp_viz) if len(comp_viz) >= 2 else 2.5, 1.5)
            diff_comp = round(s["pct_comp_2t"] - med_comp_viz, 2)
            z_comp = round(diff_comp / dp_comp_viz, 2)

            def _pct22(reg: dict) -> float:
                p2 = reg.get("pres_2t") or {}
                nom = p2.get("nominais") or {}
                v22 = nom.get("22", 0)
                v13 = nom.get("13", 0)
                return 100.0 * v22 / (v22 + v13) if (v22 + v13) > 0 else 0.0

            p22_s = _pct22(s)
            p22_viz = [_pct22(x) for x in vizinhas]
            med_p22_viz = statistics.mean(p22_viz)
            dp_p22_viz = max(statistics.stdev(p22_viz) if len(p22_viz) >= 2 else 3.0, 2.0)
            diff_p22 = round(p22_s - med_p22_viz, 2)
            z_p22 = round(diff_p22 / dp_p22_viz, 2)

            info_esc = {
                "n_salas_escola": len(salas),
                "media_comp_escola_2t": round(med_comp_viz, 2),
                "diff_comp_escola_pp": diff_comp,
                "z_comp_escola": z_comp,
                "pct_22_secao": round(p22_s, 2),
                "media_pct_22_escola": round(med_p22_viz, 2),
                "diff_pct_22_escola_pp": diff_p22,
                "z_pct_22_escola": z_p22,
            }
            mapa_desvio_escola[s["chave"]] = info_esc
            if (abs(diff_p22) >= 12.0 and abs(z_p22) >= 3.0) or (
                abs(diff_comp) >= 10.0 and abs(z_comp) >= 3.0
            ):
                outliers_escola.append(
                    {
                        "chave": s["chave"],
                        "nome_municipio": s["nome_municipio"],
                        "zona": s["zona"],
                        "secao": s["secao"],
                        "local": s["local"],
                        "pct_comp_1t": s["pct_comp_1t"],
                        "pct_comp_2t": s["pct_comp_2t"],
                        **info_esc,
                    }
                )

    outliers_escola.sort(
        key=lambda x: max(abs(x["diff_pct_22_escola_pp"]), abs(x["diff_comp_escola_pp"])),
        reverse=True,
    )

    # 4. Votos após as 17h00, curvas horárias e cadência
    votos_apos_17h_1t = 0
    votos_apos_17h_2t = 0
    urnas_com_voto_apos_17h_1t = 0
    urnas_com_voto_apos_17h_2t = 0
    curva_minuto_apos_17h_1t: Counter[str] = Counter()
    curva_minuto_apos_17h_2t: Counter[str] = Counter()
    curva_horaria_1t: Counter[str] = Counter()
    curva_horaria_2t: Counter[str] = Counter()

    # Comparação de votos nas urnas com votação após 17h vs até 17h (no 2T)
    votos_2t_urnas_ate_17h = Counter({"13": 0, "22": 0, "urnas": 0, "votos_apos_17h": 0})
    votos_2t_urnas_apos_17h = Counter({"13": 0, "22": 0, "urnas": 0, "votos_apos_17h": 0})

    hist_delta_comp: Counter[str] = Counter()
    hist_mediana_intervalo_1t: Counter[str] = Counter()
    hist_mediana_intervalo_2t: Counter[str] = Counter()

    saltos_comparecimento: list[dict] = []
    comparecimento_100_ou_acima: list[dict] = []
    aptos_alterados: list[dict] = []
    perda_liquida_votos: list[dict] = []
    urnas_unanimes: list[dict] = []
    alta_sem_biometria: list[dict] = []
    urnas_pos_17h_top: list[dict] = []
    urnas_votacao_rapida: list[dict] = []
    divergencia_log_bu: list[dict] = []
    trocas_e_reboots: list[dict] = []
    hashes_1t_alterados: list[dict] = []
    dossie_secoes_criticas: list[dict] = []

    pontos_scatter_comp: list[dict] = []
    pontos_scatter_migracao: list[dict] = []
    pontos_scatter_biometria: list[dict] = []

    def _faixa_delta_comp(d: float) -> str:
        limites = [-15, -10, -6, -3, 0, 3, 6, 10, 15]
        for i, lim in enumerate(limites):
            if d < lim:
                return f"< {lim}" if i == 0 else f"{limites[i - 1]} a {lim}"
        return ">= 15"

    def _faixa_intervalo(s: float) -> str:
        for lim in (15, 25, 35, 45, 60, 90, 120):
            if s < lim:
                return f"< {lim}s"
        return ">= 120s"

    for r in registros:
        if r.get("hash_1t_mudou_pos_snapshot"):
            hashes_1t_alterados.append(
                {
                    "chave": r["chave"],
                    "nome_municipio": r["nome_municipio"],
                    "hash_snapshot_05_10": r["hash_1t_snapshot"][:24],
                    "hash_atual": r["hash_1t_atual"][:24],
                }
            )

    for r in completas_ambos:
        chave = r["chave"]
        l1 = r["log_1t"]
        l2 = r["log_2t"]
        p1_nom = (r.get("pres_1t") or {}).get("nominais") or {}
        p2_nom = (r.get("pres_2t") or {}).get("nominais") or {}
        v13_1t, v22_1t = int(p1_nom.get("13", 0)), int(p1_nom.get("22", 0))
        v13_2t, v22_2t = int(p2_nom.get("13", 0)), int(p2_nom.get("22", 0))
        d13 = v13_2t - v13_1t
        d22 = v22_2t - v22_1t
        pct_22_2t = round(100.0 * v22_2t / (v13_2t + v22_2t), 2) if (v13_2t + v22_2t) > 0 else 0.0
        pct_13_2t = round(100.0 * v13_2t / (v13_2t + v22_2t), 2) if (v13_2t + v22_2t) > 0 else 0.0

        hist_delta_comp[_faixa_delta_comp(r["delta_comp_pp"])] += 1
        if l1.get("intervalo_mediana_s") is not None:
            hist_mediana_intervalo_1t[_faixa_intervalo(l1["intervalo_mediana_s"])] += 1
        if l2.get("intervalo_mediana_s") is not None:
            hist_mediana_intervalo_2t[_faixa_intervalo(l2["intervalo_mediana_s"])] += 1

        ap1 = int(l1.get("votos_apos_17h", 0))
        ap2 = int(l2.get("votos_apos_17h", 0))
        votos_apos_17h_1t += ap1
        votos_apos_17h_2t += ap2
        if ap1 > 0:
            urnas_com_voto_apos_17h_1t += 1
        if ap2 > 0:
            urnas_com_voto_apos_17h_2t += 1
            votos_2t_urnas_apos_17h["13"] += v13_2t
            votos_2t_urnas_apos_17h["22"] += v22_2t
            votos_2t_urnas_apos_17h["urnas"] += 1
            votos_2t_urnas_apos_17h["votos_apos_17h"] += ap2
        else:
            votos_2t_urnas_ate_17h["13"] += v13_2t
            votos_2t_urnas_ate_17h["22"] += v22_2t
            votos_2t_urnas_ate_17h["urnas"] += 1

        for k, v in (l1.get("votos_apos_17h_por_minuto") or {}).items():
            curva_minuto_apos_17h_1t[k] += v
        for k, v in (l2.get("votos_apos_17h_por_minuto") or {}).items():
            curva_minuto_apos_17h_2t[k] += v
        for k, v in (l1.get("votos_por_hora") or {}).items():
            curva_horaria_1t[k] += v
        for k, v in (l2.get("votos_por_hora") or {}).items():
            curva_horaria_2t[k] += v

        # Motivos de alerta individualizados por seção
        motivos: list[str] = []
        score = 0.0
        med_mun, dp_mun = media_delta_mun.get(r["municipio"], (0.0, 2.5))
        z_delta_mun = (r["delta_comp_pp"] - med_mun) / dp_mun

        # (A) Comparecimento 100% ou > Aptos
        if (
            r["comp_1t"] >= r["aptos_1t"] > 0
            or r["comp_2t"] >= r["aptos_2t"] > 0
            or r["pct_comp_2t"] >= 99.0
        ):
            comparecimento_100_ou_acima.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "aptos_1t": r["aptos_1t"],
                    "comp_1t": r["comp_1t"],
                    "pct_comp_1t": r["pct_comp_1t"],
                    "aptos_2t": r["aptos_2t"],
                    "comp_2t": r["comp_2t"],
                    "pct_comp_2t": r["pct_comp_2t"],
                    "v13_2t": v13_2t,
                    "v22_2t": v22_2t,
                }
            )
            if r["comp_1t"] > r["aptos_1t"] or r["comp_2t"] > r["aptos_2t"]:
                motivos.append(
                    f"Comparecimento maior que eleitores aptos (1T: {r['comp_1t']}/{r['aptos_1t']}, 2T: {r['comp_2t']}/{r['aptos_2t']})"
                )
                score += 50.0
            elif r["comp_2t"] == r["aptos_2t"] or r["pct_comp_2t"] >= 99.5:
                motivos.append(
                    f"Comparecimento de {r['pct_comp_2t']:.1f}% no 2T ({r['comp_2t']}/{r['aptos_2t']} aptos; era {r['pct_comp_1t']:.1f}% no 1T)"
                )
                score += 20.0

        # (B) Salto de comparecimento (ex.: 80% -> 100% ou +10 p.p.)
        if (
            r["delta_comp_pp"] >= 8.0
            or (r["pct_comp_1t"] <= 88.0 and r["pct_comp_2t"] >= 95.0)
            or z_delta_mun >= 3.5
        ):
            saltos_comparecimento.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "aptos_2t": r["aptos_2t"],
                    "comp_1t": r["comp_1t"],
                    "pct_comp_1t": r["pct_comp_1t"],
                    "comp_2t": r["comp_2t"],
                    "pct_comp_2t": r["pct_comp_2t"],
                    "delta_comp_abs": r["delta_comp_abs"],
                    "delta_comp_pp": r["delta_comp_pp"],
                    "z_municipio": round(z_delta_mun, 2),
                    "v13_1t": v13_1t,
                    "v13_2t": v13_2t,
                    "v22_1t": v22_1t,
                    "v22_2t": v22_2t,
                }
            )
            if r["delta_comp_pp"] >= 10.0 or z_delta_mun >= 4.0:
                motivos.append(
                    f"Salto de comparecimento de {r['pct_comp_1t']:.1f}% (1T) para {r['pct_comp_2t']:.1f}% (2T) (+{r['delta_comp_pp']:.1f} p.p., Z={z_delta_mun:.1f})"
                )
                score += max(12.0, r["delta_comp_pp"] * 1.2)

        # (C) Mudança no número de eleitores aptos
        if r["delta_aptos"] != 0:
            aptos_alterados.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "aptos_1t": r["aptos_1t"],
                    "aptos_2t": r["aptos_2t"],
                    "delta_aptos": r["delta_aptos"],
                }
            )
            motivos.append(
                f"Número de eleitores aptos mudou entre turnos: {r['aptos_1t']} (1T) -> {r['aptos_2t']} (2T)"
            )
            score += 18.0

        # (D) Perda líquida de votos absolutos entre 1T e 2T
        if (d13 <= -10 or d22 <= -10) and r["delta_comp_abs"] >= -5:
            perda_liquida_votos.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "comp_1t": r["comp_1t"],
                    "comp_2t": r["comp_2t"],
                    "v13_1t": v13_1t,
                    "v13_2t": v13_2t,
                    "delta_13": d13,
                    "v22_1t": v22_1t,
                    "v22_2t": v22_2t,
                    "delta_22": d22,
                }
            )
            if d13 <= -15 or d22 <= -15:
                cand_perda = "Cand. 13" if d13 < d22 else "Cand. 22"
                perda_v = min(d13, d22)
                motivos.append(
                    f"Perda líquida de {abs(perda_v)} votos absolutos para {cand_perda} no 2T (13: {v13_1t}->{v13_2t}, 22: {v22_1t}->{v22_2t})"
                )
                score += abs(perda_v) * 0.5

        # (E) Urnas unânimes (0 votos para um dos candidatos)
        if (v13_2t == 0 or v22_2t == 0) and (v13_2t + v22_2t) > 0:
            urnas_unanimes.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "comp_2t": r["comp_2t"],
                    "v13_1t": v13_1t,
                    "v13_2t": v13_2t,
                    "v22_1t": v22_1t,
                    "v22_2t": v22_2t,
                }
            )
            motivos.append(
                f"Votação unânime no 2T (Cand. 13={v13_2t}, Cand. 22={v22_2t}; no 1T foi 13={v13_1t}, 22={v22_1t})"
            )
            score += 22.0

        # (F) Alta liberação sem biometria
        if r["pct_sem_bio_2t"] >= 25.0 or r["delta_sem_bio_pp"] >= 15.0:
            alta_sem_biometria.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "pct_sem_bio_1t": r["pct_sem_bio_1t"],
                    "pct_sem_bio_2t": r["pct_sem_bio_2t"],
                    "sem_bio_2t": r["sem_bio_2t"],
                    "comp_2t": r["comp_2t"],
                    "pct_comp_2t": r["pct_comp_2t"],
                    "pct_13_2t": pct_13_2t,
                    "pct_22_2t": pct_22_2t,
                }
            )
            if r["pct_sem_bio_2t"] >= 35.0:
                motivos.append(
                    f"Alta liberação manual sem biometria no 2T: {r['pct_sem_bio_2t']:.1f}% ({r['sem_bio_2t']}/{r['comp_2t']} eleitores)"
                )
                score += r["pct_sem_bio_2t"] * 0.35

        # (G) Votos após as 17h00
        if ap1 >= 15 or ap2 >= 15:
            urnas_pos_17h_top.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "votos_apos_17h_1t": ap1,
                    "encerramento_1t": _hms_encerramento(r["encerramento_1t"]),
                    "votos_apos_17h_2t": ap2,
                    "encerramento_2t": _hms_encerramento(r["encerramento_2t"]),
                    "comp_2t": r["comp_2t"],
                    "v13_2t": v13_2t,
                    "v22_2t": v22_2t,
                }
            )
            if ap2 >= 35 or ap1 >= 50:
                motivos.append(
                    f"Volume elevado de votos após as 17h00 (1T: {ap1} votos até {_hms_encerramento(r['encerramento_1t'])}; 2T: {ap2} votos até {_hms_encerramento(r['encerramento_2t'])})"
                )
                score += max(ap1, ap2) * 0.25

        # (H) Cadência rápida de votação ou divergência log vs BU
        v_rap_10_1t = int(l1.get("votos_intervalo_menor_10s", 0))
        v_rap_10_2t = int(l2.get("votos_intervalo_menor_10s", 0))
        med_2t = l2.get("intervalo_mediana_s")
        if v_rap_10_1t >= 3 or v_rap_10_2t >= 3 or (med_2t is not None and med_2t < 18.0):
            urnas_votacao_rapida.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "mediana_1t_s": l1.get("intervalo_mediana_s"),
                    "min_1t_s": l1.get("intervalo_min_s"),
                    "menor_10s_1t": v_rap_10_1t,
                    "mediana_2t_s": med_2t,
                    "min_2t_s": l2.get("intervalo_min_s"),
                    "menor_10s_2t": v_rap_10_2t,
                    "cabine_menor_5s_2t": l2.get("votos_cabine_menor_5s", 0),
                    "comp_2t": r["comp_2t"],
                }
            )
            if v_rap_10_2t >= 5 or (med_2t is not None and med_2t < 15.0):
                motivos.append(
                    f"Cadência acelerada no log 2T: mediana {med_2t}s entre eleitores ({v_rap_10_2t} votos com intervalo <10s)"
                )
                score += 15.0

        if (l1.get("presente") and l1.get("votos_computados") != r["comp_1t"]) or (
            l2.get("presente") and l2.get("votos_computados") != r["comp_2t"]
        ):
            divergencia_log_bu.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "comp_bu_1t": r["comp_1t"],
                    "votos_log_1t": l1.get("votos_computados"),
                    "comp_bu_2t": r["comp_2t"],
                    "votos_log_2t": l2.get("votos_computados"),
                }
            )
            motivos.append(
                f"Diferença entre votos no BU e eventos no Log (1T BU={r['comp_1t']}/Log={l1.get('votos_computados')}, 2T BU={r['comp_2t']}/Log={l2.get('votos_computados')})"
            )
            score += 20.0

        # (I) Troca de urna, contingência, reinícios ou relógio
        reboots = int(l1.get("reinicios_durante_votacao", 0)) + int(
            l2.get("reinicios_durante_votacao", 0)
        )
        regr_rel = int(l1.get("regressoes_relogio", 0)) + int(l2.get("regressoes_relogio", 0))
        if (
            r.get("trocou_urna_entre_turnos")
            or l1.get("trocou_urna_no_dia")
            or l2.get("trocou_urna_no_dia")
            or reboots > 0
            or regr_rel > 0
        ):
            trocas_e_reboots.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "urna_1t": r["urna_1t"],
                    "urna_2t": r["urna_2t"],
                    "trocou_entre_turnos": r["trocou_urna_entre_turnos"],
                    "contingencia_1t": l1.get("trocou_urna_no_dia", False),
                    "contingencia_2t": l2.get("trocou_urna_no_dia", False),
                    "reboots": reboots,
                    "regressoes_relogio": regr_rel,
                }
            )
            if reboots > 0 or regr_rel > 0:
                motivos.append(
                    f"Evento operacional no log: {reboots} reinício(s) durante votação, {regr_rel} regressão(ões) de relógio"
                )
                score += 12.0

        # (J) Divergência intralocal (mesma escola)
        esc = mapa_desvio_escola.get(chave)
        if esc:
            if abs(esc["diff_pct_22_escola_pp"]) >= 12.0 and abs(esc["z_pct_22_escola"]) >= 3.0:
                motivos.append(
                    f"Divergência na mesma escola (local {r['local']}): Cand. 22 teve {esc['pct_22_secao']:.1f}% nesta sala vs {esc['media_pct_22_escola']:.1f}% nas outras {esc['n_salas_escola']-1} salas ({esc['diff_pct_22_escola_pp']:+.1f} p.p., Z={esc['z_pct_22_escola']:+.1f})"
                )
                score += abs(esc["diff_pct_22_escola_pp"]) * 0.8
            if abs(esc["diff_comp_escola_pp"]) >= 10.0 and abs(esc["z_comp_escola"]) >= 3.0:
                motivos.append(
                    f"Comparecimento destoante da própria escola: {r['pct_comp_2t']:.1f}% nesta sala vs {esc['media_comp_escola_2t']:.1f}% nas salas vizinhas ({esc['diff_comp_escola_pp']:+.1f} p.p.)"
                )
                score += abs(esc["diff_comp_escola_pp"]) * 0.8

        if motivos:
            dossie_secoes_criticas.append(
                {
                    "chave": chave,
                    "nome_municipio": r["nome_municipio"],
                    "zona": r["zona"],
                    "secao": r["secao"],
                    "local": r["local"],
                    "score": round(score, 1),
                    "aptos_2t": r["aptos_2t"],
                    "pct_comp_1t": r["pct_comp_1t"],
                    "pct_comp_2t": r["pct_comp_2t"],
                    "delta_comp_pp": r["delta_comp_pp"],
                    "pct_sem_bio_2t": r["pct_sem_bio_2t"],
                    "votos_apos_17h_2t": ap2,
                    "v13_1t": v13_1t,
                    "v13_2t": v13_2t,
                    "v22_1t": v22_1t,
                    "v22_2t": v22_2t,
                    "motivos": motivos,
                }
            )

        # Amostragem determinística + todos os outliers para os gráficos de dispersão SVG
        eh_destaque = bool(motivos) or abs(r["delta_comp_pp"]) >= 7.0 or r["pct_sem_bio_2t"] >= 22.0
        if eh_destaque or (hash(chave) % 6 == 0):
            pontos_scatter_comp.append(
                {
                    "c": chave,
                    "m": r["nome_municipio"],
                    "x": r["pct_comp_1t"],
                    "y": r["pct_comp_2t"],
                    "a": 1 if (r["delta_comp_pp"] >= 10.0 or r["pct_comp_2t"] >= 99.0) else 0,
                }
            )
            pontos_scatter_migracao.append(
                {
                    "c": chave,
                    "m": r["nome_municipio"],
                    "x": d13,
                    "y": d22,
                    "a": 1 if (d13 <= -10 or d22 <= -10) else 0,
                }
            )
            pontos_scatter_biometria.append(
                {
                    "c": chave,
                    "m": r["nome_municipio"],
                    "x": r["pct_sem_bio_2t"],
                    "y": r["pct_comp_2t"],
                    "v22": pct_22_2t,
                    "a": 1 if r["pct_sem_bio_2t"] >= 25.0 else 0,
                }
            )

    saltos_comparecimento.sort(key=lambda x: x["delta_comp_pp"], reverse=True)
    comparecimento_100_ou_acima.sort(
        key=lambda x: (x["pct_comp_2t"], x["comp_2t"]), reverse=True
    )
    perda_liquida_votos.sort(key=lambda x: min(x["delta_13"], x["delta_22"]))
    alta_sem_biometria.sort(key=lambda x: x["pct_sem_bio_2t"], reverse=True)
    urnas_pos_17h_top.sort(
        key=lambda x: max(x["votos_apos_17h_1t"], x["votos_apos_17h_2t"]), reverse=True
    )
    urnas_votacao_rapida.sort(
        key=lambda x: (x["menor_10s_2t"] + x["menor_10s_1t"]), reverse=True
    )
    dossie_secoes_criticas.sort(key=lambda x: x["score"], reverse=True)

    return {
        "uf": uf.upper(),
        "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "totais": {
            "urnas_malha": total_urnas,
            "urnas_completas_ambos_turnos": len(completas_ambos),
            "urnas_incompletas": total_urnas - len(completas_ambos),
            "secoes_agregadas_1t": agregadas_1t,
            "secoes_agregadas_2t": agregadas_2t,
            "aptos_1t": aptos_1t_tot,
            "aptos_2t": aptos_2t_tot,
            "comparecimento_1t": comp_1t_tot,
            "comparecimento_2t": comp_2t_tot,
            "pct_comparecimento_1t": round(100.0 * comp_1t_tot / aptos_1t_tot, 2)
            if aptos_1t_tot
            else 0.0,
            "pct_comparecimento_2t": round(100.0 * comp_2t_tot / aptos_2t_tot, 2)
            if aptos_2t_tot
            else 0.0,
            "delta_comparecimento_pp": round(
                (100.0 * comp_2t_tot / aptos_2t_tot) - (100.0 * comp_1t_tot / aptos_1t_tot), 2
            )
            if (aptos_1t_tot and aptos_2t_tot)
            else 0.0,
            "sem_biometria_1t": sem_bio_1t_tot,
            "sem_biometria_2t": sem_bio_2t_tot,
            "pct_sem_biometria_1t": round(100.0 * sem_bio_1t_tot / comp_1t_tot, 2)
            if comp_1t_tot
            else 0.0,
            "pct_sem_biometria_2t": round(100.0 * sem_bio_2t_tot / comp_2t_tot, 2)
            if comp_2t_tot
            else 0.0,
            "votos_apos_17h_1t": votos_apos_17h_1t,
            "votos_apos_17h_2t": votos_apos_17h_2t,
            "urnas_com_voto_apos_17h_1t": urnas_com_voto_apos_17h_1t,
            "urnas_com_voto_apos_17h_2t": urnas_com_voto_apos_17h_2t,
            "hashes_1t_alterados_pos_snapshot": len(hashes_1t_alterados),
        },
        "presidente": {
            "soma_bu_1t": {
                "nominais": dict(soma_pres_1t),
                "brancos": brancos_1t,
                "nulos": nulos_1t,
            },
            "soma_bu_2t": {
                "nominais": dict(soma_pres_2t),
                "brancos": brancos_2t,
                "nulos": nulos_2t,
            },
            "oficial_tse_1t": of_pres_1t,
            "oficial_tse_2t": of_pres_2t,
        },
        "governador": {
            "oficial_tse_1t": of_gov_1t,
            "oficial_tse_2t": of_gov_2t,
        },
        "pos_17h": {
            "curva_minuto_1t": dict(sorted(curva_minuto_apos_17h_1t.items())),
            "curva_minuto_2t": dict(sorted(curva_minuto_apos_17h_2t.items())),
            "curva_horaria_1t": dict(sorted(curva_horaria_1t.items())),
            "curva_horaria_2t": dict(sorted(curva_horaria_2t.items())),
            "comparativo_votos_2t": {
                "urnas_ate_17h": dict(votos_2t_urnas_ate_17h),
                "urnas_apos_17h": dict(votos_2t_urnas_apos_17h),
            },
            "top_urnas": urnas_pos_17h_top[:100],
        },
        "distribuicoes": {
            "delta_comparecimento": dict(hist_delta_comp),
            "mediana_intervalo_1t": dict(hist_mediana_intervalo_1t),
            "mediana_intervalo_2t": dict(hist_mediana_intervalo_2t),
        },
        "anomalias": {
            "contagens": {
                "saltos_comparecimento": len(saltos_comparecimento),
                "comparecimento_100_ou_acima": len(comparecimento_100_ou_acima),
                "aptos_alterados": len(aptos_alterados),
                "perda_liquida_votos": len(perda_liquida_votos),
                "urnas_unanimes": len(urnas_unanimes),
                "alta_sem_biometria": len(alta_sem_biometria),
                "outliers_mesma_escola": len(outliers_escola),
                "urnas_votacao_rapida": len(urnas_votacao_rapida),
                "divergencia_log_bu": len(divergencia_log_bu),
                "trocas_e_reboots": len(trocas_e_reboots),
                "hashes_1t_alterados": len(hashes_1t_alterados),
                "secoes_com_alerta": len(dossie_secoes_criticas),
            },
            "saltos_comparecimento": saltos_comparecimento[:100],
            "comparecimento_100_ou_acima": comparecimento_100_ou_acima[:100],
            "aptos_alterados": aptos_alterados[:100],
            "perda_liquida_votos": perda_liquida_votos[:100],
            "urnas_unanimes": urnas_unanimes[:100],
            "alta_sem_biometria": alta_sem_biometria[:100],
            "outliers_mesma_escola": outliers_escola[:100],
            "urnas_votacao_rapida": urnas_votacao_rapida[:100],
            "divergencia_log_bu": divergencia_log_bu[:100],
            "trocas_e_reboots": trocas_e_reboots[:100],
            "hashes_1t_alterados": hashes_1t_alterados[:100],
            "dossie_secoes_criticas": dossie_secoes_criticas[:150],
        },
        "graficos": {
            "scatter_comparecimento": pontos_scatter_comp[:2500],
            "scatter_migracao": pontos_scatter_migracao[:2500],
            "scatter_biometria": pontos_scatter_biometria[:2500],
        },
    }
