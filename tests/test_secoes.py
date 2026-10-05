import pytest

from tse_coleta.codigos import CodigoInvalido
from tse_coleta.secoes import ler_lista_secoes


def test_le_lista_rr(carregar):
    lista = ler_lista_secoes(carregar("rr-cs-min.json"), "rr")
    assert lista.gerado_em == "04/10/2026 22:47:53"
    assert len(lista.secoes) == 5
    assert len(lista.urnas) == 4  # 0120 é agregada
    assert [s.id.chave for s in lista.publicadas] == [
        "rr-03085-0008-0001",
        "rr-03085-0008-0002",
        "rr-03123-0007-0012",
    ]
    assert [s.id.chave for s in lista.pendentes] == ["rr-03085-0008-0003"]


def test_agregadas(carregar):
    lista = ler_lista_secoes(carregar("rr-cs-min.json"), "rr")
    por_chave = {s.id.chave: s for s in lista.secoes}
    principal = por_chave["rr-03123-0007-0012"]
    agregada = por_chave["rr-03123-0007-0120"]
    assert principal.agregadas == ("0120",)
    assert principal.tem_urna
    assert agregada.agregada_a == "0012"
    assert not agregada.tem_urna
    assert not agregada.publicada


def test_data_hora_publicacao(carregar):
    lista = ler_lista_secoes(carregar("rr-cs-min.json"), "rr")
    assert lista.publicadas[1].data_hora == "04/10/2026 21:09:55"
    assert lista.pendentes[0].data_hora is None


def test_rejeita_uf_divergente(carregar):
    with pytest.raises(CodigoInvalido):
        ler_lista_secoes(carregar("rr-cs-min.json"), "sp")


def test_rejeita_codigo_malicioso(carregar):
    doc = carregar("rr-cs-min.json")
    doc["abr"][0]["mu"][0]["zon"][0]["sec"][0]["ns"] = "../../x"
    with pytest.raises(CodigoInvalido):
        ler_lista_secoes(doc, "rr")


def test_rejeita_lista_vazia():
    with pytest.raises(CodigoInvalido):
        ler_lista_secoes({"abr": []}, "rr")
