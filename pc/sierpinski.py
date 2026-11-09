#!/usr/bin/env python3
"""
Sierpińského trojúhelník jedním tahem (Sierpińského šipková křivka) pro Minigraf A 0507 / XY 4131.

Křivka řádu N projde celý trojúhelník jednou nepřerušenou čarou (3^N úseček),
pero se zvedne jen na začátku a na konci. Trojúhelník se zvětší na celou
kreslicí plochu (stejnou jako u text_plot.py) a vycentruje.

    py sierpinski.py                     soubor sierpinski.hpgl + náhled sierpinski.png
    py sierpinski.py --send              rovnou nakreslit (plot.py ve stejné složce)
    py sierpinski.py --order 6 --send    hrubší (řád 5-8, výchozí 7)
    py sierpinski.py --plotter 4131 --send
    py sierpinski.py --speed 40 --send   pomaleji (ostré rohy)
    py sierpinski.py --fill --send       roztáhnout na celou plochu (už ne rovnostranný)
"""
import argparse, math, os, sys

VERSION = "0.5.11"
AREA = {"0507": (1520, 2140, 8), "4131": (1600, 2400, 10)}   # kroky od startu po HM, kroků/mm


def arrowhead(order):
    """Vrcholy šipkové křivky v jednotkách délky úsečky (L-systém A -> B-A-B, B -> A+B+A)."""
    s = "A"
    for _ in range(order):
        s = "".join({"A": "B-A-B", "B": "A+B+A"}.get(c, c) for c in s)
    ang = 0 if order % 2 == 0 else 60     # aby trojúhelník stál na základně
    x = y = 0.0
    pts = [(x, y)]
    for c in s:
        if c in "AB":
            x += math.cos(math.radians(ang)); y += math.sin(math.radians(ang))
            pts.append((x, y))
        elif c == "+":
            ang += 60
        else:
            ang -= 60
    return pts


def fit(pts, W, H, margin, stretch=False):
    """Otočí trojúhelník základnou podél delší strany plochy a zvětší na maximum.
    stretch=True: roztáhne ho na celou plochu (už nebude rovnostranný)."""
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    best = None
    for rot in (False, True):            # rot: základna podél osy Y (dlouhá strana papíru)
        w, h = (bh, bw) if rot else (bw, bh)
        k = min((W - 2 * margin) / w, (H - 2 * margin) / h)
        if best is None or k > best[0]:
            best = (k, rot)
    k, rot = best
    ku = kv = k
    if stretch:
        w, h = (bh, bw) if rot else (bw, bh)
        kx, ky = (W - 2 * margin) / w, (H - 2 * margin) / h
        ku, kv = (ky, kx) if rot else (kx, ky)
    out = []
    for x, y in pts:
        u, v = (x - min(xs)) * ku, (y - min(ys)) * kv
        X, Y = (v, u) if rot else (u, v)
        out.append((X, Y))
    ox = (W - max(p[0] for p in out)) / 2; oy = (H - max(p[1] for p in out)) / 2
    return [(int(round(x + ox)), int(round(y + oy))) for x, y in out], k


def main():
    ap = argparse.ArgumentParser(description="Sierpińského trojúhelník jedním tahem (sierpinski.py %s)" % VERSION)
    ap.add_argument("--order", type=int, default=7, help="řád křivky 5-8 (výchozí 7)")
    ap.add_argument("--plotter", choices=("0507", "4131"), default="0507")
    ap.add_argument("--margin", type=float, default=0, help="okraj navíc v mm (výchozí 0 = celá plocha)")
    ap.add_argument("--fill", action="store_true", help="roztáhnout na celou plochu (trojúhelník nebude rovnostranný)")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--port", default=None)
    ap.add_argument("--speed", type=int, default=None)
    ap.add_argument("-o", "--out", default="sierpinski.hpgl")
    ap.add_argument("--version", action="version", version="sierpinski.py " + VERSION)
    a = ap.parse_args()

    W, H, spm = AREA[a.plotter]
    pts, k = fit(arrowhead(a.order), W, H, a.margin * spm, a.fill)
    # sloučit body ležící na jedné přímce (dlouhé rovné úseky = méně příkazů)
    simp = [pts[0]]
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = simp[-1], pts[i], pts[i + 1]
        if (x1 - x0) * (y2 - y1) != (y1 - y0) * (x2 - x1):
            simp.append(pts[i])
    simp.append(pts[-1])
    with open(a.out, "w") as f:
        f.write("IN;PU%d,%d;PD" % simp[0])
        f.write(",".join("%d,%d" % p for p in simp[1:]))
        f.write(";PU;\n")
    seg_mm = k / spm                      # u --fill délka ve směru základny
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    print("Řád %d: %d úseček po %.2f mm, %d bodů, trojúhelník %.0f x %.0f mm -> %s"
          % (a.order, 3 ** a.order, seg_mm, len(simp), (max(xs) - min(xs)) / spm, (max(ys) - min(ys)) / spm, a.out))
    if seg_mm < 1.0:
        print("POZOR: úsečky kratší než 1 mm – s fixem 0,5 mm splynou, zvol menší --order.")
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8.3, 11.7))
        ax.plot([p[0] for p in pts], [p[1] for p in pts], lw=0.3, color="navy")
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
