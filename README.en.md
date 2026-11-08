# Minigraf 0507 – control with Arduino Nano Every

🇨🇿 [Česky](README.md) · 🇬🇧 **English**

An interface that brings the Czechoslovak **Aritma Minigraf A 0507** pen plotter back to life and lets you
plot from an **Atari XE/XL** computer (via SIO) and from a **PC** (via USB).

![Example – lettering with frame and star](docs/img/ukazka_napis.jpg)

*Author: Zdeněk Kotrba · © 2026 · version 0.3.2 (firmware 0.3.2)*

---

## Features

- **From the Atari** you plot with a plain `LPRINT` – the Arduino appears on the SIO bus as printer **P1:**.
- **From a PC** you plot HPGL files (e.g. from Inkscape) and lettering in a built-in stroke font with Czech diacritics.
- Simplified **HPGL commands**: `IN`, `PU`, `PD`, `PA`, `PR`, `CI`, plus `VS` (speed) and `PT` (pen delay).
- **Handshaking** – the next command is sent only after the plotter has finished the previous one; nothing gets lost.
- **Gradual acceleration and deceleration** of the motors, tested up to 80 mm/s (default 60 mm/s).
- The Atari is **galvanically isolated** by three CNY75C optocouplers.

```
Atari XE ──SIO──[3× optocoupler]── Arduino ──7 signals── Minigraf A 0507
                                      │
                                     USB
                                      │
                                      PC
```

## Repository layout

| Path | Content |
|---|---|
| `firmware/minigraf_sio/minigraf_sio.ino` | firmware for Arduino Nano Every (ATmega4809) and Leonardo/Micro (ATmega32U4) |
| `pc/plot.py` | sending HPGL files from a PC |
| `pc/text_plot.py` | lettering, text in lines and test page |
| `docs/Minigraf_0507_manual_v0.3.2_EN.pdf` | full manual in English (wiring, commands, examples, troubleshooting) |
| `docs/Minigraf_0507_navod_v0.3.2.pdf` | full manual in Czech |
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

Schematics: [Nano Every](docs/img/schema_nano_every_en.jpg) · [Leonardo / Micro](docs/img/schema_leonardo_micro_en.jpg)

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
py text_plot.py --test --portrait --send
py plot.py drawing.hpgl
```
Gentler drawing (older plotter): `py text_plot.py --test --portrait --send --accel 9000,150 --diag 1`

The default port is `COM4` (another one: `py plot.py COM7 drawing.hpgl` or `--port COM7`).
Before plotting the head homes itself to the left stop and the start position X = 60 (`HM` command); disable with `--nohome`.

## Command reference

| Command | Meaning |
|---|---|
| `HM[x];` | home to the left stop (X = 0), then move to the start position (default X = 60) |
| `LM x[,y];` | area limits in steps from the stop, stored in EEPROM (default 1580, 2103) |
| `IN;` | current position = drawing origin 0,0, pen up |
| `PU x,y;` | pen up and move |
| `PD x,y,...;` | pen down and draw |
| `PA;` / `PR;` | absolute / relative coordinates |
| `CI r[,n];` | circle of radius r around the current position |
| `VS v;` | speed in mm/s (`VS;` = default 60) |
| `PT d,u;` | pen delay in ms after pen down / pen up (`PT;` = 30 / 70) |
| `AC s,r;` | acceleration: start delay s µs, shortened by r µs per step (`AC;` = 6000 / 250) |
| `DG0;` / `DG1;` | diagonal lines at full speed / slowed ×1.4 (`DG;` = 0) |
| `?` | USB only: firmware version and status |

Unit = 1 step = 0.125 mm. Drawing area from the start position 1521 × 2104 steps (190 × 263 mm).

![Test page](docs/img/ukazka_test.jpg)

See the [PDF manual](docs/Minigraf_0507_manual_v0.3.2_EN.pdf) for details.
Note: the firmware and the PC programs print their status messages in Czech.

## Version history

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
