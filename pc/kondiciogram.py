#!/usr/bin/env python3
"""
Kondiciogram (biorytmy) pro Minigraf A 0507 / XY 4131 – jako za časů osmibitů.

Podle data narození spočítá na zvolený měsíc tři biorytmy:
    F  fyzický         23 dní  (síla, výdrž, zdraví)          plná čára
    P  psychický       28 dní  (nálada, city, kreativita)      čárkovaná čára
    I  intelektuální   33 dní  (paměť, logika, soustředění)     tečkovaná čára
Pod grafem je tabulka po dnech se znaménky:
    +  kladná fáze (křivka nad osou)
    -  záporná fáze (křivka pod osou)
    *  kritický den (křivka protíná osu – den nejistoty)

    py kondiciogram.py                              výchozí narození (NAROZENI_DEFAULT), aktuální měsíc
    py kondiciogram.py 12/2026 --send               výchozí narození, zvolený měsíc
    py kondiciogram.py 12.5.1965                    jiné datum narození, aktuální měsíc -> kondiciogram.hpgl + .png
    py kondiciogram.py 12.5.1965 11/2026 --send     zvolený měsíc a rovnou nakreslit
    py kondiciogram.py 12.5.1965 --jmeno "Zdeněk Kotrba" --send
    py kondiciogram.py 12.5.1965 --pera --send      každá křivka jiným perem (program počká na výměnu)
    py kondiciogram.py 12.5.1965 --plotter 4131 --send
    py kondiciogram.py 12.5.1965 --ps "Jiný dodatek" --send   jiný P.S. (výchozí je hláška o elektrónce E13)
    py kondiciogram.py 12.5.1965 --bez-ps --send             bez P.S.

Biorytmy jsou zábava z 80. let, ne věda – vědecky se nepotvrdily.
"""
import argparse, calendar, datetime as dt, math, os, sys

VERSION = "0.5.7"
AREA = {"0507": (1520, 2140, 8), "4131": (1600, 2400, 10)}   # kroky od startu po HM, kroků/mm
CYCLES = [("F", "fyzický", 23, "plná"), ("P", "psychický", 28, "čárkovaná"), ("I", "intelektuální", 33, "tečkovaná")]
# výchozí datum narození – když se v příkazu žádné nezadá
NAROZENI_DEFAULT = "18.2.1975"
# dodatek tištěný na každý kondiciogram (změní --ps "…", vypne --bez-ps)
PS_DEFAULT = "„Přéčinó byla chybná elektrónka E13 z našeho podniku Katóda Olomóc.“"
MESICE = ["leden", "únor", "březen", "duben", "květen", "červen", "červenec", "srpen", "září", "říjen",
          "listopad", "prosinec"]
DNY = ["po", "út", "st", "čt", "pá", "so", "ne"]


def parse_date(s):
    for sep in ".-/":
        s = s.replace(sep, ".")
    d, m, y = (int(x) for x in s.split("."))
    return dt.date(y, m, d)


def parse_month(s):
    for sep in "./-":
        s = s.replace(sep, ".")
    m, y = (int(x) for x in s.split("."))
    return y, m


def value(cycle, days):
    return math.sin(2 * math.pi * days / cycle)


def symbol(cycle, days):
    """+ / - / * pro den (kritický = křivka během dne protne osu)."""
    a, b = value(cycle, days), value(cycle, days + 1)
    if a == 0 or (a > 0) != (b > 0):
        return "*"
    return "+" if a > 0 else "-"


class Page:
    """Kreslení v mm na stránce na výšku (0,0 vlevo dole); převod na kroky plotteru."""

    def __init__(self, W, H, spm):
        self.W, self.H, self.spm = W / spm, H / spm, spm
        self.layers = {}                       # vrstva -> seznam tahů (v mm)

    def line(self, pts, layer="text"):
        self.layers.setdefault(layer, []).append(list(pts))

    def dashed(self, pts, on, off, layer):
        """Přerušovaná čára po křivce (on/off v mm)."""
        seg, pos, draw, cur = [], 0.0, True, [pts[0]]
        lim = on
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            t = 0.0
            while L - t > 1e-9:
                step = min(lim - pos, L - t)
                t += step; pos += step
                p = (x0 + (x1 - x0) * t / L, y0 + (y1 - y0) * t / L)
                if draw:
                    cur.append(p)
                if pos >= lim - 1e-9:
                    if draw and len(cur) > 1:
                        seg.append(cur)
                    draw = not draw
                    pos, lim = 0.0, (on if draw else off)
                    cur = [p]
        if draw and len(cur) > 1:
            seg.append(cur)
        for s in seg:
            self.line(s, layer)

    def text(self, s, x, y, size, align="left", layer="text"):
        import text_plot as t
        t.FONT_STYLE = "blok"
        st, w = t.text_strokes(s)
        k = size / 6.0
        if align == "center":
            x -= w * k / 2
        elif align == "right":
            x -= w * k
        for p in st:
            self.line([(x + u * k, y + v * k) for u, v in p], layer)


def build(birth, year, month, name, today, W, H, spm, ps=""):
    pg = Page(W, H, spm)
    sc = min(pg.W / 190.0, pg.H / 267.5)       # rozvržení je pro Minigraf, XY 4131 se zmenší
    S = lambda v: v * sc
    top = pg.H
    nd = calendar.monthrange(year, month)[1]
    first = dt.date(year, month, 1)
    d0 = (first - birth).days

    # záhlaví
    pg.text("KONDICIOGRAM", pg.W / 2, top - S(12), S(8), "center")
    info = "Narozen(a) %d. %d. %d" % (birth.day, birth.month, birth.year)
    if name:
        info = name + ", " + info.lower()
    pg.text(info, pg.W / 2, top - S(20), S(3.5), "center")
    pg.text("%s %d,  %d. až %d. den života" % (MESICE[month - 1].capitalize(), year, d0 + 1, d0 + nd),
            pg.W / 2, top - S(26), S(3), "center")

    # graf
    gx0, gx1 = S(18), pg.W - S(6)
    gy_mid, amp = top - S(88), S(50)
    colw = (gx1 - gx0) / nd
    pg.line([(gx0, gy_mid - amp), (gx1, gy_mid - amp), (gx1, gy_mid + amp), (gx0, gy_mid + amp), (gx0, gy_mid - amp)])
    pg.line([(gx0, gy_mid), (gx1, gy_mid)])                       # osa 0
    for frac in (0.5, -0.5):                                      # pomocné značky 50 %
        y = gy_mid + frac * amp
        pg.line([(gx0, y), (gx0 + S(2), y)]); pg.line([(gx1 - S(2), y), (gx1, y)])
    pg.text("+", gx0 - S(4), gy_mid + amp - S(4), S(3.5), "center")
    pg.text("0", gx0 - S(4), gy_mid - S(1.5), S(3), "center")
    pg.text("-", gx0 - S(4), gy_mid - amp + S(1), S(3.5), "center")
    for d in range(nd):                                           # dny
        xc = gx0 + (d + 0.5) * colw
        pg.line([(xc, gy_mid - S(1)), (xc, gy_mid + S(1))])
        wd = dt.date(year, month, d + 1).weekday()
        if d + 1 == 1 or (d + 1) % 5 == 0:
            pg.text(str(d + 1), xc, gy_mid - amp - S(5), S(2.5), "center")
        if wd == 6:                                               # neděle: tečkovaná svislice
            pg.dashed([(xc, gy_mid - amp), (xc, gy_mid + amp)], S(0.6), S(3), "text")
    if today and today.year == year and today.month == month:     # dnešek
        xc = gx0 + (today.day - 0.5) * colw
        pg.line([(xc, gy_mid - amp - S(1)), (xc, gy_mid + amp + S(1))])
        pg.text("dnes", xc, gy_mid + amp + S(2), S(2.5), "center")

    # křivky: hodnota v poledne dne d je ve středu sloupce
    for code, nm, per, style in CYCLES:
        pts = []
        n = nd * 8
        for i in range(n + 1):
            t = i / 8.0                                           # dny od začátku 1. dne
            x = gx0 + t * colw
            v = value(per, d0 + t - 0.5)
            pts.append((x, gy_mid + v * amp * 0.95))
        layer = "krivka_" + code
        if style == "plná":
            pg.line(pts, layer)
        elif style == "čárkovaná":
            pg.dashed(pts, S(3), S(1.5), layer)
        else:
            pg.dashed(pts, S(0.7), S(1.2), layer)
        # popisek u konce křivky
        pg.text(code, gx1 + S(1.5), pts[-1][1] - S(1.2), S(2.5), "left", layer)

    # tabulka znamének
    ty = gy_mid - amp - S(18)
    rowh = S(7)
    pg.text("den", gx0 - S(2), ty + S(1), S(2.5), "right")
    for d in range(nd):
        xc = gx0 + (d + 0.5) * colw
        pg.text(str(d + 1), xc, ty + S(1), S(2) if d >= 9 else S(2.5), "center")
        wd = dt.date(year, month, d + 1).weekday()
        pg.text(DNY[wd][0].upper(), xc, ty - S(4), S(2), "center")
    for r, (code, nm, per, style) in enumerate(CYCLES):
        y = ty - S(11) - r * rowh
        pg.text(code, gx0 - S(2), y, S(3), "right")
        for d in range(nd):
            xc = gx0 + (d + 0.5) * colw
            pg.text(symbol(per, d0 + d), xc, y, S(3), "center")
    # mřížka tabulky
    yt, yb = ty + S(4.5), ty - S(11) - 2 * rowh - S(2)
    pg.line([(gx0, yt), (gx1, yt), (gx1, yb), (gx0, yb), (gx0, yt)])
    pg.line([(gx0, ty - S(6.5)), (gx1, ty - S(6.5))])
    for d in range(1, nd):
        x = gx0 + d * colw
        pg.line([(x, yt), (x, yb)])

    # legenda
    ly = yb - S(12)
    for r, (code, nm, per, style) in enumerate(CYCLES):
        y = ly - r * S(7)
        pg.text("%s  %s cyklus %d dní, %s čára" % (code, nm, per, style), gx0, y, S(3))
    y = ly - 3 * S(7) - S(4)
    pg.text("+ kladná fáze    - záporná fáze    * kritický den", gx0, y, S(3))
    pg.text("Kladná fáze: dny plné síly. Záporná: odpočinek, regenerace.", gx0, y - S(6), S(2.5))
    pg.text("Kritický den: přechod přes nulu, den nejistoty a opatrnosti.", gx0, y - S(10.5), S(2.5))
    if ps:                                                        # P.S. pod legendu, zalomené na šířku stránky
        import text_plot as t
        t.FONT_STYLE = "blok"
        size = S(3)
        lines = t.wrap("P.S. " + ps, (gx1 - gx0) / (size / 6.0))
        for i, ln in enumerate(lines):
            pg.text(ln, gx0, y - S(20) - i * S(5.5), size)
    pg.text("Vytištěno %d. %d. %d na plotteru, kondiciogram.py %s" % (today.day, today.month, today.year, VERSION),
            pg.W / 2, S(3), S(2), "center")
    return pg


def to_steps(pg, layers):
    out = []
    for lay in layers:
        for st in pg.layers.get(lay, []):
            pts = []
            for x, y in st:
                p = (int(round(min(max(x * pg.spm, 0), pg.W * pg.spm))), int(round(min(max(y * pg.spm, 0), pg.H * pg.spm))))
                if not pts or p != pts[-1]:
                    pts.append(p)
            if len(pts) == 1:
                pts.append(pts[0])
            out.append(pts)
    return out


def hpgl(strokes, init=True):
    s = "IN;" if init else ""
    for st in strokes:
        s += "PU%d,%d;PD" % st[0] + ",".join("%d,%d" % p for p in st[1:]) + ";"
    return s + "PU;\n"


def main():
    ap = argparse.ArgumentParser(description="Kondiciogram – biorytmy na plotter (kondiciogram.py %s)" % VERSION)
    ap.add_argument("datum", nargs="*", help="datum narození (např. 12.5.1965, výchozí %s) a/nebo měsíc "
                    "a rok (např. 11/2026, výchozí aktuální) – v libovolném pořadí" % NAROZENI_DEFAULT)
    ap.add_argument("--jmeno", default="", help="jméno do záhlaví")
    ap.add_argument("--ps", default=PS_DEFAULT, help="dodatek P.S. pod legendou (výchozí hláška o elektrónce E13)")
    ap.add_argument("--bez-ps", action="store_true", help="nepsat dodatek P.S.")
    ap.add_argument("--plotter", choices=("0507", "4131"), default="0507")
    ap.add_argument("--pera", action="store_true", help="křivky různými pery – před každou se počká na výměnu")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--port", default=None)
    ap.add_argument("--speed", type=int, default=None)
    ap.add_argument("-o", "--out", default="kondiciogram.hpgl")
    ap.add_argument("--version", action="version", version="kondiciogram.py " + VERSION)
    a = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    today = dt.date.today()
    birth_s, month_s = NAROZENI_DEFAULT, None
    for arg in a.datum:                    # 3 části = datum narození, 2 části = měsíc/rok
        parts = arg.replace("/", ".").replace("-", ".").split(".")
        if len(parts) == 3:
            birth_s = arg
        elif len(parts) == 2:
            month_s = arg
        else:
            sys.exit("Nerozumím '%s'. Příklad: py kondiciogram.py 12.5.1965 11/2026" % arg)
    try:
        birth = parse_date(birth_s)
        year, month = parse_month(month_s) if month_s else (today.year, today.month)
    except (ValueError, TypeError):
        sys.exit("Špatné datum. Příklad: py kondiciogram.py 12.5.1965 11/2026")
    if dt.date(year, month, 1) < birth.replace(day=1):
        sys.exit("Zvolený měsíc je před datem narození.")
    W, H, spm = AREA[a.plotter]
    pg = build(birth, year, month, a.jmeno, today, W, H, spm, "" if a.bez_ps else a.ps)
    layers = ["text", "krivka_F", "krivka_P", "krivka_I"]
    all_strokes = to_steps(pg, layers)
    with open(a.out, "w") as f:
        f.write(hpgl(all_strokes))
    nd = calendar.monthrange(year, month)[1]
    d0 = (dt.date(year, month, 1) - birth).days
    print("Kondiciogram %s %d pro narozené %s: %d tahů -> %s" % (MESICE[month - 1], year, birth.strftime("%d.%m.%Y"),
                                                              len(all_strokes), a.out))
    for code, nm, per, _ in CYCLES:
        print("  %s %-13s %s" % (code, nm, " ".join(symbol(per, d0 + d) for d in range(nd))))
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8.3, 11.7))
        colors = {"text": "black", "krivka_F": "red", "krivka_P": "blue", "krivka_I": "green"}
        for lay in layers:
            for st in to_steps(pg, [lay]):
                ax.plot([p[0] for p in st], [p[1] for p in st], lw=0.6, color=colors[lay])
        ax.add_patch(plt.Rectangle((0, 0), W, H, fill=False, ls="--", color="gray"))
        ax.set_aspect("equal"); ax.axis("off")
        png = os.path.splitext(a.out)[0] + ".png"
        fig.savefig(png, dpi=150, bbox_inches="tight"); print("Náhled:", png)
    except ImportError:
        pass
    if a.send:
        import plot
        port = a.port or plot.DEFAULT_PORT
        ser, ver, found = plot.open_plotter(port)
        if found != a.plotter:
            plot.select_plotter(ser, a.plotter)
        lines = plot.setup_lines(a.speed or 0, "", "", None, True)
        if a.pera:
            names = {"text": "text a mřížka (černé pero)", "krivka_F": "F – fyzická křivka (např. červené pero)",
                     "krivka_P": "P – psychická křivka (např. modré pero)", "krivka_I": "I – intelektuální křivka (např. zelené pero)"}
            for i, lay in enumerate(layers):
                if i:
                    lines.append("PU;")
                    lines.append("#PAUSE Vyměň pero: " + names[lay])
                lines += plot.to_lines(hpgl(to_steps(pg, [lay]), init=(i == 0)), 1.0)
        else:
            lines += plot.to_lines(hpgl(all_strokes), 1.0)
        print("Posílám %d řádků na %s ..." % (len(lines), port))
        plot.send_lines(ser, lines, ver)


if __name__ == "__main__":
    main()
