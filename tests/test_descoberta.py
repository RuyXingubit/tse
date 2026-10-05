import pytest

from tse_coleta.descoberta import PleitoNaoEncontrado, descobrir_pleito


def test_descobre_pleito_2026(carregar):
    p = descobrir_pleito(carregar("ele-c-min.json"), "ele2026", "04/10/2026")
    assert p.codigo == "3220"
    assert [e.codigo for e in p.eleicoes] == ["6257", "6259", "6261"]
    est = p.eleicoes[1]
    assert [c.codigo for c in est.cargos] == ["3", "5", "6", "7", "8"]
    assert p.eleicoes[2].cargos[0].descricao == "Conselheiro Distrital"


def test_nao_confunde_com_suplementar_de_2026_do_ciclo_2024(carregar):
    # Suplementar de RR em 21/06/2026 pertence ao ciclo ele2024
    with pytest.raises(PleitoNaoEncontrado):
        descobrir_pleito(carregar("ele-c-min.json"), "ele2026", "21/06/2026")


def test_falha_se_nao_encontrar(carregar):
    with pytest.raises(PleitoNaoEncontrado):
        descobrir_pleito(carregar("ele-c-min.json"), "ele2026", "25/10/2026")


def test_falha_se_ambiguo(carregar):
    cfg = carregar("ele-c-min.json")
    cfg["pl"].append(dict(cfg["pl"][-1]))
    with pytest.raises(PleitoNaoEncontrado):
        descobrir_pleito(cfg, "ele2026", "04/10/2026")
