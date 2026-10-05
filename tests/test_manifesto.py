import gzip
import os

import pytest

from tse_coleta.manifesto import (
    Diario,
    Layout,
    Registro,
    carregar_estado,
    gravar_estado_atual,
    gravar_snapshot,
    ler_manifesto,
    mudou,
    serializar_manifesto,
    ultimo_snapshot_com_manifesto,
)


def reg(chave="rr-03085-0008-0001", **kw):
    uf, mun, zona, sec = chave.split("-")
    base = dict(chave=chave, uf=uf, municipio=mun, zona=zona, secao=sec, tem_urna=True)
    base.update(kw)
    return Registro(**base)


def test_final():
    assert not reg(publicada=True, completa=True, status_tse="Recebida").final
    assert reg(publicada=True, completa=True, status_tse="Totalizada").final
    assert not reg(publicada=True, completa=False, status_tse="Totalizada").final
    assert reg(tem_urna=False).final  # agregada


def test_roundtrip_json():
    r = reg(publicada=True, hashes=["ab" * 20], verificado_em="2026-10-04T23:00:00-03:00")
    assert Registro.de_json(r.para_json()) == r


def test_manifesto_deterministico():
    regs = {r.chave: r for r in [reg("rr-03085-0008-0002"), reg("rr-03085-0008-0001")]}
    a = serializar_manifesto(regs)
    b = serializar_manifesto(dict(reversed(list(regs.items()))))
    assert a == b
    linhas = gzip.decompress(a).decode().splitlines()
    assert '"rr-03085-0008-0001"' in linhas[0]


def test_mudou_ignora_carimbo_de_verificacao():
    a = {"k": reg("rr-03085-0008-0001", verificado_em="2026-10-04T23:00:00-03:00")}
    b = {"k": reg("rr-03085-0008-0001", verificado_em="2026-10-04T23:30:00-03:00")}
    assert not mudou(a, b)
    c = {"k": reg("rr-03085-0008-0001", status_tse="Totalizada")}
    assert mudou(a, c)
    assert mudou(None, a)
    assert mudou(a, {})


def test_snapshot_somente_leitura_e_checksums(tmp_path):
    lay = Layout(tmp_path)
    r = reg()
    regs = {r.chave: r}
    p = gravar_snapshot(lay, "2026-10-04T23-00-00", {"rr": b"{}"}, regs, {"x": 1})
    assert ler_manifesto(p / "manifesto.jsonl.gz") == regs
    sums = (p / "SHA256SUMS").read_text()
    assert "listas/rr.json" in sums and "manifesto.jsonl.gz" in sums and "resumo.json" in sums
    assert not os.access(p / "manifesto.jsonl.gz", os.W_OK)
    with pytest.raises(PermissionError):
        (p / "novo").write_text("x")


def test_snapshot_nunca_reutiliza_pasta(tmp_path):
    lay = Layout(tmp_path)
    p1 = gravar_snapshot(lay, "N", {}, {}, {"a": 1})
    p2 = gravar_snapshot(lay, "N", {}, {}, {"a": 2})
    assert p1.name == "N" and p2.name == "N-2"
    assert '"a": 1' in (p1 / "resumo.json").read_text()


def test_ultimo_snapshot_ignora_pastas_sem_manifesto(tmp_path):
    lay = Layout(tmp_path)
    gravar_snapshot(lay, "2026-10-04T23-00-00", {}, {"k": reg()}, {})
    (lay.snapshots / "2026-10-04T23-01-51").mkdir()  # bootstrap manual, sem manifesto
    assert ultimo_snapshot_com_manifesto(lay).name == "2026-10-04T23-00-00"


def test_estado_de_trabalho_tem_prioridade(tmp_path):
    lay = Layout(tmp_path)
    k = reg().chave
    gravar_snapshot(lay, "S1", {}, {k: reg(status_tse="Recebida")}, {})
    gravar_estado_atual(lay, {k: reg(status_tse="Recebida", verificado_em="2026-10-04T23:30:00-03:00")})
    trabalho, historico = carregar_estado(lay)
    assert trabalho[k].verificado_em == "2026-10-04T23:30:00-03:00"
    assert historico[k].verificado_em is None


def test_diario_tolera_linha_truncada(tmp_path):
    d = Diario(tmp_path / "d.jsonl")
    d.anotar(reg("rr-03085-0008-0001"))
    d.anotar(reg("rr-03085-0008-0002"))
    d.fechar()
    with open(tmp_path / "d.jsonl", "a") as f:
        f.write('{"chave": "rr-030')  # queda no meio da escrita
    assert set(Diario(tmp_path / "d.jsonl").carregar()) == {"rr-03085-0008-0001", "rr-03085-0008-0002"}


def test_diario_encerrar_apaga(tmp_path):
    d = Diario(tmp_path / "d.jsonl")
    d.anotar(reg())
    d.encerrar()
    assert not (tmp_path / "d.jsonl").exists()
