
#include <Adafruit_NeoPixel.h>

// =====================================
// CAU HINH PHAN CUNG
// =====================================
#define LED_PIN 6
#define PWM_PIN 9

#define EXPORT_LEDS 3
#define TOTAL_LEDS (69 + EXPORT_LEDS)

// PWM 25 Hz: giu cau hinh da thu chay cham
const unsigned long PWM_PERIOD_US = 40000UL;

// Khoi dong: tang luc trong thoi gian ngan
const unsigned long KHOI_DONG_MS = 600UL;
const int PWM_KHOI_DONG = 20;  // Khoang 7.8%

// Toc do mac dinh: 8/255, khoang 3.1% duty cycle
// SPEED=0 dung; SPEED=1..7 duoc nang len 8 de tranh xung qua ngan.
int tocDo = 8;
bool bangTaiDangChay = false;

unsigned long thoiDiemBatDauBangTai = 0;
unsigned long chuKyBatDauUs = 0;
bool pwmDangMucCao = false;

// Nhan lenh Serial khong chan
char rxBuffer[48];
byte rxIndex = 0;

// =====================================
// LED CAC O KHO
// =====================================
Adafruit_NeoPixel leds(
  TOTAL_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800
);

const int batDau[12] = {
  0, 5, 11, 21, 31, 36,
  42, 46, 49, 56, 62, 66
};

const int soLed[12] = {
  5, 6, 10, 10, 5, 6,
  4, 3, 7, 6, 4, 3
};

const int XUAT_START = 69;

bool coHang[12] = {false};
bool ledCanCapNhat = false;

// =====================================
// TINH THOI GIAN BAT PWM
// =====================================
unsigned long tinhThoiGianBatUs() {
  if (!bangTaiDangChay || tocDo <= 0) {
    return 0;
  }

  int mucPWM = tocDo;

  // Tang luc trong 600 ms dau khi START
  if (millis() - thoiDiemBatDauBangTai < KHOI_DONG_MS) {
    if (mucPWM < PWM_KHOI_DONG) {
      mucPWM = PWM_KHOI_DONG;
    }
  }

  if (mucPWM >= 255) {
    return PWM_PERIOD_US;
  }

  unsigned long batUs =
      (PWM_PERIOD_US * (unsigned long)mucPWM + 127UL) / 255UL;

  return batUs;
}

// =====================================
// DAT LAI PWM VE MUC THAP
// =====================================
void duaPWMVeThap() {
  digitalWrite(PWM_PIN, LOW);
  pwmDangMucCao = false;
  chuKyBatDauUs = micros();
}

// =====================================
// CAP NHAT PWM LIEN TUC
// =====================================
void capNhatXungPWM() {
  unsigned long batUs = tinhThoiGianBatUs();

  if (batUs == 0) {
    if (pwmDangMucCao) {
      digitalWrite(PWM_PIN, LOW);
      pwmDangMucCao = false;
    }
    return;
  }

  unsigned long now = micros();
  unsigned long pha = (now - chuKyBatDauUs) % PWM_PERIOD_US;

  // Dong bo lai moc chu ky
  chuKyBatDauUs = now - pha;

  bool mucCao =
      (batUs >= PWM_PERIOD_US) || (pha < batUs);

  if (mucCao != pwmDangMucCao) {
    digitalWrite(PWM_PIN, mucCao ? HIGH : LOW);
    pwmDangMucCao = mucCao;
  }
}

// =====================================
// DIEU KHIEN BANG TAI
// =====================================
void startBangTai() {
  bangTaiDangChay = true;
  thoiDiemBatDauBangTai = millis();
  duaPWMVeThap();

  Serial.println("OK START");
}

void stopBangTai() {
  bangTaiDangChay = false;
  duaPWMVeThap();

  Serial.println("OK STOP");
}

// =====================================
// DIEU KHIEN LED CAC O
// =====================================
void capNhatO(int o) {
  if (o < 1 || o > 12) return;

  uint32_t mau = coHang[o - 1]
      ? leds.Color(255, 0, 0)   // Co hang: do
      : leds.Color(0, 255, 0);  // Trong: xanh

  int start = batDau[o - 1];

  for (int i = start; i < start + soLed[o - 1]; i++) {
    leds.setPixelColor(i, mau);
  }

  // De danh dau; khong show ngay de tranh lam giat PWM
  ledCanCapNhat = true;
}

// =====================================
// DEN O XUAT HANG
// =====================================
void denXuat(bool bat) {
  uint32_t mau = bat
      ? leds.Color(0, 0, 255)
      : leds.Color(0, 0, 0);

  for (int i = XUAT_START;
       i < XUAT_START + EXPORT_LEDS; i++) {
    leds.setPixelColor(i, mau);
  }

  ledCanCapNhat = true;
}

// =====================================
// CAP NHAT LED KHI PWM DANG THAP
// =====================================
void hienThiLEDAnToan() {
  if (!ledCanCapNhat) return;

  unsigned long batUs = tinhThoiGianBatUs();
  unsigned long pha =
      (micros() - chuKyBatDauUs) % PWM_PERIOD_US;

  bool dangTrongPhaThap =
      !bangTaiDangChay ||
      batUs == 0 ||
      batUs >= PWM_PERIOD_US ||
      pha >= batUs;

  if (!dangTrongPhaThap) return;

  // Dam bao PWM thap trong luc cap nhat LED
  digitalWrite(PWM_PIN, LOW);
  pwmDangMucCao = false;

  leds.show();
  ledCanCapNhat = false;

  // show() co the chiem CPU vai ms, tao moc PWM moi
  chuKyBatDauUs = micros();
}

// =====================================
// XU LY LENH SERIAL
// =====================================
void xuLyLenh(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "START") {
    startBangTai();
    return;
  }

  if (cmd == "STOP") {
    stopBangTai();
    return;
  }

  if (cmd.startsWith("SPEED=")) {
    int giaTri = cmd.substring(6).toInt();

    if (giaTri >= 0 && giaTri <= 255) {
      if (giaTri > 0 && giaTri < 8) {
        giaTri = 8;
      }

      bool tocDoCuBangKhong = (tocDo == 0);
      tocDo = giaTri;

      if (bangTaiDangChay && tocDoCuBangKhong && tocDo > 0) {
        thoiDiemBatDauBangTai = millis();
        duaPWMVeThap();
      }

      if (tocDo == 0) {
        duaPWMVeThap();
      }

      Serial.println("OK SPEED");
    } else {
      Serial.println("ERROR SPEED_RANGE");
    }
    return;
  }

  if (cmd == "XUAT_ON") {
    denXuat(true);
    Serial.println("OK XUAT_ON");
    return;
  }

  if (cmd == "XUAT_OFF") {
    denXuat(false);
    Serial.println("OK XUAT_OFF");
    return;
  }

  if (cmd == "CLEAR") {
    leds.clear();
    ledCanCapNhat = true;
    Serial.println("OK CLEAR");
    return;
  }

  // Dinh dang lenh: O1_ON, O1_OFF ... O12_ON, O12_OFF
  if (cmd.length() >= 4 && cmd[0] == 'O') {
    int gach = cmd.indexOf('_');

    if (gach > 1) {
      int o = cmd.substring(1, gach).toInt();
      String lenh = cmd.substring(gach + 1);

      if (o >= 1 && o <= 12) {
        if (lenh == "ON") {
          coHang[o - 1] = true;
          capNhatO(o);
          Serial.println("OK " + cmd);
          return;
        }

        if (lenh == "OFF") {
          coHang[o - 1] = false;
          capNhatO(o);
          Serial.println("OK " + cmd);
          return;
        }
      }
    }
  }

  Serial.println("ERROR UNKNOWN_COMMAND");
}

// =====================================
// DOC SERIAL KHONG CHAN
// =====================================
void docSerialKhongChan() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\r') continue;

    if (c == '\n') {
      rxBuffer[rxIndex] = '\0';

      if (rxIndex > 0) {
        String cmd(rxBuffer);
        xuLyLenh(cmd);
      }

      rxIndex = 0;
    } else {
      if (rxIndex < sizeof(rxBuffer) - 1) {
        rxBuffer[rxIndex++] = c;
      } else {
        rxIndex = 0;
        Serial.println("ERROR COMMAND_TOO_LONG");
      }
    }
  }
}

// =====================================
// SETUP
// =====================================
void setup() {
  Serial.begin(115200);

  pinMode(PWM_PIN, OUTPUT);
  digitalWrite(PWM_PIN, LOW);
  chuKyBatDauUs = micros();

  leds.begin();
  leds.setBrightness(80);
  leds.clear();

  // Khoi tao 12 o: xanh = trong
  for (int o = 1; o <= 12; o++) {
    capNhatO(o);
  }

  // Hien thi LED khoi dong mot lan
  leds.show();
  ledCanCapNhat = false;

  Serial.println("ARDUINO_READY");
}

// =====================================
// LOOP
// =====================================
void loop() {
  capNhatXungPWM();

  unsigned long batUs = tinhThoiGianBatUs();
  bool PWM100PhanTram = (batUs >= PWM_PERIOD_US);

  // Doc lenh khi PWM dang thap.
  // Truong hop toc do 255 van cho phep nhan lenh Serial.
  if (!pwmDangMucCao || PWM100PhanTram) {
    docSerialKhongChan();
  }

  capNhatXungPWM();

  batUs = tinhThoiGianBatUs();
  PWM100PhanTram = (batUs >= PWM_PERIOD_US);

  if (!pwmDangMucCao || PWM100PhanTram) {
    hienThiLEDAnToan();
  }

  capNhatXungPWM();
}