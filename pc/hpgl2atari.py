#!/usr/bin/env python3
"""
Převod výkresu HPGL na programy v Atari BASICu (LPRINT přes náš převodník) + disketa ATR.

Každý vstupní soubor .hpgl je jedna část (např. jedno pero). Z každé části vznikne program
D:JMENOn.LST, který se na Atari nahraje příkazem ENTER a spustí RUN. Programy se uloží
jako textové soubory (.LST, konce řádků ATASCII) a zároveň na disketu ATR (DOS 2.0/2.5,
jednoduchá hustota, 720 sektorů) – tu otevřeš v SIO2PC, FujiNetu, SDrive nebo emulátoru.

    py hpgl2atari.py obrazek.hpgl                          -> OBRAZEK1.LST + obrazek.atr
    py hpgl2atari.py cast1.hpgl cast2.hpgl --jmeno TRAM    -> TRAM1.LST, TRAM2.LST + tram.atr
    py hpgl2atari.py obrazek.hpgl --plotter 4131

    py hpgl2atari.py obrazek.hpgl --dos mojedos.atr        -> soubory přidá na kopii tvé diskety s DOSem

Na Atari (DOS nabootovaný, disketa s programy v D1: nebo D2:):
    ENTER "D:TRAM1.LST"      RUN       (1. program najede HM a nakreslí 1. část)
    NEW  ENTER "D:TRAM2.LST" RUN       (další části navazují, poslední vrátí hlavu na začátek)

Souřadnice v .hpgl musí být v krocích plotteru (jako z text_plot.py, fraktaly.py, mzxr_tap.py).
"""
import argparse, os, re, sys

VERSION = "0.5.12"
EOL = b"\x9b"
START = {"0507": (60, 144), "4131": (100, 0)}       # start po HM (pro návrat papíru a hlavy na konci)
MAXSTR = 96                                          # délka řetězce v LPRINT (řádek Atari BASICu max. ~120 znaků)


def hpgl_cmds(text):
    """HPGL -> seznam příkazů ('PU'|'PD', [(x,y),...]); IN a ostatní se vynechají."""
    out = []
    for m in re.finditer(r"([A-Za-z]{2})([^;A-Za-z]*)", text):
        c = m.group(1).upper()
        nums = [int(round(float(v))) for v in re.findall(r"-?\d+(?:\.\d+)?", m.group(2))]
        pts = list(zip(nums[0::2], nums[1::2]))
        if c in ("PU", "PD"):
            out.append((c, pts))
    return out


def lprint_strings(cmds):
    """Příkazy -> řetězce pro LPRINT (každý nejvýš MAXSTR znaků, jen celé příkazy)."""
    out, cur = [], ""
    for c, pts in cmds:
        if not pts:
            piece = [c + ";"]
        else:
            piece, s = [], c
            for x, y in pts:
                t = "%d,%d" % (x, y)
                cand = s + ("" if s == c else ",") + t
                if len(cand) + 1 > MAXSTR:
                    piece.append(s + ";"); s = c + t
                else:
                    s = cand
            piece.append(s + ";")
        for p in piece:
            if len(cur) + len(p) > MAXSTR:
                out.append(cur); cur = ""
            cur += p
    if cur:
        out.append(cur)
    return out


def make_lst(name, part, nparts, strings, plotter, title):
    L, n = [], 10
    def add(s):
        nonlocal n
        L.append(("%d %s" % (n, s)).encode("ascii")); n += 10
    add("REM %s %d/%d - Minigraf/XY4131, hpgl2atari %s" % (title, part, nparts, VERSION))
    add('? "%s: TISK %d/%d ..."' % (title, part, nparts))
    if part == 1:
        add('LPRINT "PL%s;HM;IN;"' % plotter)
    n = 100
    for s in strings:
        add('LPRINT "%s"' % s)
    if part < nparts:
        add('LPRINT "PU;"')
        add('? "HOTOVO %d/%d. VYMEN PERO, POTOM:"' % (part, nparts))
        add('? "NEW  ENTER ";CHR$(34);"D:%s%d.LST";CHR$(34);"  RUN"' % (name, part + 1))   # Atari BASIC nezná ""
    else:
        sx, sy = START[plotter]
        add('LPRINT "PU;PU%d,%d;HM;"' % (-sx, -sy))       # papír i hlava zpět na začátek
        add('? "%s HOTOVO."' % title)
    add("END")
    return EOL.join(L) + EOL


def make_atr(files, base=None):
    """Disketa DOS 2.0/2.5 SD (720 sektorů po 128 B) se zadanými soubory [(jméno8, ext3, data)].
    base = obsah existující diskety .atr (např. systémová disketa s DOSem) – soubory se přidají k ní."""
    SEC, NS = 128, 720
    def sec(n):                                          # n = 1..720
        return (n - 1) * SEC
    if base:
        if len(base) != 16 + SEC * NS or base[:2] != b"\x96\x02":
            sys.exit("Základní disketa musí být ATR, DOS 2.0/2.5, jednoduchá hustota (720 sektorů po 128 B).")
        disk = bytearray(base[16:])
        v = sec(360)
        used = set(n for n in range(1, 720) if not disk[v + 10 + n // 8] & (0x80 >> (n % 8)))
        slots = [i for i in range(64) if not (disk[sec(361 + i // 8) + (i % 8) * 16] & 0x40)
                 or disk[sec(361 + i // 8) + (i % 8) * 16] & 0x80]
    else:
        disk = bytearray(SEC * NS)
        used = set([1, 2, 3] + list(range(360, 369)))
        slots = list(range(64))
    used |= set(range(360, 369))
    nxt = 4
    dirents = []
    for k, (nm, ext, data) in enumerate(files):
        if k >= len(slots):
            sys.exit("Na disketě není volná položka v adresáři.")
        fi = slots[k]
        chunks = [data[i:i + 125] for i in range(0, len(data), 125)] or [b""]
        secs = []
        for _ in chunks:
            while nxt in used or nxt == 0:
                nxt += 1
            if nxt > 719:
                sys.exit("Na disketu se soubory nevejdou.")
            secs.append(nxt); used.add(nxt); nxt += 1
        for i, ch in enumerate(chunks):
            o = sec(secs[i])
            disk[o:o + len(ch)] = ch
            link = secs[i + 1] if i + 1 < len(secs) else 0
            disk[o + 125] = (fi << 2) | (link >> 8)
            disk[o + 126] = link & 0xFF
            disk[o + 127] = len(ch)
        dirents.append((fi, nm, ext, len(secs), secs[0]))
    for i, nm, ext, cnt, start in dirents:
        o = sec(361 + i // 8) + (i % 8) * 16
        disk[o] = 0x42
        disk[o + 1:o + 3] = cnt.to_bytes(2, "little")
        disk[o + 3:o + 5] = start.to_bytes(2, "little")
        disk[o + 5:o + 13] = nm.ljust(8).encode("ascii")
        disk[o + 13:o + 16] = ext.ljust(3).encode("ascii")
    v = sec(360)
    data_used = len([s for s in used if 4 <= s <= 719 and not 360 <= s <= 368])
    disk[v] = 2
    disk[v + 1:v + 3] = (707).to_bytes(2, "little")
    disk[v + 3:v + 5] = (707 - data_used).to_bytes(2, "little")
    for s in range(720):                                 # bitová mapa: 1 = volný sektor (sektor 0 neexistuje)
        bit = 0x80 >> (s % 8)
        if s >= 1 and s not in used:
            disk[v + 10 + s // 8] |= bit
        else:
            disk[v + 10 + s // 8] &= ~bit & 0xFF
    size = len(disk) // 16
    hdr = bytes([0x96, 0x02, size & 0xFF, (size >> 8) & 0xFF, SEC & 0xFF, SEC >> 8, (size >> 16) & 0xFF]) + bytes(9)
    return hdr + bytes(disk)


def write(parts, name, plotter, title, outdir=".", base_atr=None):
    """parts = [seznam příkazů] -> zapíše .LST a .atr, vrátí cesty."""
    name = re.sub(r"[^A-Z0-9]", "", name.upper())[:7] or "OBRAZEK"
    files, paths = [], []
    for i, cmds in enumerate(parts, 1):
        lst = make_lst(name, i, len(parts), lprint_strings(cmds), plotter, title)
        fn = "%s%d" % (name, i)
        p = os.path.join(outdir, fn + ".LST")
        with open(p, "wb") as f:
            f.write(lst)
        files.append((fn, "LST", lst)); paths.append(p)
    atr = os.path.join(outdir, name.lower() + ".atr")
    base = open(base_atr, "rb").read() if base_atr else None
    with open(atr, "wb") as f:
        f.write(make_atr(files, base))
    paths.append(atr)
    return paths, name


def main():
    ap = argparse.ArgumentParser(description="HPGL -> programy v Atari BASICu + disketa ATR (hpgl2atari.py %s)" % VERSION)
    ap.add_argument("hpgl", nargs="+", help="soubor(y) .hpgl v krocích plotteru; každý = jedna část / jedno pero")
    ap.add_argument("--jmeno", default=None, help="jméno programů na disketě (max 7 znaků), výchozí podle souboru")
    ap.add_argument("--plotter", choices=("0507", "4131"), default="0507")
    ap.add_argument("--dos", default=None, help="přidat soubory na kopii této diskety .atr (např. tvoje systémová disketa s DOSem)")
    ap.add_argument("--version", action="version", version="hpgl2atari.py " + VERSION)
    a = ap.parse_args()
    parts = []
    for fn in a.hpgl:
        with open(fn) as f:
            parts.append(hpgl_cmds(f.read()))
    base = a.jmeno or os.path.splitext(os.path.basename(a.hpgl[0]))[0]
    paths, name = write(parts, base, a.plotter, base.upper()[:12], base_atr=a.dos)
    for p in paths:
        print("  " + p)
    print("Na Atari: ENTER \"D:%s1.LST\"  a  RUN" % name)


if __name__ == "__main__":
    main()
