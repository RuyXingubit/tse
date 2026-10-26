import gzip
import hashlib
import json

import httpx

from test_analisador_log import construir_log_jez
from test_decodificador_bu import construir_bu_sintetico
from tse_coleta.auditoria_uf import (
    consolidar_analise_uf,
    enriquecer_logs_mesarios_secoes_criticas,
    executar_auditoria_uf,
    exportar_csv_prioridade_fiscais,
)
from tse_coleta.cliente import ClienteTSE
from tse_coleta.integridade import codificar_hash_tse


def _pacote_secao(pleito: int, uf: str, mun: str, zona: str, secao: str, bu_bytes: bytes, log_bytes: bytes):
    vsc = b"VSC-HEADER-" + hashlib.sha512(bu_bytes).digest() + b"-" + hashlib.sha512(log_bytes).digest()
    hash_hex = codificar_hash_tse(hashlib.sha256(vsc).digest())
    pref = f"o{str(pleito).zfill(5)}{uf}{mun}{zona}{secao}"
    aux = {
        "dg": "25/10/2026",
        "hg": "20:00:00",
        "st": "Totalizada",
        "hashes": [
            {
                "hash": hash_hex,
                "dr": "25/10/2026",
                "hr": "18:00:00",
                "st": "Totalizado",
                "arq": [
                    {"nm": f"{pref}-vota.vsc", "tp": "vota"},
                    {"nm": f"{pref}-bu.dat", "tp": "bu"},
                    {"nm": f"{pref}-log.jez", "tp": "log"},
                ],
            }
        ],
    }
    return hash_hex, vsc, aux


async def test_executar_auditoria_uf_streaming_e_detecta_anomalias(tmp_path):
    uf = "pa"
    mun = "04685"
    zona = "0033"

    # Criamos 4 salas na mesma escola (local 1015):
    # - 0001, 0002, 0003: normais (~80% -> ~80%, Cand 22 ~50%)
    # - 0004: anomalia! Salta de 80% no 1T para 100% no 2T, Cand 13 perde votos absolutos e Cand 22 vai a 95%
    rotas: dict[str, bytes] = {}

    sec_list_1t = []
    sec_list_2t = []
    manifesto_1t = []

    config_secoes = [
        ("0001", 300, 240, 300, 20, 115, 115, 120, 120),
        ("0002", 300, 240, 240, 18, 118, 112, 120, 120),
        ("0003", 300, 240, 238, 15, 116, 114, 119, 119),
        ("0004", 300, 240, 300, 120, 120, 100, 20, 280),  # 0004: 80%->100%, 13 cai de 120->20, 22 sobe 100->280
    ]
    # Ajuste: em 0001 deixamos 240 no 2T para ser normal, e em 0004 deixamos 300 (100%)
    config_secoes[0] = ("0001", 300, 240, 240, 20, 115, 115, 120, 120)

    for sec, aptos, c1, c2, sem_bio2, v13_1, v22_1, v13_2, v22_2 in config_secoes:
        bu1 = construir_bu_sintetico(
            pleito=3220,
            municipio=int(mun),
            zona=int(zona),
            local=1015,
            secao=int(sec),
            aptos=aptos,
            comparecimento=c1,
            biometria=c1 - 15,
            liberados_codigo=15,
            votos_13=v13_1,
            votos_22=v22_1,
            brancos=5,
            nulos=5,
            eleicao=6257,
        )
        bu2 = construir_bu_sintetico(
            pleito=3221,
            municipio=int(mun),
            zona=int(zona),
            local=1015,
            secao=int(sec),
            aptos=aptos,
            comparecimento=c2,
            biometria=c2 - sem_bio2,
            liberados_codigo=sem_bio2,
            votos_13=v13_2,
            votos_22=v22_2,
            brancos=0,
            nulos=0,
            eleicao=6258,
        )
        linhas_log = [
            f"04/10/2026 10:00:{i % 60:02d}\tINFO\t02394579\tVOTA\tO voto do eleitor foi computado\tX"
            for i in range(c1)
        ] + [
            f"25/10/2026 {'17:05' if (sec == '0004' and i >= c2 - 25) else '10:00'}:{i % 60:02d}\tINFO\t02394579\tVOTA\tO voto do eleitor foi computado\tY"
            for i in range(c2)
        ]
        log_jez = construir_log_jez(linhas_log)

        h1, vsc1, aux1 = _pacote_secao(3220, uf, mun, zona, sec, bu1, log_jez)
        h2, vsc2, aux2 = _pacote_secao(3221, uf, mun, zona, sec, bu2, log_jez)

        p1 = f"ele2026/arquivo-urna/3220/dados/{uf}/{mun}/{zona}/{sec}"
        pref1 = f"o03220{uf}{mun}{zona}{sec}"
        rotas[f"{p1}/p003220-{uf}-m{mun}-z{zona}-s{sec}-aux.json"] = json.dumps(aux1).encode()
        rotas[f"{p1}/{h1}/{pref1}-vota.vsc"] = vsc1
        rotas[f"{p1}/{h1}/{pref1}-bu.dat"] = bu1
        rotas[f"{p1}/{h1}/{pref1}-log.jez"] = log_jez

        p2 = f"ele2026/arquivo-urna/3221/dados/{uf}/{mun}/{zona}/{sec}"
        pref2 = f"o03221{uf}{mun}{zona}{sec}"
        rotas[f"{p2}/p003221-{uf}-m{mun}-z{zona}-s{sec}-aux.json"] = json.dumps(aux2).encode()
        rotas[f"{p2}/{h2}/{pref2}-vota.vsc"] = vsc2
        rotas[f"{p2}/{h2}/{pref2}-bu.dat"] = bu2
        rotas[f"{p2}/{h2}/{pref2}-log.jez"] = log_jez

        sec_list_1t.append({"ns": sec, "da": "04/10/2026", "ha": "18:00:00"})
        sec_list_2t.append({"ns": sec, "da": "25/10/2026", "ha": "18:00:00"})
        manifesto_1t.append(
            {
                "chave": f"{uf}-{mun}-{zona}-{sec}",
                "uf": uf,
                "tem_urna": True,
                "hashes": [h1],
                "data_hora_lista": "04/10/2026 18:00:00",
                "status_tse": "Totalizada",
            }
        )

    # Grava snapshot 1T simulado em tmp_path
    snap_dir = tmp_path / "snapshots" / "2026-10-05T11-48-08"
    snap_dir.mkdir(parents=True)
    with gzip.open(snap_dir / "manifesto.jsonl.gz", "wt", encoding="utf-8") as f:
        for m in manifesto_1t:
            f.write(json.dumps(m) + "\n")

    cs_base = lambda pl, secs: {
        "dg": "25/10/2026",
        "hg": "20:00:00",
        "abr": [{"cd": uf, "mu": [{"cd": mun, "zon": [{"cd": zona, "sec": secs}]}]}],
    }
    rotas[f"ele2026/arquivo-urna/3220/config/{uf}/{uf}-p003220-cs.json"] = json.dumps(
        cs_base(3220, sec_list_1t)
    ).encode()
    rotas[f"ele2026/arquivo-urna/3221/config/{uf}/{uf}-p003221-cs.json"] = json.dumps(
        cs_base(3221, sec_list_2t)
    ).encode()
    rotas["ele2026/6258/config/mun-e006258-cm.json"] = json.dumps(
        {"abr": [{"cd": uf.upper(), "mu": [{"cd": mun, "nm": "BELÉM"}]}]}
    ).encode()

    def handler(req: httpx.Request) -> httpx.Response:
        rel = req.url.path.lstrip("/")
        if rel in rotas:
            return httpx.Response(200, content=rotas[rel])
        return httpx.Response(404)

    async with ClienteTSE(
        "https://exemplo.test/",
        transport=httpx.MockTransport(handler),
        max_req_por_s=None,
    ) as c:
        arq_gz, arq_an = await executar_auditoria_uf(c, tmp_path, uf)

    assert arq_gz.is_file() and arq_an.is_file()
    # Garante que nenhum arquivo bruto .dat/.vsc/.jez foi gravado em disco
    arquivos_gerados = [p.name for p in (tmp_path / "auditoria" / uf).rglob("*") if p.is_file()]
    assert not any(n.endswith((".dat", ".vsc", ".jez")) for n in arquivos_gerados)

    analise = json.loads(arq_an.read_text(encoding="utf-8"))
    assert analise["totais"]["urnas_completas_ambos_turnos"] == 4
    assert analise["totais"]["votos_apos_17h_2t"] == 25
    assert analise["totais"]["hashes_1t_alterados_pos_snapshot"] == 0

    cont = analise["anomalias"]["contagens"]
    assert cont["saltos_comparecimento"] >= 1
    assert cont["comparecimento_100_ou_acima"] >= 1
    assert cont["perda_liquida_votos"] >= 1
    assert cont["alta_sem_biometria"] >= 1
    assert cont["outliers_mesma_escola"] >= 1
    assert analise["anomalias"]["dossie_secoes_criticas"][0]["chave"] == f"{uf}-{mun}-{zona}-0004"
    assert analise["subida_comparecimento"]["total_secoes_subiram"] == 1
    assert "janela_manha_e_mesarios" in analise
    assert "prioridade_fiscais" in analise
    assert "detalhe_aptos_alterados" in analise

    csv_out = exportar_csv_prioridade_fiscais(
        analise["prioridade_fiscais"]["lista_ordenada_por_tamanho"],
        tmp_path / "prioridade_fiscais_pa.csv",
    )
    assert csv_out.is_file()
    assert "BELÉM,0033,0004" in csv_out.read_text(encoding="utf-8")
