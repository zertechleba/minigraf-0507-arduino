"""Vygeneruje data písem pro firmware (PROGMEM) z pc/text_plot.py -> font_data.inc; vložit do minigraf_sio.ino. Jednotka: velká písmena = 42."""
import sys, math, unicodedata
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pc'))
import text_plot as t

EXTRA = "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽäöüÄÖÜ"
CHARS = [chr(c) for c in range(32, 127)] + list(EXTRA)
U = 7  # naše jednotky (velká = 6) -> 42

def umlaut(strokes, low):
    pts = [p for s in strokes for p in s]
    top = [x for x, y in pts if y >= (1.6 if low else 4.2)] or [x for x, _ in pts]
    cx = (min(top) + max(top)) / 2
    y0 = 3.4 if low else 6.7
    return strokes + [[(cx - 0.7, y0), (cx - 0.7, y0 + 0.35)], [(cx + 0.7, y0), (cx + 0.7, y0 + 0.35)]]

def glyph(style, ch):
    t.FONT_STYLE = style
    d = unicodedata.normalize('NFD', ch)
    if len(d) > 1 and d[1] == '̈':
        base = d[0]
        if style == 'psane':
            st, adv = t.script_glyph(base)
        else:
            st, adv = t.glyph(base), t.ADVANCE
        return umlaut(st, base.islower()), adv
    if style == 'psane':
        return t.script_glyph(ch)
    return t.glyph(ch), t.ADVANCE

def encode(style):
    data, offs = [], []
    for ch in CHARS:
        st, adv = glyph(style, ch)
        offs.append(len(data))
        data.append(int(round(adv * U)))
        first = True
        for s in st:
            if not first:
                data.append(0x80)
            first = False
            for x, y in s:
                xi, yi = int(round(x * U)), int(round(y * U))
                assert -126 <= xi <= 127 and -126 <= yi <= 127, (ch, xi, yi)
                data += [xi & 0xFF, yi & 0xFF]
        data.append(0x81)
    return data, offs

out = ['// ---- data písem (vygenerováno gen_font.py z text_plot.py; velká písmena = 42 jednotek) ----',
       '// znaky: ASCII 32..126, pak: ' + EXTRA,
       'const uint8_t FONT_NCH = %d;' % len(CHARS),
       'const uint16_t FONT_EXTRA_CP[] PROGMEM = {' + ','.join('0x%04X' % ord(c) for c in EXTRA) + '};']
total = 0
for name, style in (('BLOK', 'blok'), ('PSANE', 'psane')):
    data, offs = encode(style)
    total += len(data) + 2 * len(offs)
    out.append('const uint16_t FONT_%s_OFS[] PROGMEM = {%s};' % (name, ','.join(map(str, offs))))
    rows = [','.join('%d' % (b if b < 128 else b - 256) if b not in (0x80, 0x81) else ('-128' if b == 0x80 else '-127') for b in data[i:i + 40]) for i in range(0, len(data), 40)]
    out.append('const int8_t FONT_%s[] PROGMEM = {\n  %s\n};' % (name, ',\n  '.join(rows)))
open('font_data.inc', 'w').write('\n'.join(out) + '\n')
print('bytes', total)
