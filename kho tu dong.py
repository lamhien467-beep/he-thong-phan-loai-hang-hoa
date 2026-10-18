import sys
import cv2
import serial
import time

from pyzbar.pyzbar import decode, ZBarSymbol
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap


# ==================================================
# CAU HINH
# ==================================================

COM_PORT = "COM4"
BAUD_RATE = 115200

ARDUINO_PORT = "COM10"
ARDUINO_BAUD = 115200

CHE_DO_MO_PHONG = False
CAMERA_INDEX = 1

# Luu y: neu servo khong quay dung, kiem tra cau hinh spindle trong FluidNC
# (max_speed_map, disable_with_s0). S0 co the bi hieu la TAT spindle.
SERVO_MO = "M3 S0"
SERVO_KHOA = "M3 S450"

# Thoi gian cho servo dong/mo xong (giay)
THOI_GIAN_SERVO = 0.8

TRAM_GAP = {
    "X": 0,
    "Y": 400,
    "Z_TREN": 0,
    "Z_GAP": -68,
}

KHO = {
    "O_1":  {"X": 150, "Y": 410, "Z_GAP": -118, "trang_thai": 0},
    "O_2":  {"X": 220, "Y": 410, "Z_GAP": -120, "trang_thai": 0},
    "O_3":  {"X": 280, "Y": 410, "Z_GAP": -120, "trang_thai": 0},
    "O_4":  {"X": 280, "Y": 350, "Z_GAP": -120, "trang_thai": 0},
    "O_5":  {"X": 213, "Y": 350, "Z_GAP": -120, "trang_thai": 0},
    "O_6":  {"X": 153, "Y": 350, "Z_GAP": -120, "trang_thai": 0},
    "O_7":  {"X": 169, "Y": 288, "Z_GAP": -120, "trang_thai": 0},
    "O_8":  {"X": 214, "Y": 288, "Z_GAP": -118, "trang_thai": 0},
    "O_9":  {"X": 261, "Y": 288, "Z_GAP": -120, "trang_thai": 0},
    "O_10": {"X": 261, "Y": 248, "Z_GAP": -120, "trang_thai": 0},
    "O_11": {"X": 218, "Y": 248, "Z_GAP": -120, "trang_thai": 0},
    "O_12": {"X": 172, "Y": 248, "Z_GAP": -120, "trang_thai": 0},
}

O_XUAT = {
    "X": 214,
    "Y": 138,
    "Z_GAP": -120,
}


# ==================================================
# KET NOI ARDUINO
# ==================================================

arduino = None

try:
    arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
    time.sleep(2)
    arduino.reset_input_buffer()
    print("Da ket noi Arduino:", ARDUINO_PORT)
except Exception as e:
    print("Khong ket noi duoc Arduino:", e)
    arduino = None


def gui_arduino(lenh):
    """Gui lenh Arduino va kiem tra phan hoi OK."""
    if arduino is None or not arduino.is_open:
        print("Arduino chua ket noi!")
        return False

    try:
        arduino.reset_input_buffer()
        arduino.write((lenh + "\n").encode("utf-8"))
        arduino.flush()

        phan_hoi = arduino.readline().decode(
            "utf-8", errors="ignore"
        ).strip()

        print("Arduino phan hoi:", phan_hoi)
        return phan_hoi.startswith("OK")

    except Exception as e:
        print("Loi gui lenh Arduino:", e)
        return False


def cap_nhat_led_o(ten_o, co_hang):
    so_o = ten_o.replace("O_", "")
    trang_thai = "ON" if co_hang else "OFF"
    return gui_arduino(f"O{so_o}_{trang_thai}")


def dieu_khien_bang_tai(chay):
    return gui_arduino("START" if chay else "STOP")


def cap_nhat_led_tat_ca():
    for ten_o, o in KHO.items():
        cap_nhat_led_o(ten_o, bool(o["trang_thai"]))


# ==================================================
# KET NOI FLUIDNC
# ==================================================

fluidnc = None

if not CHE_DO_MO_PHONG:
    try:
        fluidnc = serial.Serial(COM_PORT, BAUD_RATE, timeout=0.05)
        time.sleep(2)
        print("Da ket noi FluidNC:", COM_PORT)
    except Exception as e:
        print("Loi ket noi FluidNC:", e)
        fluidnc = None
else:
    print("=== CHE DO MO PHONG ===")


def send_gcode(cmd, timeout=5.0):
    """Gui G-code va cho phan hoi ok/error."""
    if CHE_DO_MO_PHONG:
        print("[SIM]", cmd)
        time.sleep(0.15)
        return True

    if fluidnc is None or not fluidnc.is_open:
        print("FluidNC chua ket noi!")
        return False

    try:
        fluidnc.reset_input_buffer()
        fluidnc.write((cmd + "\n").encode("utf-8"))
        fluidnc.flush()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = fluidnc.readline().decode(
                "utf-8", errors="ignore"
            ).strip()

            if not line:
                continue

            print("FluidNC:", line)
            lower = line.lower()

            if lower == "ok":
                return True
            if lower.startswith("error") or lower.startswith("alarm"):
                return False

        print("FluidNC het thoi gian cho:", cmd)
    except Exception as e:
        print("Loi G-code:", e)

    return False


def doc_trang_thai():
    """Hoi FluidNC bang '?' va tra ve trang thai: 'Idle', 'Run', 'Alarm'...
    Tra ve None neu khong doc duoc."""
    if CHE_DO_MO_PHONG or fluidnc is None or not fluidnc.is_open:
        return None

    try:
        fluidnc.reset_input_buffer()
        fluidnc.write(b"?")
        fluidnc.flush()

        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            line = fluidnc.readline().decode(
                "utf-8", errors="ignore"
            ).strip()

            if line.startswith("<") and line.endswith(">"):
                return line[1:-1].split("|")[0].split(":")[0]
    except Exception as e:
        print("Loi doc trang thai FluidNC:", e)

    return None


def cho_dung_yen(timeout=30.0):
    """Cho den khi FluidNC o trang thai Idle (da chay xong lenh)."""
    if CHE_DO_MO_PHONG:
        return True

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = doc_trang_thai()

        if state == "Idle":
            return True

        if state == "Alarm":
            print("FluidNC dang Alarm! Hay bam HOME de mo khoa.")
            return False

        time.sleep(0.05)

    print("Het thoi gian cho FluidNC ve Idle")
    return False


def doc_cam_bien_quang():
    """True: probe tac dong; False: probe nha; None: khong doc duoc."""
    if CHE_DO_MO_PHONG or fluidnc is None or not fluidnc.is_open:
        return None

    try:
        fluidnc.write(b"?")
        fluidnc.flush()
        deadline = time.monotonic() + 0.15

        while time.monotonic() < deadline:
            line = fluidnc.readline().decode(
                "utf-8", errors="ignore"
            ).strip()

            if line.startswith("<") and line.endswith(">"):
                fields = line[1:-1].split("|")
                for field in fields:
                    if field.startswith("Pn:"):
                        return "P" in field[3:]
                return False
    except Exception as e:
        print("Loi doc cam bien GPIO22:", e)

    return None


# ==================================================
# DIEU KHIEN CHUYEN DONG
# ==================================================

def home():
    # $H co the chay lau hon 5 giay nen cho timeout dai
    if not send_gcode("$H", timeout=60):
        return False
    return cho_dung_yen(60)


def tram_gap():
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F3000"):
        return False
    if not send_gcode(f"G0 X{TRAM_GAP['X']} Y{TRAM_GAP['Y']} F3000"):
        return False
    return cho_dung_yen()


def gap():
    if not send_gcode(f"G1 Z{TRAM_GAP['Z_GAP']} F3000"):
        return False

    # Cho Z xuong toi noi roi moi kep
    if not cho_dung_yen():
        return False

    if not send_gcode(SERVO_KHOA):
        return False

    time.sleep(THOI_GIAN_SERVO)
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F3000"):
        return False
    return cho_dung_yen()


def den(x, y):
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F2000"):
        return False
    if not send_gcode(f"G0 X{x} Y{y} F3000"):
        return False
    return cho_dung_yen()


def tha(z):
    if not send_gcode(f"G1 Z{z} F3000"):
        return False

    # Cho Z xuong toi noi roi moi nha
    if not cho_dung_yen():
        return False

    if not send_gcode(SERVO_MO):
        return False

    time.sleep(THOI_GIAN_SERVO)
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F1000"):
        return False
    return cho_dung_yen()


# ==================================================
# QUAN LY KHO
# ==================================================

def o_trong(loai_hang):
    """Hang TO dung O_1..O_6; hang NHO dung O_7..O_12."""
    ds_o = range(1, 7) if loai_hang == "TO" else range(7, 13)

    for i in ds_o:
        ten = f"O_{i}"
        if not KHO[ten]["trang_thai"]:
            return ten

    return None


def nhan_hang(data):
    """Nhan dien QR, gap hang va cat vao o phu hop."""
    if "HAT GIONG" in data:
        loai_hang = "TO"
    elif "GAO" in data:
        loai_hang = "NHO"
    else:
        print("QR khong hop le:", data)
        return False

    ten = o_trong(loai_hang)
    if ten is None:
        print(f"Kho {loai_hang} da day!")
        return False

    print(f"Nhan {loai_hang} -> {ten}")

    if not tram_gap() or not gap():
        return False

    o = KHO[ten]
    if not den(o["X"], o["Y"]):
        return False
    if not tha(o["Z_GAP"]):
        return False

    o["trang_thai"] = 1
    cap_nhat_led_o(ten, True)

    if not tram_gap():
        return False

    return True


def xuat_mot_o(ten_o):
    """Xuat hang tu mot o da chon."""
    if ten_o not in KHO:
        return False

    o = KHO[ten_o]
    if not o["trang_thai"]:
        print(ten_o, "dang trong")
        return False

    print("Dang xuat:", ten_o)

    if not den(o["X"], o["Y"]):
        return False
    if not send_gcode(f"G1 Z{o['Z_GAP']} F3000"):
        return False

    # Cho Z xuong toi noi roi moi kep
    if not cho_dung_yen():
        return False

    if not send_gcode(SERVO_KHOA):
        return False

    time.sleep(THOI_GIAN_SERVO)
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F3000"):
        return False
    if not cho_dung_yen():
        return False
    if not den(O_XUAT["X"], O_XUAT["Y"]):
        return False
    if not tha(O_XUAT["Z_GAP"]):
        return False

    o["trang_thai"] = 0
    cap_nhat_led_o(ten_o, False)
    return tram_gap()


def xuat_theo_thu_tu(danh_sach):
    for ten_o in danh_sach:
        if not xuat_mot_o(ten_o):
            print("Xuat that bai tai", ten_o)
            return False
    return True


def xuat_hang():
    print("========== XUAT HANG ==========")
    for ten_o, o in KHO.items():
        if o["trang_thai"] and not xuat_mot_o(ten_o):
            print("Xuat that bai tai", ten_o)
            return False

    tram_gap()
    print("DA XUAT HET HANG")
    return True


# ==================================================
# GIAO DIEN PYSIDE6
# ==================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.running = False
        self.qr_lock = False
        self.cam_bien_da_phat_hien = False
        self.bang_tai_da_dung = False
        self.cho_cam_bien_nha = False
        self.qr_candidate = None
        self.qr_stable_count = 0
        self.loi_chu_ky = False
        self.danh_sach_xuat = []

        self.setWindowTitle("HE THONG PHAN LOAI HANG")
        self.resize(1200, 800)

        # Camera
        self.camera = cv2.VideoCapture(CAMERA_INDEX)
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.camera_label = QLabel("Dang mo camera...")
        self.camera_label.setMinimumSize(640, 480)
        self.camera_label.setAlignment(Qt.AlignCenter)

        # Vi tri va trang thai
        self.x_label = QLabel("X: -- mm")
        self.y_label = QLabel("Y: -- mm")
        self.z_label = QLabel("Z: -- mm")
        self.status = QLabel("Trang thai: SAN SANG")

        # Nut dieu khien
        home_btn = QPushButton("HOME")
        start_btn = QPushButton("START")
        stop_btn = QPushButton("STOP")
        export_btn = QPushButton("XUAT HANG")
        xuat_o_btn = QPushButton("XUAT O DANG CHON")
        xuat_thu_tu_btn = QPushButton("XUAT THEO THU TU")
        xoa_chon_btn = QPushButton("XOA CHON")

        home_btn.clicked.connect(self.home)
        start_btn.clicked.connect(self.start)
        stop_btn.clicked.connect(self.stop)
        export_btn.clicked.connect(self.export)
        xuat_o_btn.clicked.connect(self.xuat_o_chon)
        xuat_thu_tu_btn.clicked.connect(self.xuat_thu_tu)
        xoa_chon_btn.clicked.connect(self.xoa_chon)

        # 12 o hang
        self.box_btn = []
        grid = QGridLayout()

        for i in range(12):
            b = QPushButton(f"O {i + 1}\nTRONG")
            b.setMinimumSize(130, 80)
            b.clicked.connect(lambda _, n=i: self.toggle(n))
            self.box_btn.append(b)
            grid.addWidget(b, i // 4, i % 4)

        box_group = QGroupBox("TRANG THAI 12 O HANG")
        box_group.setLayout(grid)

        # Vi tri
        pos = QHBoxLayout()
        pos.addWidget(self.x_label)
        pos.addWidget(self.y_label)
        pos.addWidget(self.z_label)
        pos_group = QGroupBox("VI TRI HIEN TAI")
        pos_group.setLayout(pos)

        # Hang nut
        buttons = QHBoxLayout()
        for b in (
            home_btn, start_btn, stop_btn, export_btn,
            xuat_o_btn, xuat_thu_tu_btn, xoa_chon_btn
        ):
            buttons.addWidget(b)

        left = QVBoxLayout()
        left.addWidget(QLabel("CAMERA GIAM SAT"))
        left.addWidget(self.camera_label)
        left.addWidget(pos_group)
        left.addWidget(self.status)
        left.addLayout(buttons)

        left_widget = QWidget()
        left_widget.setLayout(left)

        main = QHBoxLayout()
        main.addWidget(left_widget, 2)
        main.addWidget(box_group, 1)

        center = QWidget()
        center.setLayout(main)
        self.setCentralWidget(center)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.camera_update)
        self.timer.start(30)

        self.update_boxes()

    # --------------------------------------------------
    # CAMERA VA QUET QR
    # --------------------------------------------------

    def camera_update(self):
        ret, frame = self.camera.read()
        if not ret:
            return

        if self.running and not CHE_DO_MO_PHONG:
            trang_thai_cam_bien = doc_cam_bien_quang()

            if trang_thai_cam_bien is True:
                if not self.cam_bien_da_phat_hien:
                    self.cam_bien_da_phat_hien = True
                    self.bang_tai_da_dung = False
                    self.cho_cam_bien_nha = False
                    self.qr_candidate = None
                    self.qr_stable_count = 0
                    self.loi_chu_ky = False
                    self.status.setText(
                        "CAM BIEN PHAT HIEN HANG - DANG DUNG BANG TAI"
                    )

                if not self.bang_tai_da_dung:
                    if dieu_khien_bang_tai(False):
                        self.bang_tai_da_dung = True
                        self.status.setText("BANG TAI DA DUNG - DANG DOC QR")
                    else:
                        self.status.setText("LOI: ARDUINO CHUA XAC NHAN STOP")

                if (
                    self.bang_tai_da_dung
                    and not self.qr_lock
                    and not self.cho_cam_bien_nha
                    and not self.loi_chu_ky
                ):
                    codes = decode(
                        frame,
                        symbols=[ZBarSymbol.QRCODE, ZBarSymbol.CODE128],
                    )
                    ma_hang = set()

                    for code in codes:
                        text_qr = code.data.decode(
                            "utf-8", errors="ignore"
                        ).strip()
                        if "HAT GIONG" in text_qr or "GAO" in text_qr:
                            ma_hang.add(text_qr)

                    if len(ma_hang) > 1:
                        self.qr_candidate = None
                        self.qr_stable_count = 0
                        self.status.setText(
                            "CO NHIEU MA HANG - CHI DE MOT MA TAI TRAM"
                        )

                    elif len(ma_hang) == 1:
                        qr_hang = next(iter(ma_hang))
                        if qr_hang == self.qr_candidate:
                            self.qr_stable_count += 1
                        else:
                            self.qr_candidate = qr_hang
                            self.qr_stable_count = 1

                        if self.qr_stable_count >= 3:
                            self.qr_lock = True
                            self.cho_cam_bien_nha = True
                            print("NHAN QR:", qr_hang)
                            self.status.setText(f"DANG XU LY: {qr_hang}")
                            QApplication.processEvents()

                            try:
                                thanh_cong = nhan_hang(qr_hang)
                                if thanh_cong:
                                    self.update_boxes()
                                    self.status.setText(
                                        "DA CAT HANG - DANG CHO CAM BIEN NHA"
                                    )
                                else:
                                    self.cho_cam_bien_nha = False
                                    self.loi_chu_ky = True
                                    self.status.setText(
                                        "KHONG CAT DUOC HANG - BANG TAI GIU DUNG"
                                    )
                            except Exception as e:
                                self.cho_cam_bien_nha = False
                                self.loi_chu_ky = True
                                print("LOI GAP HANG:", e)
                                self.status.setText(f"LOI GAP HANG: {e}")
                            finally:
                                self.qr_lock = False
                    else:
                        self.qr_candidate = None
                        self.qr_stable_count = 0

            elif (
                trang_thai_cam_bien is False
                and self.cam_bien_da_phat_hien
            ):
                if self.cho_cam_bien_nha and not self.loi_chu_ky:
                    if dieu_khien_bang_tai(True):
                        self.cam_bien_da_phat_hien = False
                        self.bang_tai_da_dung = False
                        self.cho_cam_bien_nha = False
                        self.qr_candidate = None
                        self.qr_stable_count = 0
                        self.status.setText(
                            "CAM BIEN DA NHA - BANG TAI CHAY LAI"
                        )
                    else:
                        self.loi_chu_ky = True
                        self.running = False
                        self.status.setText(
                            "LOI: ARDUINO CHUA XAC NHAN START"
                        )
                elif not self.loi_chu_ky:
                    self.loi_chu_ky = True
                    dieu_khien_bang_tai(False)
                    self.running = False
                    self.status.setText(
                        "CANH BAO: CAM BIEN NHA TRUOC KHI CAT HANG - DA DUNG"
                    )

        # Hien thi camera
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, c = frame_rgb.shape
        img = QImage(frame_rgb.data, w, h, c * w, QImage.Format_RGB888)
        self.camera_label.setPixmap(
            QPixmap.fromImage(img).scaled(
                self.camera_label.size(), Qt.KeepAspectRatio
            )
        )

    # --------------------------------------------------
    # CAP NHAT O KHO / CHON O
    # --------------------------------------------------

    def update_boxes(self):
        for i in range(12):
            state = KHO[f"O_{i + 1}"]["trang_thai"]
            status_text = "CO HANG" if state else "TRONG"
            selected = f"O_{i + 1}" in self.danh_sach_xuat
            prefix = "[CHON] " if selected else ""
            self.box_btn[i].setText(f"{prefix}O {i + 1}\n{status_text}")

    def toggle(self, i):
        ten_o = f"O_{i + 1}"
        if not KHO[ten_o]["trang_thai"]:
            self.status.setText(f"{ten_o}: TRONG")
            return

        if ten_o in self.danh_sach_xuat:
            self.danh_sach_xuat.remove(ten_o)
        else:
            self.danh_sach_xuat.append(ten_o)

        self.update_boxes()
        if self.danh_sach_xuat:
            self.status.setText(
                "Thu tu xuat: " + " -> ".join(self.danh_sach_xuat)
            )
        else:
            self.status.setText("Chua chon o xuat")

    def xoa_chon(self):
        self.danh_sach_xuat.clear()
        self.update_boxes()
        self.status.setText("DA XOA LUA CHON")

    # --------------------------------------------------
    # XUAT HANG
    # --------------------------------------------------

    def xuat_o_chon(self):
        if not self.danh_sach_xuat:
            self.status.setText("Chua chon o!")
            return

        ten_o = self.danh_sach_xuat[-1]
        self.status.setText(f"DANG XUAT {ten_o}")
        QApplication.processEvents()

        try:
            if xuat_mot_o(ten_o):
                self.danh_sach_xuat.remove(ten_o)
                self.update_boxes()
                self.status.setText(f"DA XUAT {ten_o}")
            else:
                self.status.setText(f"XUAT THAT BAI: {ten_o}")
        except Exception as e:
            self.status.setText(f"LOI XUAT HANG: {e}")

    def xuat_thu_tu(self):
        if not self.danh_sach_xuat:
            self.status.setText("Chua chon o!")
            return

        self.running = False
        danh_sach = self.danh_sach_xuat.copy()
        self.status.setText("DANG XUAT: " + " -> ".join(danh_sach))
        QApplication.processEvents()

        try:
            if xuat_theo_thu_tu(danh_sach):
                self.danh_sach_xuat.clear()
                self.status.setText("DA XUAT THEO THU TU")
            else:
                self.danh_sach_xuat = [
                    ten for ten in danh_sach if KHO[ten]["trang_thai"]
                ]
                self.status.setText(
                    "XUAT CHUA HOAN TAT - KIEM TRA O CON HANG"
                )
            self.update_boxes()
        except Exception as e:
            self.status.setText(f"LOI XUAT HANG: {e}")

    def export(self):
        self.running = False
        self.status.setText("DANG XUAT HANG")
        QApplication.processEvents()

        if arduino is not None:
            gui_arduino("XUAT_ON")

        try:
            if xuat_hang():
                self.update_boxes()
                self.danh_sach_xuat.clear()
                self.status.setText("DA XUAT HET HANG")
            else:
                self.update_boxes()
                self.status.setText(
                    "XUAT CHUA HOAN TAT - KIEM TRA MAY"
                )
        except Exception as e:
            self.status.setText(f"LOI XUAT HANG: {e}")
        finally:
            if arduino is not None:
                gui_arduino("XUAT_OFF")

    # --------------------------------------------------
    # HOME / START / STOP
    # --------------------------------------------------

    def home(self):
        self.running = False
        self.status.setText("DANG HOME (CO THE MAT VAI CHUC GIAY)")
        QApplication.processEvents()

        if home():
            if send_gcode(SERVO_MO) and tram_gap():
                self.status.setText("SAN SANG")
            else:
                self.status.setText(
                    "HOME XONG NHUNG DI CHUYEN VE TRAM GAP LOI"
                )
        else:
            self.status.setText("HOME THAT BAI - XEM CONSOLE")

    def start(self):
        if CHE_DO_MO_PHONG:
            self.status.setText(
                "DANG MO PHONG - KHONG DOC CAM BIEN THAT"
            )
            return

        if fluidnc is None or not fluidnc.is_open:
            self.status.setText("CHUA KET NOI FLUIDNC")
            return

        if arduino is None or not arduino.is_open:
            self.status.setText("CHUA KET NOI ARDUINO")
            return

        # Kiem tra FluidNC khong bi Alarm (chua home)
        state = doc_trang_thai()
        if state == "Alarm":
            self.status.setText("FLUIDNC DANG ALARM - BAM HOME TRUOC")
            return
        if state is None:
            self.status.setText("KHONG DOC DUOC TRANG THAI FLUIDNC")
            return

        if not dieu_khien_bang_tai(True):
            self.status.setText("ARDUINO KHONG XAC NHAN START")
            return

        self.cam_bien_da_phat_hien = False
        self.bang_tai_da_dung = False
        self.cho_cam_bien_nha = False
        self.qr_candidate = None
        self.qr_stable_count = 0
        self.loi_chu_ky = False
        self.running = True
        self.status.setText("DANG CHAY - CHO CAM BIEN")
        print("START")

    def stop(self):
        self.running = False
        self.qr_lock = False
        ok_arduino = dieu_khien_bang_tai(False)

        if (
            not CHE_DO_MO_PHONG
            and fluidnc is not None
            and fluidnc.is_open
        ):
            try:
                fluidnc.write(b"!")
                fluidnc.flush()
            except Exception as e:
                print("Loi gui Feed Hold:", e)

        self.cam_bien_da_phat_hien = False
        self.bang_tai_da_dung = False
        self.cho_cam_bien_nha = False
        self.qr_candidate = None
        self.qr_stable_count = 0
        self.loi_chu_ky = False

        self.status.setText(
            "DA DUNG" if ok_arduino
            else "DA GUI DUNG - ARDUINO CHUA XAC NHAN"
        )
        print("STOP")

    # --------------------------------------------------
    # DONG CHUONG TRINH
    # --------------------------------------------------

    def closeEvent(self, event):
        self.running = False

        if hasattr(self, "timer"):
            self.timer.stop()

        if hasattr(self, "camera") and self.camera:
            self.camera.release()

        if fluidnc is not None and fluidnc.is_open:
            fluidnc.close()

        if arduino is not None and arduino.is_open:
            try:
                arduino.write(b"STOP\n")
                arduino.flush()
                arduino.close()
            except Exception:
                pass

        event.accept()


# ==================================================
# CHAY CHUONG TRINH
# ==================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())