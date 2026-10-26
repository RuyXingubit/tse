"""Analisador em memória de arquivos `-log.jez` (ZIP contendo `logd.dat`) da urna eletrônica.

Observação importante descoberta na sondagem real:
O arquivo `-log.jez` do 2º turno (`pleito 3221`) já contém o histórico completo do `logd.dat`
tanto do 1º turno (`04/10/2026`) quanto do 2º turno (`25/10/2026`) quando a seção utilizou a
mesma urna física.
"""

from __future__ import annotations

import io
import statistics
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field

FUSO_OFFSET_UF: dict[str, int] = {
    # Diferença em horas do relógio local da urna em relação ao horário de Brasília (BRT)
    "ac": -2,
    "am": -1,
    "ms": -1,
    "mt": -1,
    "ro": -1,
    "rr": -1,
}


class ErroAnaliseLog(ValueError):
    """Arquivo `log.jez` corrompido, sem `logd.dat` ou formato inválido."""


@dataclass(frozen=True, slots=True)
class ResumoLogTurno:
    data: str
    presente: bool
    ids_urna: list[str] = field(default_factory=list)
    trocou_urna_no_dia: bool = False
    hora_limite_local: str = "17:00:00"
    primeiro_voto_em: str = ""
    ultimo_voto_em: str = ""
    votos_computados: int = 0
    votos_ate_17h: int = 0
    votos_apos_17h: int = 0
    votos_por_hora: dict[str, int] = field(default_factory=dict)  # hora "08".."20" (normalizada BRT)
    votos_apos_17h_por_minuto: dict[str, int] = field(default_factory=dict)  # "17:00".."20:59" (BRT)
    intervalo_min_s: float | None = None
    intervalo_p10_s: float | None = None
    intervalo_mediana_s: float | None = None
    votos_intervalo_menor_10s: int = 0
    votos_intervalo_menor_15s: int = 0
    duracao_cabine_min_s: float | None = None
    duracao_cabine_mediana_s: float | None = None
    votos_cabine_menor_5s: int = 0
    habilitacoes_biometricas: int = 0
    falhas_digital: int = 0
    teclas_indevidas: int = 0
    reinicios_durante_votacao: int = 0
    regressoes_relogio: int = 0
    fotos_apresentadas: int = 0
    solicitacoes_dado_manual: int = 0
    manuais_por_hora: dict[str, int] = field(default_factory=dict)
    mesarios_habilitadores: dict[str, int] = field(default_factory=dict)
    mesarios_manha_08_11: dict[str, int] = field(default_factory=dict)
    digital_nao_associada_mesario: int = 0
    gerou_relatorio_habilitados_biograficamente: bool = False

    def para_dict(self) -> dict:
        return asdict(self)


def _hms_para_segundos(hms: str) -> int | None:
    if len(hms) != 8 or hms[2] != ":" or hms[5] != ":":
        return None
    try:
        h = int(hms[0:2])
        m = int(hms[3:5])
        s = int(hms[6:8])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
        return None
    return h * 3600 + m * 60 + s


def _segundos_para_hms(seg: int) -> str:
    seg = max(0, min(86399, seg))
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def extrair_texto_logd(dados_jez: bytes) -> str:
    """Descompacta `logd.dat` (incluindo `.jez` aninhados de contingência) em memória."""
    if not dados_jez:
        raise ErroAnaliseLog("log.jez vazio")
    vistas: set[str] = set()
    linhas_ordenadas: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(dados_jez)) as zf:
            nomes = zf.namelist()
            if not nomes:
                raise ErroAnaliseLog("log.jez sem arquivos internos")
            # Processa primeiro eventuais `.jez` aninhados (urna substituída/contingência) e depois `logd.dat`
            for nm in sorted(nomes, key=lambda n: (n.lower() == "logd.dat", n)):
                bruto = zf.read(nm)
                if nm.lower().endswith(".jez") and bruto[:4] == b"PK\x03\x04":
                    try:
                        with zipfile.ZipFile(io.BytesIO(bruto)) as zf2:
                            for nm2 in sorted(zf2.namelist()):
                                if nm2.lower().endswith(".dat"):
                                    txt2 = zf2.read(nm2).decode("latin-1", errors="replace")
                                    for l in txt2.splitlines():
                                        if l not in vistas:
                                            vistas.add(l)
                                            linhas_ordenadas.append(l)
                    except zipfile.BadZipFile:
                        continue
                elif nm.lower().endswith(".dat") or len(nomes) == 1:
                    txt = bruto.decode("latin-1", errors="replace")
                    for l in txt.splitlines():
                        if l not in vistas:
                            vistas.add(l)
                            linhas_ordenadas.append(l)
    except (zipfile.BadZipFile, OSError, KeyError) as e:
        raise ErroAnaliseLog(f"falha ao abrir log.jez: {e}") from e
    return "\n".join(linhas_ordenadas)


def analisar_log_por_datas(
    dados_jez: bytes,
    datas: tuple[str, ...] = ("04/10/2026", "25/10/2026"),
    *,
    uf: str = "pa",
) -> dict[str, ResumoLogTurno]:
    """Analisa `log.jez` em memória e devolve o `ResumoLogTurno` para cada data solicitada."""
    texto = extrair_texto_logd(dados_jez)
    return analisar_texto_logd(texto, datas=datas, uf=uf)


def analisar_texto_logd(
    texto: str,
    datas: tuple[str, ...] = ("04/10/2026", "25/10/2026"),
    *,
    uf: str = "pa",
) -> dict[str, ResumoLogTurno]:
    offset_h = FUSO_OFFSET_UF.get(uf.lower(), 0)
    seg_limite_padrao = (17 + offset_h) * 3600  # 17:00 em BRT ajustado ao fuso da UF

    # Agrupa linhas por data alvo (comparando os 10 primeiros caracteres "dd/mm/aaaa")
    conjunto_datas = set(datas)
    linhas_por_data: dict[str, list[str]] = {d: [] for d in datas}
    for linha in texto.splitlines():
        if len(linha) >= 19:
            d = linha[:10]
            if d in conjunto_datas:
                linhas_por_data[d].append(linha)

    resultado: dict[str, ResumoLogTurno] = {}
    for data in datas:
        linhas = linhas_por_data[data]
        if not linhas:
            resultado[data] = ResumoLogTurno(
                data=data,
                presente=False,
                hora_limite_local=_segundos_para_hms(seg_limite_padrao),
            )
            continue

        ids_urna: list[str] = []
        ids_vistos: set[str] = set()
        tempos_voto: list[int] = []
        hms_votos: list[str] = []
        duracoes_cabine: list[int] = []
        ultimo_habilitado_s: int | None = None
        ultimo_ts_s: int | None = None
        ja_abriu_votacao = False
        encerrada_votacao = False

        habilitacoes_bio = 0
        falhas_digital = 0
        teclas_indevidas = 0
        reinicios_votacao = 0
        regressoes_relogio = 0
        fotos_apresentadas = 0
        solicitacoes_dado_manual = 0
        tempos_manuais: list[int] = []
        mesarios_hab: Counter[str] = Counter()
        eventos_mesario: list[tuple[int, str]] = []
        digital_nao_assoc = 0
        gerou_rel_biografico = False

        for linha in linhas:
            partes = linha.split("\t")
            if len(partes) < 5:
                continue
            dh = partes[0]
            hms = dh[11:19] if len(dh) >= 19 else ""
            seg = _hms_para_segundos(hms)
            if seg is None:
                continue
            if ultimo_ts_s is not None and seg < ultimo_ts_s - 2:
                regressoes_relogio += 1
            ultimo_ts_s = seg

            id_u = partes[2].strip()
            if id_u and id_u not in ids_vistos:
                ids_vistos.add(id_u)
                ids_urna.append(id_u)

            msg = partes[4]
            if "Eleitor foi habilitado" in msg:
                ja_abriu_votacao = True
                ultimo_habilitado_s = seg
            elif "O voto do eleitor foi computado" in msg:
                ja_abriu_votacao = True
                tempos_voto.append(seg)
                hms_votos.append(hms)
                if ultimo_habilitado_s is not None and seg >= ultimo_habilitado_s:
                    dur = seg - ultimo_habilitado_s
                    if dur <= 1800:
                        duracoes_cabine.append(dur)
                ultimo_habilitado_s = None
            elif "Tipo de habilitação do eleitor [biométrica]" in msg:
                habilitacoes_bio += 1
            elif "Foto do eleitor apresentada" in msg:
                fotos_apresentadas += 1
            elif "Solicitação de dado pessoal do eleitor para habilitação manual" in msg:
                solicitacoes_dado_manual += 1
                tempos_manuais.append(seg)
            elif msg.startswith("Mesário ") and " habilitou o eleitor" in msg:
                partes_m = msg.split()
                if len(partes_m) >= 2:
                    id_mes = partes_m[1]
                    mesarios_hab[id_mes] += 1
                    eventos_mesario.append((seg, id_mes))
            elif "Não é possível associar a habilitação a um mesário" in msg:
                digital_nao_assoc += 1
            elif "ELEITORES HABILITADOS BIOGRAFICAMENTE" in msg:
                gerou_rel_biografico = True
            elif "Número de tentativas de reconhecimento do dedo" in msg:
                falhas_digital += 1
            elif "Tecla indevida pressionada" in msg:
                teclas_indevidas += 1
            elif "Gerando arquivo de resultado [bu.dat]" in msg or "Encerrando a votação" in msg:
                encerrada_votacao = True
            elif (
                ja_abriu_votacao
                and not encerrada_votacao
                and ("Início das operações do logd" in msg or "Urna ligada em" in msg)
            ):
                reinicios_votacao += 1

        # Detecta se a urna estava em fuso diferente pelo horário do primeiro voto (ex. Extremo Oeste do AM)
        seg_limite = seg_limite_padrao
        if tempos_voto:
            h_primeiro = tempos_voto[0] // 3600
            if h_primeiro == 6 and offset_h == -1:
                seg_limite = 15 * 3600
        deslocamento_brt = 17 * 3600 - seg_limite

        votos_computados = len(tempos_voto)
        votos_ate_17h = 0
        votos_apos_17h = 0
        por_hora: Counter[str] = Counter()
        apos_17h_min: Counter[str] = Counter()
        manuais_hora: Counter[str] = Counter()
        mesarios_manha: Counter[str] = Counter()

        for seg in tempos_manuais:
            seg_brt = seg + deslocamento_brt
            h_brt = max(0, min(23, seg_brt // 3600))
            manuais_hora[f"{h_brt:02d}"] += 1

        for seg, id_mes in eventos_mesario:
            seg_brt = seg + deslocamento_brt
            h_brt = max(0, min(23, seg_brt // 3600))
            if 8 <= h_brt <= 10:
                mesarios_manha[id_mes] += 1

        for seg in tempos_voto:
            seg_brt = seg + deslocamento_brt
            h_brt = max(0, min(23, seg_brt // 3600))
            por_hora[f"{h_brt:02d}"] += 1
            if seg <= seg_limite:
                votos_ate_17h += 1
            else:
                votos_apos_17h += 1
                m_brt = (seg_brt % 3600) // 60
                apos_17h_min[f"{h_brt:02d}:{m_brt:02d}"] += 1

        intervalos = [
            b - a for a, b in zip(tempos_voto, tempos_voto[1:]) if 0 <= (b - a) <= 1800
        ]
        if intervalos:
            ord_int = sorted(intervalos)
            intervalo_min = float(ord_int[0])
            idx_p10 = max(0, int(len(ord_int) * 0.10) - 1)
            intervalo_p10 = float(ord_int[idx_p10])
            intervalo_med = float(statistics.median(ord_int))
            menores_10s = sum(1 for x in intervalos if x < 10)
            menores_15s = sum(1 for x in intervalos if x < 15)
        else:
            intervalo_min = intervalo_p10 = intervalo_med = None
            menores_10s = menores_15s = 0

        if duracoes_cabine:
            ord_cab = sorted(duracoes_cabine)
            cab_min = float(ord_cab[0])
            cab_med = float(statistics.median(ord_cab))
            cab_menores_5s = sum(1 for x in duracoes_cabine if x < 5)
        else:
            cab_min = cab_med = None
            cab_menores_5s = 0

        resultado[data] = ResumoLogTurno(
            data=data,
            presente=votos_computados > 0 or bool(ids_urna),
            ids_urna=ids_urna,
            trocou_urna_no_dia=len(ids_urna) > 1,
            hora_limite_local=_segundos_para_hms(seg_limite),
            primeiro_voto_em=hms_votos[0] if hms_votos else "",
            ultimo_voto_em=hms_votos[-1] if hms_votos else "",
            votos_computados=votos_computados,
            votos_ate_17h=votos_ate_17h,
            votos_apos_17h=votos_apos_17h,
            votos_por_hora=dict(sorted(por_hora.items())),
            votos_apos_17h_por_minuto=dict(sorted(apos_17h_min.items())),
            intervalo_min_s=intervalo_min,
            intervalo_p10_s=intervalo_p10,
            intervalo_mediana_s=intervalo_med,
            votos_intervalo_menor_10s=menores_10s,
            votos_intervalo_menor_15s=menores_15s,
            duracao_cabine_min_s=cab_min,
            duracao_cabine_mediana_s=cab_med,
            votos_cabine_menor_5s=cab_menores_5s,
            habilitacoes_biometricas=habilitacoes_bio,
            falhas_digital=falhas_digital,
            teclas_indevidas=teclas_indevidas,
            reinicios_durante_votacao=reinicios_votacao,
            regressoes_relogio=regressoes_relogio,
            fotos_apresentadas=fotos_apresentadas,
            solicitacoes_dado_manual=solicitacoes_dado_manual,
            manuais_por_hora=dict(sorted(manuais_hora.items())),
            mesarios_habilitadores=dict(mesarios_hab.most_common()),
            mesarios_manha_08_11=dict(mesarios_manha.most_common()),
            digital_nao_associada_mesario=digital_nao_assoc,
            gerou_relatorio_habilitados_biograficamente=gerou_rel_biografico,
        )

    return resultado
