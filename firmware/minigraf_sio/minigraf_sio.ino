/*
 * Atari XE (SIO) -> Aritma Minigraf A 0507      firmware verze 0.3
 * -----------------------------------------
 * Arduino se na SIO sběrnici tváří jako tiskárna P1: (ID $40).
 * Z Atari se kreslí obyčejným LPRINT příkazy ve zjednodušeném HPGL:
 *
 *   IN;              inicializace, aktuální poloha pera = 0,0
 *   PU[x,y,...];     pero nahoru (+ přesun)
 *   PD[x,y,...];     pero dolů (+ kreslení)
 *   PA[x,y,...];     absolutní souřadnice (výchozí)
 *   PR[x,y,...];     relativní souřadnice
 *   CI r[,n];        kružnice o poloměru r kolem aktuální polohy (n úseků)
 *   VS v;            rychlost v mm/s (např. VS30;), VS; = výchozí
 *   PT d[,u];        prodleva pera v ms: po položení d, po zvednutí u (PT; = výchozí)
 *   LM x[,y];        meze plochy v krocích absolutně od levého dorazu, uloží se do EEPROM (LM; = vypsat)
 *   HM[x];           najetí na levý doraz (X=0) a popojetí na X (výchozí 60), Y = 0
 *   AC s[,r];        zrychlení: pauza při rozjezdu s µs, zkrácení r µs/krok (AC; = výchozí)
 *   DG0; / DG1;      šikmé čáry plnou rychlostí / zpomalené ×1,4 (DG; = výchozí)
 *
 * Jednotka = 1 krok Minigrafu = 0,125 mm. Meze plochy nastaví LM (výchozí 0..1580 x 0..2103, ověřeno).
 *
 * Desky (vybírá se automaticky podle procesoru):
 *   Arduino Nano Every (ATmega4809)  – doporučeno
 *   Arduino Leonardo / Micro (ATmega32U4)
 * Na obou: Serial1 (D0 RX, D1 TX) = SIO data, Serial (USB) = ladicí výpisy.
 *
 * Výstupy na Minigraf – všech 6 fází leží na jednom portu a mění se naráz
 * (žádné přechodové stavy čítače fáze):
 *
 *            Nano Every (PORTD)    Leonardo/Micro (PORTF)
 *   X1       A0                    A0
 *   X2       A1                    A1
 *   X4       A2                    A2
 *   Y1       A3                    A3
 *   Y2       A6   (!)              A4
 *   Y4       A7   (!)              A5
 *   P        D10                   D10
 */

#include <Arduino.h>
#include <math.h>
#include <EEPROM.h>

#define FW_VERSION "0.3"

// ================= Nastavení =================
const uint8_t  PIN_CMD        = 2;      // SIO Command přes optočlen (LOW = aktivní)
const uint8_t  PIN_PEN        = 10;
const uint8_t  DEVICE_ID      = 0x40;   // P1:
const uint32_t SIO_BAUD       = 19200;

const bool     PEN_DOWN_LEVEL = HIGH;   // ověřit na plotteru, případně LOW
const int8_t   X_DIR          = +1;     // -1 když osa jede obráceně
const int8_t   Y_DIR          = +1;
const int      X_MAX_DEF      = 1580;   // výchozí meze (absolutně od levého dorazu), mění LM
const int      Y_MAX_DEF      = 2103;   // a ukládají se do EEPROM
const unsigned STEP_US        = 2083;   // výchozí rychlost 60 mm/s (125000 / 60)
const unsigned START_US       = 9000;   // výchozí pauza při rozjezdu z klidu (~14 mm/s), mění AC
const unsigned RAMP_US        = 150;    // výchozí zkrácení pauzy každým krokem rozjezdu, mění AC
const bool     DIAG_SLOW      = true;
const int      HOME_X         = 60;     // HM: kam popojet od levého dorazu (startovní pozice osy X)
const int8_t   HOME_DIR       = -1;     // HM: směr k dorazu (-1 = k menším X); +1 když jede na druhou stranu
const int      HOME_EXTRA     = 200;    // HM: o kolik kroků víc než šířka plochy (jistota dorazu)
const unsigned HOME_US        = 2500;   // HM: rychlost jízdy k dorazu (~50 mm/s)   // výchozí zpomalení šikmých čar ×1,4, mění DG
const unsigned MIN_STEP_US    = 1500;   // nejrychlejší povolené (VS nepustí rychleji)
const unsigned PEN_DOWN_MS    = 0;      // čekání po položení pera (vyzkoušeno: 0)
const unsigned PEN_UP_MS      = 70;     // čekání po zvednutí pera (vyzkoušeno: 70)
const uint8_t  PRN_TIMEOUT_S  = 255;    // max. doba čekání Atari na 'C' (jednotka ~1 s, 255 = max.)

// ================= Minigraf =================
static unsigned stepUs = STEP_US;                         // rychlost (VS)
static unsigned startUs = START_US, rampUs = RAMP_US;     // zrychlení (AC)
static bool     diagSlow = DIAG_SLOW;                     // šikmé čáry (DG)
static unsigned penDownMs = PEN_DOWN_MS, penUpMs = PEN_UP_MS; // prodleva pera (PT)
static uint8_t phX = 0, phY = 0;
static int     posX = 0, posY = 0;      // ABSOLUTNÍ poloha v krocích (od dorazu po HM, jinak od zapnutí)
static int     orgX = 0, orgY = 0;      // počátek kreslení nastavený IN (souřadnice příkazů jsou relativně k němu)
static int     xMax = X_MAX_DEF, yMax = Y_MAX_DEF;

// ---- meze v EEPROM ----
struct Limits { uint16_t magic; int16_t x, y; };
const uint16_t LIM_MAGIC = 0x4D47;      // "MG"
static void loadLimits() {
  Limits l; EEPROM.get(0, l);
  if (l.magic == LIM_MAGIC && l.x >= 100 && l.y >= 100) { xMax = l.x; yMax = l.y; }
}
static void saveLimits() {
  Limits l = { LIM_MAGIC, (int16_t)xMax, (int16_t)yMax };
  EEPROM.put(0, l);
}
static bool    penIsDown = false;
static bool    absMode = true;

#if defined(__AVR_ATmega4809__)
// Nano Every: A3=PD0 A2=PD1 A1=PD2 A0=PD3 A6=PD4 A7=PD5
const uint8_t PH_PINS[6] = { A0, A1, A2, A3, A6, A7 };   // X1 X2 X4 Y1 Y2 Y4
const uint8_t PH_BIT[6]  = { 3, 2, 1, 0, 4, 5 };
#define PH_PORT VPORTD.OUT
#elif defined(__AVR_ATmega32U4__)
// Leonardo/Micro: A0=PF7 A1=PF6 A2=PF5 A3=PF4 A4=PF1 A5=PF0
const uint8_t PH_PINS[6] = { A0, A1, A2, A3, A4, A5 };
const uint8_t PH_BIT[6]  = { 7, 6, 5, 4, 1, 0 };
#define PH_PORT PORTF
#else
#error "Podporovano: Nano Every (ATmega4809) nebo Leonardo/Micro (ATmega32U4)"
#endif

static void writePhases() {
  uint8_t mask = 0, v = 0;
  for (uint8_t i = 0; i < 6; i++) {
    uint8_t ph = (i < 3) ? phX : phY;
    uint8_t b  = _BV(PH_BIT[i]);
    mask |= b;
    if (ph & (1 << (i % 3))) v |= b;
  }
  uint8_t s = SREG; cli();
  PH_PORT = (PH_PORT & ~mask) | v;
  SREG = s;
}

static void stepAxes(int8_t mx, int8_t my) {
  if (mx) { phX = (phX + mx * X_DIR) & 7; posX += mx; }
  if (my) { phY = (phY + my * Y_DIR) & 7; posY += my; }
  writePhases();
}

static void pen(bool down) {
  if (down == penIsDown) return;
  digitalWrite(PIN_PEN, down ? PEN_DOWN_LEVEL : !PEN_DOWN_LEVEL);
  delay(down ? penDownMs : penUpMs);
  penIsDown = down;
}

static void lineTo(int x, int y) {          // Bresenham, obě osy současně
  x = constrain(x, 0, xMax);               // meze platí pro absolutní polohu
  y = constrain(y, 0, yMax);
  int dx = abs(x - posX), dy = abs(y - posY);
  int8_t sx = (x > posX) ? 1 : -1;
  int8_t sy = (y > posY) ? 1 : -1;
  int err = dx - dy;
  int total = max(dx, dy), done = 0;
  while (posX != x || posY != y) {
    int e2 = 2 * err;
    int8_t mx = 0, my = 0;
    if (e2 > -dy) { err -= dy; mx = sx; }
    if (e2 <  dx) { err += dx; my = sy; }
    stepAxes(mx, my);
    // lichoběžníková rampa: pomalý rozjezd, plná rychlost, pomalý dojezd
    int edge = min(done, total - 1 - done);
    long d = (long)startUs - (long)edge * rampUs;
    if (d < (long)stepUs) d = stepUs;
    if (diagSlow && mx && my) d = d * 7 / 5; // šikmo jedou oba motory -> zpomalit (~sqrt 2)
    delayMicroseconds((unsigned)d);
    done++;
  }
}

// HM: jízda na levý doraz přes celou šířku (motor na dorazu proklouzne), pak na startovní X
static void homeX(int targetX) {
  pen(false);
  long n = (long)xMax + HOME_EXTRA;
  for (long i = 0; i < n; i++) {
    phX = (phX + HOME_DIR * X_DIR) & 7;
    writePhases();
    long d = (long)startUs - i * (long)rampUs;
    if (d < (long)HOME_US) d = HOME_US;
    delayMicroseconds((unsigned)d);
  }
  delay(100);                              // dorazit a uklidnit
  posX = 0;
  posY = 0;                                // osa Y (papír) se nehýbe, aktuální řádek = 0
  orgX = 0; orgY = 0;                      // souřadnice = absolutní (PU60,0 = startovní pozice)
  absMode = true;
  lineTo(targetX, 0);
  Serial.print(F("HM: na dorazu X=0, ted X=")); Serial.print(posX); Serial.println(F(" Y=0"));
}

static void moveCoords(const long *v, uint8_t n) {
  for (uint8_t i = 0; i + 1 < n; i += 2) {
    if (absMode) lineTo(orgX + (int)v[i], orgY + (int)v[i + 1]);
    else         lineTo(posX + (int)v[i], posY + (int)v[i + 1]);
  }
}

static void circle(long r, long segs) {
  if (r <= 0) return;
  if (segs < 8) segs = 72;
  int cx = posX, cy = posY;
  bool wasDown = penIsDown;
  pen(false);
  lineTo(cx + r, cy);
  pen(true);
  for (long i = 1; i <= segs; i++) {
    float a = 2.0f * (float)M_PI * i / segs;
    lineTo(cx + (int)lround(r * cosf(a)), cy + (int)lround(r * sinf(a)));
  }
  pen(false);
  lineTo(cx, cy);
  pen(wasDown);
}

// ================= Interpret příkazů =================
static void execCmd(char c1, char c2, const long *v, uint8_t n) {
  Serial.print(c1); Serial.print(c2); Serial.print(" n="); Serial.println(n);
  if      (c1 == 'I' && c2 == 'N') { pen(false); orgX = posX; orgY = posY; absMode = true; }   // počátek = aktuální poloha, motory se nehýbou
  else if (c1 == 'P' && c2 == 'U') { pen(false); moveCoords(v, n); }
  else if (c1 == 'P' && c2 == 'D') { pen(true);  moveCoords(v, n); }
  else if (c1 == 'P' && c2 == 'A') { absMode = true;  moveCoords(v, n); }
  else if (c1 == 'P' && c2 == 'R') { absMode = false; moveCoords(v, n); }
  else if (c1 == 'V' && c2 == 'S') {       // VS rychlost v mm/s, VS bez čísla = výchozí
    if (n >= 1 && v[0] > 0) {
      long us = 125000L / v[0];            // 1 krok = 0,125 mm
      stepUs = (us < MIN_STEP_US) ? MIN_STEP_US : (us > 9000 ? 9000 : (unsigned)us);
    } else stepUs = STEP_US;
    Serial.print(F("rychlost: krok ")); Serial.print(stepUs); Serial.println(F(" us"));
  }
  else if (c1 == 'L' && c2 == 'M') {       // LM x[,y]; meze plochy (absolutně od dorazu), uloží se; LM; = vypsat
    if (n >= 1) {
      xMax = constrain(v[0], 100, 30000);
      if (n >= 2) yMax = constrain(v[1], 100, 30000);
      saveLimits();
    }
    Serial.print(F("meze: X 0..")); Serial.print(xMax); Serial.print(F(" Y 0..")); Serial.print(yMax);
    Serial.println(n >= 1 ? F(" (ulozeno)") : F(""));
  }
  else if (c1 == 'H' && c2 == 'M') {       // HM[x]; najetí na levý doraz a pak na X (výchozí 60)
    homeX(n >= 1 ? (int)v[0] : HOME_X);
  }
  else if (c1 == 'A' && c2 == 'C') {       // AC rozjezd_us[,ramp_us], AC; = výchozí
    if (n >= 1) { startUs = constrain(v[0], MIN_STEP_US, 16000); if (n >= 2) rampUs = constrain(v[1], 1, 5000); }
    else        { startUs = START_US; rampUs = RAMP_US; }
    Serial.print(F("zrychleni: rozjezd ")); Serial.print(startUs);
    Serial.print(F(" us, ramp ")); Serial.print(rampUs); Serial.println(F(" us/krok"));
  }
  else if (c1 == 'D' && c2 == 'G') {       // DG0 = šikmo bez zpomalení, DG1 = se zpomalením, DG; = výchozí
    diagSlow = (n >= 1) ? (v[0] != 0) : DIAG_SLOW;
    Serial.print(F("sikme cary: ")); Serial.println(diagSlow ? F("zpomalene") : F("plna rychlost"));
  }
  else if (c1 == 'P' && c2 == 'T') {       // PT dolů[,nahoru] v ms, PT; = výchozí
    if (n >= 1) { penDownMs = constrain(v[0], 0, 1000); penUpMs = (n >= 2) ? constrain(v[1], 0, 1000) : penUpMs; }
    else        { penDownMs = PEN_DOWN_MS; penUpMs = PEN_UP_MS; }
    Serial.print(F("pero: dolu ")); Serial.print(penDownMs);
    Serial.print(F(" ms, nahoru ")); Serial.print(penUpMs); Serial.println(F(" ms"));
  }
  else if (c1 == 'C' && c2 == 'I') { if (n >= 1) circle(v[0], n >= 2 ? v[1] : 72); }
  // ostatní (SP, ...) se ignorují
}

static void parseLine(char *s) {
  const uint8_t MAXN = 32;
  long v[MAXN];
  while (*s) {
    if (!isalpha(s[0])) { s++; continue; }
    if (!isalpha(s[1])) { s++; continue; }
    char c1 = toupper(s[0]), c2 = toupper(s[1]);
    s += 2;
    uint8_t n = 0;
    for (;;) {
      while (*s == ' ' || *s == ',') s++;
      char *e;
      long x = strtol(s, &e, 10);
      if (e == s) break;
      if (n < MAXN) v[n++] = x;
      s = e;
    }
    execCmd(c1, c2, v, n);
  }
}

// Řádek se skládá z více SIO záznamů (po 40 B), konec = ATASCII EOL $9B
static char    lineBuf[256];
static uint8_t lineLen = 0;

static void feedPrinterData(const uint8_t *d, uint8_t n) {
  for (uint8_t i = 0; i < n; i++) {
    uint8_t c = d[i];
    if (c == 0x9B) {                       // EOL -> zpracovat, zbytek záznamu je výplň
      lineBuf[lineLen] = 0;
      parseLine(lineBuf);
      lineLen = 0;
      return;
    }
    c &= 0x7F;                             // inverzní znaky -> normální
    if (lineLen < sizeof(lineBuf) - 1) lineBuf[lineLen++] = (char)c;
  }
}

// ================= SIO =================
static uint8_t sioChecksum(const uint8_t *b, uint8_t n) {
  unsigned s = 0;
  for (uint8_t i = 0; i < n; i++) {
    s += b[i];
    if (s > 0xFF) s = (s & 0xFF) + 1;      // součet s přenosem
  }
  return (uint8_t)s;
}

static bool sioRead(uint8_t *b, uint8_t n, unsigned long toMs) {
  unsigned long t = millis();
  uint8_t i = 0;
  while (i < n) {
    if (Serial1.available()) b[i++] = Serial1.read();
    else if (millis() - t > toMs) return false;
  }
  return true;
}

static void sioSend(uint8_t c) { Serial1.write(c); Serial1.flush(); }

static void handleStatus() {
  delayMicroseconds(850);
  sioSend('A');
  delayMicroseconds(300);
  sioSend('C');
  uint8_t st[5] = { 0x00, 0x00, PRN_TIMEOUT_S, 0x00, 0 };
  st[4] = sioChecksum(st, 4);
  Serial1.write(st, 5); Serial1.flush();
}

static void handleWrite(uint8_t aux1) {
  uint8_t len = 40;                        // 'N' normální
  if (aux1 == 'S') len = 29;               // sideways
  if (aux1 == 'D') len = 20;               // double width
  delayMicroseconds(850);
  sioSend('A');

  uint8_t buf[41];
  if (!sioRead(buf, len + 1, 100)) { Serial.println(F("data timeout")); return; }
  if (sioChecksum(buf, len) != buf[len]) {
    delayMicroseconds(850); sioSend('N');  // NAK
    Serial.println(F("data chksum"));
    return;
  }
  delayMicroseconds(850);
  sioSend('A');

  feedPrinterData(buf, len);               // kreslí se TEĎ -> Atari čeká = řízení toku
  delayMicroseconds(300);
  sioSend('C');
}

// ================= Ladění přes USB (Sériový monitor 115200 Bd) =================
static char    usbBuf[128];
static uint8_t usbLen = 0;
static unsigned long lastBeat = 0, lastBlink = 0;
static unsigned long sioCount = 0;

static void printStatus() {
  Serial.print(F("[bezi] FW " FW_VERSION " | cas ")); Serial.print(millis() / 1000);
  Serial.print(F(" s | pozice X=")); Serial.print(posX - orgX);
  Serial.print(F(" Y=")); Serial.print(posY - orgY);
  Serial.print(F(" (absolutne ")); Serial.print(posX); Serial.print(','); Serial.print(posY);
  Serial.print(F(", meze ")); Serial.print(xMax); Serial.print(','); Serial.print(yMax); Serial.print(')');
  Serial.print(F(" | pero ")); Serial.print(penIsDown ? F("dole") : F("nahore"));
  Serial.print(F(" | Command=")); Serial.print(digitalRead(PIN_CMD) ? F("H (klid)") : F("L"));
  Serial.print(F(" | SIO zprav pro P1: ")); Serial.println(sioCount);
  Serial.print(F("        rychlost krok ")); Serial.print(stepUs);
  Serial.print(F(" us | AC ")); Serial.print(startUs); Serial.print(','); Serial.print(rampUs);
  Serial.print(F(" | DG")); Serial.print(diagSlow ? 1 : 0);
  Serial.print(F(" | PT ")); Serial.print(penDownMs); Serial.print(','); Serial.println(penUpMs);
}

static void idleTasks() {
  unsigned long now = millis();
  if (now - lastBlink >= 500) {            // LED na desce bliká = program běží
    lastBlink = now;
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
  }
  if (now - lastBeat >= 10000) {           // každých 10 s stav
    lastBeat = now;
    printStatus();
  }
  while (Serial.available()) {             // příkazy přímo z monitoru
    char c = Serial.read();
    if (c == '\r' || c == '\n') {
      if (usbLen == 0) continue;
      usbBuf[usbLen] = 0;
      if (usbBuf[0] == '?') printStatus();
      else {
        Serial.print(F("> ")); Serial.println(usbBuf);
        digitalWrite(LED_BUILTIN, HIGH);
        parseLine(usbBuf);
        Serial.println(F("hotovo"));
      }
      usbLen = 0;
    } else if (usbLen < sizeof(usbBuf) - 1) usbBuf[usbLen++] = c;
  }
}

void setup() {
  Serial.begin(115200);                    // USB ladění (nečeká se na připojení)
  Serial1.begin(SIO_BAUD);
  pinMode(PIN_CMD, INPUT);                 // externí pull-up 2,2k
  pinMode(PIN_PEN, OUTPUT);
  digitalWrite(PIN_PEN, !PEN_DOWN_LEVEL);
  pinMode(LED_BUILTIN, OUTPUT);
  for (uint8_t i = 0; i < 6; i++) pinMode(PH_PINS[i], OUTPUT);
  writePhases();
  loadLimits();
  delay(300);
  Serial.println();
  Serial.println(F("=== Atari SIO -> Minigraf A 0507, emulace P1:  FW " FW_VERSION " ==="));
  Serial.println(F("Prikazy z monitoru: IN; PU x,y; PD x,y; PR dx,dy; CI r; VS mm/s; PT ms,ms; AC us,us; DG0/1; HM; LM x,y;  ? = stav"));
  printStatus();
}

void loop() {
  if (digitalRead(PIN_CMD) != LOW) { idleTasks(); return; }

  while (Serial1.available()) Serial1.read();
  uint8_t f[5];
  bool ok = sioRead(f, 5, 20);

  unsigned long t = millis();              // počkat na konec Command
  while (digitalRead(PIN_CMD) == LOW && millis() - t < 50) {}

  if (!ok || f[0] != DEVICE_ID) return;    // cizí zařízení -> mlčet
  if (sioChecksum(f, 4) != f[4]) { delayMicroseconds(850); sioSend('N'); Serial.println(F("SIO: chyba souctu prikazu")); return; }

  sioCount++;
  digitalWrite(LED_BUILTIN, HIGH);         // svítí = komunikace / kreslení
  switch (f[1]) {
    case 'S': handleStatus(); Serial.println(F("SIO: status"));  break;
    case 'W': handleWrite(f[2]); Serial.println(F("SIO: zapis OK")); break;
    default:  delayMicroseconds(850); sioSend('N');
              Serial.print(F("SIO: neznamy prikaz $")); Serial.println(f[1], HEX); break;
  }
}
