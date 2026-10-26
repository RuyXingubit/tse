import io
import zipfile

import pytest

from tse_coleta.analisador_log import (
    ErroAnaliseLog,
    analisar_log_por_datas,
)


def construir_log_jez(linhas: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("logd.dat", ("\n".join(linhas) + "\n").encode("latin-1"))
    return buf.getvalue()


def test_analisa_log_1t_e_2t_no_mesmo_jez_com_votos_apos_17h():
    linhas = [
        "04/10/2026 08:00:10\tINFO\t02394579\tVOTA\tEleitor foi habilitado\tAAA",
        "04/10/2026 08:00:10\tINFO\t02394579\tVOTA\tTipo de habilitação do eleitor [biométrica]\tAAA",
        "04/10/2026 08:00:40\tINFO\t02394579\tVOTA\tO voto do eleitor foi computado\tAAA",
        "04/10/2026 16:59:50\tINFO\t02394579\tVOTA\tEleitor foi habilitado\tAAA",
        "04/10/2026 17:00:20\tINFO\t02394579\tVOTA\tO voto do eleitor foi computado\tAAA",
        "04/10/2026 17:00:25\tINFO\t02394579\tVOTA\tEleitor foi habilitado\tAAA",
        "04/10/2026 17:00:28\tINFO\t02394579\tVOTA\tO voto do eleitor foi computado\tAAA",
        "25/10/2026 09:00:00\tINFO\t02394579\tVOTA\tEleitor foi habilitado\tBBB",
        "25/10/2026 09:00:20\tINFO\t02394579\tVOTA\tO voto do eleitor foi computado\tBBB",
        "25/10/2026 12:00:00\tINFO\t02394579\tLOGD\tInício das operações do logd\tBBB",
        "25/10/2026 11:59:00\tINFO\t02394579\tVOTA\tTecla indevida pressionada\tBBB",
        "25/10/2026 17:05:10\tINFO\t02394579\tVOTA\tEleitor foi habilitado\tBBB",
        "25/10/2026 17:05:35\tINFO\t02394579\tVOTA\tO voto do eleitor foi computado\tBBB",
    ]
    jez = construir_log_jez(linhas)
    res = analisar_log_por_datas(jez, ("04/10/2026", "25/10/2026"), uf="pa")

    r1 = res["04/10/2026"]
    assert r1.presente is True
    assert r1.ids_urna == ["02394579"]
    assert r1.votos_computados == 3
    assert r1.votos_ate_17h == 1
    assert r1.votos_apos_17h == 2
    assert r1.votos_apos_17h_por_minuto == {"17:00": 2}
    assert r1.votos_intervalo_menor_10s == 1
    assert r1.votos_cabine_menor_5s == 1
    assert r1.habilitacoes_biometricas == 1

    r2 = res["25/10/2026"]
    assert r2.presente is True
    assert r2.votos_computados == 2
    assert r2.votos_ate_17h == 1
    assert r2.votos_apos_17h == 1
    assert r2.votos_apos_17h_por_minuto == {"17:05": 1}
    assert r2.reinicios_durante_votacao == 1
    assert r2.regressoes_relogio == 1
    assert r2.teclas_indevidas == 1


def test_fuso_acre_ajusta_hora_limite_para_15h_local():
    linhas = [
        "25/10/2026 14:59:50\tINFO\t01111111\tVOTA\tO voto do eleitor foi computado\tAAA",
        "25/10/2026 15:02:10\tINFO\t01111111\tVOTA\tO voto do eleitor foi computado\tAAA",
    ]
    res = analisar_log_por_datas(construir_log_jez(linhas), ("25/10/2026",), uf="ac")["25/10/2026"]
    assert res.hora_limite_local == "15:00:00"
    assert res.votos_ate_17h == 1
    assert res.votos_apos_17h == 1
    assert res.votos_apos_17h_por_minuto == {"17:02": 1}


def test_log_invalido_levanta_excecao():
    with pytest.raises(ErroAnaliseLog):
        analisar_log_por_datas(b"")
    with pytest.raises(ErroAnaliseLog):
        analisar_log_por_datas(b"nao-e-um-zip")
