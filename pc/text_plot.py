#!/usr/bin/env python3
"""
Velký nápis přes celou šířku A4 (na šířku) pro Minigraf A 0507 a XY 4131.

Vytvoří HPGL soubor v krocích plotteru (Minigraf 0,125 mm, XY 4131 0,1 mm)
a s --send ho rovnou nakreslí:
    py text_plot.py "AHOJ" --frame --bold 3 --send
nebo jen soubor a kreslení zvlášť:
    py text_plot.py "AHOJ" --frame --bold 3
    py plot.py napis.hpgl --scale 1

Volby:
    -o SOUBOR     výstupní soubor (výchozí napis.hpgl)
    --bold N      ztučnění: každé písmeno se obtáhne N-krát (1-4)
    --font psane  písmo jako psané rukou (Hersheyho psací písmo, potřebuje soubor
                  hershey_script.py ve stejné složce); výchozí --font blok
    --frame       dvojitý rámeček kolem stránky
    --star        osmicípá hvězda nad nápisem
    --flip        otočí výkres o 180° (když vyjde vzhůru nohama)
    --margin 8    okraj uvnitř kreslicí plochy v mm (výchozí 8 u nápisu, 5 u textu;
                  rámeček je 7 mm vně textu, nejméně 1 mm od kraje plochy)
    --preview     uloží náhled napis.png (potřebuje matplotlib)
    --send        hned poslat na plotter (port COM4, plot.py musí být ve stejné složce)
    --port COMx   jiný port než COM4
    --speed 30    rychlost kreslení v mm/s (s --send)
    --pen 30,60   prodleva pera v ms po položení / zvednutí (s --send)
    --accel 5000,300  zrychlení: rozjezd v µs, zkrácení v µs za krok (s --send)
    --diag 0      šikmé čáry plnou rychlostí, 1 = zpomalené (s --send)
    --nohome      nenajíždět na levý doraz (s --send)
    --plotter 4131  plotter, pro který se kreslí (výchozí auto: s --send se zjistí
                  z Arduina, bez --send Minigraf 0507); s --send ho v Arduinu i přepne
    --version     verze programu

Kreslicí plocha od startovní pozice (po HM a IN):
  Minigraf 0507: 1520 x 2140 kroků (190 x 267,5 mm) = A4 s okraji 10 mm po stranách a 15 mm nahoře a dole
  XY 4131:       1600 x 2400 kroků (160 x 240 mm), start 10 mm od levého kontaktu
Volba --margin přidává okraj UVNITŘ této plochy.
Nápis běží podél dlouhé strany (osa Y) = A4 na šířku.
Umí velká i malá písmena, 0–9, interpunkci a českou diakritiku.

Běžný text v řádcích (zalomí se sám, | = nový řádek):
    py text_plot.py "Ahoj, tady Minigraf.|Druhý řádek." --size 5 --send
    py text_plot.py --file dopis.txt --size 4 --send
A4 na výšku jako z běžné tiskárny (řádky podél krátké strany):
    py text_plot.py --file dopis.txt --size 4 --portrait --send
Zkušební stránka (stejný text ve velikostech 6 / 4 / 3 / 2 mm):
    py text_plot.py --test --send --speed 40
"""
import argparse
import math
import unicodedata

VERSION = "0.5.9"        # verze programu (potřebuje firmware 0.3 nebo novější, pro XY 4131 firmware 0.4.0)

# kreslicí plocha v krocích od startovní pozice a kroků na mm podle plotteru
PLOTTERS = {
    "0507": (1520, 2140, 8),        # X = 1580 - 60, Y = 2284 - 144 (firmware 0.3.8 a novější)
    "4131": (1600, 2400, 10),       # X = 1700 z 1780 (start 100), Y 240 mm papíru
}
X_MAX, Y_MAX = 1520, 2140
STEPS_PER_MM = 8
MARGIN = 8 * STEPS_PER_MM           # okraj uvnitř kreslicí plochy (mění --margin)

# ---- jednoduchý čárový font: mřížka 4 x 6, účaří y=0 ----
O_ = [(1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)]
P_ = [(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]
FONT = {
    'A': [[(0, 0), (0, 4), (2, 6), (4, 4), (4, 0)], [(0, 3), (4, 3)]],
    'B': [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    'C': [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1)]],
    'D': [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 1), (3, 0), (0, 0)]],
    'E': [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]],
    'F': [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    'G': [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (2, 3)]],
    'H': [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    'I': [[(1, 6), (3, 6)], [(2, 6), (2, 0)], [(1, 0), (3, 0)]],
    'J': [[(4, 6), (4, 1), (3, 0), (1, 0), (0, 1)]],
    'K': [[(0, 0), (0, 6)], [(4, 6), (0, 2)], [(1, 3), (4, 0)]],
    'L': [[(0, 6), (0, 0), (4, 0)]],
    'M': [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    'N': [[(0, 0), (0, 6), (4, 0), (4, 6)]],
    'O': [O_],
    'P': [P_],
    'Q': [O_, [(2, 2), (4, 0)]],
    'R': [P_, [(2, 3), (4, 0)]],
    'S': [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 4), (1, 3), (3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    'T': [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    'U': [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    'V': [[(0, 6), (2, 0), (4, 6)]],
    'W': [[(0, 6), (1, 0), (2, 3), (3, 0), (4, 6)]],
    'X': [[(0, 6), (4, 0)], [(0, 0), (4, 6)]],
    'Y': [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]],
    'Z': [[(0, 6), (4, 6), (0, 0), (4, 0)]],
    '0': [O_, [(0, 1), (4, 5)]],
    '1': [[(1, 5), (2, 6), (2, 0)], [(1, 0), (3, 0)]],
    '2': [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (0, 0), (4, 0)]],
    '3': [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)], [(1, 3), (3, 3)]],
    '4': [[(3, 0), (3, 6), (0, 2), (4, 2)]],
    '5': [[(4, 6), (0, 6), (0, 3), (3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    '6': [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]],
    '7': [[(0, 6), (4, 6), (1, 0)]],
    '8': [[(1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1, 3), (0, 2), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3)]],
    '9': [[(4, 3), (1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0), (0, 1)]],
    ' ': [],
    '-': [[(1, 3), (3, 3)]],
    '.': [[(2, 0), (2, 0.4)]],
    ',': [[(2, 0.4), (2, 0), (1.5, -0.8)]],
    '!': [[(2, 6), (2, 2)], [(2, 0), (2, 0.4)]],
    '?': [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (2, 3), (2, 2)], [(2, 0), (2, 0.4)]],
    ':': [[(2, 0), (2, 0.4)], [(2, 3), (2, 3.4)]],
    ';': [[(2, 3), (2, 3.4)], [(2, 0.4), (2, 0), (1.5, -0.8)]],
    '/': [[(0, 0), (4, 6)]],
    '+': [[(2, 1), (2, 5)], [(0, 3), (4, 3)]],
    '*': [[(2, 1), (2, 5)], [(0.3, 2), (3.7, 4)], [(0.3, 4), (3.7, 2)]],
    '„': [[(1.4, 0.4), (1.4, 0), (0.9, -0.8)], [(2.8, 0.4), (2.8, 0), (2.3, -0.8)]],   # české uvozovky dole
    '“': [[(1.6, 5.2), (1.1, 6)], [(3, 5.2), (2.5, 6)]],                               # české uvozovky nahoře
    '=': [[(0, 2), (4, 2)], [(0, 4), (4, 4)]],
    '(': [[(3, 6), (2, 5), (2, 1), (3, 0)]],
    ')': [[(1, 6), (2, 5), (2, 1), (1, 0)]],
    '"': [[(1.5, 6), (1.5, 5)], [(2.5, 6), (2.5, 5)]],
    "'": [[(2, 6), (2, 5)]],
}
# malá písmena: x-výška 4, dotahy do 6, dolní dotahy do -2
_o = [(1, 0), (0, 1), (0, 3), (1, 4), (3, 4), (4, 3), (4, 1), (3, 0), (1, 0)]
_c = [(4, 3), (3, 4), (1, 4), (0, 3), (0, 1), (1, 0), (3, 0), (4, 1)]
FONT.update({
    'a': [[(4, 4), (4, 0)], _c],
    'b': [[(0, 6), (0, 0)], [(0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (3, 4), (1, 4), (0, 3)]],
    'c': [_c],
    'd': [[(4, 6), (4, 0)], [(4, 1), (3, 0), (1, 0), (0, 1), (0, 3), (1, 4), (3, 4), (4, 3)]],
    'e': [[(0, 2), (4, 2), (4, 3), (3, 4), (1, 4), (0, 3), (0, 1), (1, 0), (3, 0), (4, 1)]],
    'f': [[(1, 0), (1, 5), (2, 6), (4, 6)], [(0, 4), (3, 4)]],
    'g': [[(4, 4), (4, -1), (3, -2), (1, -2), (0, -1)], _c],
    'h': [[(0, 6), (0, 0)], [(0, 3), (1, 4), (3, 4), (4, 3), (4, 0)]],
    'i': [[(2, 4), (2, 0)], [(2, 5.4), (2, 6)]],
    'j': [[(3, 4), (3, -1), (2, -2), (1, -2)], [(3, 5.4), (3, 6)]],
    'k': [[(0, 6), (0, 0)], [(4, 4), (0, 1.5)], [(1.5, 2.4), (4, 0)]],
    'l': [[(1, 6), (2, 6), (2, 1), (3, 0)]],
    'm': [[(0, 0), (0, 4)], [(0, 3), (1, 4), (2, 3), (2, 0)], [(2, 3), (3, 4), (4, 3), (4, 0)]],
    'n': [[(0, 0), (0, 4)], [(0, 3), (1, 4), (3, 4), (4, 3), (4, 0)]],
    'o': [_o],
    'p': [[(0, 4), (0, -2)], [(0, 3), (1, 4), (3, 4), (4, 3), (4, 1), (3, 0), (1, 0), (0, 1)]],
    'q': [[(4, 4), (4, -2)], _c],
    'r': [[(0, 0), (0, 4)], [(0, 2.5), (1.5, 4), (4, 4)]],
    's': [[(4, 3.5), (3, 4), (1, 4), (0, 3.2), (1, 2), (3, 2), (4, 0.8), (3, 0), (1, 0), (0, 0.5)]],
    't': [[(1, 6), (1, 1), (2, 0), (3, 0)], [(0, 4), (3, 4)]],
    'u': [[(0, 4), (0, 1), (1, 0), (3, 0), (4, 1)], [(4, 4), (4, 0)]],
    'v': [[(0, 4), (2, 0), (4, 4)]],
    'w': [[(0, 4), (1, 0), (2, 3), (3, 0), (4, 4)]],
    'x': [[(0, 4), (4, 0)], [(0, 0), (4, 4)]],
    'y': [[(0, 4), (2, 0)], [(4, 4), (1, -2)]],
    'z': [[(0, 4), (4, 4), (0, 0), (4, 0)]],
})
ACCENTS = {                         # diakritika nad písmenem
    '́': [[(1.6, 6.7), (2.6, 7.6)]],               # čárka
    '̌': [[(1, 7.6), (2, 6.7), (3, 7.6)]],         # háček
    '̊': [[(1.6, 6.8), (2.4, 6.8), (2.4, 7.6), (1.6, 7.6), (1.6, 6.8)]],  # kroužek
}
ADVANCE = 6                         # šířka znaku 4 + mezera 2
CAP = 7.6                           # výška včetně diakritiky


def glyph(ch):
    d = unicodedata.normalize('NFD', ch)
    base, marks = d[0], d[1:]
    if base not in FONT:
        base = base.upper()
    strokes = list(FONT.get(base, FONT['?']))
    low = base.islower()
    if low and base == 'i' and marks:
        strokes = [[(2, 4), (2, 0)]]                     # í bez tečky
    for mark in marks:
        if low and mark == '\u030C' and base in 'dtl':    # ď ť ľ = apostrof vpravo
            xs = {'d': 5.2, 't': 2.6, 'l': 3.4}[base]
            strokes.append([(xs, 6), (xs - 0.4, 5)])
            continue
        dy = -2 if low else 0                              # nad malými níž
        strokes += [[(x, y + dy) for x, y in st] for st in ACCENTS.get(mark, [])]
    return strokes


# ---- psací písmo (Hershey "cursive", --font psane) ----
FONT_STYLE = "blok"                 # "blok" = vlastní čárové písmo, "psane" = Hershey cursive
SK = 6 / 21                         # Hershey: velká písmena 21 jednotek -> 6 jednotek našeho písma
_script = None


def _script_data():
    global _script
    if _script is None:
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from hershey_script import GLYPHS
        _script = GLYPHS
    return _script


def _accent(mark, cx, y0):
    if mark == '\u0301':                                  # čárka
        return [[(cx - 0.2, y0), (cx + 0.55, y0 + 0.8)]]
    if mark == '\u030C':                                  # háček
        return [[(cx - 0.45, y0 + 0.65), (cx, y0), (cx + 0.45, y0 + 0.65)]]
    if mark == '\u030A':                                  # kroužek
        return [[(cx + 0.32 * math.cos(a * math.pi / 4), y0 + 0.35 + 0.32 * math.sin(a * math.pi / 4))
                 for a in range(9)]]
    return []


def script_glyph(ch):
    """Tahy a šířka znaku psacího písma v jednotkách našeho písma (účaří 0, velká písmena 6)."""
    G = _script_data()
    d = unicodedata.normalize('NFD', ch)
    base, marks = d[0], d[1:]
    if base not in G:
        base = '?'
    L, Rr, st = G[base]
    strokes = [[((x - L) * SK, (9 - y) * SK) for x, y in t] for t in st]
    low = base.islower()
    if base == 'i' and marks:                                # í bez tečky
        strokes = [t for t in strokes if min(y for _, y in t) < 2.9]
    for mark in marks:
        pts = [pt for t in strokes for pt in t]
        if low and mark == '\u030C' and base in 'dt':        # ď ť = apostrof vpravo nahoře
            xt, yt = max(pts, key=lambda q: q[1])
            strokes.append([(xt + 0.55, yt - 0.1), (xt + 0.3, yt - 0.85)])
            continue
        top = [x for x, y in pts if y >= (1.6 if low else 4.2)] or [x for x, _ in pts]
        cx = (min(top) + max(top)) / 2 + (0.15 if low else 0.6)   # písmo je skloněné doprava
        strokes += _accent(mark, cx, 3.3 if low else 6.5)
    return strokes, (Rr - L) * SK


def char_advance(ch):
    return script_glyph(ch)[1] if FONT_STYLE == "psane" else ADVANCE


def text_width(text):
    if FONT_STYLE == "psane":
        return sum(char_advance(c) for c in text)
    return len(text) * ADVANCE - 2


def text_strokes(text):
    out = []
    x0 = 0.0
    for ch in text:
        if FONT_STYLE == "psane":
            st, adv = script_glyph(ch)
        else:
            st, adv = glyph(ch), ADVANCE
        for s in st:
            out.append([(x + x0, y) for x, y in s])
        x0 += adv
    return out, text_width(text)


def star(cx, cy, r):
    pts = []
    for i in range(17):
        a = math.pi / 2 + i * math.pi / 8
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return [pts]


def build(text, bold, frame, with_star, flip, margin_mm=8):
    MARGIN = int(margin_mm * STEPS_PER_MM)
    strokes_u, width_u = text_strokes(text)
    page_len = Y_MAX - 2 * MARGIN                    # podél nápisu (osa Y)
    page_h = X_MAX - 2 * MARGIN                      # výška stránky na šířku (osa X)
    text_h_max = page_h * (0.45 if with_star else 0.7)
    k = min(page_len / width_u, text_h_max / CAP)    # kroky na jednotku fontu

    # souřadnice "na šířku": u = vodorovně (0..Y_MAX), v = svisle (0..X_MAX)
    u0 = (Y_MAX - width_u * k) / 2
    v0 = (X_MAX - 6 * k) / 2 - (0.18 * page_h if with_star else 0)
    paths = []
    off = 3                                          # ~0,4 mm posun pro ztučnění
    offsets = [(0, 0), (off, 0), (0, off), (off, off)][:max(1, min(4, bold))]
    for du, dv in offsets:
        for s in strokes_u:
            paths.append([(u0 + x * k + du, v0 + y * k + dv) for x, y in s])
    if with_star:
        paths += star(Y_MAX / 2, v0 + 6 * k + 0.27 * page_h, 0.15 * page_h)
    if frame:
        fm = max(1 * STEPS_PER_MM, MARGIN - 7 * STEPS_PER_MM)   # rámeček 7 mm vně textu
        for m in (fm, fm + 2 * STEPS_PER_MM):
            paths.append([(m, m), (Y_MAX - m, m), (Y_MAX - m, X_MAX - m), (m, X_MAX - m), (m, m)])

    # převod na plotter: u -> Y, v -> X (horní okraj nápisu u X=0)
    def to_plot(u, v):
        x, y = X_MAX - v, u
        if flip:
            x, y = X_MAX - x, Y_MAX - y
        return int(round(min(max(x, 0), X_MAX))), int(round(min(max(y, 0), Y_MAX)))

    return [[to_plot(u, v) for u, v in p] for p in paths], paths, k


def wrap(text, maxw):
    """Zalomí text na řádky široké nejvýš maxw jednotek písma."""
    out = []
    for para in text.replace("|", "\n").split("\n"):
        line = ""
        for w in para.split():
            if line and text_width(line + " " + w) > maxw:
                out.append(line); line = w
            else:
                line = (line + " " + w) if line else w
        out.append(line)
    return out


def block(lines, size_mm, u0, v_top, bold=1):
    """Řádky textu o výšce velkých písmen size_mm od bodu (u0, v_top) dolů."""
    k = size_mm * STEPS_PER_MM / 6
    pitch = 11 * k
    off = 3
    offsets = [(0, 0), (off, 0), (0, off), (off, off)][:max(1, min(4, bold))]
    paths = []
    v = v_top - 7.6 * k
    for ln in lines:
        st, _ = text_strokes(ln)
        for du, dv in offsets:
            for p in st:
                paths.append([(u0 + x * k + du, v + y * k + dv) for x, y in p])
        v -= pitch
    return paths, v_top - len(lines) * pitch


TEST_TEXT = ("Příliš žluťoučký kůň úpěl ďábelské ódy. "
             "Malá písmena: abcdefghijklmnopqrstuvwxyz, "
             "VELKÁ: ABCDEFGHIJKLMNOPQRSTUVWXYZ, čísla 0123456789 (+-=/:;?!)")


def build_text(text, size_mm, bold, frame, flip, margin_mm, test, portrait=False):
    M = int(margin_mm * STEPS_PER_MM)
    W, H = (X_MAX, Y_MAX) if portrait else (Y_MAX, X_MAX)   # šířka a výška stránky
    page_len = W - 2 * M
    paths, v = [], H - M
    if test:
        for sz in (6, 4, 3, 2):
            k = sz * STEPS_PER_MM / 6
            lab, v = block(["%s mm:" % sz], 2.5, M, v)
            p, v = block(wrap(TEST_TEXT, page_len / k), sz, M, v, bold)
            paths += lab + p
            v -= 4 * STEPS_PER_MM
    else:
        k = size_mm * STEPS_PER_MM / 6
        paths, v = block(wrap(text, page_len / k), size_mm, M, v, bold)
    if v < M:
        print("POZOR: text se nevešel na stránku (přetéká o %.0f mm)" % ((M - v) / STEPS_PER_MM))
    if frame:
        fm = max(1 * STEPS_PER_MM, M - 7 * STEPS_PER_MM)
        for m in (fm, fm + 2 * STEPS_PER_MM):
            paths.append([(m, m), (W - m, m), (W - m, H - m), (m, H - m), (m, m)])

    def to_plot(u, vv):
        x, y = (u, vv) if portrait else (X_MAX - vv, u)
        if flip:
            x, y = X_MAX - x, Y_MAX - y
        return int(round(min(max(x, 0), X_MAX))), int(round(min(max(y, 0), Y_MAX)))
    return [[to_plot(u, vv) for u, vv in p] for p in paths], paths, size_mm * STEPS_PER_MM / 6


def to_hpgl(paths):
    out = ["IN;"]
    last = None
    for p in paths:
        if p[0] != last:                     # navazující tah -> pero se nezvedá
            out.append("PU%d,%d;" % p[0])
        out.append("PD" + ",".join("%d,%d" % xy for xy in p[1:]) + ";")
        last = p[-1]
    out.append("PU0,0;")
    return "\n".join(out) + "\n"


def set_plotter(pl):
    global X_MAX, Y_MAX, STEPS_PER_MM
    X_MAX, Y_MAX, STEPS_PER_MM = PLOTTERS[pl]


def main():
    ap = argparse.ArgumentParser(description="Nápisy a text pro Minigraf A 0507 a XY 4131 (text_plot.py %s)" % VERSION)
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--size", type=float, default=0,
                    help="výška velkých písmen v mm -> běžný text na řádky (| = nový řádek)")
    ap.add_argument("--file", help="text ze souboru (UTF-8), s --size")
    ap.add_argument("--test", action="store_true", help="zkušební stránka 6 / 4 / 3 / 2 mm")
    ap.add_argument("--portrait", action="store_true",
                    help="A4 na výšku jako z tiskárny: řádky podél krátké strany")
    ap.add_argument("-o", "--out", default="napis.hpgl")
    ap.add_argument("--bold", type=int, default=1)
    ap.add_argument("--font", choices=("blok", "psane"), default="blok",
                    help="písmo: blok (výchozí) nebo psane (jako psané rukou)")
    ap.add_argument("--frame", action="store_true")
    ap.add_argument("--star", action="store_true")
    ap.add_argument("--flip", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--port", default="COM4")
    ap.add_argument("--speed", type=int, default=0)
    ap.add_argument("--pen", default="", help="prodleva pera v ms: dolů,nahoru (např. 30,60)")
    ap.add_argument("--accel", default="", help="zrychlení: rozjezd_us,ramp_us (např. 5000,300)")
    ap.add_argument("--diag", type=int, choices=(0, 1), default=None, help="šikmé čáry: 0 = plná rychlost, 1 = zpomalené")
    ap.add_argument("--nohome", action="store_true", help="nenajíždět na začátku na levý doraz")
    ap.add_argument("--version", action="version", version="text_plot.py " + VERSION)
    ap.add_argument("--margin", type=float, default=8)
    ap.add_argument("--plotter", choices=("auto", "0507", "4131"), default="auto",
                    help="plotter (auto = zjistit z Arduina při --send, jinak 0507)")
    a = ap.parse_args()

    ser = ver = None
    pl = "0507" if a.plotter == "auto" else a.plotter
    if a.send:
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import plot
        ser, ver, found = plot.open_plotter(a.port)
        if a.plotter == "auto":
            pl = found
        elif found != pl:
            plot.select_plotter(ser, pl)
    set_plotter(pl)
    global FONT_STYLE
    FONT_STYLE = a.font

    if a.file:
        with open(a.file, encoding="utf-8") as f:
            a.text = f.read()
    if a.test or a.size > 0 or a.portrait:
        if a.margin == 8:                    # výchozí okraj u textu v řádcích
            a.margin = 5
        plot_paths, page_paths, k = build_text(a.text, a.size or 5, a.bold, a.frame,
                                               a.flip, a.margin, a.test, a.portrait)
    else:
        if not a.text:
            ap.error("zadej text, nebo --test")
        plot_paths, page_paths, k = build(a.text, a.bold, a.frame, a.star, a.flip, a.margin)
    with open(a.out, "w") as f:
        f.write(to_hpgl(plot_paths))
    print("Plotter %s | uloženo %s: %d tahů%s" % ("XY 4131" if pl == "4131" else "Minigraf 0507", a.out, len(plot_paths),
          "" if a.test else ", výška písmen %.1f mm" % (6 * k / STEPS_PER_MM)))
    if not a.send:
        print("Kreslení: py plot.py %s --scale 1   (nebo příště přidej --send)" % a.out)

    if a.preview:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        W, H = (X_MAX, Y_MAX) if a.portrait else (Y_MAX, X_MAX)
        fig, ax = plt.subplots(figsize=(8.3, 11.7) if a.portrait else (11.7, 8.3))
        ax.add_patch(plt.Rectangle((0, 0), W, H, fill=False, ls="--", color="gray"))
        for p in page_paths:
            ax.plot([u for u, v in p], [v for u, v in p], color="navy", lw=1)
        ax.set_aspect("equal"); ax.axis("off")
        png = a.out.rsplit(".", 1)[0] + ".png"
        fig.savefig(png, dpi=110, bbox_inches="tight")
        print("Náhled:", png)

    if a.send:
        with open(a.out) as f:
            lines = plot.to_lines(f.read(), 1.0)
        lines = plot.setup_lines(a.speed, a.pen, a.accel, a.diag, not a.nohome) + lines
        print("Posílám na %s ..." % a.port)
        plot.send_lines(ser, lines, ver)


if __name__ == "__main__":
    main()
