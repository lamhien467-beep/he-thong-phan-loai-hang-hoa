import os
import sys
import cv2
import serial
import time
import numpy as np
from datetime import datetime

from openpyxl import Workbook, load_workbook
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

# Toc do chay on dinh cua bang tai (0..255, PWM that cua L298N)
BANG_TAI_TOC_DO = 200

CHE_DO_MO_PHONG = False
CAMERA_INDEX = 1

# Thu muc luu nhat ky (doi thanh duong dan day du neu muon, vd r"D:\KHO\NhatKy")
THU_MUC_EXCEL = r"D:\New folder\New folder03\NhatKy_luukho"

# Moi lan chay chuong trinh tao 1 file moi, ten theo ngay gio luc khoi dong
FILE_EXCEL = os.path.join(
    THU_MUC_EXCEL,
    "nhat_ky_kho_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
)

SERVO_MO = "M3 S0"
SERVO_KHOA_TO = "M3 S320"     # hang to  (O_1..O_6)
SERVO_KHOA_NHO = "M3 S440"    # hang nho (O_7..O_12)

# Toc do di chuyen (mm/phut) - neu bi mat buoc thi GIAM cac so nay
F_XY = 1500                   # di chuyen ngang X, Y
F_Z_LEN = 1000                # nang Z len
F_Z_XUONG = 1000              # ha Z xuong de gap / cat

# Toc do ha hang
F_HA_NHANH = 1500
F_HA_CHAM = 600
KHOANG_CHAM = 25              # mm cuoi cung ha cham

TRAM_GAP = {
    "X": 0,
    "Y": 375,
    "Z_TREN": 0,
    "Z_GAP": -56,
}

KHO = {
    "O_1":  {"X": 137, "Y": 430, "Z_GAP": -116, "trang_thai": 0, "ten_hang": ""},
    "O_2":  {"X": 203, "Y": 430, "Z_GAP": -116, "trang_thai": 0, "ten_hang": ""},
    "O_3":  {"X": 273, "Y": 430, "Z_GAP": -116, "trang_thai": 0, "ten_hang": ""},
    "O_4":  {"X": 273, "Y": 354, "Z_GAP": -116, "trang_thai": 0, "ten_hang": ""},
    "O_5":  {"X": 203, "Y": 354, "Z_GAP": -116, "trang_thai": 0, "ten_hang": ""},
    "O_6":  {"X": 137, "Y": 354, "Z_GAP": -116, "trang_thai": 0, "ten_hang": ""},
    "O_7":  {"X": 135, "Y": 295, "Z_GAP": -114, "trang_thai": 0, "ten_hang": ""},
    "O_8":  {"X": 180, "Y": 295, "Z_GAP": -114, "trang_thai": 0, "ten_hang": ""},
    "O_9":  {"X": 225, "Y": 295, "Z_GAP": -114, "trang_thai": 0, "ten_hang": ""},
    "O_10": {"X": 225, "Y": 244, "Z_GAP": -114, "trang_thai": 0, "ten_hang": ""},
    "O_11": {"X": 175, "Y": 244, "Z_GAP": -114, "trang_thai": 0, "ten_hang": ""},
    "O_12": {"X": 135, "Y": 244, "Z_GAP": -114, "trang_thai": 0, "ten_hang": ""},
}

O_XUAT = {
    "X": 214,
    "Y": 138,
    "Z_GAP": -120,
}


def servo_khoa_theo_loai(loai_hang):
    """Chon lenh kep theo loai hang: TO hoac NHO."""
    return SERVO_KHOA_TO if loai_hang == "TO" else SERVO_KHOA_NHO


def servo_khoa_theo_o(ten_o):
    """Chon lenh kep theo so o: O_1..O_6 la hang to, O_7..O_12 la hang nho."""
    so_o = int(ten_o.replace("O_", ""))
    return SERVO_KHOA_TO if so_o <= 6 else SERVO_KHOA_NHO


# ==================================================
# GHI NHAT KY EXCEL
# ==================================================

# Cac dong chua ghi duoc (vd file Excel dang mo) - se ghi bu o lan sau
HANG_CHO_GHI = []


def ten_hien_thi(noi_dung_qr):
    """Doi noi dung QR thanh ten mat hang de ghi vao Excel."""
    if "HAT GIONG" in noi_dung_qr:
        return "Hạt giống"
    if "GAO" in noi_dung_qr:
        return "Gạo"
    return noi_dung_qr


def tao_file_excel():
    """Tao file Excel moi (kem tieu de cot) ngay khi khoi dong chuong trinh."""
    try:
        os.makedirs(THU_MUC_EXCEL, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = "NhatKy"
        ws.append(["Ngày", "Giờ", "Ô lưu", "Tên mặt hàng", "Hành động"])
        for cot, rong in zip("ABCDE", (14, 12, 10, 30, 14)):
            ws.column_dimensions[cot].width = rong
        wb.save(FILE_EXCEL)
        print("Da tao file nhat ky:", os.path.abspath(FILE_EXCEL))
        return True
    except Exception as e:
        print("Khong tao duoc file Excel:", e)
        return False


def ghi_excel(ten_o, ten_hang, hanh_dong):
    """Ghi 1 dong: Ngay, Gio, O luu, Ten mat hang, Hanh dong (NHAP/XUAT).
    Neu file dang bi mo (khoa) thi giu dong lai va ghi bu o lan sau."""
    bay_gio = datetime.now()
    HANG_CHO_GHI.append([
        bay_gio.strftime("%d/%m/%Y"),
        bay_gio.strftime("%H:%M:%S"),
        ten_o.replace("_", " "),          # O_1 -> O 1
        ten_hang,
        hanh_dong,
    ])

    try:
        if os.path.exists(FILE_EXCEL):
            wb = load_workbook(FILE_EXCEL)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "NhatKy"
            ws.append(["Ngày", "Giờ", "Ô lưu", "Tên mặt hàng", "Hành động"])
            for cot, rong in zip("ABCDE", (14, 12, 10, 30, 14)):
                ws.column_dimensions[cot].width = rong

        for dong in HANG_CHO_GHI:
            ws.append(dong)
        wb.save(FILE_EXCEL)

        print(f"Da ghi Excel: {ten_o} - {ten_hang} - {hanh_dong}")
        HANG_CHO_GHI.clear()
        return True

    except PermissionError:
        print(
            f"Khong ghi duoc Excel - hay DONG file {FILE_EXCEL}! "
            f"({len(HANG_CHO_GHI)} dong dang cho, se ghi bu lan sau)"
        )
    except Exception as e:
        print("Loi ghi Excel:", e)
    return False


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
    # Gui toc do truoc moi lan START de Arduino luon chay dung toc do cai dat
    if chay:
        gui_arduino(f"SPEED={BANG_TAI_TOC_DO}")

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


VI_TRI = {"loai": "", "x": None, "y": None, "z": None}


def luu_vi_tri(line):
    """Tach MPos/WPos trong bao cao trang thai FluidNC de hien len giao dien."""
    try:
        for f in line[1:-1].split("|"):
            if f.startswith("MPos:") or f.startswith("WPos:"):
                v = f[5:].split(",")
                VI_TRI["loai"] = f[:4]
                VI_TRI["x"], VI_TRI["y"], VI_TRI["z"] = (
                    float(v[0]), float(v[1]), float(v[2])
                )
    except Exception:
        pass


def doc_trang_thai():
    """Hoi FluidNC bang '?' va tra ve trang thai: 'Idle', 'Run', 'Hold', 'Alarm'...
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
                luu_vi_tri(line)
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
                luu_vi_tri(line)
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
    # $H co the chay lau nen cho timeout dai
    if not send_gcode("$H", timeout=60):
        return False
    return cho_dung_yen(60)


def tram_gap():
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F{F_Z_LEN}"):
        return False
    if not send_gcode(f"G0 X{TRAM_GAP['X']} Y{TRAM_GAP['Y']} F{F_XY}"):
        return False
    return cho_dung_yen()


def phuc_hoi_may():
    """Tu phuc hoi sau loi/STOP: go Hold hoac Alarm nhe, nang Z, mo servo.
    KHONG chay ra tram gap (chi ra tram gap khi co hang moi trong nhan_hang()).
    Tra ve False neu may van Alarm (mat vi tri) -> luc do moi can bam HOME."""
    if CHE_DO_MO_PHONG:
        return True

    state = doc_trang_thai()

    if state is None:
        print("Khong doc duoc trang thai FluidNC")
        return False

    if state.startswith("Hold"):
        try:
            fluidnc.write(b"~")          # tiep tuc sau Feed Hold
            fluidnc.flush()
        except Exception as e:
            print("Loi gui Resume:", e)
            return False
        time.sleep(0.2)

    elif state == "Alarm":
        send_gcode("$X")                 # mo khoa Alarm, khong home
        time.sleep(0.2)
        if doc_trang_thai() == "Alarm":
            print("Van Alarm - can bam HOME")
            return False

    if not cho_dung_yen(10):
        return False

    # Nang Z len truoc roi moi mo servo
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F{F_Z_LEN}"):
        return False
    if not cho_dung_yen(10):
        return False

    if not send_gcode(SERVO_MO):         # nha kep de lan sau gap duoc
        return False
    time.sleep(0.3)

    return True


def den(x, y):
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F{F_Z_LEN}"):
        return False
    if not send_gcode(f"G0 X{x} Y{y} F{F_XY}"):
        return False
    return cho_dung_yen()


def gap(lenh_khoa):
    if not send_gcode(f"G1 Z{TRAM_GAP['Z_GAP']} F{F_Z_XUONG}"):
        return False
    if not cho_dung_yen():
        return False
    if not send_gcode(lenh_khoa):
        return False
    time.sleep(0.8)          # cho servo kep chat
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F{F_Z_LEN}"):
        return False
    return cho_dung_yen()


def tha(z, lenh_khoa=None):
    """Ha hang xuong do cao z roi nha.
    Gui lai lenh kep truoc khi ha, ha nhanh den gan roi ha cham doan cuoi."""
    if lenh_khoa and not send_gcode(lenh_khoa):
        return False

    z_gan = min(z + KHOANG_CHAM, TRAM_GAP["Z_TREN"])
    if not send_gcode(f"G1 Z{z_gan} F{F_HA_NHANH}"):
        return False
    if not send_gcode(f"G1 Z{z} F{F_HA_CHAM}"):
        return False
    if not cho_dung_yen():
        return False

    if not send_gcode(SERVO_MO):
        return False
    time.sleep(0.8)
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F{F_Z_LEN}"):
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
    """Nhan dien QR, chay ra tram gap, gap hang va cat vao o phu hop."""
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

    lenh_khoa = servo_khoa_theo_loai(loai_hang)

    # Co hang moi moi chay ra tram gap (may dang dung yen o home)
    if not tram_gap() or not gap(lenh_khoa):
        return False

    o = KHO[ten]
    if not den(o["X"], o["Y"]):
        return False
    if not tha(o["Z_GAP"], lenh_khoa):
        return False

    o["trang_thai"] = 1
    o["ten_hang"] = ten_hien_thi(data.strip())      # nho ten hang cua o nay
    cap_nhat_led_o(ten, True)
    ghi_excel(ten, o["ten_hang"], "NHẬP")

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

    lenh_khoa = servo_khoa_theo_o(ten_o)

    if not den(o["X"], o["Y"]):
        return False
    if not send_gcode(f"G1 Z{o['Z_GAP']} F{F_Z_XUONG}"):
        return False
    if not cho_dung_yen():
        return False

    if not send_gcode(lenh_khoa):
        return False

    time.sleep(0.8)
    if not send_gcode(f"G0 Z{TRAM_GAP['Z_TREN']} F{F_Z_LEN}"):
        return False
    if not cho_dung_yen():
        return False
    if not den(O_XUAT["X"], O_XUAT["Y"]):
        return False
    if not tha(O_XUAT["Z_GAP"], lenh_khoa):
        return False

    ten_hang = o.get("ten_hang", "")
    o["trang_thai"] = 0
    o["ten_hang"] = ""
    cap_nhat_led_o(ten_o, False)
    ghi_excel(ten_o, ten_hang, "XUẤT")
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
# VE KHUNG QR LEN HINH CAMERA
# ==================================================

def ve_qr_len_frame(frame, codes):
    """Ve khung va noi dung QR/Barcode len frame."""
    for code in codes:
        try:
            text = code.data.decode("utf-8", errors="ignore").strip()
            hop_le = "HAT GIONG" in text or "GAO" in text
            mau = (0, 255, 0) if hop_le else (0, 0, 255)

            pts = code.polygon
            if len(pts) >= 3:
                diem = np.array(
                    [[int(p.x), int(p.y)] for p in pts], dtype=np.int32
                ).reshape((-1, 1, 2))
                cv2.polylines(frame, [diem], True, mau, 3)
            else:
                r = code.rect
                cv2.rectangle(
                    frame,
                    (int(r.left), int(r.top)),
                    (int(r.left + r.width), int(r.top + r.height)),
                    mau, 3
                )

            r = code.rect
            nhan = f"{code.type}: {text}"
            y_text = int(r.top - 10 if r.top > 25 else r.top + r.height + 25)
            cv2.putText(
                frame, nhan, (int(r.left), y_text),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, mau, 2, cv2.LINE_AA
            )
        except Exception as e:
            print("Loi ve khung QR:", e)
    return frame


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

        self.pos_timer = QTimer(self)
        self.pos_timer.timeout.connect(self.cap_nhat_vi_tri)
        self.pos_timer.start(400)

        self.update_boxes()

    # --------------------------------------------------
    # VI TRI HIEN TAI / CHUAN BI MAY
    # --------------------------------------------------

    def cap_nhat_vi_tri(self):
        if self.qr_lock:
            return
        doc_trang_thai()
        if VI_TRI["x"] is not None:
            k = VI_TRI["loai"]
            self.x_label.setText(f"X ({k}): {VI_TRI['x']:.1f} mm")
            self.y_label.setText(f"Y ({k}): {VI_TRI['y']:.1f} mm")
            self.z_label.setText(f"Z ({k}): {VI_TRI['z']:.1f} mm")

    def chuan_bi_may(self):
        """Go Hold/Alarm nhe truoc khi xuat hang. Tra ve False neu may chua san sang."""
        if CHE_DO_MO_PHONG:
            return True

        if fluidnc is None or not fluidnc.is_open:
            self.status.setText("CHUA KET NOI FLUIDNC")
            return False

        state = doc_trang_thai()
        if state is None:
            self.status.setText("KHONG DOC DUOC TRANG THAI FLUIDNC")
            return False

        if state.startswith("Hold") or state == "Alarm":
            self.status.setText("DANG PHUC HOI MAY...")
            QApplication.processEvents()
            if not phuc_hoi_may():
                self.status.setText("FLUIDNC DANG ALARM - BAM HOME TRUOC")
                return False

        return True

    # --------------------------------------------------
    # RESET TRANG THAI CHU KY
    # --------------------------------------------------

    def reset_chu_ky(self):
        self.cam_bien_da_phat_hien = False
        self.bang_tai_da_dung = False
        self.cho_cam_bien_nha = False
        self.qr_candidate = None
        self.qr_stable_count = 0
        self.loi_chu_ky = False
        self.qr_lock = False

    # --------------------------------------------------
    # CAMERA VA QUET QR
    # --------------------------------------------------

    def camera_update(self):
        ret, frame = self.camera.read()
        if not ret:
            return

        # Quet QR/Barcode tren moi frame (de ve khung + xu ly logic)
        codes = decode(
            frame,
            symbols=[ZBarSymbol.QRCODE, ZBarSymbol.CODE128],
        )

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
                                        "KHONG CAT DUOC HANG - LAY HANG RA DE TU PHUC HOI"
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
                    # Chu ky binh thuong: da cat xong, hang roi khoi cam bien
                    if dieu_khien_bang_tai(True):
                        self.reset_chu_ky()
                        self.status.setText(
                            "CAM BIEN DA NHA - BANG TAI CHAY LAI"
                        )
                    else:
                        self.loi_chu_ky = True
                        self.running = False
                        self.status.setText(
                            "LOI: ARDUINO CHUA XAC NHAN START"
                        )
                else:
                    # Chu ky loi / cam bien nha som: TU PHUC HOI, khong can HOME
                    self.status.setText(
                        "HANG DA RA KHOI CAM BIEN - DANG TU PHUC HOI"
                    )
                    QApplication.processEvents()

                    if phuc_hoi_may() and dieu_khien_bang_tai(True):
                        self.reset_chu_ky()
                        self.status.setText(
                            "DA PHUC HOI - BANG TAI CHAY LAI, CHO HANG MOI"
                        )
                    else:
                        self.running = False
                        self.status.setText(
                            "TU PHUC HOI THAT BAI - BAM HOME"
                        )

        # Ve khung QR len hinh (truoc khi doi sang RGB)
        ve_qr_len_frame(frame, codes)

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

        if not self.chuan_bi_may():
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
        if not self.chuan_bi_may():
            return
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

        if not any(o["trang_thai"] for o in KHO.values()):
            self.status.setText("KHO TRONG - KHONG CO HANG DE XUAT")
            return

        if not self.chuan_bi_may():
            return

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
        """Chi ve HOME va dung yen. Co hang moi nhan_hang() se tu ra tram gap."""
        self.running = False
        self.reset_chu_ky()
        self.status.setText("DANG HOME")
        QApplication.processEvents()

        if home():
            if send_gcode(SERVO_MO):
                self.status.setText(
                    "DA HOME - BAM START, CO HANG MOI CHAY RA TRAM GAP"
                )
            else:
                self.status.setText("HOME XONG NHUNG MO SERVO LOI")
        else:
            self.status.setText("HOME THAT BAI")

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

        state = doc_trang_thai()
        if state is not None and (state.startswith("Hold") or state == "Alarm"):
            self.status.setText("DANG PHUC HOI MAY...")
            QApplication.processEvents()
            if not phuc_hoi_may():
                self.status.setText("FLUIDNC DANG ALARM - BAM HOME TRUOC")
                return

        if not dieu_khien_bang_tai(True):
            self.status.setText("ARDUINO KHONG XAC NHAN START")
            return

        self.reset_chu_ky()
        self.running = True
        self.status.setText("DANG CHAY - CHO CAM BIEN")
        print("START")

    def stop(self):
        self.running = False
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

        self.reset_chu_ky()

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
        if hasattr(self, "pos_timer"):
            self.pos_timer.stop()

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
    tao_file_excel()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())