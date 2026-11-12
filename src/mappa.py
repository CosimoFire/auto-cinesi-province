"""Disegna la mappa SVG interattiva della quota di auto di marchi cinesi per provincia.

Uso:
    python src/mappa.py dati/quota_auto_cinesi_province_gen-ott2026.csv dati/province_2023.geojson output/mappa.svg

Il CSV ha separatore ';' e colonne Provincia, Totale immatricolazioni,
Marchi cinesi, Quota marchi cinesi %. Il GeoJSON sono i confini openpolis
con le 107 province usate dal MIT (versione 2023, con Sud Sardegna).

Schema: etichetta di sezione, titolo, sottotitolo e legenda continua in alto;
mappa con le prime 5 province numerate e commentate; fonte in basso.
Tooltip al passaggio del mouse.
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
TITOLO_LEGENDA = "QUOTA DI AUTO DI MARCHI CINESI"
TITOLO_TOP = "TOP 5 PER IMMATRICOLAZIONI IN %"
NOTA_TOP = "Le prime 5 province per quota di auto cinesi sul totale"
MEDIA_ITALIA = 11.6
FONTE = [
    "Fonte: elaborazione su dati MIT – Centro elaborazione dati, pubblicati da UNRAE (unrae.it); confini openpolis su dati ISTAT",
    "Marchi cinesi considerati: BYD, MG (gruppo SAIC), Omoda e Jaecoo (gruppo Chery), Leapmotor",
]

# Top 5: provincia -> (x, y dell'etichetta in px dall'angolo in alto a sinistra della mappa,
# righe di commento). Il numero d'ordine è calcolato dai dati. La linea parte dalla provincia
# e arriva al bordo più vicino del testo.
RICHIAMI = {
    "AOSTA": (-92, 8, ["La quota più alta. Pesano", "le flotte di noleggio"]),
    "BOLZANOBOZEN": (320, 0, ["Anche qui pesano", "le flotte di noleggio"]),
    "VICENZA": (400, 150, ["Sei auto cinesi su dieci", "sono BYD"]),
    "NAPOLI": (170, 470, ["Due auto cinesi su tre", "sono Leapmotor"]),
    "CATANIA": (520, 640, ["Più di metà sono", "Leapmotor"]),
}

# --- scala di colore continua (OKLab) tra i 5 toni di blu, da 0% a 25% ---------
STOPS = ["#f1f1ef", "#cfe6f9", "#83c3ef", "#009cdf", "#005f8a"]
DMAX = 25.0
BLU = "#009cdf"


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c):
    c = max(0, min(1, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _to_lab(h):
    r, g, b = [_lin(int(h[i:i + 2], 16)) for i in (1, 3, 5)]
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _to_hex(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    return "#%02x%02x%02x" % tuple(round(_gam(v) * 255) for v in rgb)


LABS = [_to_lab(h) for h in STOPS]


def colore(v):
    """Colore per una quota in %, interpolato in modo continuo tra STOPS (0% -> 25% e oltre)."""
    t = max(0, min(1, v / DMAX)) * (len(LABS) - 1)
    i = min(int(t), len(LABS) - 2)
    f = t - i
    a, b = LABS[i], LABS[i + 1]
    return _to_hex(*[a[k] + (b[k] - a[k]) * f for k in range(3)])


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


def marcatore(x, y, n):
    """Cerchio bianco numerato sulla provincia."""
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="#fff" stroke="#000" stroke-width="1.5" pointer-events="none"/>'
            f'<text x="{x:.1f}" y="{y + 3.6:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" pointer-events="none">{n}</text>')


# --- grafica -------------------------------------------------------------------
def main(csv_path, geo_path, out_path):
    righe = list(csv.DictReader(open(csv_path, encoding="utf-8-sig"), delimiter=";"))
    dati = {chiave(r["Provincia"]): r for r in righe if r["Provincia"] != "ITALIA"}
    feats = json.load(open(geo_path, encoding="utf-8"))["features"]

    W = 800
    MAP_X, MAP_W = 100, 600        # mappa al centro, margini per le etichette
    TOP = 210                      # inizio della mappa (sopra: intestazione e legenda)
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
    top5 = sorted(province, key=lambda o: -o["q"])[:5]
    assert {o["k"] for o in top5} == set(RICHIAMI), "RICHIAMI deve contenere le prime 5 province"

    el = []

    # intestazione: etichetta di sezione, titolo, sottotitolo
    el.append(f'<rect x="10" y="10" width="22" height="22" fill="{BLU}"/>'
              f'<text x="21" y="26" text-anchor="middle" font-size="13" font-weight="700" fill="#fff">{esc(SEZIONE_NUMERO)}</text>'
              f'<rect x="32.5" y="10.5" width="{len(SEZIONE_NOME) * 8 + 26}" height="21" fill="#fff" stroke="{BLU}" stroke-width="1.2"/>'
              f'<text x="44" y="25" font-size="10" font-weight="700" letter-spacing="0.6" fill="{BLU}">{esc(SEZIONE_NOME)}</text>')
    el.append(f'<text x="10" y="74" font-size="34" font-weight="700">{esc(TITOLO)}</text>')
    for i, riga in enumerate(SOTTOTITOLO):
        el.append(f'<text x="10" y="{98 + i * 17}" font-size="13">{esc(riga)}</text>')

    # legenda continua in alto
    y = 150
    LW, LH = 400, 10
    el.append(f'<text x="10" y="{y}" font-size="9.5" font-weight="700" letter-spacing="0.6">{TITOLO_LEGENDA}</text>')
    grad = "".join(f'<stop offset="{i / 20:.2f}" stop-color="{colore(DMAX * i / 20)}"/>' for i in range(21))
    el.append(f'<defs><linearGradient id="g">{grad}</linearGradient></defs>'
              f'<rect x="10" y="{y + 16}" width="{LW}" height="{LH}" fill="url(#g)"/>')
    for v in range(0, 26, 5):
        x = 10 + LW * v / DMAX
        lab = f"{v}%" if v < 25 else "25% e oltre"
        anc = "start" if v == 0 else "middle"
        el.append(f'<line x1="{x:.1f}" y1="{y + 16 + LH}" x2="{x:.1f}" y2="{y + 20 + LH}" stroke="#a0acad"/>'
                  f'<text x="{x:.1f}" y="{y + 38 + LH}" font-size="10" text-anchor="{anc}">{lab}</text>')
    xa = 10 + LW * MEDIA_ITALIA / DMAX
    el.append(f'<line x1="{xa:.1f}" y1="{y + 12}" x2="{xa:.1f}" y2="{y + 20 + LH}" stroke="#000" stroke-width="1.5"/>'
              f'<text x="{xa + 5:.1f}" y="{y + 12}" font-size="10">Media Italia {it(MEDIA_ITALIA)}%</text>')

    # spiegazione dei numeri della Top 5, accanto alla legenda
    xt = 470
    el.append(f'<text x="{xt}" y="{y}" font-size="9.5" font-weight="700" letter-spacing="0.6">{TITOLO_TOP}</text>')
    el.append(marcatore(xt + 8, y + 21, "1"))
    el.append(f'<text x="{xt + 24}" y="{y + 25}" font-size="10.5">{esc(NOTA_TOP)}</text>')

    # mappa
    regioni = []
    for o in province:
        regioni.append(f'<path d="{path(o["g"].simplify(0.004, preserve_topology=True))}" '
                       f'fill="{colore(round(o["q"], 1))}" data-nome="{esc(o["nome"])}" '
                       f'data-auto="{it(o["cn"], 0)}" data-quota="{it(o["q"])}%"/>')
    el.append(f'<g class="prov">{"".join(regioni)}</g>')

    # Top 5: linea, cerchio numerato, nome con quota e commento
    for n, o in enumerate(top5, 1):
        lx, ly, testo = RICHIAMI[o["k"]]
        c = o["g"].representative_point()
        x, y = P(c.x, c.y)
        tx, ty = MAP_X + lx, TOP + ly
        titolo = f'{n}. {o["nome"]} {it(o["q"])}%'
        bw = max(len(titolo) * 7, max(len(t) for t in testo) * 5.4)
        x0, y0, x1, y1 = tx - 3, ty - 12, tx + bw, ty + 13 * len(testo) + 4
        ex, ey = min(max(x, x0), x1), min(max(y, y0), y1)
        el.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#555" stroke-width="0.8" pointer-events="none"/>')
        el.append(marcatore(x, y, n))
        blocco = [f'<tspan x="{tx:.1f}" dy="0" font-size="12.5" font-weight="700">{esc(titolo)}</tspan>']
        blocco += [f'<tspan x="{tx:.1f}" dy="13.5" font-size="10.5">{esc(t)}</tspan>' for t in testo]
        el.append(f'<text x="{tx:.1f}" y="{ty:.1f}" class="lab" pointer-events="none">{"".join(blocco)}</text>')

    # fonte
    y = TOP + MAPH + 26
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
