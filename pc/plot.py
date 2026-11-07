#!/usr/bin/env python3
"""
Posílání HPGL souboru z PC na Minigraf A 0507 přes Arduino (USB).

Použití:
    py -m pip install pyserial
    py plot.py obrazek.hpgl                 (port COM4 je výchozí)
    py plot.py COM7 obrazek.hpgl            (jiný port)

Volby:
    --scale 0.2   přepočet souřadnic (výchozí 0.2 = HPGL z Inkscape,
                  40 jednotek/mm -> kroky Minigrafu 8/mm)
    --scale 1     soubor už je v krocích Minigrafu (0,125 mm)
    --dry         nic neposílá, jen vypíše, co by poslal
    --speed 30    rychlost kreslení v mm/s (bez volby = výchozí z Arduina)
    --pen 40,70   prodleva pera v ms: po položení, po zvednutí

Před spuštěním dej pero do levého dolního rohu papíru (to bude 0,0).
Program posílá po jednom příkazu a čeká, až Arduino odpoví "hotovo",
takže se nic neztratí ani nepředběhne.
"""
import argparse
import re
import sys
import time

DEFAULT_PORT = "COM4"     # port Arduina s plotterem

MAX_PAIRS = 8            # max. dvojic souřadnic na jeden řádek
REPLY_TIMEOUT = 300      # s, max. doba kreslení jednoho řádku
KNOWN = {"IN", "PU", "PD", "PA", "PR", "CI", "PT"}


def hpgl_commands(text):
    """Rozdělí HPGL na (příkaz, [čísla])."""
    for part in re.split(r"[;\n\r]+", text):
        part = part.strip()
        if len(part) < 2 or not part[:2].isalpha():
            continue
        cmd = part[:2].upper()
        nums = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", part[2:])]
        yield cmd, nums


def to_lines(text, scale):
    """Převede HPGL na řádky pro Arduino (celá čísla, max. MAX_PAIRS dvojic)."""
    out = []
    for cmd, nums in hpgl_commands(text):
        if cmd not in KNOWN:
            continue                      # SP, VS, ... se ignorují
        if cmd == "IN":
            out.append("IN;")
            continue
        if cmd == "PT":
            out.append("PT" + ",".join(str(int(v)) for v in nums) + ";")
            continue
        if cmd == "CI":
            if nums:
                out.append("CI%d;" % round(nums[0] * scale))
            continue
        vals = [round(v * scale) for v in nums]
        if not vals:
            out.append(cmd + ";")
            continue
        for i in range(0, len(vals) - 1, 2 * MAX_PAIRS):
            chunk = vals[i:i + 2 * MAX_PAIRS]
            out.append(cmd + ",".join(str(v) for v in chunk) + ";")
    return out


def send_lines(port, lines):
    """Pošle řádky na Arduino, po každém čeká na 'hotovo'."""
    import serial                          # pyserial
    try:
        ser = serial.Serial(port, 115200, timeout=1)
    except serial.SerialException:
        sys.exit("Nejde otevřít port %s. Je Arduino připojené a Sériový monitor zavřený?" % port)
    time.sleep(2)                          # Arduino se může po otevření portu restartovat
    ser.reset_input_buffer()
    t0 = time.time()
    for n, line in enumerate(lines, 1):
        ser.write((line + "\n").encode("ascii"))
        deadline = time.time() + REPLY_TIMEOUT
        while True:
            reply = ser.readline().decode("ascii", errors="ignore").strip()
            if reply == "hotovo":
                break
            if reply.startswith("==="):
                sys.exit("\nARDUINO SE RESTARTOVALO u řádku %d/%d (%s).\n"
                         "Nejspíš rušení nebo pokles napájení od motorů - viz rady." % (n, len(lines), line))
            if time.time() > deadline:
                sys.exit("\nArduino neodpovědělo na: " + line)
        print("\r%d/%d  %3d %%  %s" % (n, len(lines), n * 100 // len(lines), line[:40].ljust(40)),
              end="", flush=True)
    ser.close()
    print("\nHotovo za %.0f s." % (time.time() - t0))


def main():
    ap = argparse.ArgumentParser(description="HPGL -> Minigraf A 0507 přes Arduino")
    ap.add_argument("args", nargs="+", metavar="[PORT] SOUBOR",
                    help="HPGL soubor, volitelně před ním port (výchozí %s)" % DEFAULT_PORT)
    ap.add_argument("--scale", type=float, default=0.2)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--speed", type=int, default=0)
    ap.add_argument("--pen", default="")
    a = ap.parse_args()
    if len(a.args) == 1:
        port, fname = DEFAULT_PORT, a.args[0]
    elif len(a.args) == 2:
        port, fname = a.args
    else:
        ap.error("zadej: [PORT] SOUBOR")

    with open(fname, "r", errors="ignore") as f:
        lines = to_lines(f.read(), a.scale)
    if not lines:
        sys.exit("V souboru nejsou žádné příkazy.")
    lines.insert(0, "VS%d;" % a.speed if a.speed > 0 else "VS;")
    lines.insert(1, "PT%s;" % a.pen)

    if a.dry:
        print("\n".join(lines))
        print("--- %d řádků" % len(lines))
        return
    print("Port %s, %d řádků" % (port, len(lines)))
    send_lines(port, lines)


if __name__ == "__main__":
    main()
