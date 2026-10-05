import os

import pytest

from tse_coleta.espelho import CaminhoForaDaRaiz, ConflitoDeConteudo, Espelho


def test_grava_e_le(tmp_path):
    e = Espelho(tmp_path)
    assert e.gravar_imutavel("a/b/c.dat", b"123") is True
    assert e.ler("a/b/c.dat") == b"123"


def test_idempotente_com_mesmo_conteudo(tmp_path):
    e = Espelho(tmp_path)
    e.gravar_imutavel("x.dat", b"1")
    assert e.gravar_imutavel("x.dat", b"1") is False


def test_nunca_sobrescreve(tmp_path):
    e = Espelho(tmp_path)
    e.gravar_imutavel("x.dat", b"original")
    with pytest.raises(ConflitoDeConteudo):
        e.gravar_imutavel("x.dat", b"outro")
    assert e.ler("x.dat") == b"original"


def test_nao_deixa_part(tmp_path):
    e = Espelho(tmp_path)
    e.gravar_imutavel("d/x.dat", b"1")
    assert [p.name for p in (tmp_path / "d").iterdir()] == ["x.dat"]


def test_falha_na_escrita_nao_deixa_arquivo_final(tmp_path, monkeypatch):
    e = Espelho(tmp_path)

    def explode(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "fsync", explode)
    with pytest.raises(OSError):
        e.gravar_imutavel("d/x.dat", b"1")
    assert list((tmp_path / "d").iterdir()) == []


def test_versionado_dedup_e_preserva_historico(tmp_path):
    e = Espelho(tmp_path)
    r1, g1 = e.gravar_versionado("s/aux.json", b'{"st":"Recebida"}')
    r1b, g1b = e.gravar_versionado("s/aux.json", b'{"st":"Recebida"}')
    r2, g2 = e.gravar_versionado("s/aux.json", b'{"st":"Totalizada"}')
    assert (g1, g1b, g2) == (True, False, True)
    assert r1 == r1b != r2
    assert r1.startswith("s/aux@") and r1.endswith(".json")
    assert e.ler(r1) == b'{"st":"Recebida"}'


@pytest.mark.parametrize("rel", ["../fora.dat", "/etc/passwd", "a/../../fora", ""])
def test_bloqueia_fora_da_raiz(tmp_path, rel):
    with pytest.raises(CaminhoForaDaRaiz):
        Espelho(tmp_path / "raiz").gravar_imutavel(rel, b"x")


def test_bloqueia_symlink_para_fora(tmp_path):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    (raiz / "link").symlink_to(tmp_path)
    with pytest.raises(CaminhoForaDaRaiz):
        Espelho(raiz).gravar_imutavel("link/../../x", b"x")
    with pytest.raises(CaminhoForaDaRaiz):
        Espelho(raiz).gravar_imutavel("link/x", b"x")
