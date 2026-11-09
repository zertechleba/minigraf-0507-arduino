# Minigraf 0507 and XY 4131 – control with Arduino Nano Every

🇨🇿 [Česky](README.md) · 🇬🇧 **English**

An interface that brings the Czechoslovak **Aritma Minigraf A 0507** and **Aritma XY 4131** pen plotters back to life and lets you
plot from an **Atari XE/XL** computer (via SIO) and from a **PC** (via USB).

![Example – lettering with frame and star](docs/img/ukazka_napis.jpg)

*Author: Zdeněk Kotrba · © 2026 · version 0.5.0 (firmware 0.5.0)*

---

## Features

- **From the Atari** you plot with a plain `LPRINT` – the Arduino appears on the SIO bus as printer **P1:**.
- **From a PC** you plot HPGL files (e.g. from Inkscape) and lettering in a built-in stroke font with Czech diacritics.
- Simplified **HPGL commands**: `IN`, `PU`, `PD`, `PA`, `PR`, `CI`, plus `VS` (speed) and `PT` (pen delay).
- **Handshaking** – the next command is sent only after the plotter has finished the previous one; nothing gets lost.
- **Gradual acceleration and deceleration** of the motors, tested up to 80 mm/s (default 60 mm/s).
- The Atari is **galvanically isolated** by three CNY75C optocouplers.
- Since version 0.4.0 the same Arduino also drives the **XY 4131** plotter – both plotters can be connected at once, the one selected with `PL` draws.

```
Atari XE ──SIO──[3× optocoupler]── Arduino ──7 signals── Minigraf A 0507
                                      │       └─5 signals── XY 4131
                                      │
                                     USB
                                      │
                                      PC
```

## Repository layout

| Path | Content |
|---|---|
| `firmware/minigraf_sio/minigraf_sio.ino` | firmware for Arduino Nano Every (ATmega4809) and Leonardo/Micro (ATmega32U4), Minigraf and XY 4131 |
| `firmware/xy4131_test/xy4131_test.ino` | test program for bringing up the XY 4131 (single-signal control) |
| `pc/plot.py` | sending HPGL files from a PC |
| `pc/text_plot.py` | lettering, text in lines and test page, block and script font |
| `pc/hershey_script.py` | script font data (`--font psane`), must be in the same folder as `text_plot.py` |
| `docs/Minigraf_0507_XY4131_manual_v0.5.0_EN.pdf` | full manual in English (wiring, commands, examples, troubleshooting) |
| `docs/Minigraf_0507_XY4131_navod_v0.5.0.pdf` | full manual in Czech |
| `docs/img/` | schematics (EN and CZ) and photos of results |

## Hardware

| Signal | Nano Every | Leonardo / Micro | Minigraf pin |
|---|---|---|---|
| SIO Data Out (via OK1) | D0 (RX1) | D0 (RX1) | – |
| SIO Data In (via OK3) | D1 (TX1) | D1 (TX1) | – |
| SIO Command (via OK2) | D2 | D2 | – |
| X1 / X2 / X4 | A0 / A1 / A2 | A0 / A1 / A2 | 10 / 9 / 8 |
| Y1 / Y2 / Y4 | A3 / **A6** / **A7** | A3 / A4 / A5 | 4 / 3 / 2 |
| P (pen) | D10 | D10 | 5 |
| GND | GND | GND | 1, 11 |

**Plotter connector:** edge connector with 2.54 mm pitch (same type as ZX Spectrum bus peripherals),
12 positions, **position 7 is a key** and counts in the numbering. Only the bottom row of contacts is used.

![Minigraf connector](docs/img/konektor.png)

> ⚠️ Atari ground and Arduino/plotter ground must **never be connected** – that is what the optocouplers are for.
> The Arduino is powered from USB, the plotter from its own 24 V supply.

Schematics: [Nano Every](docs/img/schema_nano_every_en.jpg) · [Leonardo / Micro](docs/img/schema_leonardo_micro_en.jpg) · [XY 4131](docs/img/schema_xy4131_en.jpg)

### XY 4131 plotter (since version 0.4.0)

| Signal | Nano Every / Leonardo | INPUT pin | Meaning (verified) |
|---|---|---|---|
| PEN | D6 | 1 | 1 = pen down (coil), 0 = up (spring) |
| STEP | D3 | 2 | idle 1, pulse to 0 = one 0.1 mm step |
| X/Y | D5 | 3 | 0 = carriage (X axis), 1 = paper (Y axis) |
| +/− | D4 | 4 | carriage 1 = right, paper 1 = forward |
| READY | D7 | 5 | not used |
| GND | GND | 6 | ground |

Connector: round 7-pin **INPUT** socket on the plotter, TESLA **WK 180 35** plug with coupling nut on the cable. Pin numbers are moulded in the blue insert; pin 7 (centre) is not connected.

![XY 4131 connector](docs/img/konektor_xy4131.jpg)

220 Ω in series with D3–D6 recommended. Select the plotter with `PL4131;` (back: `PL0507;`); the choice is stored in EEPROM. It can be switched from the Serial Monitor, from a PC (`py plot.py --select 0507`, or `--plotter 4131` directly when drawing) and from the Atari (`LPRINT "PL0507;"`).
Step 0.1 mm, carriage travel about 180 mm (X limit = 1780), start after `HM` 10 mm from the left end contact.
The PC programs detect the plotter from the Arduino:
```
py text_plot.py "Zdeněk XY4131" --frame --star --bold 3 --send
```
> ⚠️ The plotter has a **pen switch** on its panel – when off, the pen does not react. The carriage end contacts must spring back freely:
> a stuck left contact also blocks moving right.

## Quick start

### 1. Firmware
1. Arduino IDE → Boards Manager → install **Arduino megaAVR Boards**.
2. Board **Arduino Nano Every**, open `firmware/minigraf_sio/minigraf_sio.ino` and upload.

### 2. Plotting from Atari BASIC
```basic
10 LPRINT "HM;IN;"
20 LPRINT "PU100,100;PD1400,100,1400,2000,100,2000,100,100;"
30 LPRINT "PU750,1050;CI400;"
40 LPRINT "PU0,0;"
```

### 3. Plotting from a PC (Windows)
```
py -m pip install pyserial
cd pc
py text_plot.py "HELLO" --frame --bold 3 --send
py text_plot.py "Zdeněk Kotrba" --font psane --frame --star --send
py text_plot.py --test --portrait --send
py plot.py drawing.hpgl
```
Gentler drawing (older plotter): `py text_plot.py --test --portrait --send --accel 9000,150 --diag 1`

The default port is `COM4` (another one: `py plot.py COM7 drawing.hpgl` or `--port COM7`).
Load A4 paper **with its top edge at the cut-outs under the feed pinch wheels**. Before plotting the head homes itself to the left stop and the start position X = 60, Y = 144 (`HM` command); disable with `--nohome`.

## Command reference

| Command | Meaning |
|---|---|
| `HM[x[,y]];` | home to the left stop (X = 0), loaded paper = Y 0, then move to start (default 60,144) |
| `LM x[,y];` | area limits in steps from the stop, stored in EEPROM (default 1580, 2284) |
| `IN;` | current position = drawing origin 0,0, pen up |
| `PU x,y;` | pen up and move |
| `PD x,y,...;` | pen down and draw |
| `PA;` / `PR;` | absolute / relative coordinates |
| `CI r[,n];` | circle of radius r around the current position |
| `VS v;` | speed in mm/s (`VS;` = default 60) |
| `PT d,u;` | pen delay in ms after pen down / pen up (`PT;` = 30 / 70) |
| `AC s,r;` | acceleration: start delay s µs, shortened by r µs per step (`AC;` = 6000 / 250) |
| `DG0;` / `DG1;` | diagonal lines at full speed / slowed ×1.4 (`DG;` = 0) |
| `PL0507;` / `PL4131;` | plotter selection, stored in EEPROM (`PL;` = print) |
| `SI n;` | text height in mm (capitals), default 6 |
| `FN0;` / `FN1;` | block / script font |
| `DI0;` / `DI1;` | text along X / rotated 90° |
| `LBtext` | writes text from the pen position (to the end of the line or `CHR$(3)`); Czech: `c^` = č, `a'` = á, `u*` = ů, UTF-8 or Kamenický |
| `?` | USB only: firmware version and status |

Unit = 1 plotter step: Minigraf 0.125 mm, XY 4131 0.1 mm. Each plotter has its own `VS`, `PT`, `AC` defaults and `LM` limits. Minigraf: drawing area from the start position 1520 × 2140 steps (190 × 267.5 mm) = A4 with 10 mm side margins and 15 mm top and bottom.

![Test page](docs/img/ukazka_test.jpg)

*Test page 6 / 4 / 3 / 2 mm, 0.5 mm marker, default settings of version 0.3.4.*
*The ink blot in the last line near "JKLM" appeared because one command was lost on USB and version 0.3.4 waited
20 s with the pen down before resending it. From version 0.3.5 the firmware lifts the pen after 1 s and `plot.py` queries after 3 s.*

See the [PDF manual](docs/Minigraf_0507_XY4131_manual_v0.5.0_EN.pdf) for details.
Note: the firmware and the PC programs print their status messages in Czech.

## Version history

- **0.5.0** – **text directly from the Atari**: the firmware contains the block and script fonts and new commands `SI` (size), `FN` (font), `DI` (direction) and `LB` (label). Czech via `c^`/`a'`/`u*`, UTF-8 or Kamenický encoding. Font data generator `tools/gen_font.py`. Firmware 27 kB (Nano Every 48 kB, Leonardo 28 kB – just fits).

- **0.4.5** (manuals only) – photo of the script font plotted on the Minigraf A 0507.
- **0.4.4** (PC programs only) – switching the plotter from the command line: `py plot.py --select 0507` / `--select 4131`; `--plotter 0507/4131` in `plot.py` and `text_plot.py` switches the Arduino directly. The manual shows plotter selection from Atari BASIC. Firmware stays 0.4.2.
- **0.4.3** (`text_plot.py` only) – **handwriting-like script**: option `--font psane` (Hershey single-stroke script font with added Czech diacritics, data in `hershey_script.py`); text wraps by actual letter widths. Firmware stays 0.4.2.

![Script font](docs/img/psane_ukazka.png)

![Script font on the Minigraf 0507](docs/img/foto_psane_0507.jpg)

*Script font plotted on the Minigraf A 0507.*

- **0.4.2** – manual renamed to "Minigraf 0507 and XY 4131" with a section on the XY 4131 connector (INPUT socket, TESLA WK 180 35 cable plug, photos); corrected connector designation in firmware, schematic and test program (0.10). No functional firmware change.
- **0.4.1** (firmware only) – fix: with the SIO interface disconnected (Command line stuck L) the firmware waited only for the Atari, ignored USB and the LED did not blink. It now reports it after 0.3 s and keeps serving USB; D2 also gets the internal pull-up.
- **0.4.0** – **Aritma XY 4131** support in the same firmware (selection `PL0507;` / `PL4131;`, stored in EEPROM; limits stored per plotter); `plot.py` and `text_plot.py` detect the plotter from the Arduino and use the right scale and area (`--plotter` option); test program `xy4131_test.ino`; manuals with an XY 4131 chapter.
- **0.3.8** – Y axis referenced to paper loading: start after `HM` is 60,144 and Y limit 2284, giving A4 margins of 10 / 10 / 15 / 15 mm (measured) and keeping the paper in the feed wheels; `text_plot.py` uses a 190 × 267.5 mm area (default `--margin` 8 / 5 mm).
- **0.3.5** – no ink blots on a dropout: the firmware lifts the pen when no command arrives for 1 s; `plot.py` recovers after 3 s.
- **0.3.4** – fixed the cause of dropouts: the 10-second status printout could overflow the Arduino's 64-byte receive buffer and truncate a command; it is no longer printed while drawing and `plot.py` sends lines shorter than 64 characters.
- **0.3.3** (PC programs only) – `plot.py` checks that the firmware supports `HM` (version 0.3 or newer) and stops with a clear message if the head does not home.
- **0.3.2** – new defaults verified by printing: acceleration `AC6000,250`, diagonal lines at full speed `DG0`, pen delay `PT30,70`.
- **0.3.1** – fix: `plot.py` recovers from communication dropouts (after 20 s it queries the Arduino and resends the line), the firmware discards incomplete commands, `plot.py` prints the firmware version again.
- **0.3** – homing to the left stop `HM` (automatic before every PC drawing, `--nohome`), absolute position and area limits `LM` stored in EEPROM (verified X limit = 1580), `IN` no longer moves the motors.
- **0.2** – `AC` (acceleration) and `DG` (diagonal lines) commands, firmware version in `?` status and in the PC programs (`--version`), `--accel` and `--diag` options.
- **0.1** – first version: P1: printer emulation for Atari, PC control, lettering and text.

## Sources

- Connector pinout: [cygnus.speccy.cz – Aritma Minigraf 0507](https://cygnus.speccy.cz/popis_printer-aritma0507.php)
- Signal meaning: MZXR documentation for the ZX Spectrum, Minigraf emulation in the MAME project

## License

[MIT](LICENSE) © 2026 Zdeněk Kotrba
