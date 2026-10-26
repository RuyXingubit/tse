import pytest

from tse_coleta.decodificador_bu import (
    ErroDecodificacaoBU,
    decodificar_ber,
    decodificar_bu,
)


def _tlv(classe: int, construido: bool, tag: int, conteudo: bytes) -> bytes:
    b0 = ((classe & 0x03) << 6) | (0x20 if construido else 0x00) | (tag & 0x1F)
    n = len(conteudo)
    if n < 128:
        tam = bytes([n])
    else:
        nb = (n.bit_length() + 7) // 8
        tam = bytes([0x80 | nb]) + n.to_bytes(nb, "big")
    return bytes([b0]) + tam + conteudo


def _int_tlv(n: int, classe: int = 0, tag: int = 2) -> bytes:
    if n == 0:
        b = b"\x00"
    else:
        nb = (n.bit_length() + 7) // 8
        b = n.to_bytes(nb, "big")
    return _tlv(classe, False, tag, b)


def _str_tlv(s: str, classe: int = 0, tag: int = 27) -> bytes:
    return _tlv(classe, False, tag, s.encode("latin-1"))


def _seq(*itens: bytes, classe: int = 0, tag: int = 16) -> bytes:
    return _tlv(classe, True, tag, b"".join(itens))


def construir_bu_sintetico(
    *,
    pleito: int = 3221,
    municipio: int = 4685,
    zona: int = 33,
    local: int = 1015,
    secao: int = 165,
    urna: int = 2394579,
    abertura: str = "20261025T080001",
    encerramento: str = "20261025T170512",
    aptos: int = 300,
    comparecimento: int = 240,
    biometria: int = 220,
    liberados_codigo: int = 20,
    votos_13: int = 110,
    votos_22: int = 120,
    brancos: int = 4,
    nulos: int = 6,
    eleicao: int = 6258,
) -> bytes:
    cab = _seq(_str_tlv("20261025T170600"), _int_tlv(pleito, classe=2, tag=2))
    fase = _tlv(0, False, 10, b"\x02")
    bloco_urna = _seq(
        _tlv(0, False, 10, b"\x01"),
        _str_tlv("10.23.0.0 - Teste"),
        _seq(
            _tlv(2, True, 0, _seq(_int_tlv(municipio), _int_tlv(zona))),
            _seq(_int_tlv(urna)),
        ),
    )
    id_sec = _seq(_seq(_int_tlv(municipio), _int_tlv(zona)), _int_tlv(local), _int_tlv(secao))
    emissao = _str_tlv("20261025T170600")
    dados_sa = _seq(_str_tlv(abertura), _str_tlv(encerramento), classe=2, tag=0)
    comp_tlv = _int_tlv(comparecimento)
    bio_tlv = _seq(_int_tlv(0), _int_tlv(biometria), _int_tlv(liberados_codigo), classe=2, tag=1)

    v13 = _seq(
        _int_tlv(1, classe=2, tag=1),
        _int_tlv(votos_13, classe=2, tag=2),
        _seq(_int_tlv(13), _int_tlv(13), classe=2, tag=3),
    )
    v22 = _seq(
        _int_tlv(1, classe=2, tag=1),
        _int_tlv(votos_22, classe=2, tag=2),
        _seq(_int_tlv(22), _int_tlv(22), classe=2, tag=3),
    )
    vb = _seq(_int_tlv(2, classe=2, tag=1), _int_tlv(brancos, classe=2, tag=2))
    vn = _seq(_int_tlv(3, classe=2, tag=1), _int_tlv(nulos, classe=2, tag=2))

    tot_cargo = _seq(_int_tlv(1, classe=2, tag=1), _int_tlv(1), _seq(v13, v22, vb, vn))
    res_vot = _seq(_int_tlv(1), _int_tlv(comparecimento), _seq(tot_cargo))
    ele_seq = _seq(
        _int_tlv(eleicao),
        _int_tlv(aptos),
        _int_tlv(aptos),
        _int_tlv(0),
        _seq(res_vot),
    )
    interno = _seq(
        cab,
        fase,
        bloco_urna,
        id_sec,
        emissao,
        dados_sa,
        comp_tlv,
        bio_tlv,
        _seq(ele_seq),
    )
    return _seq(cab, fase, _tlv(0, False, 4, interno))


def test_decodificar_bu_sintetico_completo():
    bruto = construir_bu_sintetico()
    bu = decodificar_bu(bruto)
    assert bu.pleito == 3221
    assert bu.fase == 2
    assert bu.municipio == 4685
    assert bu.zona == 33
    assert bu.local == 1015
    assert bu.secao == 165
    assert bu.numero_interno_urna == 2394579
    assert bu.abertura == "20261025T080001"
    assert bu.encerramento == "20261025T170512"
    assert bu.comparecimento_urna == 240
    assert bu.habilitados_biometria == 220
    assert bu.liberados_codigo == 20
    pres = bu.cargos[1]
    assert pres.eleicao == 6258
    assert pres.aptos == 300
    assert pres.comparecimento == 240
    assert pres.nominais == {13: 110, 22: 120}
    assert pres.brancos == 4
    assert pres.nulos == 6
    assert pres.total == 240


def test_decodificar_bu_rejeita_dados_invalidos():
    with pytest.raises(ErroDecodificacaoBU):
        decodificar_bu(b"")
    with pytest.raises(ErroDecodificacaoBU):
        decodificar_bu(b"\x30\x80\x00\x00")
    with pytest.raises(ErroDecodificacaoBU):
        decodificar_ber(b"\x30\x10\x01")
