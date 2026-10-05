import pytest

from tse_coleta.codigos import Caminhos, CodigoInvalido, IdSecao, validar

HASH = "53466b716d4c5a62356d676937517462695a696849483941793735726379396d4a716d73694c32426e6f6b3d"


@pytest.fixture
def cam():
    return Caminhos(ciclo="ele2026", pleito="3220")


@pytest.fixture
def sec():
    return IdSecao("rr", "03085", "0008", "0001")


def test_lista_secoes(cam):
    assert cam.lista_secoes("rr") == "ele2026/arquivo-urna/3220/config/rr/rr-p003220-cs.json"


def test_aux_secao(cam, sec):
    assert cam.aux_secao(sec) == (
        "ele2026/arquivo-urna/3220/dados/rr/03085/0008/0001/"
        "p003220-rr-m03085-z0008-s0001-aux.json"
    )


def test_arquivo_urna(cam, sec):
    assert cam.arquivo_urna(sec, HASH, "o03220rr0308500080001-bu.dat") == (
        f"ele2026/arquivo-urna/3220/dados/rr/03085/0008/0001/{HASH}/o03220rr0308500080001-bu.dat"
    )


def test_agregados(cam):
    assert cam.agregado("6257", "1", "br") == "ele2026/6257/dados/br/br-c0001-e006257-u.json"
    assert cam.agregado("6259", "3", "sp") == "ele2026/6259/dados/sp/sp-c0003-e006259-u.json"
    assert (
        cam.agregado("6261", "25", "pe", "30015")
        == "ele2026/6261/dados/pe/pe30015-c0025-e006261-u.json"
    )
    assert cam.config_municipios("6257") == "ele2026/6257/config/mun-e006257-cm.json"


@pytest.mark.parametrize(
    "tipo,valor",
    [
        ("uf", "../"),
        ("uf", "RR"),
        ("uf", "rrr"),
        ("municipio", "0308"),
        ("municipio", "03085/.."),
        ("zona", "8"),
        ("secao", "0001\n"),
        ("hash_hex", "zz"),
        ("hash_hex", "../" * 20),
        ("ciclo", "ele2026/../x"),
    ],
)
def test_rejeita_codigos_invalidos(tipo, valor):
    with pytest.raises(CodigoInvalido):
        validar(tipo, valor)


def test_idsecao_valida_no_construtor():
    with pytest.raises(CodigoInvalido):
        IdSecao("rr", "../..", "0008", "0001")


def test_rejeita_nome_de_arquivo_com_traversal(cam, sec):
    with pytest.raises(CodigoInvalido):
        cam.arquivo_urna(sec, HASH, "../../../etc/passwd")


def test_rejeita_nome_de_arquivo_de_outra_secao(cam, sec):
    with pytest.raises(CodigoInvalido):
        cam.arquivo_urna(sec, HASH, "o03220rr0308500080002-bu.dat")


def test_rejeita_hash_invalido(cam, sec):
    with pytest.raises(CodigoInvalido):
        cam.arquivo_urna(sec, "..", "o03220rr0308500080001-bu.dat")
