#!/usr/bin/env python3
"""
Posílání HPGL souboru z PC na Minigraf A 0507 nebo XY 4131 přes Arduino (USB).

Použití:
    py -m pip install pyserial
    py plot.py obrazek.hpgl                 (port COM4 je výchozí)
    py plot.py COM7 obrazek.hpgl            (jiný port)

Volby:
    --scale 0.2   přepočet souřadnic. Výchozí podle plotteru: HPGL z Inkscape
                  (40 jednotek/mm) -> Minigraf 0.2 (8 kroků/mm), XY 4131 0.25 (10 kroků/mm)
    --scale 1     soubor už je v krocích plotteru (Minigraf 0,125 mm, XY 4131 0,1 mm)
    --plotter 4131  kreslit pro tento plotter; má-li Arduino vybraný jiný, přepne ho
                  (příkaz PL, uloží se). Bez volby se plotter zjistí z Arduina.
    --select 0507   jen přepne plotter v Arduinu (0507 nebo 4131) a skončí:
                  py plot.py --select 0507
    --dry         nic neposílá, jen vypíše, co by poslal
    --speed 30    rychlost kreslení v mm/s (bez volby = výchozí z Arduina)
    --pen 40,70   prodleva pera v ms: po položení, po zvednutí
    --accel 5000,300  zrychlení: pauza při rozjezdu v µs, zkrácení v µs za krok
    --diag 0      šikmé čáry plnou rychlostí (1 = zpomalené ×1,4)
    --nohome      nenajíždět na začátku na levý doraz (výkres začne tam, kde hlava stojí)
    --version     verze programu
Po připojení program vypíše verzi firmwaru a vybraný plotter. Před kreslením hlava
automaticky najede na levý doraz a startovní pozici (příkaz HM).

Před spuštěním dej pero do levého dolního rohu papíru (to bude 0,0).
Program posílá po jednom příkazu a čeká, až Arduino odpoví "hotovo",
takže se nic neztratí ani nepředběhne.
"""
import argparse
import re
import sys
import time

VERSION = "0.5.10"        # verze programu (potřebuje firmware 0.3 nebo novější, pro XY 4131 firmware 0.4.0)

DEFAULT_PORT = "COM4"     # port Arduina s plotterem

MAX_PAIRS = 4            # max. dvojic souřadnic na řádek (řádek < 64 znaků = buffer Arduina)
REPLY_TIMEOUT = 300      # s, max. doba kreslení jednoho řádku
PROBE_AFTER = 3          # s bez odpovědi -> zeptat se Arduina (dlouhé kreslení odpoví až po dokončení)
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
    out = ["AL1;",                         # tisk: firmware 0.5.2+ zvedne pero, když 1 s nepřijde příkaz (výpadek)
           "VS%d;" % speed if speed > 0 else "VS;", "PT%s;" % pen, "AC%s;" % accel]
    out.append("DG;" if diag is None else "DG%d;" % diag)
    if home:
        out.append("HM;")
    return out


SCALE = {"0507": 0.2, "4131": 0.25}     # HPGL z Inkscape (40 jednotek/mm) -> kroky plotteru


def firmware_info(ser):
    """Zeptá se Arduina na stav ('?'). Vrátí (verze, plotter): plotter '0507' nebo '4131'."""
    ser.reset_input_buffer()
    ser.write(b"?\n")
    deadline = time.time() + 2
    ver, pl = None, "0507"                 # firmware před 0.4.0 zná jen Minigraf
    while time.time() < deadline:
        line = ser.readline().decode("ascii", errors="ignore")
        m = re.search(r"FW ([0-9][0-9.]*)", line)
        if m:
            ver = m.group(1)
        if "XY4131" in line:
            pl = "4131"
    ser.reset_input_buffer()
    return ver, pl


def firmware_version(ser):
    return firmware_info(ser)[0]


def open_plotter(port):
    """Otevře port, vypíše verzi firmwaru a plotter. Vrátí (ser, verze, plotter)."""
    import serial                          # pyserial
    try:
        ser = serial.Serial(port, 115200, timeout=1)
    except serial.SerialException:
        sys.exit("Nejde otevřít port %s. Je Arduino připojené a Sériový monitor zavřený?" % port)
    time.sleep(2)                          # Arduino se může po otevření portu restartovat
    ser.reset_input_buffer()
    ver, pl = firmware_info(ser)
    print("plot.py %s | firmware v Arduinu: %s | plotter: %s" % (
        VERSION, ver or "neznámá (starší než 0.2?)", "XY 4131" if pl == "4131" else "Minigraf A 0507"))
    return ser, ver, pl


def select_plotter(ser, pl):
    """Přepne plotter v Arduinu příkazem PL (uloží se do EEPROM). Vrátí nově zjištěný plotter."""
    ser.reset_input_buffer()
    ser.write(("PL%s;\n" % pl).encode("ascii"))
    deadline = time.time() + 3
    while time.time() < deadline:
        line = ser.readline().decode("ascii", errors="ignore").strip()
        if line == "hotovo":
            break
    ver, found = firmware_info(ser)
    print("Plotter v Arduinu přepnut na: %s" % ("XY 4131" if found == "4131" else "Minigraf A 0507"))
    if found != pl:
        sys.exit("Přepnutí se nepovedlo – firmware v Arduinu je asi starší než 0.4.0.")
    return found


def hms(sec):
    """Čas jako 1 h 05 min 07 s / 12 min 34 s / 45 s."""
    sec = int(round(sec))
    h, m, s_ = sec // 3600, sec % 3600 // 60, sec % 60
    if h:
        return "%d h %02d min %02d s" % (h, m, s_)
    if m:
        return "%d min %02d s" % (m, s_)
    return "%d s" % s_


def clock(sec):
    sec = int(round(sec))
    return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60) if sec >= 3600 else "%d:%02d" % (sec // 60, sec % 60)


LOG_FILE = "plot_log.txt"   # záznam komunikace (přepíše se při každém kreslení)


def usb_count(ser):
    """Počet příkazových řádků, které Arduino z USB přijalo (firmware 0.5.1+), jinak None."""
    ser.reset_input_buffer()
    ser.write(b"?\n")
    deadline = time.time() + 2
    while time.time() < deadline:
        m = re.search(r"USB radku (\d+)", ser.readline().decode("ascii", errors="ignore"))
        if m:
            ser.reset_input_buffer()
            return int(m.group(1))
    return None


def send_lines(port, lines, ver=None):
    """Pošle řádky na Arduino, po každém čeká na 'hotovo'. port = název portu nebo otevřený port.
    Vše, co jde tam i zpět, se zapisuje do plot_log.txt."""
    if isinstance(port, str):
        ser, ver, _ = open_plotter(port)
    else:
        ser = port
    try:
        log = open(LOG_FILE, "w", encoding="utf-8")
    except OSError:
        log = None
    t_log = time.time()

    def L(kind, text):
        if log:
            log.write("%9.3f %s %s\n" % (time.time() - t_log, kind, text))
            log.flush()

    done_n = usb_count(ser)                # firmware 0.5.1+: počítadlo přijatých řádků
    L("--", "plot.py %s, firmware %s, USB radku na zacatku: %s" % (VERSION, ver, done_n))
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
    start_xy = None
    for n, line in enumerate(lines, 1):
        retry = 0
        if line.startswith("#PAUSE"):          # pauza pro výměnu pera (kondiciogram.py --pera)
            L("--", line)
            print("\n\n  >>> " + line[6:].strip())
            input("  >>> Až budeš hotov, stiskni Enter ... ")
            continue
        ser.write((line + "\n").encode("ascii"))
        L("->", line)
        echo_n = None
        deadline = time.time() + REPLY_TIMEOUT
        probe_at = time.time() + PROBE_AFTER
        probed = False
        saw_hm = False
        while True:
            reply = ser.readline().decode("ascii", errors="ignore").strip()
            if reply:
                L("<-", reply)
            m = re.match(r"> #(\d+) ", reply)
            if m:
                echo_n = int(m.group(1))
            elif reply and not (reply == "hotovo" or reply.startswith(("[bezi]", "HM:", "> ", "rychlost", "pero:", "plotter:"))
                                or reply.startswith(" ")):
                print("\n  Arduino: " + reply)       # neočekávaná hláška (např. zahozený neúplný příkaz)
            if reply.startswith("HM:"):
                saw_hm = True
                m = re.search(r"ted X=(-?\d+) Y=(-?\d+)", reply)
                if m and start_xy is None:
                    start_xy = (int(m.group(1)), int(m.group(2)))   # start po HM (= počátek IN)
                print("\r  " + reply)
            if reply == "hotovo":
                if line == "HM;" and not saw_hm:
                    ser.close()
                    sys.exit("\nArduino potvrdilo HM, ale hlava na nulu nenajela (firmware HM nezná?). Kreslení zastaveno.")
                if done_n is not None:
                    done_n = echo_n if echo_n else done_n + 1
                break
            if reply.startswith("==="):
                sys.exit("\nARDUINO SE RESTARTOVALO u řádku %d/%d (%s).\n"
                         "Poloha je ztracená. Nejspíš rušení nebo pokles napájení od motorů." % (n, len(lines), line))
            if probed and reply.startswith("[bezi]"):
                # Arduino žije, ale na řádek neodpovědělo -> ztratil se příkaz nebo odpověď
                m = re.search(r"USB radku (\d+)", reply)
                if m and done_n is not None and int(m.group(1)) > done_n:
                    # řádek Arduino přijalo a nakreslilo, ztratila se jen odpověď -> neposílat znovu
                    done_n = int(m.group(1))
                    retries_total += 1
                    print("\n  ! odpověď se ztratila, řádek ale Arduino nakreslilo – pokračuji: %s" % line)
                    L("!!", "ztracena odpoved, radek proveden (USB radku %d)" % done_n)
                    break
                retry += 1
                retries_total += 1
                if retry > MAX_RETRY:
                    sys.exit("\nŘádek %d/%d se nepodařilo poslat ani na %d. pokus: %s" % (n, len(lines), MAX_RETRY, line))
                print("\n  ! bez odpovědi, posílám znovu (%d. pokus): %s" % (retry, line))
                L("!!", "radek neprisel, posilam znovu (%d. pokus)" % retry)
                ser.reset_input_buffer()
                ser.write((line + "\n").encode("ascii"))
                probe_at = time.time() + PROBE_AFTER
                probed = False
                continue
            if not probed and time.time() > probe_at:
                ser.write(b"?\n")                # zeptat se; dlouhé kreslení odpoví až po dokončení
                L("->", "?")
                probed = True
            if time.time() > deadline:
                sys.exit("\nArduino neodpovídá ani na dotaz (řádek %d/%d: %s).\n"
                         "Zkontroluj LED na Arduinu a zkus reset." % (n, len(lines), line))
        el = time.time() - t0
        eta = el / n * (len(lines) - n)
        print("\r%d/%d  %3d %%  %s / zbývá ~%s  %s" % (n, len(lines), n * 100 // len(lines), clock(el), clock(eta),
                                                    line[:30].ljust(30)), end="", flush=True)
    if retries_total:
        print("\nVýpadky komunikace: %d (podrobnosti v %s)" % (retries_total, LOG_FILE), end="")
    # konec tisku: pero nahoru, papír i hlava zpět na začátek (HM) – jen když se kreslilo s HM;
    # pak AL0 = ruční příkazy z monitoru pero nezvedají
    # Papír i vozík nejdřív zpět do polohy, kde byly při prvním HM (absolutně 0,0 = počátek IN minus start),
    # takže po HM je papír přesně tam, kde se začínalo.
    if "HM;" in lines:
        back = "PU%d,%d;" % (-start_xy[0], -start_xy[1]) if start_xy else "PU0,0;"
        tail = ["PU;", back, "HM;", "AL0;"]
        print("\nPapír a hlava se vracejí na začátek (HM) ...", end="", flush=True)
    else:
        tail = ["PU;", "AL0;"]
    for cmd in tail:
        ser.write((cmd + "\n").encode("ascii"))
        L("->", cmd)
        end = time.time() + 120               # couvání papíru přes celou stránku chvíli trvá
        while time.time() < end:
            r = ser.readline().decode("ascii", errors="ignore").strip()
            if r:
                L("<-", r)
            if r == "hotovo":
                break
    ser.close()
    total = time.time() - t0
    L("--", "tisk dokoncen za %s, %d radku" % (hms(total), len(lines)))
    if log:
        log.close()
    print("\nTisk dokončen za %s (%d řádků, konec v %s)." % (hms(total), len(lines), time.strftime("%H:%M")))


def main():
    ap = argparse.ArgumentParser(description="HPGL -> Minigraf A 0507 přes Arduino (plot.py %s)" % VERSION)
    ap.add_argument("args", nargs="*", metavar="[PORT] SOUBOR",
                    help="HPGL soubor, volitelně před ním port (výchozí %s)" % DEFAULT_PORT)
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--plotter", choices=("auto", "0507", "4131"), default="auto")
    ap.add_argument("--select", choices=("0507", "4131"), default=None,
                    help="jen přepnout plotter v Arduinu a skončit")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--speed", type=int, default=0)
    ap.add_argument("--pen", default="")
    ap.add_argument("--accel", default="")
    ap.add_argument("--diag", type=int, choices=(0, 1), default=None)
    ap.add_argument("--nohome", action="store_true")
    ap.add_argument("--version", action="version", version="plot.py " + VERSION)
    a = ap.parse_args()
    if a.select:                           # py plot.py [PORT] --select 0507
        port = a.args[0] if a.args else DEFAULT_PORT
        ser, _, found = open_plotter(port)
        if found != a.select:
            select_plotter(ser, a.select)
        else:
            print("Plotter už je vybraný, nic se nemění.")
        ser.close()
        return
    if len(a.args) == 1:
        port, fname = DEFAULT_PORT, a.args[0]
    elif len(a.args) == 2:
        port, fname = a.args
    else:
        ap.error("zadej: [PORT] SOUBOR")

    with open(fname, "r", errors="ignore") as f:
        text = f.read()
    ser = ver = None
    pl = "0507" if a.plotter == "auto" else a.plotter
    if not a.dry:
        ser, ver, found = open_plotter(port)
        if a.plotter == "auto":
            pl = found
        elif found != pl:
            select_plotter(ser, pl)
    scale = a.scale if a.scale is not None else SCALE[pl]
    lines = to_lines(text, scale)
    if not lines:
        sys.exit("V souboru nejsou žádné příkazy.")
    lines = setup_lines(a.speed, a.pen, a.accel, a.diag, not a.nohome) + lines

    if a.dry:
        print("\n".join(lines))
        print("--- %d řádků (plotter %s, měřítko %g)" % (len(lines), pl, scale))
        return
    print("Port %s, %d řádků, měřítko %g" % (port, len(lines), scale))
    send_lines(ser, lines, ver)


if __name__ == "__main__":
    main()
