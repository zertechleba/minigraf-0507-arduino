#!/usr/bin/env python3
"""
Tisk obrázků pro ZX Spectrum + Minigraf (ovladač MZXR) na Minigrafu A 0507 / XY 4131.

Načte kazetový soubor .tap se programy v BASICu, které kreslí přes MZXR příkazy
    PRINT #7, ma,x,y; pd; ma,x,y; ...; pu
(ma = přesun na x,y v mm, pd = pero dolů, pu = pero nahoru), a převede je na náš plotter.
Takhle jsou uložené např. obrázky ze stránky cygnus.speccy.cz (tramvaj Tatra T3, smajlíci).

    py mzxr_tap.py data_basic_tramvaj_ckd_t3.tap                 výpis programů, soubor .hpgl + náhled .png
    py mzxr_tap.py data_basic_tramvaj_ckd_t3.tap --send          rovnou nakreslit (plot.py ve stejné složce)
    py mzxr_tap.py data_basic_tramvaj_ckd_t3.tap --pera --send   každý program jiným perem (počká na výměnu)
    py mzxr_tap.py tramvaj.tap --casti 1,3 --send                jen 1. a 3. program
    py mzxr_tap.py tramvaj.tap --meritko 1 --send                původní velikost v mm (jako na Spectru)
    py mzxr_tap.py tramvaj.tap --plotter 4131 --send

Výchozí je obrázek co největší na celou kreslicí plochu (zachová poměr stran, vycentruje).
Obrázek se nezrcadlí ani neotáčí: osa x MZXR = napříč papírem, osa y = podél papíru.
"""
import argparse, os, re, sys

VERSION = "0.5.11"
AREA = {"0507": (1520, 2140, 8), "4131": (1600, 2400, 10)}   # kroky od startu po HM, kroků/mm

TOK = ["RND", "INKEY$", "PI", "FN ", "POINT ", "SCREEN$ ", "ATTR ", "AT ", "TAB ", "VAL$ ", "CODE ", "VAL ",
       "LEN ", "SIN ", "COS ", "TAN ", "ASN ", "ACS ", "ATN ", "LN ", "EXP ", "INT ", "SQR ", "SGN ", "ABS ",
       "PEEK ", "IN ", "USR ", "STR$ ", "CHR$ ", "NOT ", "BIN ", "OR ", " AND ", "<=", ">=", "<>", " LINE ",
       " THEN ", " TO ", " STEP ", " DEF FN ", " CAT ", " FORMAT ", " MOVE ", " ERASE ", " OPEN #", " CLOSE #",
       " MERGE ", " VERIFY ", " BEEP ", " CIRCLE ", " INK ", " PAPER ", " FLASH ", " BRIGHT ", " INVERSE ",
       " OVER ", " OUT ", " LPRINT ", " LLIST ", " STOP ", " READ ", " DATA ", " RESTORE ", " NEW ", " BORDER ",
       " CONTINUE ", " DIM ", " REM ", " FOR ", " GO TO ", " GO SUB ", " INPUT ", " LOAD ", " LIST ", " LET ",
       " PAUSE ", " NEXT ", " POKE ", " PRINT ", " PLOT ", " RUN ", " SAVE ", " RANDOMIZE ", " IF ", " CLS ",
       " DRAW ", " CLEAR ", " RETURN ", " COPY "]


def tap_programs(data):
    """Vrátí [(jméno, [(číslo řádku, text)])] pro programy v BASICu v souboru .tap."""
    blocks, i = [], 0
    while i + 2 <= len(data):
        n = data[i] | data[i + 1] << 8
        blocks.append(data[i + 2:i + 2 + n]); i += 2 + n
    progs, k = [], 0
    while k + 1 < len(blocks):
        h = blocks[k]
        if len(h) >= 19 and h[0] == 0 and h[1] == 0:          # hlavička programu v BASICu
            name = h[2:12].decode("latin-1").strip()
            b = blocks[k + 1][1:-1]                            # bez příznaku a kontrolního součtu
            lines, p = [], 0
            while p + 4 <= len(b):
                ln = b[p] << 8 | b[p + 1]; L = b[p + 2] | b[p + 3] << 8
                body = b[p + 4:p + 4 + L]; p += 4 + L
                s, j = [], 0
                while j < len(body):
                    c = body[j]
                    if c == 0x0E:                              # skrytá binární hodnota čísla
                        j += 6; continue
                    if c == 0x0D:
                        break
                    s.append(TOK[c - 0xA5] if c >= 0xA5 else chr(c) if 32 <= c < 127 else " ")
                    j += 1
                lines.append((ln, "".join(s)))
            progs.append((name, lines)); k += 2
        else:
            k += 1
    return progs


NUM = r'(?:VAL\s*"\s*(-?[\d.]+)\s*"|(-?[\d.]+))'
RX = re.compile(r'\b(pu|pd)\b|\bma\s*,\s*' + NUM + r'\s*,\s*' + NUM, re.I)


def strokes_of(lines):
    """MZXR příkazy ma/pd/pu -> tahy v mm. Vrátí (tahy, počet neznámých řádků)."""
    strokes, pen, cur, pos, unknown = [], False, None, None, 0
    for ln, body in sorted(lines):
        if "#7" not in body.replace(" ", ""):
            continue
        found = False
        for t in RX.finditer(body):
            found = True
            if t.group(1):
                if t.group(1).lower() == "pu":
                    pen, cur = False, None
                else:
                    pen = True
                    cur = [pos] if pos else None
                    if cur:
                        strokes.append(cur)
            else:
                x = float(t.group(2) or t.group(3)); y = float(t.group(4) or t.group(5))
                pos = (x, y)
                if pen:
                    if cur is None:
                        cur = [pos]; strokes.append(cur)
                    else:
                        cur.append(pos)
        if not found:
            unknown += 1
    return [s for s in strokes if len(s) > 1], unknown


def main():
    ap = argparse.ArgumentParser(description="Obrázky pro ZX Spectrum + MZXR na Minigraf / XY 4131 (mzxr_tap.py %s)" % VERSION)
    ap.add_argument("tap", help="soubor .tap s programy v BASICu pro MZXR")
    ap.add_argument("--casti", default="", help="které programy kreslit, např. 1,3 (výchozí všechny)")
    ap.add_argument("--meritko", default="fit", help="fit = co největší (výchozí), číslo = měřítko (1 = původní mm)")
    ap.add_argument("--plotter", choices=("0507", "4131"), default="0507")
    ap.add_argument("--pera", action="store_true", help="každý program jiným perem – před každým se počká na výměnu")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--port", default=None)
    ap.add_argument("--speed", type=int, default=None)
    ap.add_argument("-o", "--out", default=None, help="výstupní .hpgl (výchozí podle jména .tap)")
    ap.add_argument("--version", action="version", version="mzxr_tap.py " + VERSION)
    a = ap.parse_args()

    with open(a.tap, "rb") as f:
        progs = tap_programs(f.read())
    if not progs:
        sys.exit("V souboru %s nejsou žádné programy v BASICu." % a.tap)
    parts = []
    for i, (name, lines) in enumerate(progs, 1):
        st, unk = strokes_of(lines)
        print("  %d. program \"%s\": %d řádků, %d tahů, %d bodů%s" % (
            i, name, len(lines), len(st), sum(len(s) for s in st), (", %d řádků bez MZXR příkazů" % unk) if unk else ""))
        parts.append((name, st))
    if a.casti:
        sel = [int(x) for x in a.casti.split(",") if x.strip()]
        parts = [parts[i - 1] for i in sel if 1 <= i <= len(parts)]
    parts = [(n, s) for n, s in parts if s]
    if not parts:
        sys.exit("Nic ke kreslení – programy neobsahují příkazy ma/pd/pu pro MZXR.")

    W, H, spm = AREA[a.plotter]
    pts = [p for _, st in parts for s in st for p in s]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    if a.meritko == "fit":
        k = min(W / ((x1 - x0) * spm), H / ((y1 - y0) * spm))
        ox = (W - (x1 - x0) * spm * k) / 2 - x0 * spm * k
        oy = (H - (y1 - y0) * spm * k) / 2 - y0 * spm * k
    else:
        k = float(a.meritko.replace(",", "."))
        ox = oy = 0.0
        if x1 * spm * k > W or y1 * spm * k > H:
            print("POZOR: v měřítku %g obrázek přesahuje kreslicí plochu – co přesahuje, ořízne firmware." % k)
    conv = lambda p: (int(round(p[0] * spm * k + ox)), int(round(p[1] * spm * k + oy)))
    steps = [(n, [[conv(p) for p in s] for s in st]) for n, st in parts]

    def hpgl(strokes, init):
        s = "IN;" if init else ""
        for st in strokes:
            s += "PU%d,%d;PD" % st[0] + ",".join("%d,%d" % p for p in st[1:]) + ";"
        return s + "PU;\n"

    out = a.out or os.path.splitext(os.path.basename(a.tap))[0] + ".hpgl"
    with open(out, "w") as f:
        f.write(hpgl([s for _, st in steps for s in st], True))
    print("Měřítko %.3g (%.0f x %.0f mm na papíře) -> %s" % (k, (x1 - x0) * k, (y1 - y0) * k, out))
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8.3, 11.7))
        colors = ["black", "red", "blue", "green", "orange", "purple"]
        for i, (_, st) in enumerate(steps):
            for s in st:
                ax.plot([p[0] for p in s], [p[1] for p in s], lw=0.4, color=colors[i % len(colors)])
        ax.add_patch(plt.Rectangle((0, 0), W, H, fill=False, ls="--", color="gray"))
        ax.set_aspect("equal"); ax.axis("off")
        png = os.path.splitext(out)[0] + ".png"
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
        lines = plot.setup_lines(a.speed or 0, "", "", None, True)
        if a.pera:
            for i, (name, st) in enumerate(steps):
                if i:
                    lines += ["PU;", "#PAUSE Vyměň pero pro %d. program \"%s\"" % (i + 1, name)]
                lines += plot.to_lines(hpgl(st, i == 0), 1.0)
        else:
            lines += plot.to_lines(hpgl([s for _, st in steps for s in st], True), 1.0)
        print("Posílám %d řádků na %s ..." % (len(lines), port))
        plot.send_lines(ser, lines, ver)


if __name__ == "__main__":
    main()
