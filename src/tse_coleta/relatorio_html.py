"""Gerador de relatório visual em HTML5/XHTML poliglota com gráficos SVG vetoriais,
explicações técnicas detalhadas e suporte nativo a impressão / exportação em PDF.
"""

from __future__ import annotations

import html
from pathlib import Path

AUTOR_RELATORIO = "Ruy França"
FONTE_DADOS_CURTA = (
    "Dados Públicos Oficiais do TSE (resultados.tse.jus.br — BU, Log da Urna e VSC — Eleições 2026)"
)
FONTE_DADOS_COMPLETA = (
    "Tribunal Superior Eleitoral (TSE) — Repositório Oficial de Dados Brutos de Urna "
    "(https://resultados.tse.jus.br/oficial/ele2026/) — Pleitos 3220 (1º Turno, 04/10/2026) e "
    "3221 (2º Turno, 25/10/2026): Boletins de Urna (-bu.dat), Logs de Urna (-log.jez) e "
    "Pacotes de Assinatura (-vota.vsc) validados por SHA-256 e SHA-512."
)


def _esc(val: object) -> str:
    return html.escape(str(val), quote=True)


def _rodape_svg(w: int, h: int) -> str:
    """Injeta a assinatura de autoria e fonte dos dados diretamente dentro de cada imagem SVG."""
    texto = f"Autor: {AUTOR_RELATORIO}  |  Fonte dos dados: {FONTE_DADOS_CURTA}"
    return (
        f'<line x1="16" y1="{h - 24}" x2="{w - 16}" y2="{h - 24}" stroke="#e2e8f0" stroke-width="1" />'
        f'<text x="{w / 2:.1f}" y="{h - 9}" text-anchor="middle" font-size="10" font-weight="600" fill="#334155">'
        f"{_esc(texto)}</text>"
    )


def _bloco_grafico(svg: str) -> str:
    """Envolve um gráfico SVG (que já traz a autoria e a fonte embutidas na imagem)."""
    return f'<div class="chart-wrap">{svg}</div>'


def _fmt_int(n: int | float | None) -> str:
    if n is None:
        return "0"
    return f"{int(n):,}".replace(",", ".")


def _fmt_pct(v: float | None, casas: int = 2) -> str:
    if v is None:
        return "0,00%"
    return f"{v:.{casas}f}%".replace(".", ",")


def _svg_scatter_comparecimento(pontos: list[dict]) -> str:
    w, h = 680, 448
    pad_l, pad_r, pad_t, pad_b = 58, 24, 26, 76
    pw = w - pad_l - pad_r
    ph = h - pad_t - pad_b

    def cx(v: float) -> float:
        v_cl = max(40.0, min(100.0, v))
        return pad_l + ((v_cl - 40.0) / 60.0) * pw

    def cy(v: float) -> float:
        v_cl = max(40.0, min(100.0, v))
        return pad_t + ph - ((v_cl - 40.0) / 60.0) * ph

    grades = []
    for g in (40, 50, 60, 70, 80, 90, 100):
        xg = cx(g)
        yg = cy(g)
        grades.append(
            f'<line x1="{xg:.1f}" y1="{pad_t}" x2="{xg:.1f}" y2="{pad_t + ph}" stroke="#e2e8f0" stroke-width="1" />'
        )
        grades.append(
            f'<line x1="{pad_l}" y1="{yg:.1f}" x2="{pad_l + pw}" y2="{yg:.1f}" stroke="#e2e8f0" stroke-width="1" />'
        )
        grades.append(
            f'<text x="{xg:.1f}" y="{pad_t + ph + 18}" text-anchor="middle" font-size="11" fill="#475569">{g}%</text>'
        )
        grades.append(
            f'<text x="{pad_l - 8}" y="{yg + 4:.1f}" text-anchor="end" font-size="11" fill="#475569">{g}%</text>'
        )

    # Linha diagonal 1T == 2T e linha de alerta +10 p.p.
    diag = f'<line x1="{cx(40):.1f}" y1="{cy(40):.1f}" x2="{cx(100):.1f}" y2="{cy(100):.1f}" stroke="#0f172a" stroke-width="1.5" stroke-dasharray="5,4" />'
    diag_mais10 = f'<line x1="{cx(40):.1f}" y1="{cy(50):.1f}" x2="{cx(90):.1f}" y2="{cy(100):.1f}" stroke="#dc2626" stroke-width="1.2" stroke-dasharray="3,3" />'

    normais = []
    alertas = []
    for p in pontos:
        vx, vy = float(p["x"]), float(p["y"])
        x = cx(vx)
        y = cy(vy)
        titulo = _esc(f"{p['m']} ({p['c']}): 1T={p['x']}% -> 2T={p['y']}%")
        if (vy - vx) >= 10.0 or vy >= 99.0:
            alertas.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="#dc2626" fill-opacity="0.88"><title>{titulo}</title></circle>'
            )
        else:
            normais.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#2563eb" fill-opacity="0.38"><title>{titulo}</title></circle>'
            )

    return (
        f'<svg viewBox="0 0 {w} {h}" class="svg-chart" role="img" aria-label="Dispersão de comparecimento 1º vs 2º turno">'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff" rx="8" />'
        + "".join(grades)
        + diag
        + diag_mais10
        + "".join(normais)
        + "".join(alertas)
        + f'<text x="{pad_l + pw / 2:.1f}" y="{h - 34}" text-anchor="middle" font-size="12" font-weight="600" fill="#1e293b">Comparecimento no 1º Turno (%)</text>'
        + f'<text x="16" y="{pad_t + ph / 2:.1f}" text-anchor="middle" font-size="12" font-weight="600" fill="#1e293b" transform="rotate(-90 16 {pad_t + ph / 2:.1f})">Comparecimento no 2º Turno (%)</text>'
        + _rodape_svg(w, h)
        + "</svg>"
    )


def _svg_scatter_migracao(pontos: list[dict]) -> str:
    w, h = 680, 448
    pad_l, pad_r, pad_t, pad_b = 58, 24, 26, 76
    pw = w - pad_l - pad_r
    ph = h - pad_t - pad_b

    xs = [float(p["x"]) for p in pontos] or [-50.0, 50.0]
    ys = [float(p["y"]) for p in pontos] or [-50.0, 50.0]
    min_v = min(min(xs), min(ys), -40.0)
    max_v = max(max(xs), max(ys), 80.0)
    span_x = max(10.0, max_v - min_v)

    def cx(v: float) -> float:
        v_cl = max(min_v, min(max_v, v))
        return pad_l + ((v_cl - min_v) / span_x) * pw

    def cy(v: float) -> float:
        v_cl = max(min_v, min(max_v, v))
        return pad_t + ph - ((v_cl - min_v) / span_x) * ph

    x0, y0 = cx(0.0), cy(0.0)
    eixos = (
        f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{pad_l + pw}" y2="{y0:.1f}" stroke="#64748b" stroke-width="1.3" stroke-dasharray="4,3" />'
        f'<line x1="{x0:.1f}" y1="{pad_t}" x2="{x0:.1f}" y2="{pad_t + ph}" stroke="#64748b" stroke-width="1.3" stroke-dasharray="4,3" />'
    )

    grades = []
    passo = max(20, int(span_x // 6 // 10) * 10 or 20)
    ini_g = int(min_v // passo) * passo
    for g in range(ini_g, int(max_v) + 1, passo):
        xg = cx(g)
        yg = cy(g)
        if pad_l <= xg <= pad_l + pw:
            grades.append(
                f'<line x1="{xg:.1f}" y1="{pad_t}" x2="{xg:.1f}" y2="{pad_t + ph}" stroke="#f1f5f9" stroke-width="1" />'
                f'<text x="{xg:.1f}" y="{pad_t + ph + 18}" text-anchor="middle" font-size="11" fill="#475569">{g:+d}</text>'
            )
        if pad_t <= yg <= pad_t + ph:
            grades.append(
                f'<line x1="{pad_l}" y1="{yg:.1f}" x2="{pad_l + pw}" y2="{yg:.1f}" stroke="#f1f5f9" stroke-width="1" />'
                f'<text x="{pad_l - 8}" y="{yg + 4:.1f}" text-anchor="end" font-size="11" fill="#475569">{g:+d}</text>'
            )

    normais = []
    alertas = []
    for p in pontos:
        x = cx(float(p["x"]))
        y = cy(float(p["y"]))
        titulo = _esc(f"{p['m']} ({p['c']}): Δ13={p['x']:+d}, Δ22={p['y']:+d}")
        if p.get("a"):
            alertas.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="#d97706" fill-opacity="0.85"><title>{titulo}</title></circle>'
            )
        else:
            normais.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#0284c7" fill-opacity="0.38"><title>{titulo}</title></circle>'
            )

    return (
        f'<svg viewBox="0 0 {w} {h}" class="svg-chart" role="img" aria-label="Migração de votos 1º para 2º turno">'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff" rx="8" />'
        + "".join(grades)
        + eixos
        + "".join(normais)
        + "".join(alertas)
        + f'<text x="{pad_l + pw / 2:.1f}" y="{h - 34}" text-anchor="middle" font-size="12" font-weight="600" fill="#1e293b">Variação de Votos do Candidato 13 (2ºT − 1ºT)</text>'
        + f'<text x="16" y="{pad_t + ph / 2:.1f}" text-anchor="middle" font-size="12" font-weight="600" fill="#1e293b" transform="rotate(-90 16 {pad_t + ph / 2:.1f})">Variação de Votos do Candidato 22 (2ºT − 1ºT)</text>'
        + _rodape_svg(w, h)
        + "</svg>"
    )


def _svg_scatter_biometria(pontos: list[dict]) -> str:
    w, h = 680, 428
    pad_l, pad_r, pad_t, pad_b = 58, 24, 26, 76
    pw = w - pad_l - pad_r
    ph = h - pad_t - pad_b

    max_x = max([float(p["x"]) for p in pontos] + [40.0])
    max_x = min(100.0, max(40.0, float(int((max_x + 9) // 10) * 10)))

    def cx(v: float) -> float:
        v_cl = max(0.0, min(max_x, v))
        return pad_l + (v_cl / max_x) * pw

    def cy(v: float) -> float:
        v_cl = max(40.0, min(100.0, v))
        return pad_t + ph - ((v_cl - 40.0) / 60.0) * ph

    grades = []
    passo_x = 10 if max_x <= 60 else 20
    for gx in range(0, int(max_x) + 1, passo_x):
        xg = cx(gx)
        grades.append(
            f'<line x1="{xg:.1f}" y1="{pad_t}" x2="{xg:.1f}" y2="{pad_t + ph}" stroke="#e2e8f0" stroke-width="1" />'
            f'<text x="{xg:.1f}" y="{pad_t + ph + 18}" text-anchor="middle" font-size="11" fill="#475569">{gx}%</text>'
        )
    for gy in (40, 50, 60, 70, 80, 90, 100):
        yg = cy(gy)
        grades.append(
            f'<line x1="{pad_l}" y1="{yg:.1f}" x2="{pad_l + pw}" y2="{yg:.1f}" stroke="#e2e8f0" stroke-width="1" />'
            f'<text x="{pad_l - 8}" y="{yg + 4:.1f}" text-anchor="end" font-size="11" fill="#475569">{gy}%</text>'
        )

    normais = []
    alertas = []
    for p in pontos:
        x = cx(float(p["x"]))
        y = cy(float(p["y"]))
        titulo = _esc(
            f"{p['m']} ({p['c']}): Sem biometria={p['x']}%, Comparecimento 2T={p['y']}%"
        )
        if p.get("a"):
            alertas.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="#7c3aed" fill-opacity="0.82"><title>{titulo}</title></circle>'
            )
        else:
            normais.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#64748b" fill-opacity="0.38"><title>{titulo}</title></circle>'
            )

    return (
        f'<svg viewBox="0 0 {w} {h}" class="svg-chart" role="img" aria-label="Sem biometria vs comparecimento">'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff" rx="8" />'
        + "".join(grades)
        + "".join(normais)
        + "".join(alertas)
        + f'<text x="{pad_l + pw / 2:.1f}" y="{h - 34}" text-anchor="middle" font-size="12" font-weight="600" fill="#1e293b">Eleitores Liberados Sem Biometria no 2º Turno (%)</text>'
        + f'<text x="16" y="{pad_t + ph / 2:.1f}" text-anchor="middle" font-size="12" font-weight="600" fill="#1e293b" transform="rotate(-90 16 {pad_t + ph / 2:.1f})">Comparecimento no 2º Turno (%)</text>'
        + _rodape_svg(w, h)
        + "</svg>"
    )


def _svg_barras_duplas(
    rotulos: list[str],
    serie_1t: list[int],
    serie_2t: list[int],
    *,
    titulo_y: str,
    legenda_1: str = "1º Turno (04/10)",
    legenda_2: str = "2º Turno (25/10)",
    cor_1: str = "#2563eb",
    cor_2: str = "#dc2626",
) -> str:
    w, h = 680, 368
    pad_l, pad_r, pad_t, pad_b = 64, 20, 36, 84
    pw = w - pad_l - pad_r
    ph = h - pad_t - pad_b
    n = max(1, len(rotulos))
    max_y = max(serie_1t + serie_2t + [1])

    elementos = [f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff" rx="8" />']
    for i in range(5):
        v = int(round(max_y * i / 4))
        yg = pad_t + ph - (i / 4) * ph
        elementos.append(
            f'<line x1="{pad_l}" y1="{yg:.1f}" x2="{pad_l + pw}" y2="{yg:.1f}" stroke="#e2e8f0" stroke-width="1" />'
            f'<text x="{pad_l - 8}" y="{yg + 4:.1f}" text-anchor="end" font-size="10.5" fill="#475569">{_fmt_int(v)}</text>'
        )

    larg_grupo = pw / n
    larg_barra = max(2.0, min(18.0, larg_grupo * 0.38))
    passo_rotulo = max(1, n // 12)

    for idx, rot in enumerate(rotulos):
        v1 = serie_1t[idx] if idx < len(serie_1t) else 0
        v2 = serie_2t[idx] if idx < len(serie_2t) else 0
        h1 = (v1 / max_y) * ph
        h2 = (v2 / max_y) * ph
        x_centro = pad_l + (idx + 0.5) * larg_grupo
        x1 = x_centro - larg_barra - 1
        x2 = x_centro + 1
        y1 = pad_t + ph - h1
        y2 = pad_t + ph - h2
        elementos.append(
            f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{larg_barra:.1f}" height="{max(0.5, h1):.1f}" fill="{cor_1}" rx="1.5"><title>{_esc(rot)} - {legenda_1}: {_fmt_int(v1)}</title></rect>'
            f'<rect x="{x2:.1f}" y="{y2:.1f}" width="{larg_barra:.1f}" height="{max(0.5, h2):.1f}" fill="{cor_2}" rx="1.5"><title>{_esc(rot)} - {legenda_2}: {_fmt_int(v2)}</title></rect>'
        )
        if idx % passo_rotulo == 0 or idx == n - 1:
            elementos.append(
                f'<text x="{x_centro:.1f}" y="{pad_t + ph + 18}" text-anchor="middle" font-size="10" fill="#334155">{_esc(rot)}</text>'
            )

    # Legenda no topo + rodapé de autoria e fonte
    elementos.append(
        f'<rect x="{pad_l}" y="8" width="12" height="12" fill="{cor_1}" rx="2" />'
        f'<text x="{pad_l + 18}" y="18" font-size="11.5" font-weight="600" fill="#1e293b">{_esc(legenda_1)}</text>'
        f'<rect x="{pad_l + 170}" y="8" width="12" height="12" fill="{cor_2}" rx="2" />'
        f'<text x="{pad_l + 188}" y="18" font-size="11.5" font-weight="600" fill="#1e293b">{_esc(legenda_2)}</text>'
        f'<text x="16" y="{pad_t + ph / 2:.1f}" text-anchor="middle" font-size="11.5" font-weight="600" fill="#1e293b" transform="rotate(-90 16 {pad_t + ph / 2:.1f})">{_esc(titulo_y)}</text>'
        + _rodape_svg(w, h)
    )
    return f'<svg viewBox="0 0 {w} {h}" class="svg-chart" role="img">' + "".join(elementos) + "</svg>"


def _svg_barras_simples(
    rotulos: list[str], valores: list[int], *, titulo_y: str, cor: str = "#0284c7"
) -> str:
    w, h = 680, 338
    pad_l, pad_r, pad_t, pad_b = 64, 20, 24, 80
    pw = w - pad_l - pad_r
    ph = h - pad_t - pad_b
    n = max(1, len(rotulos))
    max_y = max(valores + [1])

    elementos = [f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff" rx="8" />']
    for i in range(5):
        v = int(round(max_y * i / 4))
        yg = pad_t + ph - (i / 4) * ph
        elementos.append(
            f'<line x1="{pad_l}" y1="{yg:.1f}" x2="{pad_l + pw}" y2="{yg:.1f}" stroke="#e2e8f0" stroke-width="1" />'
            f'<text x="{pad_l - 8}" y="{yg + 4:.1f}" text-anchor="end" font-size="10.5" fill="#475569">{_fmt_int(v)}</text>'
        )

    larg_grupo = pw / n
    larg_barra = max(8.0, min(42.0, larg_grupo * 0.62))
    for idx, rot in enumerate(rotulos):
        val = valores[idx]
        hb = (val / max_y) * ph
        xc = pad_l + (idx + 0.5) * larg_grupo
        xb = xc - larg_barra / 2
        yb = pad_t + ph - hb
        elementos.append(
            f'<rect x="{xb:.1f}" y="{yb:.1f}" width="{larg_barra:.1f}" height="{max(0.5, hb):.1f}" fill="{cor}" rx="2"><title>{_esc(rot)}: {_fmt_int(val)}</title></rect>'
            f'<text x="{xc:.1f}" y="{max(pad_t + 10, yb - 5):.1f}" text-anchor="middle" font-size="10" font-weight="600" fill="#1e293b">{_fmt_int(val)}</text>'
            f'<text x="{xc:.1f}" y="{pad_t + ph + 18}" text-anchor="middle" font-size="10.5" fill="#334155">{_esc(rot)}</text>'
        )

    elementos.append(
        f'<text x="16" y="{pad_t + ph / 2:.1f}" text-anchor="middle" font-size="11.5" font-weight="600" fill="#1e293b" transform="rotate(-90 16 {pad_t + ph / 2:.1f})">{_esc(titulo_y)}</text>'
        + _rodape_svg(w, h)
    )
    return f'<svg viewBox="0 0 {w} {h}" class="svg-chart" role="img">' + "".join(elementos) + "</svg>"


def _agrupar_pos_17h_em_blocos_5min(
    curva_1t: dict[str, int], curva_2t: dict[str, int]
) -> tuple[list[str], list[int], list[int]]:
    """Agrupa os minutos após as 17h00 em janelas de 5 minutos (17:00..18:30+) para legibilidade."""
    faixas = [
        ("17:00", 17 * 60, 17 * 60 + 4),
        ("17:05", 17 * 60 + 5, 17 * 60 + 9),
        ("17:10", 17 * 60 + 10, 17 * 60 + 14),
        ("17:15", 17 * 60 + 15, 17 * 60 + 19),
        ("17:20", 17 * 60 + 20, 17 * 60 + 24),
        ("17:25", 17 * 60 + 25, 17 * 60 + 29),
        ("17:30", 17 * 60 + 30, 17 * 60 + 39),
        ("17:40", 17 * 60 + 40, 17 * 60 + 49),
        ("17:50", 17 * 60 + 50, 17 * 60 + 59),
        ("18:00-18:29", 18 * 60, 18 * 60 + 29),
        ("18:30-18:59", 18 * 60 + 30, 18 * 60 + 59),
        ("19:00+", 19 * 60, 23 * 60 + 59),
    ]

    def somar(curva: dict[str, int]) -> list[int]:
        somas = [0] * len(faixas)
        for hm, qtd in curva.items():
            try:
                h, m = int(hm[:2]), int(hm[3:5])
                tot_m = h * 60 + m
            except (ValueError, IndexError):
                continue
            for idx, (_, ini, fim) in enumerate(faixas):
                if ini <= tot_m <= fim:
                    somas[idx] += qtd
                    break
        return somas

    return [f[0] for f in faixas], somar(curva_1t), somar(curva_2t)


def gerar_relatorio_html(analise: dict, destino: Path) -> Path:
    """Gera o relatório completo HTML5/XHTML com gráficos SVG, textos explicativos e suporte a PDF."""
    uf = analise.get("uf", "")
    tot = analise.get("totais", {})
    pres = analise.get("presidente", {})
    pos17 = analise.get("pos_17h", {})
    dist = analise.get("distribuicoes", {})
    anom = analise.get("anomalias", {})
    cont = anom.get("contagens", {})
    graf = analise.get("graficos", {})

    # Gráficos SVG
    svg_comp = _svg_scatter_comparecimento(graf.get("scatter_comparecimento", []))
    svg_migr = _svg_scatter_migracao(graf.get("scatter_migracao", []))
    svg_bio = _svg_scatter_biometria(graf.get("scatter_biometria", []))

    ordem_delta = [
        "< -15",
        "-15 a -10",
        "-10 a -6",
        "-6 a -3",
        "-3 a 0",
        "0 a 3",
        "3 a 6",
        "6 a 10",
        "10 a 15",
        ">= 15",
    ]
    d_comp_map = dist.get("delta_comparecimento", {})
    svg_hist_delta = _svg_barras_simples(
        ordem_delta,
        [int(d_comp_map.get(k, 0)) for k in ordem_delta],
        titulo_y="Nº de Seções",
        cor="#0f766e",
    )

    rot_17h, s1_17h, s2_17h = _agrupar_pos_17h_em_blocos_5min(
        pos17.get("curva_minuto_1t", {}), pos17.get("curva_minuto_2t", {})
    )
    svg_pos_17h = _svg_barras_duplas(
        rot_17h,
        s1_17h,
        s2_17h,
        titulo_y="Votos Computados Após 17h",
    )

    horas_dia = [f"{h:02d}" for h in range(8, 20)]
    ch1 = pos17.get("curva_horaria_1t", {})
    ch2 = pos17.get("curva_horaria_2t", {})
    svg_curva_horaria = _svg_barras_duplas(
        [f"{h}h" for h in horas_dia],
        [int(ch1.get(h, 0)) for h in horas_dia],
        [int(ch2.get(h, 0)) for h in horas_dia],
        titulo_y="Votos Computados por Hora",
        cor_1="#0284c7",
        cor_2="#ea580c",
    )

    ordem_int = ["< 15s", "< 25s", "< 35s", "< 45s", "< 60s", "< 90s", "< 120s", ">= 120s"]
    m_int_1t = dist.get("mediana_intervalo_1t", {})
    m_int_2t = dist.get("mediana_intervalo_2t", {})
    svg_cadencia = _svg_barras_duplas(
        ordem_int,
        [int(m_int_1t.get(k, 0)) for k in ordem_int],
        [int(m_int_2t.get(k, 0)) for k in ordem_int],
        titulo_y="Nº de Urnas por Mediana",
        cor_1="#4f46e5",
        cor_2="#059669",
    )

    # Batimento soma dos BUs vs Oficial TSE
    soma_1t = pres.get("soma_bu_1t", {})
    soma_2t = pres.get("soma_bu_2t", {})
    of_1t = pres.get("oficial_tse_1t") or {}
    of_2t = pres.get("oficial_tse_2t") or {}

    v13_bu_1t = int((soma_1t.get("nominais") or {}).get("13", 0))
    v22_bu_1t = int((soma_1t.get("nominais") or {}).get("22", 0))
    v13_bu_2t = int((soma_2t.get("nominais") or {}).get("13", 0))
    v22_bu_2t = int((soma_2t.get("nominais") or {}).get("22", 0))

    v13_of_1t = int(((of_1t.get("candidatos") or {}).get("13") or {}).get("votos", 0))
    v22_of_1t = int(((of_1t.get("candidatos") or {}).get("22") or {}).get("votos", 0))
    v13_of_2t = int(((of_2t.get("candidatos") or {}).get("13") or {}).get("votos", 0))
    v22_of_2t = int(((of_2t.get("candidatos") or {}).get("22") or {}).get("votos", 0))

    # Comparativo de votos nas urnas encerradas até 17h vs após 17h no 2T
    comp_v2t = pos17.get("comparativo_votos_2t", {})
    ate17 = comp_v2t.get("urnas_ate_17h", {})
    apos17 = comp_v2t.get("urnas_apos_17h", {})
    tot_val_ate17 = int(ate17.get("13", 0)) + int(ate17.get("22", 0))
    tot_val_apos17 = int(apos17.get("13", 0)) + int(apos17.get("22", 0))
    pct13_ate17 = 100.0 * int(ate17.get("13", 0)) / tot_val_ate17 if tot_val_ate17 else 0.0
    pct22_ate17 = 100.0 * int(ate17.get("22", 0)) / tot_val_ate17 if tot_val_ate17 else 0.0
    pct13_apos17 = 100.0 * int(apos17.get("13", 0)) / tot_val_apos17 if tot_val_apos17 else 0.0
    pct22_apos17 = 100.0 * int(apos17.get("22", 0)) / tot_val_apos17 if tot_val_apos17 else 0.0

    # Construtores de linhas de tabelas
    def _linhas_saltos(itens: list[dict]) -> str:
        if not itens:
            return '<tr><td colspan="8" class="empty-cell">Nenhuma seção com salto extremo de comparecimento detectada.</td></tr>'
        out = []
        for x in itens[:40]:
            out.append(
                f"<tr>"
                f"<td><strong>{_esc(x['nome_municipio'])}</strong></td>"
                f"<td>{_esc(x['zona'])} / {_esc(x['secao'])}</td>"
                f"<td>{_fmt_int(x['aptos_2t'])}</td>"
                f"<td>{_fmt_int(x['comp_1t'])} ({_fmt_pct(x['pct_comp_1t'], 1)})</td>"
                f"<td><strong>{_fmt_int(x['comp_2t'])} ({_fmt_pct(x['pct_comp_2t'], 1)})</strong></td>"
                f"<td class=\"num-alert\">{x['delta_comp_pp']:+.2f} p.p. ({x['delta_comp_abs']:+d})</td>"
                f"<td>{x['z_municipio']:+.2f}σ</td>"
                f"<td>13: {_fmt_int(x['v13_1t'])}→{_fmt_int(x['v13_2t'])} | 22: {_fmt_int(x['v22_1t'])}→{_fmt_int(x['v22_2t'])}</td>"
                f"</tr>"
            )
        return "".join(out)

    def _linhas_comp_100(itens: list[dict]) -> str:
        if not itens:
            return '<tr><td colspan="7" class="empty-cell">Nenhuma seção com comparecimento ≥ 99% ou acima dos aptos.</td></tr>'
        out = []
        for x in itens[:35]:
            out.append(
                f"<tr>"
                f"<td><strong>{_esc(x['nome_municipio'])}</strong></td>"
                f"<td>{_esc(x['zona'])} / {_esc(x['secao'])}</td>"
                f"<td>{_fmt_int(x['aptos_2t'])}</td>"
                f"<td>{_fmt_int(x['comp_1t'])} ({_fmt_pct(x['pct_comp_1t'], 1)})</td>"
                f"<td class=\"num-alert\">{_fmt_int(x['comp_2t'])} ({_fmt_pct(x['pct_comp_2t'], 1)})</td>"
                f"<td>{_fmt_int(x['v13_2t'])}</td>"
                f"<td>{_fmt_int(x['v22_2t'])}</td>"
                f"</tr>"
            )
        return "".join(out)

    def _linhas_pos17h(itens: list[dict]) -> str:
        if not itens:
            return '<tr><td colspan="7" class="empty-cell">Nenhuma seção com 15 ou mais votos após as 17h00.</td></tr>'
        out = []
        for x in itens[:40]:
            out.append(
                f"<tr>"
                f"<td><strong>{_esc(x['nome_municipio'])}</strong></td>"
                f"<td>{_esc(x['zona'])} / {_esc(x['secao'])}</td>"
                f"<td>{_fmt_int(x['votos_apos_17h_1t'])} (até {_esc(x['encerramento_1t'] or '-')})</td>"
                f"<td class=\"num-alert\">{_fmt_int(x['votos_apos_17h_2t'])} (até {_esc(x['encerramento_2t'] or '-')})</td>"
                f"<td>{_fmt_int(x['comp_2t'])}</td>"
                f"<td>{_fmt_int(x['v13_2t'])}</td>"
                f"<td>{_fmt_int(x['v22_2t'])}</td>"
                f"</tr>"
            )
        return "".join(out)

    def _linhas_perda_liquida(itens: list[dict]) -> str:
        if not itens:
            return '<tr><td colspan="7" class="empty-cell">Nenhuma seção com perda líquida expressiva de votos absolutos.</td></tr>'
        out = []
        for x in itens[:40]:
            out.append(
                f"<tr>"
                f"<td><strong>{_esc(x['nome_municipio'])}</strong></td>"
                f"<td>{_esc(x['zona'])} / {_esc(x['secao'])}</td>"
                f"<td>{_fmt_int(x['comp_1t'])} → {_fmt_int(x['comp_2t'])}</td>"
                f"<td>{_fmt_int(x['v13_1t'])} → {_fmt_int(x['v13_2t'])}</td>"
                f"<td class=\"{'num-alert' if x['delta_13'] < 0 else ''}\">{x['delta_13']:+d}</td>"
                f"<td>{_fmt_int(x['v22_1t'])} → {_fmt_int(x['v22_2t'])}</td>"
                f"<td class=\"{'num-alert' if x['delta_22'] < 0 else ''}\">{x['delta_22']:+d}</td>"
                f"</tr>"
            )
        return "".join(out)

    def _linhas_escola(itens: list[dict]) -> str:
        if not itens:
            return '<tr><td colspan="8" class="empty-cell">Nenhuma seção divergiu em mais de 3 desvios-padrão das demais salas da mesma escola.</td></tr>'
        out = []
        for x in itens[:40]:
            out.append(
                f"<tr>"
                f"<td><strong>{_esc(x['nome_municipio'])}</strong></td>"
                f"<td>{_esc(x['zona'])} / {_esc(x['secao'])}</td>"
                f"<td>Local {_esc(x['local'])} ({x['n_salas_escola']} salas)</td>"
                f"<td>{_fmt_pct(x['pct_comp_2t'], 1)} (escola: {_fmt_pct(x['media_comp_escola_2t'], 1)})</td>"
                f"<td>{x['diff_comp_escola_pp']:+.1f} p.p. ({x['z_comp_escola']:+.1f}σ)</td>"
                f"<td>{_fmt_pct(x['pct_22_secao'], 1)} (escola: {_fmt_pct(x['media_pct_22_escola'], 1)})</td>"
                f"<td class=\"num-alert\">{x['diff_pct_22_escola_pp']:+.1f} p.p. ({x['z_pct_22_escola']:+.1f}σ)</td>"
                f"</tr>"
            )
        return "".join(out)

    def _linhas_biometria(itens: list[dict]) -> str:
        if not itens:
            return '<tr><td colspan="7" class="empty-cell">Nenhuma seção com liberação manual sem biometria ≥ 25%.</td></tr>'
        out = []
        for x in itens[:40]:
            out.append(
                f"<tr>"
                f"<td><strong>{_esc(x['nome_municipio'])}</strong></td>"
                f"<td>{_esc(x['zona'])} / {_esc(x['secao'])}</td>"
                f"<td>{_fmt_pct(x['pct_sem_bio_1t'], 1)}</td>"
                f"<td class=\"num-alert\">{_fmt_pct(x['pct_sem_bio_2t'], 1)} ({_fmt_int(x['sem_bio_2t'])}/{_fmt_int(x['comp_2t'])})</td>"
                f"<td>{_fmt_pct(x['pct_comp_2t'], 1)}</td>"
                f"<td>{_fmt_pct(x['pct_13_2t'], 1)}</td>"
                f"<td>{_fmt_pct(x['pct_22_2t'], 1)}</td>"
                f"</tr>"
            )
        return "".join(out)

    def _linhas_cadencia(itens: list[dict]) -> str:
        if not itens:
            return '<tr><td colspan="7" class="empty-cell">Nenhuma urna com cadência atípica detectada.</td></tr>'
        out = []
        for x in itens[:35]:
            out.append(
                f"<tr>"
                f"<td><strong>{_esc(x['nome_municipio'])}</strong></td>"
                f"<td>{_esc(x['zona'])} / {_esc(x['secao'])}</td>"
                f"<td>{_esc(x['mediana_1t_s'] if x['mediana_1t_s'] is not None else '-')}s (mín {_esc(x['min_1t_s'] if x['min_1t_s'] is not None else '-')}s)</td>"
                f"<td>{_fmt_int(x['menor_10s_1t'])}</td>"
                f"<td><strong>{_esc(x['mediana_2t_s'] if x['mediana_2t_s'] is not None else '-')}s</strong> (mín {_esc(x['min_2t_s'] if x['min_2t_s'] is not None else '-')}s)</td>"
                f"<td class=\"num-alert\">{_fmt_int(x['menor_10s_2t'])}</td>"
                f"<td>{_fmt_int(x['cabine_menor_5s_2t'])}</td>"
                f"</tr>"
            )
        return "".join(out)

    def _linhas_dossie(itens: list[dict]) -> str:
        if not itens:
            return '<tr><td colspan="6" class="empty-cell">Nenhuma seção crítica sinalizada.</td></tr>'
        out = []
        for idx, x in enumerate(itens[:60], 1):
            motivos_html = "<br />".join(f"• {_esc(m)}" for m in x.get("motivos", []))
            out.append(
                f"<tr>"
                f"<td>{idx}</td>"
                f"<td><strong>{_esc(x['nome_municipio'])}</strong><br /><span class=\"muted\">Z:{_esc(x['zona'])} S:{_esc(x['secao'])} (Local {_esc(x['local'])})</span></td>"
                f"<td class=\"num-alert\">{x['score']:.1f}</td>"
                f"<td>1T: {_fmt_pct(x['pct_comp_1t'], 1)}<br />2T: <strong>{_fmt_pct(x['pct_comp_2t'], 1)}</strong> ({x['delta_comp_pp']:+.1f} p.p.)</td>"
                f"<td>13: {_fmt_int(x['v13_1t'])}→{_fmt_int(x['v13_2t'])}<br />22: {_fmt_int(x['v22_1t'])}→{_fmt_int(x['v22_2t'])}</td>"
                f"<td class=\"motivos-cell\">{motivos_html}</td>"
                f"</tr>"
            )
        return "".join(out)

    conteudo = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Auditoria Eleitoral 1º vs 2º Turno 2026 — Estado: {_esc(uf)}</title>
  <style type="text/css">
    :root {{
      --bg: #f8fafc;
      --card: #ffffff;
      --ink: #0f172a;
      --muted: #475569;
      --border: #cbd5e1;
      --primary: #1d4ed8;
      --danger: #b91c1c;
      --warn: #b45309;
      --ok: #15803d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.55;
      font-size: 14px;
    }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: #0f172a;
      color: #ffffff;
      padding: 12px 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.18);
    }}
    .topbar-title {{
      font-size: 16px;
      font-weight: 700;
      letter-spacing: 0.2px;
    }}
    .topbar-sub {{
      font-size: 12px;
      color: #cbd5e1;
    }}
    .btn-print {{
      background: #2563eb;
      color: #ffffff;
      border: none;
      padding: 9px 18px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 13.5px;
      cursor: pointer;
    }}
    .btn-print:hover {{ background: #1d4ed8; }}
    .container {{
      max-width: 1180px;
      margin: 24px auto;
      padding: 0 20px 48px 20px;
    }}
    .section-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 22px 24px;
      margin-bottom: 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      overflow: hidden;
    }}
    h1 {{ font-size: 24px; margin: 0 0 8px 0; color: #0f172a; }}
    h2 {{
      font-size: 18px;
      margin: 0 0 12px 0;
      padding-bottom: 8px;
      border-bottom: 2px solid #e2e8f0;
      color: #0f172a;
    }}
    h3 {{ font-size: 15px; margin: 18px 0 8px 0; color: #1e293b; }}
    p {{ margin: 0 0 12px 0; color: #334155; }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 14px;
      margin: 16px 0;
    }}
    .kpi-box {{
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 14px 16px;
      background: #f8fafc;
      min-width: 0;
    }}
    .kpi-label {{ font-size: 12px; color: var(--muted); font-weight: 600; text-transform: uppercase; }}
    .kpi-value {{ font-size: 22px; font-weight: 700; color: #0f172a; margin-top: 4px; word-break: break-word; }}
    .kpi-sub {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
    .explain-box {{
      background: #eff6ff;
      border-left: 4px solid #2563eb;
      padding: 12px 16px;
      border-radius: 0 6px 6px 0;
      margin: 12px 0 16px 0;
      color: #1e3a8a;
      font-size: 13.5px;
    }}
    .warn-box {{
      background: #fef2f2;
      border-left: 4px solid #dc2626;
      padding: 12px 16px;
      border-radius: 0 6px 6px 0;
      margin: 12px 0 16px 0;
      color: #7f1d1d;
      font-size: 13.5px;
    }}
    .chart-wrap {{
      width: 100%;
      max-width: 760px;
      margin: 14px auto;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 8px 8px 6px 8px;
      background: #ffffff;
    }}
    .chart-credit {{
      margin-top: 6px;
      padding-top: 6px;
      border-top: 1px dashed #cbd5e1;
      font-size: 11.5px;
      color: #334155;
      text-align: center;
    }}
    .author-banner {{
      background: #f1f5f9;
      border: 1px solid #cbd5e1;
      border-left: 5px solid #0f172a;
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 18px;
      font-size: 13px;
      color: #0f172a;
    }}
    .report-footer {{
      margin-top: 24px;
      padding: 16px 20px;
      background: #0f172a;
      color: #f8fafc;
      border-radius: 8px;
      font-size: 12.5px;
      line-height: 1.5;
    }}
    .print-running-footer {{
      display: none;
    }}
    .svg-chart {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      margin-top: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      table-layout: auto;
    }}
    th, td {{
      border: 1px solid #cbd5e1;
      padding: 7px 9px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: break-word;
    }}
    th {{
      background: #f1f5f9;
      font-weight: 700;
      color: #0f172a;
    }}
    tr:nth-child(even) td {{ background: #f8fafc; }}
    .num-alert {{ color: var(--danger); font-weight: 700; }}
    .num-ok {{ color: var(--ok); font-weight: 700; }}
    .muted {{ color: var(--muted); font-size: 11.5px; }}
    .motivos-cell {{ max-width: 440px; line-height: 1.4; }}
    .empty-cell {{ text-align: center; color: var(--muted); font-style: italic; padding: 14px; }}

    @media print {{
      @page {{ size: A4 portrait; margin: 10mm 10mm 16mm 10mm; }}
      body {{ background: #ffffff; font-size: 11.5px; padding-bottom: 14mm; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      .no-print {{ display: none !important; }}
      .container {{ max-width: 100%; margin: 0; padding: 0; }}
      .section-card {{
        box-shadow: none;
        border: 1px solid #94a3b8;
        margin-bottom: 14px;
        padding: 14px;
        break-inside: avoid-page;
      }}
      .chart-wrap {{ max-width: 100%; break-inside: avoid; }}
      .report-footer {{
        background: #f1f5f9;
        color: #0f172a;
        border: 1px solid #64748b;
        break-inside: avoid;
      }}
      .print-running-footer {{
        display: block;
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: #ffffff;
        border-top: 1px solid #94a3b8;
        padding: 4px 8px;
        font-size: 9.5px;
        color: #1e293b;
        text-align: center;
      }}
      table {{ font-size: 10.5px; }}
      thead {{ display: table-header-group; }}
      tr {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="topbar no-print">
    <div>
      <div class="topbar-title">Relatório de Auditoria Eleitoral 1º vs. 2º Turno (2026) — UF: {_esc(uf)} • Autor: {_esc(AUTOR_RELATORIO)}</div>
      <div class="topbar-sub">Fonte dos dados: {_esc(FONTE_DADOS_CURTA)} • Gerado em {_esc(analise.get('gerado_em', ''))}</div>
    </div>
    <div>
      <button type="button" class="btn-print" onclick="window.print()">Imprimir / Salvar em PDF</button>
    </div>
  </div>

  <div class="print-running-footer">
    <strong>Autor:</strong> {_esc(AUTOR_RELATORIO)} &#160;|&#160; <strong>Fonte dos dados:</strong> {_esc(FONTE_DADOS_CURTA)} &#160;|&#160; UF: {_esc(uf)}
  </div>

  <div class="container">
    <div class="author-banner">
      <div><strong>Autor da Auditoria e Relatório:</strong> {_esc(AUTOR_RELATORIO)}</div>
      <div><strong>Fonte dos Dados:</strong> {_esc(FONTE_DADOS_COMPLETA)}</div>
    </div>

    <div class="section-card">
      <h1>1. Resumo Executivo e Verificação de Integridade — {_esc(uf)}</h1>
      <p>
        Este relatório compara seção por seção o <strong>1º turno (04/10/2026, pleito 3220)</strong> e o
        <strong>2º turno (25/10/2026, pleito 3221)</strong> do estado de <strong>{_esc(uf)}</strong>.
        Para cada seção eleitoral, os arquivos brutos (<code>vota.vsc</code>, <code>bu.dat</code> e <code>log.jez</code>)
        foram validados criptograficamente em memória antes da extração das métricas.
      </p>
      <div class="kpi-grid">
        <div class="kpi-box">
          <div class="kpi-label">Urnas Analisadas (1T + 2T)</div>
          <div class="kpi-value">{_fmt_int(tot.get('urnas_completas_ambos_turnos'))} / {_fmt_int(tot.get('urnas_malha'))}</div>
          <div class="kpi-sub">Seções agregadas: {_fmt_int(tot.get('secoes_agregadas_2t'))}</div>
        </div>
        <div class="kpi-box">
          <div class="kpi-label">Comparecimento 1T → 2T</div>
          <div class="kpi-value">{_fmt_pct(tot.get('pct_comparecimento_1t'))} → {_fmt_pct(tot.get('pct_comparecimento_2t'))}</div>
          <div class="kpi-sub">Variação estadual: {tot.get('delta_comparecimento_pp', 0.0):+.2f} p.p. ({_fmt_int(tot.get('comparecimento_2t', 0) - tot.get('comparecimento_1t', 0))} eleitores)</div>
        </div>
        <div class="kpi-box">
          <div class="kpi-label">Votos Registrados Após 17h00</div>
          <div class="kpi-value">1T: {_fmt_int(tot.get('votos_apos_17h_1t'))} | 2T: {_fmt_int(tot.get('votos_apos_17h_2t'))}</div>
          <div class="kpi-sub">Em {_fmt_int(tot.get('urnas_com_voto_apos_17h_1t'))} urnas (1T) e {_fmt_int(tot.get('urnas_com_voto_apos_17h_2t'))} urnas (2T)</div>
        </div>
        <div class="kpi-box">
          <div class="kpi-label">Habilitação Sem Biometria</div>
          <div class="kpi-value">1T: {_fmt_pct(tot.get('pct_sem_biometria_1t'))} | 2T: {_fmt_pct(tot.get('pct_sem_biometria_2t'))}</div>
          <div class="kpi-sub">Liberados por código no 2T: {_fmt_int(tot.get('sem_biometria_2t'))} eleitores</div>
        </div>
      </div>

      <h3>1.1. Batimento Matemático: Soma Individual dos BUs vs. Resultado Agregado Oficial do TSE</h3>
      <div class="explain-box">
        <strong>Por que fazemos este batimento:</strong> Somamos diretamente os votos decodificados de cada arquivo binário
        <code>bu.dat</code> assinado pelas urnas e comparamos com o arquivo JSON de totalização oficial (<code>-u.json</code>) publicado pelo TSE.
        Qualquer divergência indicaria omissão ou alteração de seção na totalização.
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Turno / Métrica (Presidente)</th>
              <th>Soma dos BUs Decodificados</th>
              <th>JSON Oficial Agregado TSE</th>
              <th>Diferença (BU − Oficial)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>1º Turno — Candidato 13</strong></td>
              <td>{_fmt_int(v13_bu_1t)}</td>
              <td>{_fmt_int(v13_of_1t)}</td>
              <td class="{'num-ok' if v13_bu_1t == v13_of_1t else 'num-alert'}">{_fmt_int(v13_bu_1t - v13_of_1t)}</td>
            </tr>
            <tr>
              <td><strong>1º Turno — Candidato 22</strong></td>
              <td>{_fmt_int(v22_bu_1t)}</td>
              <td>{_fmt_int(v22_of_1t)}</td>
              <td class="{'num-ok' if v22_bu_1t == v22_of_1t else 'num-alert'}">{_fmt_int(v22_bu_1t - v22_of_1t)}</td>
            </tr>
            <tr>
              <td><strong>2º Turno — Candidato 13</strong></td>
              <td>{_fmt_int(v13_bu_2t)}</td>
              <td>{_fmt_int(v13_of_2t)}</td>
              <td class="{'num-ok' if v13_bu_2t == v13_of_2t else 'num-alert'}">{_fmt_int(v13_bu_2t - v13_of_2t)}</td>
            </tr>
            <tr>
              <td><strong>2º Turno — Candidato 22</strong></td>
              <td>{_fmt_int(v22_bu_2t)}</td>
              <td>{_fmt_int(v22_of_2t)}</td>
              <td class="{'num-ok' if v22_bu_2t == v22_of_2t else 'num-alert'}">{_fmt_int(v22_bu_2t - v22_of_2t)}</td>
            </tr>
            <tr>
              <td><strong>Hashes 1T alterados desde o Snapshot de 05/10/2026</strong></td>
              <td colspan="2">Comparação contra o manifesto imutável salvo em 05/10/2026</td>
              <td class="{'num-ok' if tot.get('hashes_1t_alterados_pos_snapshot', 0) == 0 else 'num-alert'}">{_fmt_int(tot.get('hashes_1t_alterados_pos_snapshot', 0))} alterações</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="section-card">
      <h2>2. Análise de Comparecimento: 1º Turno vs. 2º Turno (Ex.: Saltos de 80% → 100%)</h2>
      <div class="explain-box">
        <strong>O que estamos procurando:</strong> Cada seção eleitoral possui exatamente os mesmos eleitores cadastrados nos dois turnos.
        No gráfico de dispersão abaixo, o eixo horizontal mostra o comparecimento da seção no 1º turno e o eixo vertical mostra o comparecimento da
        <strong>mesma seção</strong> no 2º turno. Pontos sobre a linha tracejada preta tiveram comparecimento idêntico nos dois turnos; pontos acima da
        linha tracejada vermelha subiram mais de <strong>+10 pontos percentuais</strong> no 2º turno ou atingiram quase 100% de presença.
      </div>
      {_bloco_grafico(svg_comp)}
      <h3>2.1. Distribuição da Variação de Comparecimento (Δ pontos percentuais 2ºT − 1ºT)</h3>
      {_bloco_grafico(svg_hist_delta)}

      <h3>2.2. Seções com Maior Salto de Comparecimento do 1º para o 2º Turno ({_fmt_int(cont.get('saltos_comparecimento'))} ocorrências)</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>Zona / Seção</th>
              <th>Aptos</th>
              <th>Comparecimento 1ºT</th>
              <th>Comparecimento 2ºT</th>
              <th>Variação (2ºT − 1ºT)</th>
              <th>Desvio no Município</th>
              <th>Votos Pres. (1ºT → 2ºT)</th>
            </tr>
          </thead>
          <tbody>{_linhas_saltos(anom.get('saltos_comparecimento', []))}</tbody>
        </table>
      </div>

      <h3>2.3. Seções com Comparecimento ≥ 99%, 100% (Abstenção Zero) ou Acima dos Aptos ({_fmt_int(cont.get('comparecimento_100_ou_acima'))} ocorrências)</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>Zona / Seção</th>
              <th>Aptos 2ºT</th>
              <th>Comparecimento 1ºT</th>
              <th>Comparecimento 2ºT</th>
              <th>Votos Cand. 13 (2ºT)</th>
              <th>Votos Cand. 22 (2ºT)</th>
            </tr>
          </thead>
          <tbody>{_linhas_comp_100(anom.get('comparecimento_100_ou_acima', []))}</tbody>
        </table>
      </div>
    </div>

    <div class="section-card">
      <h2>3. Votos Registrados Após as 17h00 e Curva Horária de Votação (1º vs. 2º Turno)</h2>
      <div class="explain-box">
        <strong>Como foi medido:</strong> O Boletim de Urna (<code>bu.dat</code>) informa apenas a hora em que a urna foi encerrada, mas não a hora de cada voto.
        Por isso, descompactamos o arquivo <code>log.jez</code> (<code>logd.dat</code>) de cada seção e lemos o horário exato de cada evento
        <code>"O voto do eleitor foi computado"</code>. Quando há fila às 17h00, os eleitores presentes recebem senha e continuam votando após as 17h00.
        No 1º turno (5 cargos na urna), as filas após as 17h00 costumam ser muito maiores do que no 2º turno (apenas 1 ou 2 cargos).
      </div>
      {_bloco_grafico(svg_pos_17h)}

      <h3>3.1. Curva Horária Completa de Votos Computados (08h às 19h+ — 1º Turno vs. 2º Turno)</h3>
      {_bloco_grafico(svg_curva_horaria)}

      <h3>3.2. Comparativo Político: Urnas Encerradas Até 17h00 vs. Urnas com Votos Após 17h00 (2º Turno)</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Grupo de Urnas no 2º Turno</th>
              <th>Quantidade de Urnas</th>
              <th>Votos Computados Após 17h00</th>
              <th>Votos Cand. 13 (%)</th>
              <th>Votos Cand. 22 (%)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Urnas sem votos após 17h00 (encerradas no horário)</strong></td>
              <td>{_fmt_int(ate17.get('urnas'))}</td>
              <td>0</td>
              <td>{_fmt_int(ate17.get('13'))} ({_fmt_pct(pct13_ate17)})</td>
              <td>{_fmt_int(ate17.get('22'))} ({_fmt_pct(pct22_ate17)})</td>
            </tr>
            <tr>
              <td><strong>Urnas com votos computados após 17h00</strong></td>
              <td>{_fmt_int(apos17.get('urnas'))}</td>
              <td>{_fmt_int(apos17.get('votos_apos_17h'))}</td>
              <td>{_fmt_int(apos17.get('13'))} ({_fmt_pct(pct13_apos17)})</td>
              <td>{_fmt_int(apos17.get('22'))} ({_fmt_pct(pct22_apos17)})</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3>3.3. Seções com Maior Quantidade de Votos Computados Após as 17h00</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>Zona / Seção</th>
              <th>Votos Pós-17h no 1ºT (Encerramento)</th>
              <th>Votos Pós-17h no 2ºT (Encerramento)</th>
              <th>Comparecimento 2ºT</th>
              <th>Cand. 13 (2ºT)</th>
              <th>Cand. 22 (2ºT)</th>
            </tr>
          </thead>
          <tbody>{_linhas_pos17h(pos17.get('top_urnas', []))}</tbody>
        </table>
      </div>
    </div>

    <div class="section-card">
      <h2>4. Cadência e Velocidade Física de Votação no Log da Urna</h2>
      <div class="explain-box">
        <strong>O que mede este indicador:</strong> Calculamos o tempo em segundos entre um eleitor ter o voto computado e o próximo eleitor
        ter o voto computado na mesma urna, além do tempo gasto dentro da cabine (entre <code>"Eleitor foi habilitado"</code> e
        <code>"O voto do eleitor foi computado"</code>). No 1º turno (5 cargos), a mediana típica fica entre 45s e 75s por eleitor; no 2º turno
        (1 ou 2 cargos), o tempo cai para ~25s a 45s. Intervalos repetidos abaixo de 10 segundos merecem inspeção.
      </div>
      {_bloco_grafico(svg_cadencia)}
      <h3>4.1. Urnas com Menor Tempo Mediano ou Votos em Intervalo Curto (&lt; 10s) ({_fmt_int(cont.get('urnas_votacao_rapida'))} ocorrências)</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>Zona / Seção</th>
              <th>Mediana / Mínimo 1ºT</th>
              <th>Votos &lt;10s (1ºT)</th>
              <th>Mediana / Mínimo 2ºT</th>
              <th>Votos &lt;10s (2ºT)</th>
              <th>Cabine &lt;5s (2ºT)</th>
            </tr>
          </thead>
          <tbody>{_linhas_cadencia(anom.get('urnas_votacao_rapida', []))}</tbody>
        </table>
      </div>
    </div>

    <div class="section-card">
      <h2>5. Auditoria de Biometria vs. Liberação Manual por Código pelo Mesário</h2>
      <div class="explain-box">
        <strong>Como funciona:</strong> Quando a digital do eleitor não é reconhecida após 4 tentativas (ou quando o eleitor não possui biometria coletada),
        o mesário pode habilitar a urna manualmente digitando o código e o ano de nascimento do eleitor. O gráfico e a tabela abaixo cruzam a
        porcentagem de eleitores liberados sem biometria com a taxa de comparecimento e a votação da seção.
      </div>
      {_bloco_grafico(svg_bio)}
      <h3>5.1. Seções com Maior Taxa de Habilitação Sem Biometria ({_fmt_int(cont.get('alta_sem_biometria'))} ocorrências)</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>Zona / Seção</th>
              <th>% Sem Biometria 1ºT</th>
              <th>% Sem Biometria 2ºT (Qtd/Total)</th>
              <th>Comparecimento 2ºT</th>
              <th>% Cand. 13 (2ºT)</th>
              <th>% Cand. 22 (2ºT)</th>
            </tr>
          </thead>
          <tbody>{_linhas_biometria(anom.get('alta_sem_biometria', []))}</tbody>
        </table>
      </div>
    </div>

    <div class="section-card">
      <h2>6. Migração de Votos e Perda Líquida Absoluta entre 1º e 2º Turno</h2>
      <div class="explain-box">
        <strong>O que estamos procurando:</strong> Como no 2º turno os votos dados a terceiros candidatos no 1º turno migram para os dois finalistas,
        o normal é que ambos os candidatos mantenham ou aumentem sua votação absoluta em cada seção (quadrante superior direito do gráfico).
        Pontos em laranja mostram seções onde um dos candidatos <strong>perdeu votos absolutos</strong> no 2º turno em comparação ao que já havia recebido
        naquela mesma urna no 1º turno, apesar de o comparecimento da seção não ter caído.
      </div>
      {_bloco_grafico(svg_migr)}
      <h3>6.1. Seções com Maior Perda Líquida de Votos Absolutos entre 1º e 2º Turno ({_fmt_int(cont.get('perda_liquida_votos'))} ocorrências)</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>Zona / Seção</th>
              <th>Comparecimento (1ºT → 2ºT)</th>
              <th>Cand. 13 (1ºT → 2ºT)</th>
              <th>Δ Cand. 13</th>
              <th>Cand. 22 (1ºT → 2ºT)</th>
              <th>Δ Cand. 22</th>
            </tr>
          </thead>
          <tbody>{_linhas_perda_liquida(anom.get('perda_liquida_votos', []))}</tbody>
        </table>
      </div>
    </div>

    <div class="section-card">
      <h2>7. Divergência Intralocal: Salas que Destoam da Própria Escola</h2>
      <div class="explain-box">
        <strong>Por que esta é uma das provas estatísticas mais fortes:</strong> Seções do mesmo local de votação (mesmo prédio escolar, identificadas pelo
        campo <code>local</code> do BU) atendem eleitores do mesmo bairro distribuídos de forma homogênea. Abaixo estão listadas as seções que divergiram
        em mais de <strong>3 desvios-padrão (≥ 3σ)</strong> e mais de 10 a 12 pontos percentuais da média das outras salas do mesmo colégio.
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>Zona / Seção</th>
              <th>Escola (Local / Salas)</th>
              <th>Comparecimento 2ºT vs. Escola</th>
              <th>Desvio Comparecimento</th>
              <th>% Cand. 22 vs. Escola</th>
              <th>Desvio Votação</th>
            </tr>
          </thead>
          <tbody>{_linhas_escola(anom.get('outliers_mesma_escola', []))}</tbody>
        </table>
      </div>
    </div>

    <div class="section-card">
      <h2>8. Cadastro de Aptos, Urnas Unânimes, Hardware e Consistência Log × BU</h2>
      <div class="kpi-grid">
        <div class="kpi-box">
          <div class="kpi-label">Mudança de Eleitores Aptos</div>
          <div class="kpi-value">{_fmt_int(cont.get('aptos_alterados'))}</div>
          <div class="kpi-sub">Seções onde aptos 1T ≠ aptos 2T</div>
        </div>
        <div class="kpi-box">
          <div class="kpi-label">Urnas Unânimes (100% a 0%)</div>
          <div class="kpi-value">{_fmt_int(cont.get('urnas_unanimes'))}</div>
          <div class="kpi-sub">Seções com 0 votos p/ um candidato no 2T</div>
        </div>
        <div class="kpi-box">
          <div class="kpi-label">Divergência Log × BU</div>
          <div class="kpi-value">{_fmt_int(cont.get('divergencia_log_bu'))}</div>
          <div class="kpi-sub">Diferença entre votos no log e no BU</div>
        </div>
        <div class="kpi-box">
          <div class="kpi-label">Trocas de Urna / Reboots</div>
          <div class="kpi-value">{_fmt_int(cont.get('trocas_e_reboots'))}</div>
          <div class="kpi-sub">Troca física entre turnos, contingência ou reinício</div>
        </div>
      </div>
    </div>

    <div class="section-card">
      <h2>9. Dossiê Ranqueado das Seções Mais Atípicas ({_fmt_int(cont.get('secoes_com_alerta'))} seções sinalizadas)</h2>
      <div class="warn-box">
        <strong>Como ler este dossiê:</strong> As seções abaixo obtiveram a maior pontuação composta de atipicidade ao cruzar todas as 10 dimensões
        auditadas (salto de comparecimento, presença de 100%, votação pós-17h, velocidade de votação, perda líquida de votos, liberação sem biometria e
        desvio em relação às outras salas da mesma escola).
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Município / Zona / Seção</th>
              <th>Score</th>
              <th>Comparecimento</th>
              <th>Votos (1ºT → 2ºT)</th>
              <th>Fatos Observados nos Arquivos da Urna</th>
            </tr>
          </thead>
          <tbody>{_linhas_dossie(anom.get('dossie_secoes_criticas', []))}</tbody>
        </table>
      </div>
    </div>

    <div class="report-footer">
      <div><strong>Autor:</strong> {_esc(AUTOR_RELATORIO)}</div>
      <div><strong>Fonte dos Dados:</strong> {_esc(FONTE_DADOS_COMPLETA)}</div>
      <div><strong>Emissão do Relatório ({_esc(uf)}):</strong> {_esc(analise.get('gerado_em', ''))}</div>
    </div>
  </div>
</body>
</html>
"""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    return destino
