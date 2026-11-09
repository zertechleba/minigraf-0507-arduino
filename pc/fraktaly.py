#!/usr/bin/env python3
"""
Fraktály pro Minigraf A 0507 / XY 4131 (L-systémy). Většina se nakreslí jedním tahem.

    py fraktaly.py --list                     přehled fraktálů
    py fraktaly.py koch                       soubor fraktal.hpgl + náhled fraktal.png
    py fraktaly.py drak --send                rovnou nakreslit (plot.py ve stejné složce)
    py fraktaly.py hilbert --order 5 --send   jiný řád (hrubší / jemnější)
    py fraktaly.py strom --plotter 4131 --send
    py fraktaly.py gosper --fill --send       roztáhnout na celou plochu (zkreslí tvar)

Obrazec se zvětší na celou kreslicí plochu (jako text_plot.py), natočí se tak, aby byl
co největší, a vycentruje. Program upozorní, když jsou úsečky kratší než 1 mm.
"""
import argparse, math, os, sys

VERSION = "0.5.4"
AREA = {"0507": (1520, 2140, 8), "4131": (1600, 2400, 10)}   # kroky od startu po HM, kroků/mm

# název: (popis, axiom, pravidla, úhel, kreslicí písmena, výchozí řád, počáteční směr)
FRACTALS = {
    "sierpinski": ("Sierpińského trojúhelník (šipková křivka), jeden tah", "A",
                   {"A": "B-A-B", "B": "A+B+A"}, 60, "AB", 7, 0),
    "koch":       ("Kochova vločka, jeden uzavřený tah", "F--F--F",
                   {"F": "F+F--F+F"}, 60, "F", 4, 0),
    "hilbert":    ("Hilbertova křivka, jeden tah", "A",
                   {"A": "+BF-AFA-FB+", "B": "-AF+BFB+FA-"}, 90, "F", 6, 0),
    "peano":      ("Peanova křivka, jeden tah", "X",
                   {"X": "XFYFX+F+YFXFY-F-XFYFX", "Y": "YFXFY-F-XFYFX+F+YFXFY"}, 90, "F", 4, 0),
    "drak":       ("Dračí křivka (Heighway), jeden tah", "FX",
                   {"X": "X+YF+", "Y": "-FX-Y"}, 90, "F", 12, 0),
    "levy":       ("Lévyho C křivka, jeden tah", "F",
                   {"F": "+F--F+"}, 45, "F", 12, 0),
    "gosper":     ("Gosperova křivka (flowsnake), jeden tah", "A",
                   {"A": "A-B--B+A++AA+B-", "B": "+A-BB--B-A++A+B"}, 60, "AB", 4, 0),
    "ctverec":    ("Kochův ostrov se čtvercovými zuby, jeden uzavřený tah", "F+F+F+F",
                   {"F": "F+F-F-FF+F+F-F"}, 90, "F", 3, 0),
    "strom":      ("fraktální rostlina (víc tahů)", "X",
                   {"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"}, 25, "F", 5, 65),
    "ker":        ("fraktální keř (víc tahů)", "F",
                   {"F": "FF+[+F-F-F]-[-F+F+F]"}, 22.5, "F", 4, 90),
}


def lsystem(name, order):
    desc, s, rules, ang, draw, _, start = FRACTALS[name]
    for _ in range(order):
        s = "".join(rules.get(c, c) for c in s)
    x = y = 0.0
    a = float(start)
    strokes = [[(x, y)]]
    stack = []
    for c in s:
        if c in draw:
            x += math.cos(math.radians(a)); y += math.sin(math.radians(a))
            strokes[-1].append((x, y))
        elif c == "+":
            a += ang
        elif c == "-":
            a -= ang
        elif c == "[":
            stack.append((x, y, a))
        elif c == "]":
            x, y, a = stack.pop()
            strokes.append([(x, y)])
    strokes = [st for st in strokes if len(st) > 1]
    nseg = sum(len(st) - 1 for st in strokes)
    return strokes, nseg


def fit(strokes, W, H, margin, stretch=False):
    pts = [p for st in strokes for p in st]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, y0 = min(xs), min(ys)
    bw, bh = max(max(xs) - x0, 1e-9), max(max(ys) - y0, 1e-9)
    best = None
    for rot in (False, True):
        w, h = (bh, bw) if rot else (bw, bh)
        k = min((W - 2 * margin) / w, (H - 2 * margin) / h)
        if best is None or k > best[0] * 1.0001:
            best = (k, rot)
    k, rot = best
    ku = kv = k
    if stretch:
        w, h = (bh, bw) if rot else (bw, bh)
        kx, ky = (W - 2 * margin) / w, (H - 2 * margin) / h
        ku, kv = (ky, kx) if rot else (kx, ky)
    out = []
    for st in strokes:
        o = []
        for x, y in st:
            u, v = (x - x0) * ku, (y - y0) * kv
            o.append((v, u) if rot else (u, v))
        out.append(o)
    mx = max(p[0] for st in out for p in st); my = max(p[1] for st in out for p in st)
    ox, oy = (W - mx) / 2, (H - my) / 2
    return [[(int(round(x + ox)), int(round(y + oy))) for x, y in st] for st in out], min(ku, kv)


def simplify(st):
    """Sloučí body na jedné přímce a vynechá opakované body."""
    out = [st[0]]
    for i in range(1, len(st)):
        p = st[i]
        if p == out[-1]:
            continue
        if len(out) >= 2:
            (x0, y0), (x1, y1) = out[-2], out[-1]
            if (x1 - x0) * (p[1] - y1) == (y1 - y0) * (p[0] - x1) and (x1 - x0) * (p[0] - x1) + (y1 - y0) * (p[1] - y1) > 0:
                out[-1] = p
                continue
        out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description="Fraktály pro Minigraf / XY 4131 (fraktaly.py %s)" % VERSION)
    ap.add_argument("typ", nargs="?", default="koch", help="druh fraktálu (viz --list)")
    ap.add_argument("--list", action="store_true", help="vypsat fraktály")
    ap.add_argument("--order", type=int, default=None, help="řád (jemnost); výchozí podle druhu")
    ap.add_argument("--plotter", choices=("0507", "4131"), default="0507")
    ap.add_argument("--margin", type=float, default=0, help="okraj navíc v mm")
    ap.add_argument("--fill", action="store_true", help="roztáhnout na celou plochu (zkreslí tvar)")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--port", default=None)
    ap.add_argument("--speed", type=int, default=None)
    ap.add_argument("-o", "--out", default="fraktal.hpgl")
    ap.add_argument("--version", action="version", version="fraktaly.py " + VERSION)
    a = ap.parse_args()

    if a.list:
        for n, f in FRACTALS.items():
            print("  %-11s %s (výchozí řád %d)" % (n, f[0], f[5]))
        return
    if a.typ not in FRACTALS:
        sys.exit("Neznámý fraktál '%s'. Seznam: py fraktaly.py --list" % a.typ)
    order = a.order if a.order is not None else FRACTALS[a.typ][5]
    W, H, spm = AREA[a.plotter]
    raw, nseg = lsystem(a.typ, order)
    strokes, k = fit(raw, W, H, a.margin * spm, a.fill)
    strokes = [simplify(st) for st in strokes]
    with open(a.out, "w") as f:
        f.write("IN;")
        for st in strokes:
            f.write("PU%d,%d;PD" % st[0] + ",".join("%d,%d" % p for p in st[1:]) + ";")
        f.write("PU;\n")
    pts = [p for st in strokes for p in st]
    seg_mm = k / spm
    print("%s, řád %d: %d úseček po %.2f mm, %d tah%s, %d bodů, %.0f x %.0f mm -> %s" % (
        FRACTALS[a.typ][0], order, nseg, seg_mm, len(strokes), "" if len(strokes) == 1 else "ů", len(pts),
        (max(p[0] for p in pts) - min(p[0] for p in pts)) / spm, (max(p[1] for p in pts) - min(p[1] for p in pts)) / spm, a.out))
    if seg_mm < 1.0:
        print("POZOR: úsečky kratší než 1 mm – s fixem 0,5 mm splynou, zvol menší --order.")
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8.3, 11.7))
        for st in strokes:
            ax.plot([p[0] for p in st], [p[1] for p in st], lw=0.4, color="navy")
        ax.add_patch(plt.Rectangle((0, 0), W, H, fill=False, ls="--", color="gray"))
        ax.set_aspect("equal"); ax.axis("off")
        png = os.path.splitext(a.out)[0] + ".png"
        fig.savefig(png, dpi=150, bbox_inches="tight"); print("Náhled:", png)
    except ImportError:
        pass
    if a.send:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import plot
        port = a.port or plot.DEFAULT_PORT
        ser, ver, found = plot.open_plotter(port)
        if found != a.plotter:
            plot.select_plotter(ser, a.plotter)
        with open(a.out) as f:
            lines = plot.to_lines(f.read(), 1.0)
        lines = plot.setup_lines(a.speed or 0, "", "", None, True) + lines
        print("Posílám %d řádků na %s ..." % (len(lines), port))
        plot.send_lines(ser, lines, ver)


if __name__ == "__main__":
    main()
