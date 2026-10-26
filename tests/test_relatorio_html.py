import xml.etree.ElementTree as ET

from tse_coleta.auditoria_uf import consolidar_analise_uf
from tse_coleta.relatorio_html import gerar_relatorio_html


def test_gerar_relatorio_html_xhtml_valido_com_print_pdf(tmp_path):
    registros = [
        {
            "chave": "pa-04685-0033-0001",
            "uf": "pa",
            "municipio": "04685",
            "nome_municipio": "BELÉM",
            "zona": "0033",
            "secao": "0001",
            "local": 1015,
            "completa_1t": True,
            "completa_2t": True,
            "status_1t": "Totalizada",
            "status_2t": "Totalizada",
            "erros": [],
            "hash_1t_snapshot": "aa" * 32,
            "hash_1t_atual": "aa" * 32,
            "hash_1t_mudou_pos_snapshot": False,
            "hash_2t": "bb" * 32,
            "urna_1t": 123,
            "urna_2t": 123,
            "trocou_urna_entre_turnos": False,
            "abertura_1t": "20261004T080001",
            "encerramento_1t": "20261004T170200",
            "abertura_2t": "20261025T080001",
            "encerramento_2t": "20261025T173000",
            "aptos_1t": 300,
            "aptos_2t": 300,
            "delta_aptos": 0,
            "comp_1t": 240,
            "comp_2t": 300,
            "pct_comp_1t": 80.0,
            "pct_comp_2t": 100.0,
            "delta_comp_abs": 60,
            "delta_comp_pp": 20.0,
            "bio_1t": 230,
            "sem_bio_1t": 10,
            "pct_sem_bio_1t": 4.17,
            "bio_2t": 180,
            "sem_bio_2t": 120,
            "pct_sem_bio_2t": 40.0,
            "delta_sem_bio_pp": 35.83,
            "pres_1t": {"aptos": 300, "comparecimento": 240, "nominais": {"13": 140, "22": 90}, "brancos": 5, "nulos": 5, "total": 240},
            "pres_2t": {"aptos": 300, "comparecimento": 300, "nominais": {"13": 110, "22": 190}, "brancos": 0, "nulos": 0, "total": 300},
            "gov_1t": None,
            "gov_2t": None,
            "log_1t": {
                "presente": True,
                "votos_computados": 240,
                "votos_ate_17h": 235,
                "votos_apos_17h": 5,
                "votos_por_hora": {"08": 30, "17": 5},
                "votos_apos_17h_por_minuto": {"17:01": 5},
                "intervalo_min_s": 14.0,
                "intervalo_mediana_s": 52.0,
                "votos_intervalo_menor_10s": 0,
                "votos_cabine_menor_5s": 0,
                "reinicios_durante_votacao": 0,
                "regressoes_relogio": 0,
                "trocou_urna_no_dia": False,
            },
            "log_2t": {
                "presente": True,
                "votos_computados": 300,
                "votos_ate_17h": 260,
                "votos_apos_17h": 40,
                "votos_por_hora": {"08": 40, "17": 40},
                "votos_apos_17h_por_minuto": {"17:10": 40},
                "intervalo_min_s": 6.0,
                "intervalo_mediana_s": 22.0,
                "votos_intervalo_menor_10s": 4,
                "votos_cabine_menor_5s": 2,
                "reinicios_durante_votacao": 1,
                "regressoes_relogio": 0,
                "trocou_urna_no_dia": False,
            },
        }
    ]
    analise = consolidar_analise_uf(uf="pa", registros=registros)
    out = gerar_relatorio_html(analise, tmp_path / "relatorio_pa_1t_2t.html")
    texto = out.read_text(encoding="utf-8")

    assert "window.print()" in texto
    assert "@media print" in texto
    assert "BELÉM" in texto
    assert "<svg" in texto
    assert "Ruy França" in texto
    assert "print-running-footer" in texto
    assert "author-banner" in texto
    assert "report-footer" in texto
    # Confere que o documento é também XML/XHTML bem-formado (após remover a linha DOCTYPE)
    xml_body = "\n".join(texto.splitlines()[1:])
    root = ET.fromstring(xml_body)
    ns = {"xhtml": "http://www.w3.org/1999/xhtml"}
    svgs = root.findall(".//xhtml:svg", ns)
    assert len(svgs) == 7
    for svg in svgs:
        svg_str = ET.tostring(svg, encoding="unicode")
        assert "Ruy França" in svg_str
        assert "resultados.tse.jus.br" in svg_str
