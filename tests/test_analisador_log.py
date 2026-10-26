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


def test_log_jez_com_contingencia_aninhada_soma_sem_duplicar():
    jez_anterior = construir_log_jez([
        "04/10/2026 08:10:00\tINFO\t01111111\tVOTA\tO voto do eleitor foi computado\tA1",
        "04/10/2026 08:20:00\tINFO\t01111111\tVOTA\tO voto do eleitor foi computado\tA2",
    ])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("011111110410202614000001ME.jez", jez_anterior)
        zf.writestr("0222222204102026150000-01.jez", jez_anterior)  # cópia idêntica da ME
        zf.writestr(
            "logd.dat",
            (
                "04/10/2026 15:10:00\tINFO\t02222222\tVOTA\tO voto do eleitor foi computado\tB1\n"
            ).encode("latin-1"),
        )
    res = analisar_log_por_datas(buf.getvalue(), ("04/10/2026",), uf="pa")["04/10/2026"]
    assert res.votos_computados == 3
    assert res.ids_urna == ["01111111", "02222222"]
    assert res.trocou_urna_no_dia is True


def test_extrai_auditoria_nominal_de_mesarios_e_habilitacao_manual():
    linhas = [
        "25/10/2026 08:15:00\tINFO\t01793135\tVOTA\tFoto do eleitor apresentada\tA1",
        "25/10/2026 08:15:10\tINFO\t01793135\tVOTA\tSolicitação de dado pessoal do eleitor para habilitação manual\tA2",
        "25/10/2026 08:15:20\tINFO\t01793135\tVOTA\tMesário 046716651333 habilitou o eleitor\tA3",
        "25/10/2026 08:15:22\tINFO\t01793135\tVOTA\tEleitor foi habilitado\tA4",
        "25/10/2026 08:15:35\tINFO\t01793135\tVOTA\tO voto do eleitor foi computado\tA5",
        "25/10/2026 14:20:00\tINFO\t01793135\tVOTA\tFoto do eleitor apresentada\tB1",
        "25/10/2026 14:20:10\tINFO\t01793135\tVOTA\tSolicitação de dado pessoal do eleitor para habilitação manual\tB2",
        "25/10/2026 14:20:20\tINFO\t01793135\tVOTA\tDigital coletada bate com uma digital gravada após o registro inicial de mesário. Não é possível associar a habilitação a um mesário.\tB3",
        "25/10/2026 14:20:22\tINFO\t01793135\tVOTA\tEleitor foi habilitado\tB4",
        "25/10/2026 14:20:35\tINFO\t01793135\tVOTA\tO voto do eleitor foi computado\tB5",
        "25/10/2026 17:01:00\tINFO\t01793135\tVOTA\tGerando relatório [ELEITORES HABILITADOS BIOGRAFICAMENTE] [INÍCIO]\tC1",
    ]
    res = analisar_log_por_datas(construir_log_jez(linhas), ("25/10/2026",), uf="pa")["25/10/2026"]
    assert res.fotos_apresentadas == 2
    assert res.solicitacoes_dado_manual == 2
    assert res.manuais_por_hora == {"08": 1, "14": 1}
    assert res.mesarios_habilitadores == {"046716651333": 1}
    assert res.mesarios_manha_08_11 == {"046716651333": 1}
    assert res.digital_nao_associada_mesario == 1
    assert res.gerou_relatorio_habilitados_biograficamente is True
