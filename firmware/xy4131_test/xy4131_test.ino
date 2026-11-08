/*
 * XY 4131 – testovací program (Arduino Nano Every / Leonardo / Nano)   verze 0.9
 * --------------------------------------------------------------------
 * Ovládá se ze Sériového monitoru (115200 Bd, "Nový řádek") nebo z PC
 * programy plot.py / text_plot.py (stejné příkazy jako firmware Minigrafu).
 *
 * Zapojení (konektor WK 46248, ověřeno schématem XY 4130 a stránkou schotek.cz):
 *   Arduino D6  -> PERO   (vývod 1)  1 = pero dole (pero musí být zapnuté přepínačem na plotteru!)
 *   Arduino D3  -> KROK   (vývod 2)  v klidu 1, impulz do 0 = jeden krok (0,1 mm, ověřeno)
 *   Arduino D5  -> X/Y    (vývod 3)  1 = papír, 0 = vozík s perem (ověřeno)
 *   Arduino D4  -> +/-    (vývod 4)  papír: 1 = dopředu, 0 = couvá; vozík: 1 = doprava, 0 = doleva (ověřeno)
 *   Arduino D7  <> READY  (vývod 5)  otevřený kolektor, EXTERNÍ pull-up 4k7 (u tohoto kusu stále 0)
 *   Arduino GND -- GND    (vývod 6)
 *   vývod 7 nezapojen
 * Doporučeno: 220 Ω v sérii s D3–D6 (na D7 ne).
 *
 * Naměřeno: krok 0,1 mm v obou osách, dráha vozíku mezi kontakty asi 1800 kroků (180 mm).
 * Koncové kontakty plotteru vozík na krajích zastaví. Pozor: zaseknutý levý kontakt
 * zablokuje i jízdu doprava – kontakt musí volně odskakovat.
 *
 * MALÁ písmena = testovací příkazy:
 *   ?            stav (řádek začíná "[bezi] FW ...")
 *   q            sonda READY      r   sleduje READY 5 s
 *   h            vozík doleva na koncový kontakt, pak 10 kroků doprava
 *   p0 / p1      PERO L / H (ručně, zůstane dole)       a0 / a1   X/Y L / H      d0 / d1   +/- L / H
 *   s N          N impulzů KROK   w N  šířka impulzu µs (20)   t N  pauza mezi kroky µs
 *   i            obrátí polaritu impulzu KROK
 *
 * VELKÁ písmena = kreslení (zjednodušené HPGL, každý řádek odpoví "hotovo"):
 *   IN;  PU[x,y,...];  PD[x,y,...];  PA[x,y,...];  PR[dx,dy,...];
 *   VS v; (mm/s)  PT d,u; (ms)  AC s,r; (µs)  DG; LM; (přijme a ignoruje)
 *   HM[x[,y]];   vozík na levý kontakt (X=0), papír Y=0, pak na start (výchozí X=100 = 10 mm)
 * Jednotka souřadnic: UNIT_NUM/UNIT_DEN kroků XY 4131. Výchozí 1/1 = 0,1 mm, takže
 * výkresy z text_plot.py (dělané pro Minigraf 0,125 mm) vyjdou v měřítku 0,8 a vejdou se.
 * X = vozík (napříč), Y = papír. Y_DIR = -1 (s +1 vycházel text zrcadlově).
 */

#define FW_VERSION "0.9"

const uint8_t PIN_STEP = 3, PIN_DIR = 4, PIN_AXIS = 5, PIN_PEN = 6, PIN_READY = 7;

// ---- nastavení kreslení ----
const long UNIT_NUM = 1, UNIT_DEN = 1;   // souřadnice -> kroky (5/4 = jednotky Minigrafu 0,125 mm ve skutečné velikosti)
const int  X_DIR = +1, Y_DIR = -1;       // +X = doprava, +Y = papír couvá (Y_DIR -1 ověřeno: +1 kreslí zrcadlově)
const long X_MAX = 1780;                 // kroky od levého kontaktu (dráha asi 1800)
const long HOME_X = 100;                 // start po HM: 10 mm od levého kontaktu
const long HOME_TRAVEL = 1900;           // HM jede doleva tolik kroků (víc než celá dráha)
const unsigned STEP_US_DEF = 2000;       // 50 mm/s
const unsigned MIN_STEP_US = 1500;       // nejrychleji 66 mm/s (test t 1500)
const unsigned START_US_DEF = 5000, RAMP_US_DEF = 250;
const unsigned PEN_DOWN_MS_DEF = 30, PEN_UP_MS_DEF = 70;   // dolů táhne cívka (hned), nahoru pružina (dokmitá)
const unsigned long PEN_IDLE_MS = 1000;  // při kreslení: pero dole a 1 s nic -> zvednout (proti kaňce)

unsigned pulseUs = 20, gapUs = 3000;
bool stepActiveHigh = false;    // v klidu 1, impulz do 0
char buf[72]; uint8_t len = 0;

unsigned stepUs = STEP_US_DEF, startUs = START_US_DEF, rampUs = RAMP_US_DEF;
unsigned penDownMs = PEN_DOWN_MS_DEF, penUpMs = PEN_UP_MS_DEF;
long posX = 0, posY = 0, orgX = 0, orgY = 0;   // absolutní kroky, počátek IN
bool penIsDown = false, relMode = false;
bool autoLift = false;              // samozvednutí pera jen při kreslení, ne po ručním p1
unsigned long lastCmdDone = 0, lastChar = 0;

// ================= nízká úroveň =================
bool probeReady() {               // true = připraven
  pinMode(PIN_READY, OUTPUT);
  digitalWrite(PIN_READY, LOW);
  delayMicroseconds(20);
  pinMode(PIN_READY, INPUT);
  delayMicroseconds(30);
  return digitalRead(PIN_READY) == LOW;
}

void pulse() {
  digitalWrite(PIN_STEP, stepActiveHigh ? HIGH : LOW);
  delayMicroseconds(pulseUs);
  digitalWrite(PIN_STEP, stepActiveHigh ? LOW : HIGH);
}

void waitUs(unsigned long us) {
  if (us > 15000) delay(us / 1000); else delayMicroseconds(us);
}

void oneStep() { pulse(); waitUs(gapUs); }

// jeden krok v ose (0 = vozík X, 1 = papír Y), směr +1/-1 v souřadnicích výkresu
void axisStep(uint8_t axis, int dir, unsigned long gap) {
  int d = dir * (axis ? Y_DIR : X_DIR);
  digitalWrite(PIN_AXIS, axis ? HIGH : LOW);
  digitalWrite(PIN_DIR, d > 0 ? HIGH : LOW);
  delayMicroseconds(10);          // ustálení X/Y a +/- před impulzem
  pulse();
  waitUs(gap);
  if (axis) posY += dir; else posX += dir;
}

void pen(bool down) {
  if (down == penIsDown) return;
  digitalWrite(PIN_PEN, down ? HIGH : LOW);
  penIsDown = down;
  delay(down ? penDownMs : penUpMs);
}

// přímka na absolutní polohu (kroky), Bresenham, osy se střídají impulz po impulzu
void lineTo(long tx, long ty) {
  if (tx < 0) tx = 0;
  if (tx > X_MAX) tx = X_MAX;
  long dx = labs(tx - posX), dy = labs(ty - posY);
  int sx = tx >= posX ? 1 : -1, sy = ty >= posY ? 1 : -1;
  long n = dx + dy;               // počet impulzů
  if (n == 0) return;
  long err = dx - dy, i = 0;
  while (posX != tx || posY != ty) {
    long k = min(i, n - 1 - i);   // rampa: rozjezd a dojezd
    long g = (long)startUs - (long)rampUs * k;
    if (g < (long)stepUs) g = stepUs;
    long e2 = 2 * err;
    bool moved = false;
    if (e2 > -dy && posX != tx) { err -= dy; axisStep(0, sx, g); i++; moved = true; }
    if (e2 < dx && posY != ty)  { err += dx; axisStep(1, sy, g); i++; moved = true; }
    if (!moved) {                 // pojistka: dojet zbývající osu
      if (posX != tx) axisStep(0, sx, g); else axisStep(1, sy, g);
      i++;
    }
  }
}

long toSteps(long v) { return v * UNIT_NUM / UNIT_DEN; }

void home(long hx, bool verbose) {
  pen(false);
  digitalWrite(PIN_AXIS, LOW);    // vozík
  digitalWrite(PIN_DIR, X_DIR > 0 ? LOW : HIGH);   // doleva
  delay(50);
  for (long n = 0; n < HOME_TRAVEL; n++) { pulse(); delayMicroseconds(1800); }
  delay(200);                     // pauza po dorazu, pak teprve změna směru
  posX = 0; posY = 0; orgX = 0; orgY = 0;
  unsigned s0 = startUs; startUs = 3000;
  lineTo(hx, 0);
  startUs = s0;
  if (verbose) {
    Serial.print(F("HM: na dorazu X=0, ted X=")); Serial.print(posX);
    Serial.print(F(" Y=")); Serial.println(posY);
  }
}

// ================= stav =================
void printState() {
  Serial.print(F("[bezi] FW " FW_VERSION " | pozice X=")); Serial.print(posX - orgX);
  Serial.print(F(" Y=")); Serial.print(posY - orgY);
  Serial.print(F(" (abs ")); Serial.print(posX); Serial.print(','); Serial.print(posY);
  Serial.print(F(") | pero ")); Serial.print(penIsDown ? F("dole") : F("nahore"));
  Serial.print(F(" | krok ")); Serial.print(stepUs); Serial.println(F(" us"));
  Serial.print(F("        PEN=")); Serial.print(digitalRead(PIN_PEN));
  Serial.print(F(" X/Y=")); Serial.print(digitalRead(PIN_AXIS));
  Serial.print(F(" +/-=")); Serial.print(digitalRead(PIN_DIR));
  Serial.print(F(" READY linka=")); Serial.print(digitalRead(PIN_READY));
  Serial.print(F(" | test: impulz ")); Serial.print(pulseUs);
  Serial.print(F(" us, pauza ")); Serial.print(gapUs); Serial.print(F(" us, STEP aktivni "));
  Serial.println(stepActiveHigh ? F("H") : F("L"));
}

// ================= testovací příkazy (malá písmena) =================
void steps(long n) {
  unsigned long t0 = millis();
  for (long i = 0; i < n; i++) oneStep();
  Serial.print(F("Hotovo: ")); Serial.print(n); Serial.print(F(" kroku za "));
  Serial.print(millis() - t0); Serial.println(F(" ms"));
}

void watchReady() {
  Serial.println(F("Sleduji READY 5 s..."));
  uint8_t r0 = digitalRead(PIN_READY);
  Serial.print(F("start READY=")); Serial.println(r0);
  unsigned long t0 = millis();
  while (millis() - t0 < 5000) {
    uint8_t r = digitalRead(PIN_READY);
    if (r != r0) { Serial.print(millis() - t0); Serial.print(F(" ms: READY=")); Serial.println(r); r0 = r; }
  }
  Serial.println(F("konec"));
}

void testCmd(char *s) {
  char c = s[0];
  long v = atol(s + 1);
  switch (c) {
    case '?': printState(); break;
    case 'r': watchReady(); break;
    case 'q': Serial.println(probeReady() ? F("READY: pripraven") : F("READY: nepripraven")); break;
    case 'h': Serial.println(F("Vozik na levy kontakt..."));
              home(10, false);
              Serial.println(F("Hotovo: levy kontakt + 10 kroku doprava.")); break;
    case 'p': digitalWrite(PIN_PEN, v ? HIGH : LOW); penIsDown = v; autoLift = false; printState(); break;
    case 'a': digitalWrite(PIN_AXIS, v ? HIGH : LOW); printState(); break;
    case 'd': digitalWrite(PIN_DIR, v ? HIGH : LOW); printState(); break;
    case 's': steps(v > 0 ? v : 1); break;
    case 'w': if (v > 0) pulseUs = v; printState(); break;
    case 't': if (v > 0) gapUs = v; printState(); break;
    case 'i': stepActiveHigh = !stepActiveHigh;
              digitalWrite(PIN_STEP, stepActiveHigh ? LOW : HIGH); printState(); break;
    default:  Serial.println(F("? q h r p0/p1 a0/a1 d0/d1 s N w N t N i | IN PU PD PA PR VS PT AC HM"));
  }
}

// ================= kreslení (velká písmena) =================
uint8_t parseNums(const char *p, long *v, uint8_t maxN) {
  uint8_t n = 0;
  while (*p && n < maxN) {
    while (*p && !(isdigit(*p) || *p == '-' || *p == '+')) p++;
    if (!*p) break;
    v[n++] = strtol(p, (char **)&p, 10);
  }
  return n;
}

void moveTo(long x, long y) {       // x, y v jednotkách výkresu
  long tx, ty;
  if (relMode) { tx = posX + toSteps(x); ty = posY + toSteps(y); }
  else         { tx = orgX + toSteps(x); ty = orgY + toSteps(y); }
  lineTo(tx, ty);
}

void doCmd(const char *c) {
  while (*c == ' ') c++;
  if (strlen(c) < 2) return;
  char a = toupper(c[0]), b = toupper(c[1]);
  long v[16];
  uint8_t n = parseNums(c + 2, v, 16);
  if (a == 'I' && b == 'N') { pen(false); orgX = posX; orgY = posY; relMode = false; }
  else if (a == 'P' && (b == 'U' || b == 'D' || b == 'A' || b == 'R')) {
    if (b == 'U') pen(false);
    if (b == 'D') pen(true);
    if (b == 'A') relMode = false;
    if (b == 'R') relMode = true;
    for (uint8_t i = 0; i + 1 < n; i += 2) moveTo(v[i], v[i + 1]);
  }
  else if (a == 'V' && b == 'S') {
    if (n >= 1 && v[0] > 0) { long u = 100000L / v[0]; stepUs = u < MIN_STEP_US ? MIN_STEP_US : u; }
    else stepUs = STEP_US_DEF;
    Serial.print(F("rychlost: krok ")); Serial.print(stepUs); Serial.println(F(" us"));
  }
  else if (a == 'P' && b == 'T') {
    penDownMs = n >= 1 ? v[0] : PEN_DOWN_MS_DEF;
    penUpMs   = n >= 2 ? v[1] : PEN_UP_MS_DEF;
  }
  else if (a == 'A' && b == 'C') {
    startUs = n >= 1 ? v[0] : START_US_DEF;
    rampUs  = n >= 2 ? v[1] : RAMP_US_DEF;
  }
  else if (a == 'H' && b == 'M') {
    home(n >= 1 ? v[0] : HOME_X, true);
    if (n >= 2) lineTo(posX, v[1]);
  }
  // DG, LM, CI a ostatní: přijmout a nic nedělat
}

void drawLine(char *s) {
  Serial.print(F("> ")); Serial.println(s);
  autoLift = true;
  char *p = strtok(s, ";");
  while (p) { doCmd(p); p = strtok(NULL, ";"); }
  lastCmdDone = millis();
  Serial.println(F("hotovo"));
}

// ================= hlavní smyčka =================
void setup() {
  Serial.begin(115200);
  pinMode(PIN_STEP, OUTPUT); pinMode(PIN_DIR, OUTPUT);
  pinMode(PIN_AXIS, OUTPUT); pinMode(PIN_PEN, OUTPUT);
  pinMode(PIN_READY, INPUT);            // externí pull-up 4k7 na +5 V
  digitalWrite(PIN_STEP, HIGH);         // KROK v klidu 1
  digitalWrite(PIN_DIR, HIGH);
  digitalWrite(PIN_AXIS, LOW);          // vozík
  digitalWrite(PIN_PEN, LOW);           // pero nahoru
  delay(500);
  Serial.println(F("=== XY 4131 test  FW " FW_VERSION " ==="));
  printState();
}

void loop() {
  unsigned long now = millis();
  if (autoLift && penIsDown && now - lastCmdDone > PEN_IDLE_MS && len == 0) {
    pen(false);
    Serial.println(F("pero zvednuto (zadny prikaz)"));
  }
  if (len && now - lastChar > 1000) { len = 0; Serial.println(F("zahozen neuplny prikaz")); }
  while (Serial.available()) {
    char c = Serial.read();
    lastChar = millis();
    if (c == '\r' || c == '\n') {
      if (len) {
        buf[len] = 0;
        if (buf[0] >= 'A' && buf[0] <= 'Z') drawLine(buf);
        else testCmd(buf);
        len = 0;
      }
    } else if (len < sizeof(buf) - 1) buf[len++] = c;
  }
}
