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
    --accel 5000,300  zrychlení: pauza při rozjezdu v µs, zkrácení v µs za krok
    --diag 0      šikmé čáry plnou rychlostí (1 = zpomalené ×1,4)
    --nohome      nenajíždět na začátku na levý doraz (výkres začne tam, kde hlava stojí)
    --version     verze programu
Po připojení program vypíše verzi firmwaru v Arduinu. Před kreslením hlava
automaticky najede na levý doraz a startovní pozici X=60 (příkaz HM).

Před spuštěním dej pero do levého dolního rohu papíru (to bude 0,0).
Program posílá po jednom příkazu a čeká, až Arduino odpoví "hotovo",
takže se nic neztratí ani nepředběhne.
"""
import argparse
import re
import sys
import time

VERSION = "0.3.4"        # verze programu (potřebuje firmware 0.3 nebo novější, doporučeno 0.3.4)

DEFAULT_PORT = "COM4"     # port Arduina s plotterem

MAX_PAIRS = 4            # max. dvojic souřadnic na řádek (řádek < 64 znaků = buffer Arduina)
REPLY_TIMEOUT = 300      # s, max. doba kreslení jednoho řádku
PROBE_AFTER = 20         # s bez odpovědi -> zeptat se Arduina, jestli žije
MAX_RETRY = 3            # kolikrát poslat stejný řádek znovu
KNOWN = {"IN", "PU", "PD", "PA", "PR", "CI"}   # nastavení (VS, PT, AC, DG) přidávají volby, ne soubor


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


def setup_lines(speed=0, pen="", accel="", diag=None, home=True):
    """Nastavovací příkazy na začátek výkresu (prázdné = výchozí hodnoty firmwaru).
    home=True: hlava nejdřív najede na levý doraz a startovní pozici (HM)."""
    out = ["VS%d;" % speed if speed > 0 else "VS;", "PT%s;" % pen, "AC%s;" % accel]
    out.append("DG;" if diag is None else "DG%d;" % diag)
    if home:
        out.append("HM;")
    return out


def firmware_version(ser):
    """Zeptá se Arduina na stav ('?') a vrátí verzi firmwaru, nebo None."""
    ser.reset_input_buffer()
    ser.write(b"?\n")
    deadline = time.time() + 2
    ver = None
    while time.time() < deadline:
        line = ser.readline().decode("ascii", errors="ignore")
        m = re.search(r"FW ([0-9][0-9.]*)", line)
        if m:
            ver = m.group(1)
    ser.reset_input_buffer()
    return ver


def send_lines(port, lines):
    """Pošle řádky na Arduino, po každém čeká na 'hotovo'."""
    import serial                          # pyserial
    try:
        ser = serial.Serial(port, 115200, timeout=1)
    except serial.SerialException:
        sys.exit("Nejde otevřít port %s. Je Arduino připojené a Sériový monitor zavřený?" % port)
    time.sleep(2)                          # Arduino se může po otevření portu restartovat
    ser.reset_input_buffer()
    ver = firmware_version(ser)
    print("plot.py %s | firmware v Arduinu: %s" % (VERSION, ver or "neznámá (starší než 0.2?)"))
    if "HM;" in lines:
        try:
            vt = tuple(int(x) for x in (ver or "0").split("."))
        except ValueError:
            vt = (0,)
        if vt < (0, 3):
            ser.close()
            sys.exit("Firmware v Arduinu (%s) nezná najetí na nulu HM – potřeba je verze 0.3 nebo novější.\n"
                     "Nahraj do Arduina aktuální minigraf_sio.ino, nebo kresli s volbou --nohome." % (ver or "neznámá"))
    t0 = time.time()
    retries_total = 0
    for n, line in enumerate(lines, 1):
        retry = 0
        ser.write((line + "\n").encode("ascii"))
        deadline = time.time() + REPLY_TIMEOUT
        probe_at = time.time() + PROBE_AFTER
        probed = False
        saw_hm = False
        while True:
            reply = ser.readline().decode("ascii", errors="ignore").strip()
            if reply.startswith("HM:"):
                saw_hm = True
                print("\r  " + reply)
            if reply == "hotovo":
                if line == "HM;" and not saw_hm:
                    ser.close()
                    sys.exit("\nArduino potvrdilo HM, ale hlava na nulu nenajela (firmware HM nezná?). Kreslení zastaveno.")
                break
            if reply.startswith("==="):
                sys.exit("\nARDUINO SE RESTARTOVALO u řádku %d/%d (%s).\n"
                         "Poloha je ztracená. Nejspíš rušení nebo pokles napájení od motorů." % (n, len(lines), line))
            if probed and reply.startswith("[bezi]"):
                # Arduino žije, ale na řádek neodpovědělo -> ztratil se příkaz nebo odpověď
                retry += 1
                retries_total += 1
                if retry > MAX_RETRY:
                    sys.exit("\nŘádek %d/%d se nepodařilo poslat ani na %d. pokus: %s" % (n, len(lines), MAX_RETRY, line))
                print("\n  ! bez odpovědi, posílám znovu (%d. pokus): %s" % (retry, line))
                ser.reset_input_buffer()
                ser.write((line + "\n").encode("ascii"))
                probe_at = time.time() + PROBE_AFTER
                probed = False
                continue
            if not probed and time.time() > probe_at:
                ser.write(b"?\n")                # zeptat se; dlouhé kreslení odpoví až po dokončení
                probed = True
            if time.time() > deadline:
                sys.exit("\nArduino neodpovídá ani na dotaz (řádek %d/%d: %s).\n"
                         "Zkontroluj LED na Arduinu a zkus reset." % (n, len(lines), line))
        print("\r%d/%d  %3d %%  %s" % (n, len(lines), n * 100 // len(lines), line[:40].ljust(40)),
              end="", flush=True)
    if retries_total:
        print("\nZnovu posláno řádků: %d (výpadky komunikace)" % retries_total, end="")
    ser.close()
    print("\nHotovo za %.0f s." % (time.time() - t0))


def main():
    ap = argparse.ArgumentParser(description="HPGL -> Minigraf A 0507 přes Arduino (plot.py %s)" % VERSION)
    ap.add_argument("args", nargs="+", metavar="[PORT] SOUBOR",
                    help="HPGL soubor, volitelně před ním port (výchozí %s)" % DEFAULT_PORT)
    ap.add_argument("--scale", type=float, default=0.2)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--speed", type=int, default=0)
    ap.add_argument("--pen", default="")
    ap.add_argument("--accel", default="")
    ap.add_argument("--diag", type=int, choices=(0, 1), default=None)
    ap.add_argument("--nohome", action="store_true")
    ap.add_argument("--version", action="version", version="plot.py " + VERSION)
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
    lines = setup_lines(a.speed, a.pen, a.accel, a.diag, not a.nohome) + lines

    if a.dry:
        print("\n".join(lines))
        print("--- %d řádků" % len(lines))
        return
    print("Port %s, %d řádků" % (port, len(lines)))
    send_lines(port, lines)


if __name__ == "__main__":
    main()
