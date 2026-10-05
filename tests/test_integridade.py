import hashlib

import pytest

from tse_coleta.codigos import CodigoInvalido
from tse_coleta.integridade import (
    HashInvalido,
    arquivo_confere_com_vsc,
    codificar_hash_tse,
    decodificar_hash_tse,
    vsc_confere,
)

# Caso real (RR 03085/0008/0001): hash publicado e o texto base64 correspondente
HASH_REAL = "53466b716d4c5a62356d676937517462695a696849483941793735726379396d4a716d73694c32426e6f6b3d"
# Caso real com "/" trocado por "-" (SE 31054/0027/0024)
HASH_COM_HIFEN = "31473042325230576f6670304a564a647a7376396a55713576763249783844693049312d6a7073734a666f3d"


def test_decodifica_hash_real():
    assert len(decodificar_hash_tse(HASH_REAL)) == 32


def test_decodifica_hash_com_hifen_como_barra():
    d = decodificar_hash_tse(HASH_COM_HIFEN)
    assert d.hex() == "d46d01d91d16a1fa7425525dcecbfd8d4ab9befd88c7c0e2d08d7f8e9b2c25fa"


def test_codificar_e_inverso():
    for i in range(200):  # cobre digests cujo base64 tem "/" e "+"
        d = hashlib.sha256(str(i).encode()).digest()
        assert decodificar_hash_tse(codificar_hash_tse(d)) == d


def test_hash_com_tamanho_errado():
    h = codificar_hash_tse(b"x" * 16)
    with pytest.raises(HashInvalido):
        decodificar_hash_tse(h)


def test_hash_nao_hex():
    with pytest.raises(CodigoInvalido):
        decodificar_hash_tse("zz" * 30)


def test_cadeia_vsc_bu():
    bu = b"conteudo do boletim"
    vsc = b"cabecalho" + hashlib.sha512(bu).digest() + b"assinatura"
    h = codificar_hash_tse(hashlib.sha256(vsc).digest())
    assert vsc_confere(vsc, h)
    assert arquivo_confere_com_vsc(bu, vsc)


def test_vsc_adulterado_e_rejeitado():
    vsc = b"pacote original"
    h = codificar_hash_tse(hashlib.sha256(vsc).digest())
    assert not vsc_confere(vsc + b"!", h)


def test_bu_adulterado_e_rejeitado():
    bu = b"boletim"
    vsc = hashlib.sha512(bu).digest()
    assert not arquivo_confere_com_vsc(bu + b"x", vsc)
    assert not arquivo_confere_com_vsc(b"", vsc)
