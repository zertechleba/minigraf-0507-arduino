/*
 * Atari XE (SIO) -> Aritma Minigraf A 0507 / Aritma XY 4131      firmware verze 0.4.1
 * -----------------------------------------------------------
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
 *   HM[x[,y]];       najetí na levý doraz (X=0), aktuální poloha papíru = Y 0, pak přesun na start (výchozí 60,144)
 *   AC s[,r];        zrychlení: pauza při rozjezdu s µs, zkrácení r µs/krok (AC; = výchozí)
 *   (pero dole a 1 s žádný příkaz -> firmware ho sám zvedne, aby nevznikla kaňka)
 *   DG0; / DG1;      šikmé čáry plnou rychlostí / zpomalené ×1,4 (DG; = výchozí)
 *   PL0507; / PL4131; výběr plotteru (uloží se do EEPROM), PL; = vypsat. Lze i PL0; / PL1;
 *
 * Jednotka = 1 krok plotteru: Minigraf 0,125 mm, XY 4131 0,1 mm.
 * XY 4131: plocha X 0..1780 (vozík, levý koncový kontakt = 0), Y 0..2600 (papír, Y 0 = kde stál
 * papír při HM), start po HM X=100 (10 mm). Rychlost výchozí 50 mm/s, nejvíc 66 mm/s.
 *
 * Jednotka = 1 krok Minigrafu = 0,125 mm. Meze plochy nastaví LM (výchozí 0..1580 x 0..2284 = A4 s okraji 10/10/15/15 mm).
 * Papír A4 se zakládá horní hranou k výřezům pod přítlačnými kolečky. Po HM je pero na startu 60,144.
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
 *
 * Výstupy na XY 4131 (konektor WK 46248, 5 V TTL, obě desky stejně):
 *   D6 -> PERO (vývod 1, 1 = pero dole)    D3 -> KROK (vývod 2, v klidu 1, impulz do 0)
 *   D5 -> X/Y  (vývod 3, 0 = vozík, 1 = papír)   D4 -> +/- (vývod 4)
 *   D7 <- READY (vývod 5, nepoužívá se)    GND -> vývod 6
 * Oba plottery mohou být připojené současně, kreslí ten vybraný příkazem PL.
 */

#include <Arduino.h>
#include <math.h>
#include <EEPROM.h>

#define FW_VERSION "0.4.1"

// ================= Nastavení =================
const uint8_t  PIN_CMD        = 2;      // SIO Command přes optočlen (LOW = aktivní)
const uint8_t  PIN_PEN        = 10;
const uint8_t  DEVICE_ID      = 0x40;   // P1:
const uint32_t SIO_BAUD       = 19200;

const bool     PEN_DOWN_LEVEL = HIGH;   // ověřit na plotteru, případně LOW
const int8_t   X_DIR          = +1;     // -1 když osa jede obráceně
const int8_t   Y_DIR          = +1;
const int      X_MAX_DEF      = 1580;   // výchozí meze (absolutně od levého dorazu), mění LM
const int      Y_MAX_DEF      = 2284;   // a ukládají se do EEPROM. A4: okraj 15 mm na konci osy Y
                                        // (změřeno: 2308 = 12 mm), papír zůstane v kolečkách posuvu
const unsigned STEP_US        = 2083;   // výchozí rychlost 60 mm/s (125000 / 60)
const unsigned START_US       = 6000;   // výchozí pauza při rozjezdu z klidu (~21 mm/s), mění AC (ověřeno)
const unsigned RAMP_US        = 250;    // výchozí zkrácení pauzy každým krokem rozjezdu, mění AC (ověřeno)
const bool     DIAG_SLOW      = false;  // výchozí: šikmé čáry plnou rychlostí (DG0), mění DG (ověřeno)
const int      HOME_X         = 60;     // HM: start X od levého dorazu (10 mm od levého okraje A4)
const int      HOME_Y         = 144;    // HM: start Y od založení papíru k výřezům = 15 mm od okraje A4 (změřeno: 80 = 7 mm)
const int8_t   HOME_DIR       = -1;     // HM: směr k dorazu (-1 = k menším X); +1 když jede na druhou stranu
const int      HOME_EXTRA     = 200;    // HM: o kolik kroků víc než šířka plochy (jistota dorazu)
const unsigned HOME_US        = 2500;   // HM: rychlost jízdy k dorazu (~50 mm/s)   // výchozí zpomalení šikmých čar ×1,4, mění DG
const unsigned MIN_STEP_US    = 1500;   // nejrychlejší povolené (VS nepustí rychleji)
const unsigned PEN_DOWN_MS    = 30;     // čekání po položení pera (ověřeno: 30)
const unsigned PEN_UP_MS      = 70;     // čekání po zvednutí pera (ověřeno: 70)
const unsigned PEN_IDLE_MS    = 1000;   // pero dole a žádný příkaz tak dlouho -> zvednout (žádné kaňky při výpadku)
const uint8_t  PRN_TIMEOUT_S  = 255;    // max. doba čekání Atari na 'C' (jednotka ~1 s, 255 = max.)

// ---- XY 4131 (ověřeno testovacím programem xy4131_test 0.9) ----
const uint8_t  XY_PIN_STEP    = 3, XY_PIN_DIR = 4, XY_PIN_AXIS = 5, XY_PIN_PEN = 6, XY_PIN_READY = 7;
const int8_t   XY_X_DIR       = +1;     // +X = vozík doprava (+/- = 1)
const int8_t   XY_Y_DIR       = -1;     // +Y = papír couvá (s +1 vycházel text zrcadlově)
const int      XY_X_MAX_DEF   = 1780;   // dráha vozíku mezi kontakty ~1800 kroků (180 mm)
const int      XY_Y_MAX_DEF   = 2600;   // papír 260 mm od polohy při HM
const unsigned XY_STEP_US     = 2000;   // výchozí 50 mm/s (100000 / 50)
const unsigned XY_START_US    = 5000;
const unsigned XY_RAMP_US     = 250;
const int      XY_HOME_X      = 100;    // start 10 mm od levého kontaktu
const int      XY_HOME_Y      = 0;
const int      XY_HOME_EXTRA  = 120;    // HM jede doleva xMax + 120 kroků; koncový kontakt vozík zastaví
const unsigned XY_HOME_US     = 1800;
const unsigned XY_PEN_DOWN_MS = 30;     // pero dolů táhne cívka (hned)
const unsigned XY_PEN_UP_MS   = 70;     // nahoru pružina (dokmitá)
const unsigned XY_PULSE_US    = 20;     // šířka impulzu KROK

// ---- výchozí hodnoty podle plotteru ----
struct PlotDef { unsigned stepUs, startUs, rampUs, penDown, penUp, homeUs; int homeX, homeY, xMax, yMax; long vsK; };
const PlotDef PDEF[2] = {
  { STEP_US,    START_US,    RAMP_US,    PEN_DOWN_MS,    PEN_UP_MS,    HOME_US,    HOME_X,    HOME_Y,    X_MAX_DEF,    Y_MAX_DEF,    125000L },
  { XY_STEP_US, XY_START_US, XY_RAMP_US, XY_PEN_DOWN_MS, XY_PEN_UP_MS, XY_HOME_US, XY_HOME_X, XY_HOME_Y, XY_X_MAX_DEF, XY_Y_MAX_DEF, 100000L },
};
static uint8_t plotter = 0;              // 0 = Minigraf A 0507, 1 = XY 4131 (PL)

// ================= Minigraf =================
static unsigned stepUs = STEP_US;                         // rychlost (VS)
static unsigned startUs = START_US, rampUs = RAMP_US;     // zrychlení (AC)
static bool     diagSlow = DIAG_SLOW;                     // šikmé čáry (DG)
static unsigned penDownMs = PEN_DOWN_MS, penUpMs = PEN_UP_MS; // prodleva pera (PT)
static unsigned long lastCmdDone = 0;   // kdy skončil poslední příkaz (USB i SIO) – pro automatické zvednutí pera
static uint8_t phX = 0, phY = 0;
static int     posX = 0, posY = 0;      // ABSOLUTNÍ poloha v krocích (od dorazu po HM, jinak od zapnutí)
static int     orgX = 0, orgY = 0;      // počátek kreslení nastavený IN (souřadnice příkazů jsou relativně k němu)
static int     xMax = X_MAX_DEF, yMax = Y_MAX_DEF;

// ---- meze v EEPROM ----
struct Limits { uint16_t magic; int16_t x, y; };
const uint16_t LIM_MAGIC[2] = { 0x4D4A, 0x5859 };   // Minigraf (adresa 0, beze změny od 0.3.8), XY 4131 (adresa 8)
const uint16_t PL_MAGIC = 0x504C;                   // výběr plotteru (adresa 16)
static void loadLimits() {
  xMax = PDEF[plotter].xMax; yMax = PDEF[plotter].yMax;
  Limits l; EEPROM.get(plotter * 8, l);
  if (l.magic == LIM_MAGIC[plotter] && l.x >= 100 && l.y >= 100) { xMax = l.x; yMax = l.y; }
}
static void saveLimits() {
  Limits l = { LIM_MAGIC[plotter], (int16_t)xMax, (int16_t)yMax };
  EEPROM.put(plotter * 8, l);
}
struct PlSel { uint16_t magic; uint8_t p; };
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

// XY 4131: jeden krok jedné osy (0 = vozík X, 1 = papír Y), osy se přepínají X/Y
static void xyStep(uint8_t axis, int8_t dir) {
  int8_t d = dir * (axis ? XY_Y_DIR : XY_X_DIR);
  digitalWrite(XY_PIN_AXIS, axis ? HIGH : LOW);
  digitalWrite(XY_PIN_DIR, d > 0 ? HIGH : LOW);
  delayMicroseconds(10);                   // ustálení X/Y a +/- před impulzem
  digitalWrite(XY_PIN_STEP, LOW);
  delayMicroseconds(XY_PULSE_US);
  digitalWrite(XY_PIN_STEP, HIGH);
  if (axis) posY += dir; else posX += dir;
}

static void pen(bool down) {
  if (down == penIsDown) return;
  if (plotter == 1) digitalWrite(XY_PIN_PEN, down ? HIGH : LOW);
  else              digitalWrite(PIN_PEN, down ? PEN_DOWN_LEVEL : !PEN_DOWN_LEVEL);
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
    // lichoběžníková rampa: pomalý rozjezd, plná rychlost, pomalý dojezd
    int edge = min(done, total - 1 - done);
    long d = (long)startUs - (long)edge * rampUs;
    if (d < (long)stepUs) d = stepUs;
    if (plotter == 1) {                    // XY 4131: osy krok po kroku (šikmo tak samo pomaleji)
      if (mx) { xyStep(0, mx); delayMicroseconds((unsigned)d); }
      if (my) { xyStep(1, my); delayMicroseconds((unsigned)d); }
    } else {
      stepAxes(mx, my);
      if (diagSlow && mx && my) d = d * 7 / 5; // šikmo jedou oba motory -> zpomalit (~sqrt 2)
      delayMicroseconds((unsigned)d);
    }
    done++;
  }
}

// HM: jízda na levý doraz přes celou šířku (motor na dorazu proklouzne), pak na start X,Y.
// Osa Y nemá doraz: aktuální poloha papíru (právě založený k výřezům) se bere jako Y = 0.
static void homeX(int targetX, int targetY) {
  pen(false);
  if (plotter == 1) {                      // XY 4131: vozík doleva, koncový kontakt ho zastaví
    long n = (long)xMax + XY_HOME_EXTRA;
    digitalWrite(XY_PIN_AXIS, LOW);
    digitalWrite(XY_PIN_DIR, XY_X_DIR > 0 ? LOW : HIGH);
    delay(50);
    for (long i = 0; i < n; i++) {
      digitalWrite(XY_PIN_STEP, LOW);
      delayMicroseconds(XY_PULSE_US);
      digitalWrite(XY_PIN_STEP, HIGH);
      long d = (long)startUs - i * (long)rampUs;
      if (d < (long)XY_HOME_US) d = XY_HOME_US;
      delayMicroseconds((unsigned)d);
    }
    delay(200);                            // pauza na dorazu, teprve pak změna směru
  } else {
    long n = (long)xMax + HOME_EXTRA;
    for (long i = 0; i < n; i++) {
      phX = (phX + HOME_DIR * X_DIR) & 7;
      writePhases();
      long d = (long)startUs - i * (long)rampUs;
      if (d < (long)HOME_US) d = HOME_US;
      delayMicroseconds((unsigned)d);
    }
    delay(100);                            // dorazit a uklidnit
  }
  posX = 0;
  posY = 0;                                // papír založený k výřezům = Y 0
  orgX = 0; orgY = 0;                      // souřadnice = absolutní (PU60,144 = startovní pozice)
  absMode = true;
  lineTo(targetX, targetY);
  Serial.print(F("HM: na dorazu X=0, ted X=")); Serial.print(posX); Serial.print(F(" Y=")); Serial.println(posY);
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

// ================= Výběr plotteru =================
static const __FlashStringHelper *plotterName() {
  return plotter == 1 ? F("XY4131") : F("Minigraf0507");
}

static void selectPlotter(uint8_t p, bool save) {
  pen(false);
  digitalWrite(PIN_PEN, !PEN_DOWN_LEVEL);  // obě pera nahoru
  digitalWrite(XY_PIN_PEN, LOW);
  penIsDown = false;
  plotter = p ? 1 : 0;
  const PlotDef &d = PDEF[plotter];
  stepUs = d.stepUs; startUs = d.startUs; rampUs = d.rampUs;
  penDownMs = d.penDown; penUpMs = d.penUp; diagSlow = DIAG_SLOW;
  loadLimits();
  posX = posY = orgX = orgY = 0;           // poloha neznámá -> před kreslením HM
  absMode = true;
  if (save) { PlSel s = { PL_MAGIC, plotter }; EEPROM.put(16, s); }
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
      long us = PDEF[plotter].vsK / v[0];  // 1 krok = 0,125 mm (Minigraf) / 0,1 mm (XY 4131)
      stepUs = (us < MIN_STEP_US) ? MIN_STEP_US : (us > 9000 ? 9000 : (unsigned)us);
    } else stepUs = PDEF[plotter].stepUs;
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
  else if (c1 == 'H' && c2 == 'M') {       // HM[x[,y]]; doraz X, papír = Y 0, pak start (výchozí 60,144)
    homeX(n >= 1 ? (int)v[0] : PDEF[plotter].homeX, n >= 2 ? (int)v[1] : PDEF[plotter].homeY);
  }
  else if (c1 == 'A' && c2 == 'C') {       // AC rozjezd_us[,ramp_us], AC; = výchozí
    if (n >= 1) { startUs = constrain(v[0], MIN_STEP_US, 16000); if (n >= 2) rampUs = constrain(v[1], 1, 5000); }
    else        { startUs = PDEF[plotter].startUs; rampUs = PDEF[plotter].rampUs; }
    Serial.print(F("zrychleni: rozjezd ")); Serial.print(startUs);
    Serial.print(F(" us, ramp ")); Serial.print(rampUs); Serial.println(F(" us/krok"));
  }
  else if (c1 == 'D' && c2 == 'G') {       // DG0 = šikmo bez zpomalení, DG1 = se zpomalením, DG; = výchozí
    diagSlow = (n >= 1) ? (v[0] != 0) : DIAG_SLOW;
    Serial.print(F("sikme cary: ")); Serial.println(diagSlow ? F("zpomalene") : F("plna rychlost"));
  }
  else if (c1 == 'P' && c2 == 'T') {       // PT dolů[,nahoru] v ms, PT; = výchozí
    if (n >= 1) { penDownMs = constrain(v[0], 0, 1000); penUpMs = (n >= 2) ? constrain(v[1], 0, 1000) : penUpMs; }
    else        { penDownMs = PDEF[plotter].penDown; penUpMs = PDEF[plotter].penUp; }
    Serial.print(F("pero: dolu ")); Serial.print(penDownMs);
    Serial.print(F(" ms, nahoru ")); Serial.print(penUpMs); Serial.println(F(" ms"));
  }
  else if (c1 == 'C' && c2 == 'I') { if (n >= 1) circle(v[0], n >= 2 ? v[1] : 72); }
  else if (c1 == 'P' && c2 == 'L') {       // PL0507 / PL4131 (nebo PL0 / PL1) = výběr plotteru, PL; = vypsat
    if (n >= 1) {
      if (v[0] == 0 || v[0] == 507) selectPlotter(0, true);
      else if (v[0] == 1 || v[0] == 4131) selectPlotter(1, true);
    }
    Serial.print(F("plotter: ")); Serial.println(plotterName());
  }
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
  lastCmdDone = millis();
  delayMicroseconds(300);
  sioSend('C');
}

// ================= Ladění přes USB (Sériový monitor 115200 Bd) =================
static char    usbBuf[128];
static uint8_t usbLen = 0;
static unsigned long lastBeat = 0, lastBlink = 0, lastUsbChar = 0;
static unsigned long sioCount = 0;

static void printStatus() {
  Serial.print(F("[bezi] FW " FW_VERSION " | plotter ")); Serial.print(plotterName());
  Serial.print(F(" | cas ")); Serial.print(millis() / 1000);
  Serial.print(F(" s | pozice X=")); Serial.print(posX - orgX);
  Serial.print(F(" Y=")); Serial.print(posY - orgY);
  Serial.print(F(" (absolutne ")); Serial.print(posX); Serial.print(','); Serial.print(posY);
  Serial.print(F(", meze ")); Serial.print(xMax); Serial.print(','); Serial.print(yMax); Serial.print(')');
  Serial.print(F(" | pero ")); Serial.print(penIsDown ? F("dole") : F("nahore"));
  Serial.print(F(" | Command=")); Serial.print(digitalRead(PIN_CMD) ? F("H (klid)") : F("L (trvale = Atari odpojeno?)"));
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
  // stav každých 10 s – ale jen když 10 s nepřišel žádný příkaz z USB. Dlouhý výpis by jinak mohl
  // zahltit 64bajtový přijímací buffer a uříznout právě přicházející příkaz.
  if (now - lastBeat >= 10000 && usbLen == 0 && now - lastUsbChar >= 10000) {
    lastBeat = now;
    printStatus();
  }
  if (penIsDown && now - lastCmdDone > PEN_IDLE_MS && usbLen == 0) {
    pen(false);                            // dlouho žádný příkaz s perem dole -> zvednout (výpadek, pauza)
    Serial.println(F("pero zvednuto (zadny prikaz)"));
  }
  if (usbLen && now - lastUsbChar > 1000) { // neúplný příkaz (ztracený konec řádku) -> zahodit
    usbLen = 0;
    Serial.println(F("zahozen neuplny prikaz"));
  }
  while (Serial.available()) {             // příkazy přímo z monitoru
    char c = Serial.read();
    lastUsbChar = millis();
    if (c == '\r' || c == '\n') {
      if (usbLen == 0) continue;
      usbBuf[usbLen] = 0;
      if (usbBuf[0] == '?') printStatus();
      else {
        Serial.print(F("> ")); Serial.println(usbBuf);
        digitalWrite(LED_BUILTIN, HIGH);
        parseLine(usbBuf);
        lastCmdDone = millis();
        Serial.println(F("hotovo"));
      }
      usbLen = 0;
    } else if (usbLen < sizeof(usbBuf) - 1) usbBuf[usbLen++] = c;
  }
}

void setup() {
  Serial.begin(115200);                    // USB ladění (nečeká se na připojení)
  Serial1.begin(SIO_BAUD);
  pinMode(PIN_CMD, INPUT_PULLUP);          // externí pull-up 2,2k; vnitřní drží H, když není převodník SIO připojen
  pinMode(PIN_PEN, OUTPUT);
  digitalWrite(PIN_PEN, !PEN_DOWN_LEVEL);
  pinMode(LED_BUILTIN, OUTPUT);
  for (uint8_t i = 0; i < 6; i++) pinMode(PH_PINS[i], OUTPUT);
  writePhases();
  pinMode(XY_PIN_STEP, OUTPUT); pinMode(XY_PIN_DIR, OUTPUT);
  pinMode(XY_PIN_AXIS, OUTPUT); pinMode(XY_PIN_PEN, OUTPUT);
  pinMode(XY_PIN_READY, INPUT);            // READY se nepoužívá (u XY 4131 stále 0)
  digitalWrite(XY_PIN_STEP, HIGH);         // KROK v klidu 1
  digitalWrite(XY_PIN_PEN, LOW);           // pero nahoru
  PlSel ps; EEPROM.get(16, ps);
  selectPlotter(ps.magic == PL_MAGIC ? ps.p : 0, false);
  delay(300);
  Serial.println();
  Serial.print(F("=== Atari SIO -> Minigraf A 0507 / XY 4131, emulace P1:  FW " FW_VERSION ", plotter "));
  Serial.print(plotterName()); Serial.println(F(" ==="));
  Serial.println(F("Prikazy z monitoru: IN; PU x,y; PD x,y; PR dx,dy; CI r; VS mm/s; PT ms,ms; AC us,us; DG0/1; HM; LM x,y; PL0507/PL4131;  ? = stav"));
  printStatus();
}

static unsigned long cmdLowSince = 0;
static bool cmdStuck = false;

void loop() {
  if (digitalRead(PIN_CMD) != LOW) {
    if (cmdStuck) { cmdStuck = false; Serial.println(F("SIO Command opet H - Atari pripojeno")); }
    cmdLowSince = 0;
    idleTasks();
    return;
  }
  // Command trvale L (odpojený převodník SIO, vadný optočlen) -> nečekat na Atari, obsluhovat USB
  if (cmdLowSince == 0) cmdLowSince = millis() | 1;
  if (cmdStuck || millis() - cmdLowSince > 300) {
    if (!cmdStuck) { cmdStuck = true; Serial.println(F("POZOR: SIO Command trvale L - Atari se ignoruje, USB funguje")); }
    idleTasks();
    return;
  }

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
