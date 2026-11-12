"""Disegna la mappa SVG della quota di auto di marchi cinesi per provincia.

Uso:
    python src/mappa.py dati/quota_auto_cinesi_province_gen-ott2026.csv dati/province_2023.geojson output/mappa.svg

Il CSV ha separatore ';' e colonne Provincia, Totale immatricolazioni,
Marchi cinesi, Quota marchi cinesi %. Il GeoJSON sono i confini openpolis
con le 107 province usate dal MIT (versione 2023, con Sud Sardegna).
"""
import csv
import html
import json
import math
import re
import sys
import unicodedata

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

# --- testi -------------------------------------------------------------------
TITOLO = "Immatricolazioni di auto cinesi"
SOTTOTITOLO = [
    "Quota di auto nuove sul totale realizzate da brand cinesi per provincia di residenza del proprietario,",
    "periodo gennaio-ottobre 2026",
]
FONTE = [
    "Fonte: elaborazione su dati MIT – Centro elaborazione dati, pubblicati da UNRAE (unrae.it). Confini: openpolis su dati ISTAT",
    "Marchi cinesi considerati: BYD, MG (gruppo SAIC), Omoda e Jaecoo (gruppo Chery), Leapmotor",
]
MEDIA_ITALIA = 11.6
ETICHETTE = {  # provincia: (lato, spostamento verticale)
    "AOSTA": (1, -2.2), "BOLZANOBOZEN": (3.2, -0.6), "VICENZA": (1, 0.9),
    "NAPOLI": (-1, 0), "CATANIA": (1, 0), "ISERNIA": (1, -0.3), "TRIESTE": (1, 0),
}

# --- scala di colore continua (OKLab) tra i toni della redazione, 0-25% -----
STOPS = ["#f3f3f1", "#dfe3e0", "#8FACB0", "#527f86", "#202F3D"]
DMAX = 25.0


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
    t = max(0, min(1, v / DMAX)) * (len(LABS) - 1)
    i = min(int(t), len(LABS) - 2)
    f = t - i
    a, b = LABS[i], LABS[i + 1]
    return _to_hex(*[a[k] + (b[k] - a[k]) * f for k in range(3)])


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


# --- mappa ---------------------------------------------------------------------
def main(csv_path, geo_path, out_path):
    dati = {chiave(r["Provincia"]): r for r in csv.DictReader(open(csv_path, encoding="utf-8-sig"), delimiter=";")
            if r["Provincia"] != "ITALIA"}
    feats = json.load(open(geo_path, encoding="utf-8"))["features"]

    W, MX = 760, 30
    lon0, lon1, lat0, lat1 = 6.55, 18.6, 36.55, 47.15
    kx = math.cos(math.radians(41.5))
    sc = (W - 2 * MX) / ((lon1 - lon0) * kx)
    TOP = 20
    MAPH = (lat1 - lat0) * sc

    def P(x, y):
        return ((x - lon0) * kx * sc + MX, TOP + (lat1 - y) * sc)

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

    province, geoms = [], []
    for f in feats:
        k = chiave(f["properties"]["prov_name"])
        r = dati[k]
        g = shape(f["geometry"])
        geoms.append(g)
        province.append(dict(k=k, nome=NOMI.get(k, f["properties"]["prov_name"]), g=g,
                             q=num(r["Quota marchi cinesi %"]), cn=int(num(r["Marchi cinesi"])),
                             tot=int(num(r["Totale immatricolazioni"]))))
    assert len(province) == 107

    regioni = []
    for o in sorted(province, key=lambda o: o["q"]):
        tip = f"{o['nome']}: {it(o['cn'], 0)} auto di marchi cinesi su {it(o['tot'], 0)} immatricolazioni ({it(o['q'])}%)"
        regioni.append(f'<path d="{path(o["g"].simplify(0.004, preserve_topology=True))}" '
                       f'fill="{colore(round(o["q"], 1))}"><title>{html.escape(tip)}</title></path>')
    contorno = path(unary_union(geoms).simplify(0.004))

    etichette = []
    per_k = {o["k"]: o for o in province}
    for k, (lato, dy) in ETICHETTE.items():
        o = per_k[k]
        c = o["g"].representative_point()
        x, y = P(c.x, c.y)
        tx, ty = x + lato * 14, y + dy * 14
        verso = 1 if lato > 0 else -1
        anc = "start" if lato > 0 else "end"
        etichette.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#000"/>'
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{tx - verso * 3:.1f}" y2="{ty - 4:.1f}" stroke="#000" stroke-width="0.7"/>'
            f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{anc}" class="lab"><tspan font-weight="600">{o["nome"]}</tspan> {it(o["q"])}%</text>')

    # testi in basso: titolo, sottotitolo, legenda, fonte
    y = TOP + MAPH + 40
    testi = [f'<text x="{MX}" y="{y:.0f}" font-size="24" font-weight="700">{html.escape(TITOLO)}</text>']
    y += 28
    for riga in SOTTOTITOLO:
        testi.append(f'<text x="{MX}" y="{y:.0f}" font-size="15">{html.escape(riga)}</text>')
        y += 20
    y += 26
    LW, LH = 420, 12
    grad = "".join(f'<stop offset="{i / 20:.2f}" stop-color="{colore(DMAX * i / 20)}"/>' for i in range(21))
    testi.append(f'<defs><linearGradient id="g">{grad}</linearGradient></defs>')
    testi.append(f'<rect x="{MX}" y="{y:.0f}" width="{LW}" height="{LH}" fill="url(#g)" stroke="#e0e0de" stroke-width="0.5"/>')
    for v in range(0, 26, 5):
        x = MX + LW * v / DMAX
        lab = f"{v}%" if v < 25 else "25% e oltre"
        anc = "start" if v == 0 else "middle"
        testi.append(f'<line x1="{x:.1f}" y1="{y + LH:.0f}" x2="{x:.1f}" y2="{y + LH + 4:.0f}" stroke="#a0acad"/>'
                     f'<text x="{x:.1f}" y="{y + LH + 18:.0f}" class="small" text-anchor="{anc}">{lab}</text>')
    xa = MX + LW * MEDIA_ITALIA / DMAX
    testi.append(f'<line x1="{xa:.1f}" y1="{y - 3:.0f}" x2="{xa:.1f}" y2="{y + LH + 3:.0f}" stroke="#000" stroke-width="1.5"/>'
                 f'<text x="{xa + 5:.1f}" y="{y - 2:.0f}" class="small" font-size="12">Media Italia {it(MEDIA_ITALIA)}%</text>')
    y += LH + 48
    for riga in FONTE:
        testi.append(f'<text x="{MX}" y="{y:.0f}" class="foot">{html.escape(riga)}</text>')
        y += 16
    H = int(y + 6)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="'Source Serif 4', Georgia, serif">
<style>@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&amp;display=swap');
text{{fill:#000;font-family:'Source Serif 4',Georgia,serif}} .small{{font-size:13px}} .foot{{font-size:11.5px}}
.lab{{font-size:13px;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}}
.prov path{{stroke:#fff;stroke-width:0.5}} .prov path:hover{{stroke:#000;stroke-width:1.5}}</style>
<rect width="{W}" height="{H}" fill="#fff"/>
<g class="prov">{"".join(regioni)}</g>
<path d="{contorno}" fill="none" stroke="#a0acad" stroke-width="0.6"/>
{"".join(etichette)}
{"".join(testi)}
</svg>'''
    open(out_path, "w", encoding="utf-8").write(svg)
    print(f"{out_path}: {len(svg) // 1024} KB, {W}x{H}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
