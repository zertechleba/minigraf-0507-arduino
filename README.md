# Minigraf 0507 – ovládání pomocí Arduino Nano Every

Převodník, který oživí československý plotter **Aritma Minigraf A 0507** a umožní na něm kreslit
z počítače **Atari XE/XL** (přes SIO) i z **PC** (přes USB).

![Ukázka – nápis s rámečkem a hvězdou](docs/img/ukazka_napis.jpg)

*Autor: Zdeněk Kotrba · © 2026 · verze 0.1*

---

## Co umí

- **Z Atari** se kreslí obyčejným `LPRINT` – Arduino se na sběrnici SIO hlásí jako tiskárna **P1:**.
- **Z PC** se kreslí HPGL soubory (např. z Inkscape) a nápisy vlastním čárovým písmem s českou diakritikou.
- Zjednodušené **HPGL příkazy**: `IN`, `PU`, `PD`, `PA`, `PR`, `CI`, plus `VS` (rychlost) a `PT` (prodleva pera).
- **Potvrzování** – další příkaz přijde, až plotter dokreslí předchozí, nic se neztratí.
- **Pozvolný rozjezd a dojezd** motorů, ověřeno do 80 mm/s (výchozí 60 mm/s).
- Atari je od zbytku **galvanicky odděleno** třemi optočleny CNY75C.

```
Atari XE ──SIO──[3× optočlen]── Arduino ──7 signálů── Minigraf A 0507
                                   │
                                  USB
                                   │
                                   PC
```

## Struktura repozitáře

| Cesta | Obsah |
|---|---|
| `firmware/minigraf_sio/minigraf_sio.ino` | firmware pro Arduino Nano Every (ATmega4809) a Leonardo/Micro (ATmega32U4) |
| `pc/plot.py` | posílání HPGL souborů z PC |
| `pc/text_plot.py` | nápisy, text v řádcích a zkušební stránka |
| `docs/Minigraf_0507_navod_v0.1.pdf` | kompletní návod (zapojení, příkazy, ukázky, řešení problémů) |
| `docs/img/` | schémata zapojení a fotky výsledků |

## Hardware

| Signál | Nano Every | Leonardo / Micro | Minigraf vývod |
|---|---|---|---|
| SIO Data Out (přes OK1) | D0 (RX1) | D0 (RX1) | – |
| SIO Data In (přes OK3) | D1 (TX1) | D1 (TX1) | – |
| SIO Command (přes OK2) | D2 | D2 | – |
| X1 / X2 / X4 | A0 / A1 / A2 | A0 / A1 / A2 | 10 / 9 / 8 |
| Y1 / Y2 / Y4 | A3 / **A6** / **A7** | A3 / A4 / A5 | 4 / 3 / 2 |
| P (pero) | D10 | D10 | 5 |
| GND | GND | GND | 1, 11 |

**Konektor plotteru:** okrajový konektor s roztečí 2,54 mm (stejný typ jako u periferií ZX Spectra),
12 pozic, **na pozici 7 je zámek** a při číslování se počítá. Používá se jen spodní řada kontaktů.

![Konektor Minigrafu](docs/img/konektor.png)

> ⚠️ Zem Atari a zem Arduina s plotterem se **nespojují** – proto jsou v obvodu optočleny.
> Arduino se napájí z USB, plotter ze svého zdroje 24 V.

Schémata: [Nano Every](docs/img/schema_nano_every.jpg) · [Leonardo / Micro](docs/img/schema_leonardo_micro.jpg)

## Rychlý start

### 1. Firmware
1. Arduino IDE → Správce desek → nainstaluj **Arduino megaAVR Boards**.
2. Deska **Arduino Nano Every**, otevři `firmware/minigraf_sio/minigraf_sio.ino` a nahraj.

### 2. Kreslení z Atari BASICu
```basic
10 LPRINT "IN;"
20 LPRINT "PU100,100;PD1400,100,1400,2000,100,2000,100,100;"
30 LPRINT "PU750,1050;CI400;"
40 LPRINT "PU0,0;"
```

### 3. Kreslení z PC (Windows)
```
py -m pip install pyserial
cd pc
py text_plot.py "AHOJ" --frame --bold 3 --send
py text_plot.py --test --portrait --send
py plot.py obrazek.hpgl
```
Výchozí port je `COM4` (jiný: `py plot.py COM7 obrazek.hpgl` nebo `--port COM7`).
Před kreslením posuň hlavu do levého dolního rohu – tam bude bod 0,0.

## Přehled příkazů

| Příkaz | Význam |
|---|---|
| `IN;` | aktuální poloha = 0,0, pero nahoru |
| `PU x,y;` | pero nahoru a přesun |
| `PD x,y,...;` | pero dolů a kreslení |
| `PA;` / `PR;` | absolutní / relativní souřadnice |
| `CI r[,n];` | kružnice o poloměru r kolem aktuální polohy |
| `VS v;` | rychlost v mm/s (`VS;` = výchozí 60) |
| `PT d,u;` | prodleva pera v ms po položení / zvednutí (`PT;` = 0 / 70) |

Jednotka = 1 krok = 0,125 mm. Pracovní plocha 1504 × 2104 kroků (188 × 263 mm).

![Zkušební stránka](docs/img/ukazka_test.jpg)

Podrobnosti najdeš v [PDF návodu](docs/Minigraf_0507_navod_v0.1.pdf).

---

## English summary

An Arduino-based interface for the Czechoslovak **Aritma Minigraf A 0507** pen plotter.
The Arduino (Nano Every or Leonardo/Micro) emulates an **Atari SIO printer (P1:)**, so the plotter can be driven
from Atari BASIC with plain `LPRINT` statements, and it also accepts the same simplified **HPGL** commands
over USB from a PC. Python tools are included for plotting HPGL files and for rendering text with a built-in
stroke font. The Atari side is galvanically isolated with three CNY75C optocouplers.
See the (Czech) PDF manual in `docs/` for wiring, commands and troubleshooting.

## Zdroje

- Zapojení konektoru: [cygnus.speccy.cz – Aritma Minigraf 0507](https://cygnus.speccy.cz/popis_printer-aritma0507.php)
- Význam signálů: dokumentace MZXR k ZX Spectru, emulace Minigrafu v projektu MAME

## Licence

[MIT](LICENSE) © 2026 Zdeněk Kotrba
