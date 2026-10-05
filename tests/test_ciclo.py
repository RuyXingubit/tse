from datetime import datetime, timedelta, timezone

import httpx
import pytest

from fabrica import CAM, ServidorFalso, aux, lista, sem_espera, versao
from tse_coleta.ciclo import ConfigCiclo, ListaIndisponivel, executar_ciclo
from tse_coleta.cliente import ClienteTSE
from tse_coleta.codigos import IdSecao
from tse_coleta.manifesto import Diario, Layout, ler_manifesto
from tse_coleta.manifesto import Registro

BRT = timezone(timedelta(hours=-3))
T0 = datetime(2026, 10, 4, 23, 0, 0, tzinfo=BRT)
CFG = ConfigCiclo(ufs=("rr",), trabalhadores=4)

S1 = IdSecao("rr", "03085", "0008", "0001")  # totalizada
S2 = IdSecao("rr", "03085", "0008", "0002")  # recebida
S3 = IdSecao("rr", "03085", "0008", "0003")  # pendente
PUB = {"da": "04/10/2026", "ha": "21:09:53"}


def secs(s3_publicada=False):
    s3 = {"ns": "0003", **PUB} if s3_publicada else {"ns": "0003"}
    return {"03085": {"0008": [
        {"ns": "0001", **PUB},
        {"ns": "0002", "nsa": ["0120"], **PUB},
        s3,
        {"ns": "0120", "nsp": "0002"},
    ]}}


def rotas(s2_status="Recebida", s3_publicada=False):
    e1, a1 = versao(S1, b"BU1")
    e2, a2 = versao(S2, b"BU2", "Recebido" if s2_status == "Recebida" else "Totalizado")
    r = {
        CAM.lista_secoes("rr"): lista("rr", secs(s3_publicada)),
        CAM.aux_secao(S1): aux("Totalizada", e1), **a1,
        CAM.aux_secao(S2): aux(s2_status, e2), **a2,
    }
    if s3_publicada:
        e3, a3 = versao(S3, b"BU3")
        r.update({CAM.aux_secao(S3): aux("Totalizada", e3), **a3})
    return r


async def rodar(tmp_path, serv, quando, cfg=CFG):
    async with ClienteTSE("https://t.test/oficial/", transport=httpx.MockTransport(serv), dormir=sem_espera) as c:
        return await executar_ciclo(c, Layout(tmp_path), CAM, cfg, agora=lambda: quando)


def manifesto(res):
    return ler_manifesto(res.snapshot / "manifesto.jsonl.gz")


async def test_primeiro_ciclo(tmp_path):
    res = await rodar(tmp_path, ServidorFalso(rotas()), T0)
    assert res.mudou and res.snapshot.name == "2026-10-04T23-00-00"
    m = manifesto(res)
    assert len(m) == 4
    assert m[S1.chave].completa and m[S1.chave].status_tse == "Totalizada"
    assert m[S2.chave].completa and m[S2.chave].status_tse == "Recebida"
    assert not m[S3.chave].publicada
    assert not m["rr-03085-0008-0120"].tem_urna
    r = res.resumo
    assert (r["urnas"], r["publicadas"], r["pendentes"], r["completas"], r["agregadas"]) == (3, 2, 1, 2, 1)
    assert not res.terminado
    lay = Layout(tmp_path)
    assert lay.estado_atual.is_file() and not lay.diario.exists()
    assert (res.snapshot / "listas" / "rr.json").is_file()


async def test_sem_mudanca_nao_grava_snapshot_nem_reconsulta(tmp_path):
    await rodar(tmp_path, ServidorFalso(rotas()), T0)
    serv = ServidorFalso(rotas())
    res = await rodar(tmp_path, serv, T0 + timedelta(minutes=10))
    assert not res.mudou and res.snapshot is None
    assert serv.pedidos == [CAM.lista_secoes("rr")]


async def test_recebida_e_reverificada_apos_intervalo_e_vira_totalizada(tmp_path):
    await rodar(tmp_path, ServidorFalso(rotas()), T0)
    serv = ServidorFalso(rotas(s2_status="Totalizada"))
    res = await rodar(tmp_path, serv, T0 + timedelta(minutes=31))
    assert CAM.aux_secao(S2) in serv.pedidos
    assert CAM.aux_secao(S1) not in serv.pedidos  # totalizada não é reconsultada
    assert res.mudou and manifesto(res)[S2.chave].status_tse == "Totalizada"


async def test_reverificacao_sem_mudanca_atualiza_estado_mas_nao_snapshot(tmp_path):
    await rodar(tmp_path, ServidorFalso(rotas()), T0)
    res = await rodar(tmp_path, ServidorFalso(rotas()), T0 + timedelta(minutes=31))
    assert not res.mudou
    # próximo ciclo 10 min depois NÃO reconsulta (o carimbo ficou no estado de trabalho)
    serv = ServidorFalso(rotas())
    await rodar(tmp_path, serv, T0 + timedelta(minutes=41))
    assert serv.pedidos == [CAM.lista_secoes("rr")]


async def test_pendente_publicada_depois_e_coletada(tmp_path):
    await rodar(tmp_path, ServidorFalso(rotas()), T0)
    res = await rodar(tmp_path, ServidorFalso(rotas(s3_publicada=True)), T0 + timedelta(minutes=10))
    assert res.mudou and manifesto(res)[S3.chave].completa


async def test_terminado_quando_tudo_final(tmp_path):
    res = await rodar(tmp_path, ServidorFalso(rotas("Totalizada", s3_publicada=True)), T0)
    assert res.terminado and res.resumo["finais"] == 3


async def test_lista_indisponivel_aborta_sem_snapshot(tmp_path):
    with pytest.raises(ListaIndisponivel):
        await rodar(tmp_path, ServidorFalso({}), T0)
    assert not any(Layout(tmp_path).snapshots.iterdir())


async def test_retoma_pelo_diario(tmp_path):
    lay = Layout(tmp_path)
    # Simula um ciclo que caiu depois de coletar S1 (arquivos no disco + linha no diário)
    serv = ServidorFalso(rotas())
    await rodar(tmp_path / "aux", serv, T0)  # só para gerar arquivos válidos
    import shutil
    shutil.copytree(tmp_path / "aux" / "espelho", lay.espelho)
    d = Diario(lay.diario)
    d.anotar(Registro(chave=S1.chave, uf="rr", municipio="03085", zona="0008", secao="0001", tem_urna=True,
                      publicada=True, data_hora_lista="04/10/2026 21:09:53", status_tse="Totalizada",
                      completa=True, verificado_em=T0.isoformat()))
    d.fechar()
    serv = ServidorFalso(rotas())
    res = await rodar(tmp_path, serv, T0 + timedelta(minutes=1))
    assert CAM.aux_secao(S1) not in serv.pedidos
    assert CAM.aux_secao(S2) in serv.pedidos
    assert manifesto(res)[S1.chave].completa
    assert not lay.diario.exists()


async def test_falha_transitoria_nao_rebaixa_secao_completa(tmp_path):
    await rodar(tmp_path, ServidorFalso(rotas()), T0)
    serv = ServidorFalso(rotas(), falhas={CAM.aux_secao(S2): 500})
    cfg = ConfigCiclo(ufs=("rr",), trabalhadores=2)
    async with ClienteTSE("https://t.test/oficial/", transport=httpx.MockTransport(serv),
                          dormir=sem_espera, max_tentativas=2) as c:
        res = await executar_ciclo(c, Layout(tmp_path), CAM, cfg, agora=lambda: T0 + timedelta(minutes=31))
    lay = Layout(tmp_path)
    from tse_coleta.manifesto import ler_manifesto as lm
    estado = lm(lay.estado_atual)
    assert estado[S2.chave].completa
    assert "reverificação falhou" in estado[S2.chave].motivo


async def test_varredura_completa_reconsulta_tudo(tmp_path):
    await rodar(tmp_path, ServidorFalso(rotas()), T0)
    serv = ServidorFalso(rotas())
    cfg = ConfigCiclo(ufs=("rr",), varredura_completa=True)
    await rodar(tmp_path, serv, T0 + timedelta(minutes=5), cfg)
    assert CAM.aux_secao(S1) in serv.pedidos and CAM.aux_secao(S2) in serv.pedidos
    assert not any(p.endswith(".dat") or p.endswith(".vsc") for p in serv.pedidos)  # arquivos já validados


async def test_data_hora_alterada_na_lista_forca_recoleta(tmp_path):
    await rodar(tmp_path, ServidorFalso(rotas()), T0)
    r = rotas()
    novo = secs()
    novo["03085"]["0008"][0]["ha"] = "23:59:00"
    r[CAM.lista_secoes("rr")] = lista("rr", novo)
    serv = ServidorFalso(r)
    await rodar(tmp_path, serv, T0 + timedelta(minutes=5))
    assert CAM.aux_secao(S1) in serv.pedidos
