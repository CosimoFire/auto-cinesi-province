"""Disegna la mappa SVG interattiva della quota di auto di marchi cinesi per provincia.

Uso:
    python src/mappa.py dati/quota_auto_cinesi_province_gen-ott2026.csv dati/province_2023.geojson output/mappa.svg

Il CSV ha separatore ';' e colonne Provincia, Totale immatricolazioni,
Marchi cinesi, Quota marchi cinesi %. Il GeoJSON sono i confini openpolis
con le 107 province usate dal MIT (versione 2023, con Sud Sardegna).

Schema grafico: etichetta di sezione, titolo e sottotitolo in alto; mappa a
classi con richiami sui casi principali; classifica delle prime province a
destra; legenda a classi e fonte in basso. Tooltip al passaggio del mouse.
"""
import csv
import html
import json
import math
import re
import sys
import unicodedata

from shapely.geometry import Polygon, shape

# --- testi -------------------------------------------------------------------
SEZIONE_NUMERO = "1"
SEZIONE_NOME = "LE PROVINCE"
TITOLO = "Immatricolazioni di auto cinesi"
SOTTOTITOLO = [
    "Quota di auto nuove sul totale realizzate da brand cinesi per provincia di residenza del proprietario,",
    "periodo gennaio-ottobre 2026",
]
TITOLO_CLASSIFICA = "LE PRIME PROVINCE"
NOTA_CLASSIFICA = [
    "Italia: {auto} auto di marchi cinesi,",
    "l'{quota}% delle nuove immatricolazioni.",
    "La percentuale è la quota sul totale",
    "delle immatricolazioni della provincia",
]
TITOLO_LEGENDA = "QUOTA DI AUTO DI MARCHI CINESI"
FONTE = [
    "Fonte: elaborazione su dati MIT – Centro elaborazione dati, pubblicati da UNRAE (unrae.it); confini openpolis su dati ISTAT",
    "Marchi cinesi considerati: BYD, MG (gruppo SAIC), Omoda e Jaecoo (gruppo Chery), Leapmotor",
]

# Richiami sulla mappa: provincia -> (x, y dell'etichetta in px dall'angolo in alto a sinistra
# della mappa, righe di testo). La linea parte dalla provincia e arriva al bordo più vicino del testo.
RICHIAMI = {
    "AOSTA": (0, 8, ["43,5%, la quota più alta.", "Pesano le flotte di noleggio"]),
    "BOLZANOBOZEN": (312, 8, ["23,6%. Anche qui pesano", "le flotte di noleggio"]),
    "NAPOLI": (166, 405, ["20,2%. Due auto cinesi", "su tre sono Leapmotor"]),
    "CATANIA": (450, 500, ["19,0%, prima in Sicilia.", "Più di metà sono", "Leapmotor"]),
}

# --- classi di colore ---------------------------------------------------------
SOGLIE = [8, 10, 13, 16]  # limiti delle classi, in %
COLORI = ["#f1f1ef", "#b2d8f6", "#83c3ef", "#009cdf", "#005f8a"]
ETICHETTE_CLASSI = ["fino all'8%", "8-10%", "10-13%", "13-16%", "oltre il 16%"]
BLU = "#009cdf"     # evidenza
GRIGIO = "#9e9e9e"  # barre della classifica


def classe(q):
    """Indice della classe per una quota (arrotondata a un decimale, come mostrata)."""
    return sum(round(q, 1) >= s for s in SOGLIE)


# --- tooltip -------------------------------------------------------------------
# Riquadro disegnato nell'SVG: compare al passaggio del mouse e al tocco.
# Funziona aprendo l'SVG direttamente o incorporandolo con <object> / <iframe>,
# non con <img> (che disattiva gli script).
TOOLTIP = """<g id="tip" visibility="hidden" pointer-events="none">
<rect id="tip-bg" rx="4" fill="#fff" stroke="#a0acad" stroke-width="1"/>
<text id="tip-nome" font-size="14" font-weight="700"></text>
<text id="tip-auto" font-size="13"></text>
<text id="tip-quota" font-size="13"></text>
</g>
<script><![CDATA[
(function () {
  var svg = document.documentElement, tip = document.getElementById('tip');
  var bg = document.getElementById('tip-bg');
  var tN = document.getElementById('tip-nome'), tA = document.getElementById('tip-auto'), tQ = document.getElementById('tip-quota');
  var vb = svg.viewBox.baseVal, PAD = 10;
  function punto(e) {
    var p = svg.createSVGPoint(), t = e.touches ? e.touches[0] : e;
    p.x = t.clientX; p.y = t.clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  }
  function mostra(e) {
    var el = e.target;
    if (!el.getAttribute || !el.getAttribute('data-nome')) return;
    tN.textContent = el.getAttribute('data-nome');
    tA.textContent = 'Auto cinesi immatricolate: ' + el.getAttribute('data-auto');
    tQ.textContent = 'In % sulle nuove immatricolazioni: ' + el.getAttribute('data-quota');
    var w = Math.max(tN.getComputedTextLength(), tA.getComputedTextLength(), tQ.getComputedTextLength()) + 2 * PAD, h = 66;
    var p = punto(e), x = p.x + 14, y = p.y + 14;
    if (x + w > vb.width - 4) x = p.x - w - 14;
    if (y + h > vb.height - 4) y = p.y - h - 14;
    bg.setAttribute('x', x); bg.setAttribute('y', y); bg.setAttribute('width', w); bg.setAttribute('height', h);
    tN.setAttribute('x', x + PAD); tN.setAttribute('y', y + 21);
    tA.setAttribute('x', x + PAD); tA.setAttribute('y', y + 40);
    tQ.setAttribute('x', x + PAD); tQ.setAttribute('y', y + 57);
    tip.setAttribute('visibility', 'visible');
  }
  function nascondi() { tip.setAttribute('visibility', 'hidden'); }
  var aree = document.querySelectorAll('.prov path');
  for (var i = 0; i < aree.length; i++) {
    aree[i].addEventListener('mousemove', mostra);
    aree[i].addEventListener('mouseleave', nascondi);
    aree[i].addEventListener('touchstart', mostra, { passive: true });
  }
  svg.addEventListener('touchstart', function (e) { if (!e.target.getAttribute('data-nome')) nascondi(); }, { passive: true });
})();
]]></script>"""


# --- utilità -----------------------------------------------------------------
def chiave(nome):
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z]", "", s)
    return {"VALLEDAOSTAVALLEEDAOSTE": "AOSTA", "VERBANOCUSIOOSSOLA": "VERBANIA",
            "PESAROEURBINO": "PESAROURBINO", "REGGIOCALABRIA": "REGGIODICALABRIA"}.get(s, s)


NOMI = {"AOSTA": "Aosta", "BOLZANOBOZEN": "Bolzano", "VERBANIA": "Verbano-Cusio-Ossola",
        "FORLICESENA": "Forlì-Cesena", "PESAROURBINO": "Pesaro e Urbino"}


def it(v, dec=1):
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def num(s):
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s.replace(".", ""))


def esc(s):
    return html.escape(s)


# --- grafica -------------------------------------------------------------------
def main(csv_path, geo_path, out_path):
    righe = list(csv.DictReader(open(csv_path, encoding="utf-8-sig"), delimiter=";"))
    italia = next(r for r in righe if r["Provincia"] == "ITALIA")
    dati = {chiave(r["Provincia"]): r for r in righe if r["Provincia"] != "ITALIA"}
    feats = json.load(open(geo_path, encoding="utf-8"))["features"]

    # area complessiva e posizioni
    W = 800
    MAP_X, MAP_W = 10, 520          # mappa a sinistra
    SIDE_X, SIDE_W = 560, 230       # classifica a destra
    TOP = 128                       # inizio della mappa
    lon0, lon1, lat0, lat1 = 6.55, 18.6, 36.55, 47.15
    kx = math.cos(math.radians(41.5))
    sc = MAP_W / ((lon1 - lon0) * kx)
    MAPH = (lat1 - lat0) * sc

    def P(x, y):
        return ((x - lon0) * kx * sc + MAP_X, TOP + (lat1 - y) * sc)

    def path(g):
        polys = [g] if isinstance(g, Polygon) else list(g.geoms)
        out = []
        for p in polys:
            if p.area < 0.0004:
                continue
            for ring in [p.exterior] + list(p.interiors):
                pts, last = [], None
                for x, y in ring.coords:
                    q = tuple(round(v, 1) for v in P(x, y))
                    if q != last:
                        pts.append(q)
                        last = q
                if len(pts) >= 4:
                    out.append("M" + "L".join(f"{x:g},{y:g}" for x, y in pts) + "Z")
        return "".join(out)

    province = []
    for f in feats:
        k = chiave(f["properties"]["prov_name"])
        r = dati[k]
        province.append(dict(k=k, nome=NOMI.get(k, f["properties"]["prov_name"]), g=shape(f["geometry"]),
                             q=num(r["Quota marchi cinesi %"]), cn=int(num(r["Marchi cinesi"])),
                             tot=int(num(r["Totale immatricolazioni"]))))
    assert len(province) == 107

    el = []  # elementi SVG, nell'ordine in cui vanno disegnati

    # intestazione: etichetta di sezione, titolo, sottotitolo
    el.append(f'<rect x="10" y="10" width="22" height="22" fill="{BLU}"/>'
              f'<text x="21" y="26" text-anchor="middle" font-size="13" font-weight="700" fill="#fff">{esc(SEZIONE_NUMERO)}</text>'
              f'<rect x="32.5" y="10.5" width="{len(SEZIONE_NOME) * 8 + 26}" height="21" fill="#fff" stroke="{BLU}" stroke-width="1.2"/>'
              f'<text x="44" y="25" font-size="10" font-weight="700" letter-spacing="0.6" fill="{BLU}">{esc(SEZIONE_NOME)}</text>')
    el.append(f'<text x="10" y="74" font-size="34" font-weight="700">{esc(TITOLO)}</text>')
    for i, riga in enumerate(SOTTOTITOLO):
        el.append(f'<text x="10" y="{98 + i * 17}" font-size="13">{esc(riga)}</text>')

    # mappa
    regioni = []
    for o in province:
        regioni.append(f'<path d="{path(o["g"].simplify(0.004, preserve_topology=True))}" '
                       f'fill="{COLORI[classe(o["q"])]}" data-nome="{esc(o["nome"])}" '
                       f'data-auto="{it(o["cn"], 0)}" data-quota="{it(o["q"])}%"/>')
    el.append(f'<g class="prov">{"".join(regioni)}</g>')

    # richiami: linea, cerchio bianco sul punto, testo
    per_k = {o["k"]: o for o in province}
    for k, (lx, ly, testo) in RICHIAMI.items():
        o = per_k[k]
        c = o["g"].representative_point()
        x, y = P(c.x, c.y)
        tx, ty = MAP_X + lx, TOP + ly
        # riquadro stimato del testo; la linea arriva al suo punto più vicino alla provincia
        bw = max(len(o["nome"]) * 7, max(len(t) for t in testo) * 5.4)
        x0, y0, x1, y1 = tx - 3, ty - 12, tx + bw, ty + 13 * len(testo) + 4
        ex, ey = min(max(x, x0), x1), min(max(y, y0), y1)
        el.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                  f'stroke="#555" stroke-width="0.8" pointer-events="none"/>')
        el.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#fff" stroke="#000" stroke-width="1.5" pointer-events="none"/>')
        blocco = [f'<tspan x="{tx:.1f}" dy="0" font-size="12" font-weight="700">{esc(o["nome"])}</tspan>']
        blocco += [f'<tspan x="{tx:.1f}" dy="13" font-size="10.5">{esc(t)}</tspan>' for t in testo]
        el.append(f'<text x="{tx:.1f}" y="{ty:.1f}" class="lab" pointer-events="none">{"".join(blocco)}</text>')

    # classifica a destra
    prime = sorted(province, key=lambda o: -o["q"])[:6]
    qmax = prime[0]["q"]
    y = TOP + 6
    el.append(f'<text x="{SIDE_X}" y="{y}" font-size="9.5" font-weight="700" letter-spacing="0.6">{TITOLO_CLASSIFICA}</text>')
    y += 26
    for i, o in enumerate(prime):
        col = BLU if i == 0 else "#000"
        barra = BLU if i == 0 else GRIGIO
        el.append(f'<text x="{SIDE_X}" y="{y}" font-size="12.5">{esc(o["nome"])}</text>'
                  f'<text x="{SIDE_X + SIDE_W}" y="{y}" font-size="12" text-anchor="end">{it(o["q"])}%</text>'
                  f'<text x="{SIDE_X}" y="{y + 20}" font-size="18" fill="{col}">{it(o["cn"], 0)}</text>'
                  f'<rect x="{SIDE_X}" y="{y + 26}" width="{SIDE_W * o["q"] / qmax:.1f}" height="4" fill="{barra}"/>')
        y += 52
    y += 4
    for riga in NOTA_CLASSIFICA:
        riga = riga.format(auto=it(int(num(italia["Marchi cinesi"])), 0),
                           quota=it(num(italia["Quota marchi cinesi %"])))
        el.append(f'<text x="{SIDE_X}" y="{y}" font-size="10.5">{esc(riga)}</text>')
        y += 14
    el.append(f'<text x="{SIDE_X}" y="{y + 10}" font-size="10.5" fill="#555">Le cifre grandi sono le auto</text>'
              f'<text x="{SIDE_X}" y="{y + 24}" font-size="10.5" fill="#555">di marchi cinesi immatricolate</text>')

    # legenda a classi in basso
    y = TOP + MAPH + 20
    el.append(f'<text x="10" y="{y:.0f}" font-size="9.5" font-weight="700" letter-spacing="0.6">{TITOLO_LEGENDA}</text>')
    lw = (W - 20 - 4 * 4) / 5
    for i, (c, lab) in enumerate(zip(COLORI, ETICHETTE_CLASSI)):
        x = 10 + i * (lw + 4)
        el.append(f'<rect x="{x:.1f}" y="{y + 8:.0f}" width="{lw:.1f}" height="9" fill="{c}"/>'
                  f'<text x="{x:.1f}" y="{y + 31:.0f}" font-size="10">{esc(lab)}</text>')

    # fonte
    y += 62
    for riga in FONTE:
        el.append(f'<text x="10" y="{y:.0f}" font-size="10.5">{esc(riga)}</text>')
        y += 15
    H = int(y + 4)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px;height:auto;display:block;margin:0 auto" font-family="'Source Serif 4', Georgia, serif">
<style>@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&amp;display=swap');
text{{font-family:'Source Serif 4',Georgia,serif}} text:not([fill]){{fill:#000}}
.lab{{paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}}
.prov path{{stroke:#fff;stroke-width:0.6}} .prov path:hover{{stroke:#000;stroke-width:1.5}}</style>
<rect width="{W}" height="{H}" fill="#fff"/>
{"".join(el)}
{TOOLTIP}
</svg>'''
    open(out_path, "w", encoding="utf-8").write(svg)
    print(f"{out_path}: {len(svg) // 1024} KB, {W}x{H}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
