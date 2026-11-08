# Minigraf 0507 – ovládání pomocí Arduino Nano Every

🇨🇿 **Česky** · 🇬🇧 [English](README.en.md)

Převodník, který oživí československý plotter **Aritma Minigraf A 0507** a umožní na něm kreslit
z počítače **Atari XE/XL** (přes SIO) i z **PC** (přes USB).

![Ukázka – nápis s rámečkem a hvězdou](docs/img/ukazka_napis.jpg)

*Autor: Zdeněk Kotrba · © 2026 · verze 0.3.5 (firmware 0.3.5)*

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
| `docs/Minigraf_0507_navod_v0.3.5.pdf` | kompletní návod česky (zapojení, příkazy, ukázky, řešení problémů) |
| `docs/Minigraf_0507_manual_v0.3.5_EN.pdf` | kompletní návod anglicky |
| `docs/img/` | schémata zapojení (CZ i EN) a fotky výsledků |

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
10 LPRINT "HM;IN;"
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
Šetrnější kreslení (starší plotter): `py text_plot.py --test --portrait --send --accel 9000,150 --diag 1`

Výchozí port je `COM4` (jiný: `py plot.py COM7 obrazek.hpgl` nebo `--port COM7`).
Před kreslením hlava sama najede na levý doraz a startovní pozici X = 60 (příkaz `HM`); vypne se volbou `--nohome`.

## Přehled příkazů

| Příkaz | Význam |
|---|---|
| `HM[x];` | najetí na levý doraz (X = 0) a pak na startovní pozici (výchozí X = 60) |
| `LM x[,y];` | meze plochy v krocích od dorazu, uloží se do EEPROM (výchozí 1580, 2103) |
| `IN;` | aktuální poloha = počátek kreslení 0,0, pero nahoru |
| `PU x,y;` | pero nahoru a přesun |
| `PD x,y,...;` | pero dolů a kreslení |
| `PA;` / `PR;` | absolutní / relativní souřadnice |
| `CI r[,n];` | kružnice o poloměru r kolem aktuální polohy |
| `VS v;` | rychlost v mm/s (`VS;` = výchozí 60) |
| `PT d,u;` | prodleva pera v ms po položení / zvednutí (`PT;` = 30 / 70) |
| `AC s,r;` | zrychlení: pauza při rozjezdu s µs, zkrácení r µs za krok (`AC;` = 6000 / 250) |
| `DG0;` / `DG1;` | šikmé čáry plnou rychlostí / zpomalené ×1,4 (`DG;` = 0) |
| `?` | jen z USB: verze firmwaru a stav |

Jednotka = 1 krok = 0,125 mm. Kreslicí plocha od startovní pozice 1521 × 2104 kroků (190 × 263 mm).

![Zkušební stránka](docs/img/ukazka_test.jpg)

*Zkušební stránka 6 / 4 / 3 / 2 mm, fix 0,5 mm, výchozí nastavení verze 0.3.4.*
*Kaňka v posledním řádku u „JKLM“ vznikla tím, že se na USB ztratil jeden příkaz a verze 0.3.4 čekala 20 s
s perem dole, než ho poslala znovu. Od verze 0.3.5 firmware pero po 1 s sám zvedne a `plot.py` se zeptá už po 3 s.*

Podrobnosti najdeš v [PDF návodu](docs/Minigraf_0507_navod_v0.3.5.pdf).

## Historie verzí

- **0.3.5** – žádné kaňky při výpadku: firmware zvedne pero, když 1 s nepřijde příkaz; `plot.py` se zotaví už po 3 s.
- **0.3.4** – oprava příčiny výpadků: stavový výpis každých 10 s mohl zahltit 64bajtový přijímací buffer Arduina a uříznout příkaz; výpis se teď neposílá během kreslení a `plot.py` posílá řádky kratší než 64 znaků.
- **0.3.3** (jen programy pro PC) – `plot.py` před kreslením ověří, že firmware zná `HM` (verze 0.3 a novější), a zastaví se s jasnou hláškou, když hlava na nulu nenajede.
- **0.3.2** – nové výchozí hodnoty ověřené tiskem: zrychlení `AC6000,250`, šikmé čáry plnou rychlostí `DG0`, prodleva pera `PT30,70`.
- **0.3.1** – oprava: `plot.py` se sám zotaví z výpadku komunikace (po 20 s se zeptá Arduina a řádek pošle znovu), firmware zahodí neúplný příkaz, `plot.py` opět vypisuje verzi firmwaru.
- **0.3** – najetí na levý doraz `HM` (automaticky před každým výkresem z PC, `--nohome`), absolutní poloha a meze plochy `LM` uložené v EEPROM (ověřená mez X = 1580), `IN` už nehýbe motory.
- **0.2** – příkazy `AC` (zrychlení) a `DG` (šikmé čáry), verze firmwaru ve výpisu `?` a v programech pro PC (`--version`), volby `--accel` a `--diag`.
- **0.1** – první verze: emulace tiskárny P1: pro Atari, ovládání z PC, nápisy a text.

## Zdroje

- Zapojení konektoru: [cygnus.speccy.cz – Aritma Minigraf 0507](https://cygnus.speccy.cz/popis_printer-aritma0507.php)
- Význam signálů: dokumentace MZXR k ZX Spectru, emulace Minigrafu v projektu MAME

## Licence

[MIT](LICENSE) © 2026 Zdeněk Kotrba
