from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W,     _MIN_H     = 820, 580
_LEFT_W  = 148
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#080000"
    PANEL     = "#0f0000"
    PANEL2    = "#120000"
    BORDER    = "#3d0a0a"
    BORDER_B  = "#7a1a1a"
    BORDER_A  = "#601010"
    PRI       = "#ff2200"
    PRI_DIM   = "#991500"
    PRI_GHO   = "#1f0000"
    ACC       = "#ff6600"
    ACC2      = "#ffaa00"
    GREEN     = "#ff4400"
    GREEN_D   = "#cc2200"
    RED       = "#ff0033"
    MUTED_C   = "#ff0044"
    TEXT      = "#ff9988"
    TEXT_DIM  = "#8a3a3a"
    TEXT_MED  = "#cc5544"
    WHITE     = "#ffe8e0"
    DARK      = "#060000"
    BAR_BG    = "#100000"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

# ── Temas de color — KITT puede cambiar entre 3 paletas ──────────────────
THEMES = {
    "rojo": {
        "BG":"#050508","PANEL":"#0a0a0f","PANEL2":"#0d0d14",
        "BORDER":"#3d0a0a","BORDER_B":"#7a1a1a","BORDER_A":"#601010",
        "PRI":"#ff2200","PRI_DIM":"#991500","PRI_GHO":"#1a0000",
        "ACC":"#ff6600","ACC2":"#ffaa00","GREEN":"#00ff88","GREEN_D":"#00cc55",
        "RED":"#ff0033","MUTED_C":"#ff0044","TEXT":"#ff9988",
        "TEXT_DIM":"#666680","TEXT_MED":"#cc5544","WHITE":"#ffe8e0",
        "DARK":"#030306","BAR_BG":"#0a0a12",
    },
    "azul": {
        "BG":"#050508","PANEL":"#080812","PANEL2":"#0a0a16",
        "BORDER":"#0a3a55","BORDER_B":"#1a6a8a","BORDER_A":"#0f4a70",
        "PRI":"#00eeff","PRI_DIM":"#0099bb","PRI_GHO":"#001830",
        "ACC":"#ff8800","ACC2":"#ffdd00","GREEN":"#00ffaa","GREEN_D":"#00cc66",
        "RED":"#ff3355","MUTED_C":"#ff3366","TEXT":"#aaffff",
        "TEXT_DIM":"#4a6a7a","TEXT_MED":"#66ccdd","WHITE":"#e0ffff",
        "DARK":"#030306","BAR_BG":"#08080f",
    },
    "verde": {
        "BG":"#050508","PANEL":"#080a08","PANEL2":"#0a0c0a",
        "BORDER":"#0a4a0a","BORDER_B":"#1a8a1a","BORDER_A":"#106010",
        "PRI":"#00ff55","PRI_DIM":"#00bb33","PRI_GHO":"#001800",
        "ACC":"#bbff00","ACC2":"#ffee00","GREEN":"#00ffbb","GREEN_D":"#00dd66",
        "RED":"#ff3355","MUTED_C":"#ff0044","TEXT":"#99ffaa",
        "TEXT_DIM":"#446644","TEXT_MED":"#55dd66","WHITE":"#e0ffe8",
        "DARK":"#030306","BAR_BG":"#080a08",
    },
}
_CURRENT_THEME = "rojo"

def apply_theme(name: str):
    global _CURRENT_THEME
    _CURRENT_THEME = name
    t = THEMES[name]
    for k, v in t.items():
        setattr(C, k, v)

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # NVIDIA
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        # AMD (Linux)
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            # Intel GPU (Linux)
            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        # macOS — powermetrics (GPU Engine)
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class WaveCanvas(QWidget):
    """
    Onda de voz estilo KITT — múltiples sinusoides cruzadas con brillo intenso.
    Efecto igual a la imagen de referencia: ondas densas que se cruzan en el centro.
    Autor: PERCI OLID TERAN CABANILLAS
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumHeight(90)
        self.setMaximumHeight(120)
        # Múltiples fases independientes para ondas que se cruzan
        self._phases     = [0.0] * 8
        self._amplitude  = 0.12
        self._tgt_amp    = 0.12
        self._speaking   = False
        self._listening  = False
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(28)  # ~35fps — fluido sin quemar CPU

    def set_state(self, speaking: bool, listening: bool):
        self._speaking  = speaking
        self._listening = listening
        if speaking:
            self._tgt_amp = random.uniform(0.65, 0.92)
        elif listening:
            self._tgt_amp = random.uniform(0.22, 0.40)
        else:
            self._tgt_amp = 0.10

    def _step(self):
        # Cada onda tiene su propia velocidad para que se crucen naturalmente
        speeds = [0.14, 0.19, 0.11, 0.23, 0.16, 0.09, 0.21, 0.13]
        for i in range(8):
            self._phases[i] += speeds[i] * (1.6 if self._speaking else 0.7)
        self._amplitude += (self._tgt_amp - self._amplitude) * 0.12
        if self._speaking:
            self._tgt_amp = random.uniform(0.58, 0.95)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(5, 5, 8))

        W, H  = self.width(), self.height()
        cy    = H / 2
        amp   = self._amplitude * (H * 0.46)
        pts   = 280
        dx    = W / pts

        # ── Binario de fondo muy tenue ─────────────────────────────────────
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.PRI, 22)))
        for cx in range(0, W, 18):
            for ry in range(0, H, 14):
                p.drawText(cx, ry, random.choice("10"))

        # ── 8 ondas independientes que se cruzan — efecto imagen KITT ──────
        # Configuración: (frecuencia, fase_idx, grosor, alpha, fracción amplitud)
        # Colores dinámicos según tema activo
        if _CURRENT_THEME == "azul":
            wave_colors = ["#00ffff","#0088ff","#aa44ff","#00ccff","#0044ff","#ff44ff","#00ffff","#0066ff"]
        elif _CURRENT_THEME == "verde":
            wave_colors = ["#00ff88","#00ffaa","#44ff44","#00cc66","#88ff00","#00ff66","#00ff44","#44ffaa"]
        else:  # rojo
            wave_colors = ["#ff2200","#ff4400","#ff6600","#ff1100","#ff3300","#ff5500","#ff2200","#ff4400"]

        wave_configs = [
            (0.055, 0, 2.8, 240, 1.00),
            (0.055, 1, 2.8, 240, 1.00),
            (0.055, 2, 2.0, 180, 0.92),
            (0.055, 3, 2.0, 180, 0.92),
            (0.055, 4, 1.4, 100, 0.82),
            (0.055, 5, 1.4, 100, 0.82),
            (0.055, 6, 0.9,  50, 0.70),
            (0.055, 7, 0.9,  50, 0.70),
        ]

        for idx2, (freq, ph_idx, stroke, alpha, amp_frac) in enumerate(wave_configs):
            ph  = self._phases[ph_idx]
            a   = amp * amp_frac
            hex_c = wave_colors[idx2 % len(wave_colors)]

            pen = QPen(qcol(hex_c, alpha), stroke)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)

            path  = QPainterPath()
            first = True
            for i in range(pts + 1):
                x = i * dx
                t   = (i / pts - 0.5) * 2
                env = math.exp(-t * t * 1.4)
                y   = cy - a * env * math.sin(ph + i * freq)
                if first:
                    path.moveTo(x, y); first = False
                else:
                    path.lineTo(x, y)
            p.drawPath(path)

        # ── Línea central brillante (el "eje" de la onda) ──────────────────
        cpen = QPen(qcol(C.PRI, 60), 1)
        p.setPen(cpen)
        p.drawLine(QPointF(0, cy), QPointF(W, cy))

        # ── Punto central brillante ────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcol(C.PRI, 200))
        p.drawEllipse(QPointF(W/2, cy), 3, 3)
        p.setBrush(qcol(C.PRI, 60))
        p.drawEllipse(QPointF(W/2, cy), 7, 7)


class BinaryRain(QWidget):
    """
    Lluvia de código binario de fondo — efecto Matrix/KITT.
    Autor: PERCI OLID TERAN CABANILLAS
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._cols   = []
        self._tmr    = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(120)  # lento para no consumir CPU
        self._font   = QFont("Courier New", 9)

    def _init_cols(self):
        W = self.width()
        col_w = 14
        n = max(1, W // col_w)
        self._cols = [
            {"x": i * col_w, "y": random.randint(-200, 0), "speed": random.randint(1, 3)}
            for i in range(n)
        ]

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._init_cols()

    def _step(self):
        H = self.height()
        for col in self._cols:
            col["y"] += col["speed"] * 10
            if col["y"] > H + 40:
                col["y"] = random.randint(-100, -10)
                col["speed"] = random.randint(1, 3)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        # Fondo negro puro galáctico
        p.fillRect(self.rect(), QColor(5, 5, 8))
        p.setFont(self._font)
        for col in self._cols:
            for j in range(7):
                y = col["y"] - j * 14
                if y < 0 or y > self.height():
                    continue
                alpha = max(30, 160 - j * 22)
                p.setPen(QPen(qcol(C.PRI, alpha)))
                p.drawText(int(col["x"]), int(y), random.choice("10"))


class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        self._load_face(face_path)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()
        if now - self._last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.14)
                self._tgt_halo  = random.uniform(145, 190)
            elif self.muted:
                self._tgt_scale = random.uniform(0.998, 1.002)
                self._tgt_halo  = random.uniform(15, 28)
            else:
                self._tgt_scale = random.uniform(1.001, 1.008)
                self._tgt_halo  = random.uniform(48, 68)
            self._last_t = now

        sp = 0.38 if self.speaking else 0.15
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        speeds = [1.3, -0.9, 2.0] if self.speaking else [0.55, -0.35, 0.9]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 4.2 if self.speaking else 2.0
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        if len(self._pulses) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            self._pulses.append(0.0)

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.9, 2.4),
                math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # grid dots
        p.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                p.drawPoint(x, y)

        r_face = fw * 0.31

        # halo glow
        for i in range(10):
            r   = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 10
            a   = max(0, min(255, int(self._halo * 0.085 * frc)))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # pulse rings
        for pr in self._pulses:
            a   = max(0, int(230 * (1.0 - pr / (fw * 0.74))))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # spinning arc rings
        for idx, (r_frac, w_r, arc_l, gap) in enumerate(
            [(0.48, 3, 115, 78), (0.40, 2, 78, 55), (0.32, 1, 56, 40)]
        ):
            ring_r = fw * r_frac
            base   = self._rings[idx]
            a_val  = max(0, min(255, int(self._halo * (1.0 - idx * 0.18))))
            col    = qcol(C.MUTED_C if self.muted else C.PRI, a_val)
            p.setPen(QPen(col, w_r)); p.setBrush(Qt.BrushStyle.NoBrush)
            angle = base
            rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap

        # scanners
        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.5))
        ex = 75 if self.speaking else 44
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, sa), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))

        # tick marks
        t_out, t_in = fw * 0.497, fw * 0.474
        p.setPen(QPen(qcol(C.PRI, 140), 1))
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        # crosshair
        ch_r, gap_h = fw * 0.51, fw * 0.16
        p.setPen(QPen(qcol(C.PRI, int(self._halo * 0.5)), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        # corner brackets
        bl = 24
        bc = qcol(C.PRI, 210)
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(bc, 2))
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        # face
        if self._face_px:
            fsz    = int(fw * 0.62 * self._scale)
            scaled = self._face_px.scaled(
                fsz, fsz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(int(cx - fsz / 2), int(cy - fsz / 2), scaled)
        else:
            orb_r = int(fw * 0.27 * self._scale)
            oc    = (80, 0, 0) if self.muted else (180, 20, 0)
            for i in range(8, 0, -1):
                r2  = int(orb_r * i / 8)
                frc = i / 8
                a   = max(0, min(255, int(self._halo * 1.1 * frc)))
                p.setBrush(QBrush(QColor(int(oc[0]*frc), int(oc[1]*frc), int(oc[2]*frc), a)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2))
            p.setPen(QPen(qcol(C.PRI, min(255, int(self._halo * 2))), 1))
            p.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
            p.drawText(QRectF(cx - 80, cy - 14, 160, 28),
                       Qt.AlignmentFlag.AlignCenter, "K.I.T.T")

        # particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        # status text
        sy = cy + fw * 0.40
        if self.muted:
            txt, col = "⊘  MUTED",     qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "●  SPEAKING",  qcol(C.ACC)
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  THINKING",   qcol(C.ACC2)
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  PROCESSING", qcol(C.ACC2)
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  LISTENING",  qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {self.state}", qcol(C.PRI)

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        # waveform
        wy = sy + 30
        N, bw = 36, 8
        wx0 = (W - N * bw) / 2
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            elif self.speaking:
                hgt = random.randint(3, 20)
                cl  = qcol(C.PRI) if hgt > 12 else qcol(C.PRI_DIM)
            else:
                hgt = int(3 + 2 * math.sin(self._tick * 0.09 + i * 0.6))
                cl  = qcol(C.BORDER_B)
            p.fillRect(QRectF(wx0 + i * bw, wy + 20 - hgt, bw - 1, hgt), cl)

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h   = 4
        bar_y   = H - bar_h - 5
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        # Normalizar nombres en el chat
        if text.startswith("You:"):
            text = "Tú:" + text[4:]
        elif text.startswith("you:"):
            text = "tú:" + text[4:]
        if text.startswith("Mark:"):
            text = "KITT:" + text[5:]
        elif text.startswith("mark:"):
            text = "KITT:" + text[5:]
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:") or tl.startswith("tú:"):   self._tag = "you"
        elif tl.startswith("kitt:") or tl.startswith("mark:"): self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif "err" in tl:              self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo para KITT", str(Path.home()),
            "Todos los archivos (*.*);;"
            "Imágenes (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documentos (*.pdf *.docx *.txt *.md *.pptx);;"
            "Datos (*.csv *.xlsx *.json *.xml);;"
            "Código (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archivos comprimidos (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2 - 10
        col  = qcol(C.PRI if hover else C.PRI_DIM)
        glow = qcol(C.PRI, 100 if hover else 50)

        # Glow exterior grande
        p.setPen(QPen(glow, 6)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 18), QPointF(cx, cy + 8))
        p.drawLine(QPointF(cx - 12, cy - 6), QPointF(cx, cy - 18))
        p.drawLine(QPointF(cx + 12, cy - 6), QPointF(cx, cy - 18))
        p.drawLine(QPointF(cx - 18, cy + 8), QPointF(cx + 18, cy + 8))
        # Línea principal
        p.setPen(QPen(col, 2))
        p.drawLine(QPointF(cx, cy - 18), QPointF(cx, cy + 8))
        p.drawLine(QPointF(cx - 12, cy - 6), QPointF(cx, cy - 18))
        p.drawLine(QPointF(cx + 12, cy - 6), QPointF(cx, cy - 18))
        p.drawLine(QPointF(cx - 18, cy + 8), QPointF(cx + 18, cy + 8))

        # Texto principal
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(4, cy + 12, W-8, 20),
                   Qt.AlignmentFlag.AlignCenter,
                   "Arrastra archivo  ◈  Clic para buscar")

        # Texto secundario
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_MED, 210), 1))
        p.drawText(QRectF(4, cy + 32, W-8, 16),
                   Qt.AlignmentFlag.AlignCenter,
                   "Imagen · Video · Audio · PDF · Doc · Código")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Suelta para cargar")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure K.I.T.T. before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 3px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d12; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)





class MetricBar(QWidget):
    """Barra de métrica futurista — cambia color según el tema activo."""
    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self._label_txt = label
        self._base_color = color
        self.setFixedHeight(36)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(2)

        top = QHBoxLayout()
        self._lbl = QLabel(label)
        self._lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        self._val = QLabel("--")
        self._val.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self._val.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        self._val.setAlignment(Qt.AlignmentFlag.AlignRight)
        top.addWidget(self._lbl); top.addStretch(); top.addWidget(self._val)
        lay.addLayout(top)

        self._bar = QProgressBar()
        self._bar.setFixedHeight(6)
        self._bar.setTextVisible(False)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ background: {C.BAR_BG}; border-radius: 3px; border: none; }}
            QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}
        """)
        lay.addWidget(self._bar)

    def set_value(self, pct: float, text: str):
        self._bar.setValue(int(max(0, min(100, pct))))
        self._val.setText(text)
        # Color dinámico según nivel Y tema actual
        if pct > 85:
            col = C.RED
        elif pct > 60:
            col = C.ACC
        else:
            col = C.PRI  # siempre toma el color del tema actual
        self._val.setStyleSheet(
            f"color: {col}; background: transparent; border: none;"
        )
        self._lbl.setStyleSheet(
            f"color: {C.TEXT_MED}; background: transparent; border: none;"
        )
        self._bar.setStyleSheet(
            f"QProgressBar {{ background: {C.BAR_BG}; border-radius: 3px; border: none; }}"
            f"QProgressBar::chunk {{ background: {col}; border-radius: 3px; }}"
        )

class MiniWaveBar(QWidget):
    """
    Onda de voz 3D multicapa — estilo imagen KITT futurista.
    Múltiples ondas superpuestas con colores cyan/azul/púrpura brillantes.
    Autor: PERCI OLID TERAN CABANILLAS
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self._active  = False
        self._phases  = [0.0] * 6
        self._amps    = [0.08] * 6
        self._tgt_amps= [0.08] * 6
        self._tmr     = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(30)

    def set_active(self, active: bool):
        self._active = active
        if active:
            for i in range(6):
                self._tgt_amps[i] = random.uniform(0.45, 0.92)
        else:
            for i in range(6):
                self._tgt_amps[i] = random.uniform(0.04, 0.12)

    def _step(self):
        speeds = [0.18, 0.13, 0.22, 0.09, 0.16, 0.25]
        for i in range(6):
            self._phases[i] += speeds[i] * (1.8 if self._active else 0.5)
            self._amps[i] += (self._tgt_amps[i] - self._amps[i]) * 0.10
        if self._active:
            for i in range(6):
                self._tgt_amps[i] = random.uniform(0.35, 0.95)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        cy   = H / 2

        # Fondo oscuro con gradiente
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.0, QColor(5, 5, 8))
        grad.setColorAt(0.5, QColor(8, 8, 14))
        grad.setColorAt(1.0, QColor(5, 5, 8))
        p.fillRect(self.rect(), QBrush(grad))

        # Marco futurista con esquinas
        frame_col = qcol(C.PRI, 80)
        p.setPen(QPen(frame_col, 1))
        p.drawRect(1, 1, W-2, H-2)
        # Esquinas brillantes
        corner = 12
        bright = QPen(qcol(C.PRI, 200), 2)
        p.setPen(bright)
        for cx2, cy2, dx, dy in [(2,2,1,1),(W-2,2,-1,1),(2,H-2,1,-1),(W-2,H-2,-1,-1)]:
            p.drawLine(cx2, cy2, cx2+dx*corner, cy2)
            p.drawLine(cx2, cy2, cx2, cy2+dy*corner)

        pts = 250
        dx  = W / pts

        # 6 capas de onda con colores distintos — efecto 3D imagen 2
        # (color_hex, alpha, grosor, amp_factor, freq_factor)
        layers = [
            ("#00ffff", 240, 2.5, 1.00, 1.0),  # cyan brillante — capa principal
            ("#0088ff", 200, 2.0, 0.90, 1.1),  # azul
            ("#aa44ff", 170, 1.8, 0.80, 0.9),  # púrpura
            ("#00ffff", 100, 1.2, 0.70, 1.2),  # cyan tenue
            ("#0044ff", 80,  1.0, 0.60, 0.8),  # azul oscuro
            ("#ff44ff", 60,  0.8, 0.50, 1.3),  # magenta exterior
        ]

        for li, (hex_col, alpha, stroke, amp_frac, freq_fac) in enumerate(layers):
            ph = self._phases[li]
            a  = self._amps[li] * amp_frac * (H * 0.44)

            # Gradiente horizontal sobre la onda
            pen = QPen(qcol(hex_col, alpha), stroke)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)

            path  = QPainterPath()
            first = True
            for i in range(pts + 1):
                x   = i * dx
                # Envolvente gaussiana — más alto en centro como imagen
                t   = (i / pts - 0.5) * 2
                env = math.exp(-t * t * 1.2)
                y   = cy - a * env * math.sin(ph + i * 0.055 * freq_fac)
                if first:
                    path.moveTo(x, y); first = False
                else:
                    path.lineTo(x, y)
            p.drawPath(path)

        # Glow central — punto de intersección brillante
        p.setPen(Qt.PenStyle.NoPen)
        for r, a in [(18, 15), (10, 40), (5, 120), (2, 255)]:
            p.setBrush(qcol("#00ffff", a))
            p.drawEllipse(QPointF(W/2, cy), r, r)

        # Línea central tenue
        p.setPen(QPen(qcol("#00ffff", 25), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(0, cy), QPointF(W, cy))

class MainWindow(QMainWindow):
    _log_sig   = pyqtSignal(str)
    _state_sig = pyqtSignal(str)

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("K.I.T.T — SISTEMA DE IA AVANZADA  |  by PERCI OLID TERAN CABANILLAS")
        self.setMinimumSize(1000, 700)
        self.resize(1280, 800)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move((screen.width()-1280)//2, (screen.height()-800)//2)

        self.on_text_command = None
        self._muted          = False
        self._current_file: str | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(0)

        # ── ZONA 1: KITT nombre grande + binario de fondo ─────────────────
        root.addWidget(self._build_title_zone())

        # ── ZONA 2: Onda de voz grande central ────────────────────────────
        self._wave = WaveCanvas()
        self._wave.setFixedHeight(170)
        root.addWidget(self._wave)

        # ── ZONA 3: AUTOR debajo de la onda ──────────────────────────────
        autor_w = QWidget()
        autor_w.setFixedHeight(28)
        autor_w.setStyleSheet(f"background: {C.BG};")
        autor_lay = QHBoxLayout(autor_w)
        autor_lay.setContentsMargins(0,0,0,0)
        self._autor_lbl = QLabel("AUTOR:  PERCI OLID TERAN CABANILLAS")
        self._autor_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._autor_lbl.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self._autor_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 3px;")
        autor_lay.addWidget(self._autor_lbl)
        root.addWidget(autor_w)

        # ── ZONA 4: 4 paneles inferiores ─────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setContentsMargins(4,4,4,4)
        bottom.setSpacing(4)
        # Inicializar listas ANTES de construir paneles (los paneles las usan)
        self._panel_headers = []
        self._badges        = []

        self._left_panel     = self._build_panel_calidad()
        self._panel_voz      = self._build_panel_voz()
        self._panel_recursos = self._build_panel_recursos()
        self._right_panel    = self._build_panel_derecho()
        bottom.addWidget(self._left_panel,     stretch=1)
        bottom.addWidget(self._panel_voz,      stretch=1)
        bottom.addWidget(self._panel_recursos, stretch=1)
        bottom.addWidget(self._right_panel,    stretch=1)
        root.addLayout(bottom, stretch=1)
        # Referencias ya inicializadas arriba — solo consolidar
        self._all_bars = [self._bar_cpu, self._bar_mem, self._bar_net,
                          self._bar_gpu, self._bar_tmp]

        # ── FOOTER ────────────────────────────────────────────────────────
        root.addWidget(self._build_footer())

        # Timers
        self._clock_tmr = QTimer(self); self._clock_tmr.timeout.connect(self._tick_clock); self._clock_tmr.start(1000); self._tick_clock()
        self._metric_tmr = QTimer(self); self._metric_tmr.timeout.connect(self._update_metrics); self._metric_tmr.start(3000); self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)

        # HUD oculto — solo para compatibilidad con main.py
        self.hud = HudCanvas(face_path)
        self.hud.hide()

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

    # ── ZONA TÍTULO ────────────────────────────────────────────────────────
    def _build_title_zone(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(130)
        w.setStyleSheet("background: #050508;")

        # BinaryRain de fondo
        self._rain = BinaryRain(w)
        self._rain.setGeometry(0, 0, 2000, 130)

        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 4)
        lay.setSpacing(2)

        # Mini barra superior
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(12, 0, 12, 0)

        # Izquierda: CREADOR + colores
        left_col = QVBoxLayout(); left_col.setSpacing(1)
        cr_lbl = QLabel("K.I.T.T  ·  IA")
        cr_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        cr_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        left_col.addWidget(cr_lbl)

        # Botones de color
        color_row = QHBoxLayout(); color_row.setSpacing(5)
        cl = QLabel("COLOR:")
        cl.setFont(QFont("Courier New", 7))
        cl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        color_row.addWidget(cl)
        for tname, tcol in [("rojo","#ff2200"),("azul","#00d4ff"),("verde","#00ff44")]:
            btn = QPushButton("●")
            btn.setFixedSize(20, 20)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"color:{tcol};background:transparent;border:1px solid {tcol};border-radius:10px;")
            btn.clicked.connect(lambda _, n=tname: self._change_theme(n))
            color_row.addWidget(btn)
        color_row.addStretch()
        left_col.addLayout(color_row)
        top_bar.addLayout(left_col)
        top_bar.addStretch()

        # Centro: KITT enorme
        self._kitt_lbl = QLabel("KITT")
        self._kitt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._kitt_lbl.setFont(QFont("Courier New", 56, QFont.Weight.Bold))
        self._kitt_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 12px;")
        top_bar.addWidget(self._kitt_lbl)
        top_bar.addStretch()

        # Derecha: reloj
        right_col = QVBoxLayout(); right_col.setSpacing(1)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 20, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 8))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        right_col.addStretch()
        top_bar.addLayout(right_col)
        lay.addLayout(top_bar)
        return w

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_rain'):
            self._rain.setGeometry(0, 0, self.width(), 130)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 560, 660
            cw = self.centralWidget()
            self._overlay.setGeometry((cw.width()-ow)//2, (cw.height()-oh)//2, ow, oh)

    # ── PANEL IZQUIERDO 1: Calidad de datos / SYS MONITOR ─────────────────
    def _build_panel_calidad(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {C.PANEL}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        lay = QVBoxLayout(w); lay.setContentsMargins(10,10,10,10); lay.setSpacing(6)

        # Header futurista
        hdr_row = QHBoxLayout()
        dot = QLabel("◈"); dot.setFont(QFont("Courier New", 10))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        hdr = QLabel("MONITOR DEL SISTEMA")
        hdr.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none; letter-spacing: 2px;")
        hdr_row.addWidget(dot); hdr_row.addWidget(hdr); hdr_row.addStretch()
        lay.addLayout(hdr_row)
        self._panel_headers.append(hdr)
        self._panel_headers.append(dot)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = MetricBar("NET", C.ACC)
        self._bar_gpu = MetricBar("GPU", C.PRI_DIM)
        self._bar_tmp = MetricBar("TMP", C.PRI_DIM)
        for bar in [self._bar_cpu, self._bar_mem, self._bar_net, self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        # Caja de info del sistema — estilo HUD
        info = QWidget()
        info.setStyleSheet(f"background: {C.PANEL2}; border: 1px solid {C.BORDER_B}; border-radius: 4px;")
        il = QVBoxLayout(info); il.setContentsMargins(10,6,10,6); il.setSpacing(3)
        self._uptime_lbl = QLabel("▸  UP   --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        self._proc_lbl = QLabel("▸  PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        os_name = {"Windows":"WIN","Darwin":"macOS","Linux":"LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"▸  OS    {os_name}")
        os_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        il.addWidget(self._uptime_lbl); il.addWidget(self._proc_lbl); il.addWidget(os_lbl)
        lay.addWidget(info)
        lay.addStretch()

        # Badges de estado futuristas
        badges = [
            ("IA NUCLEO ACTIVO",   "PRI"),
            ("SEGURIDAD LIMPIA",   "GREEN"),
            ("ESTADO OPERATIVO",   "ACC2"),
        ]
        for txt, key_col in badges:
            col = getattr(C, key_col)
            lbl = QLabel(f"⬡  {txt}")
            lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color:{col};background:{C.PANEL2};"
                f"border:1px solid {col};border-radius:3px;padding:4px;letter-spacing:1px;"
            )
            lay.addWidget(lbl)
            self._badges.append(lbl)
        return w

    # ── PANEL 2: Reconocimiento de voz / KITT Waveform ─────────────────────
    def _build_panel_voz(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {C.PANEL}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        lay = QVBoxLayout(w); lay.setContentsMargins(8,8,8,8); lay.setSpacing(5)

        # Header con puntos de esquina estilo futurista
        hdr_row = QHBoxLayout(); hdr_row.setSpacing(6)
        dot = QLabel("◉"); dot.setFont(QFont("Courier New", 9))
        dot.setStyleSheet(f"color: {C.ACC}; background: transparent; border: none;")
        hdr_row.addWidget(dot)
        hdr = QLabel("RECONOCIMIENTO DE VOZ")
        hdr.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none; letter-spacing: 2px;")
        hdr_row.addWidget(hdr); hdr_row.addStretch()
        lay.addLayout(hdr_row)
        self._panel_headers.append(hdr)

        # Mini waveform 3D
        self._mini_wave = MiniWaveBar()
        self._mini_wave.setMinimumHeight(110)
        lay.addWidget(self._mini_wave, stretch=1)

        # Estado con estilo más futurista
        state_box = QWidget()
        state_box.setStyleSheet(f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        state_inner = QHBoxLayout(state_box); state_inner.setContentsMargins(8,4,8,4)
        self._state_dot = QLabel("◉")
        self._state_dot.setFont(QFont("Courier New", 10))
        self._state_dot.setStyleSheet(f"color: {C.ACC}; background: transparent; border: none;")
        self._state_lbl = QLabel("EN ESCUCHA")
        self._state_lbl.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self._state_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none; letter-spacing: 4px;")
        state_inner.addStretch()
        state_inner.addWidget(self._state_dot)
        state_inner.addWidget(self._state_lbl)
        state_inner.addStretch()
        lay.addWidget(state_box)

        # Log de conversación
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=2)
        return w

    # ── PANEL 3: Recursos del sistema ─────────────────────────────────────
    def _build_panel_recursos(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {C.PANEL}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        lay = QVBoxLayout(w); lay.setContentsMargins(8,8,8,8); lay.setSpacing(5)

        hdr = QLabel("◈  RECURSOS DEL SISTEMA")
        hdr.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        lay.addWidget(hdr)

        self._res_boxes  = []
        self._res_icons  = []
        self._res_labels = []

        def _res_row(icon_txt, label, val_attr):
            box = QWidget()
            box.setStyleSheet(f"background:{C.PANEL2};border:1px solid {C.BORDER};border-radius:4px;")
            row = QHBoxLayout(box); row.setContentsMargins(8,6,8,6); row.setSpacing(10)

            ic_box = QWidget()
            ic_box.setFixedSize(32, 32)
            ic_box.setStyleSheet(f"background:{C.PRI_GHO};border:1px solid {C.PRI};border-radius:4px;")
            ic_lay = QHBoxLayout(ic_box); ic_lay.setContentsMargins(0,0,0,0)
            ic = QLabel(icon_txt)
            ic.setFont(QFont("Courier New", 14))
            ic.setStyleSheet(f"color:{C.PRI};background:transparent;border:none;")
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic_lay.addWidget(ic)

            col = QVBoxLayout(); col.setSpacing(2)
            lbl = QLabel(label)
            lbl.setFont(QFont("Courier New", 8))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;border:none;")
            val = QLabel("--")
            val.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
            val.setStyleSheet(f"color:{C.PRI};background:transparent;border:none;")
            setattr(self, val_attr, val)
            col.addWidget(lbl); col.addWidget(val)
            row.addWidget(ic_box); row.addLayout(col); row.addStretch()

            self._res_boxes.append(box)
            self._res_icons.append((ic_box, ic))
            self._res_labels.append(lbl)
            return box

        lay.addWidget(_res_row("◈", "CPU  /  Carga del sistema",  "_res_cpu"))
        lay.addWidget(_res_row("▣", "GPU  /  Uso de GPU",          "_res_gpu"))
        lay.addWidget(_res_row("◉", "RAM  /  Memoria activa",      "_res_ram"))
        lay.addWidget(_res_row("▲", "RED  /  Velocidad de red",    "_res_net"))

        lay.addStretch()

        # Temperatura con estilo mejorado
        tmp_box = QWidget()
        tmp_box.setStyleSheet(f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        tmp_inner = QHBoxLayout(tmp_box); tmp_inner.setContentsMargins(8,5,8,5)
        tmp_ic = QLabel("◌")
        tmp_ic.setFont(QFont("Courier New", 13))
        tmp_ic.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; border: none;")
        tmp_inner.addWidget(tmp_ic)
        tmp_lbl2 = QLabel("TEMPERATURA:")
        tmp_lbl2.setFont(QFont("Courier New", 9))
        tmp_lbl2.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        self._res_tmp = QLabel("--")
        self._res_tmp.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self._res_tmp.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        tmp_inner.addWidget(tmp_lbl2); tmp_inner.addWidget(self._res_tmp); tmp_inner.addStretch()
        lay.addWidget(tmp_box)
        return w

    # ── PANEL 4: FILE UPLOAD + COMANDO + MICRÓFONO ─────────────────────────
    def _build_panel_derecho(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {C.PANEL}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        lay = QVBoxLayout(w); lay.setContentsMargins(6,6,6,6); lay.setSpacing(4)

        def _sec(txt):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none; letter-spacing: 1px;")
            return l

        lay.addWidget(_sec("CARGAR ARCHIVO"))
        self._drop_zone = FileDropZone()
        self._drop_zone.setMinimumHeight(120)
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone, stretch=1)

        self._file_hint = QLabel("Sin archivo cargado — arrastra o haz clic arriba")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet(f"color: {C.BORDER};")
        lay.addWidget(sep)

        lay.addWidget(_sec("◈  ENTRADA DE COMANDOS"))
        lay.addLayout(self._build_input_row())

        self._mute_btn = QPushButton("◉  MICRÓFONO ACTIVO")
        self._mute_btn.setFixedHeight(32)
        self._mute_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        fs_btn = QPushButton("⛶  PANTALLA COMPLETA  [F11]")
        fs_btn.setFixedHeight(24)
        fs_btn.setFont(QFont("Courier New", 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"background:{C.PRI_GHO};color:{C.PRI_DIM};border:1px solid {C.BORDER};border-radius:3px;")
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)
        return w

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Escribe un comando o pregunta...")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"QLineEdit{{background:{C.BG};color:{C.WHITE};border:1px solid {C.BORDER};border-radius:3px;padding:3px 7px;}} QLineEdit:focus{{border:1px solid {C.PRI};}}")
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)
        send = QPushButton("▸")
        send.setFixedSize(30,30)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"QPushButton{{background:{C.PANEL};color:{C.PRI};border:1px solid {C.PRI_DIM};border-radius:3px;}} QPushButton:hover{{background:{C.PRI};color:{C.BG};}}")
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_footer(self) -> QWidget:
        w = QWidget(); w.setFixedHeight(22)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14,0,14,0)
        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l
        lay.addWidget(_fl("[F4] Mute  ·  [F11] Fullscreen"))
        lay.addStretch()
        lay.addWidget(_fl("K.I.T.T  ·  SISTEMA DE IA AVANZADA"))
        lay.addStretch()
        lay.addWidget(_fl("● ROJO  ○ AZUL  ○ VERDE", C.PRI))
        lay.addSpacing(8)
        lay.addWidget(_fl("© PERCI  2025", C.PRI_DIM))
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _change_theme(self, name: str):
        apply_theme(name)
        self.centralWidget().setStyleSheet(f"background: {C.BG};")
        self._log.append_log(f"SYS: 🎨 Tema cambiado a {name.upper()}")
        self.update(); self.repaint()

    def _update_metrics(self):
        snap = _metrics.snapshot()
        cpu = snap["cpu"]; self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")
        mem = snap["mem"]; self._bar_mem.set_value(mem, f"{mem:.0f}%")
        net = snap["net"]
        net_str = f"{net*1024:.0f}KB/s" if net < 1.0 else f"{net:.1f}MB/s"
        self._bar_net.set_value(min(100,net*10), net_str)
        gpu = snap["gpu"]
        self._bar_gpu.set_value(gpu if gpu>=0 else 0, f"{gpu:.0f}%" if gpu>=0 else "N/A")
        tmp = snap["tmp"]
        self._bar_tmp.set_value(min(100,(tmp/100)*100) if tmp>=0 else 0, f"{tmp:.0f}°C" if tmp>=0 else "N/A")

        # Panel recursos — color dinámico con el tema
        self._res_cpu.setText(f"CPU: {cpu:.0f}%")
        self._res_gpu.setText(f"{gpu:.0f}%" if gpu>=0 else "N/A")
        self._res_ram.setText(f"{mem:.0f}%  usado")
        self._res_net.setText(net_str)
        self._res_tmp.setText(f"{tmp:.0f}°C" if tmp>=0 else "N/A")
        # Actualizar color según tema actual
        for lbl in [self._res_cpu, self._res_gpu, self._res_ram, self._res_net, self._res_tmp]:
            lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")

        try:
            elapsed = time.time() - psutil.boot_time()
            h,m = int(elapsed//3600), int((elapsed%3600)//60)
            self._uptime_lbl.setText(f"▸ UP  {h:02d}:{m:02d}")
            self._uptime_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        except: self._uptime_lbl.setText("▸ UP  --:--")
        try:
            self._proc_lbl.setText(f"▸ PROC  {len(psutil.pids())}")
            self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        except: self._proc_lbl.setText("▸ PROC  --")

    def _toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state in ("SPEAKING","TRANSMITIENDO VOZ"))
        if hasattr(self, "_wave"):
            self._wave.set_state(
                speaking  = (state in ("SPEAKING","TRANSMITIENDO VOZ")),
                listening = (state in ("LISTENING","EN ESCUCHA"))
            )
        if hasattr(self, "_mini_wave"):
            self._mini_wave.set_active(state in ("SPEAKING","TRANSMITIENDO VOZ","LISTENING","EN ESCUCHA"))
        estados = {
            "SPEAKING":          ("TRANSMITIENDO VOZ", C.ACC),
            "TRANSMITIENDO VOZ": ("TRANSMITIENDO VOZ", C.ACC),
            "LISTENING":         ("EN ESCUCHA",        C.ACC),
            "EN ESCUCHA":        ("EN ESCUCHA",        C.ACC),
            "THINKING":          ("PROCESANDO...",     C.ACC2),
            "PROCESSING":        ("EJECUTANDO",        C.ACC2),
            "MUTED":             ("SILENCIADO",        C.MUTED_C),
        }
        if hasattr(self, "_state_lbl"):
            txt, col = estados.get(state, (state, C.PRI))
            self._state_lbl.setText(txt)
            self._state_lbl.setStyleSheet(
                f"color: {col}; background: transparent; border: none; letter-spacing: 4px;"
            )
        if hasattr(self, "_state_dot"):
            _, col = estados.get(state, (state, C.PRI))
            self._state_dot.setStyleSheet(
                f"color: {col}; background: transparent; border: none;"
            )

    def set_tool_active(self, tool_name: str):
        icons = {"web_search":"🌐","file_controller":"📁","office_controller":"📊",
                 "screen_process":"👁","computer_control":"🖱","code_helper":"💻"}
        icon = icons.get(tool_name,"⚙")
        self._state_sig.emit("PROCESANDO")
        self.write_log(f"SYS: {icon} {tool_name.upper().replace('_',' ')}")

    def write_log(self, text: str):
        self._log_sig.emit(text)

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        self._apply_state("MUTED" if self._muted else "LISTENING")
        self._log_sig.emit("SYS: ⊘ Micrófono silenciado." if self._muted else "SYS: ◉ Micrófono activo.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("⊘  MICRÓFONO SILENCIADO")
            self._mute_btn.setStyleSheet(f"background:{C.PANEL};color:{C.MUTED_C};border:1px solid {C.MUTED_C};border-radius:3px;")
        else:
            self._mute_btn.setText("◉  MICRÓFONO ACTIVO")
            self._mute_btn.setStyleSheet(f"background:{C.PRI_GHO};color:{C.PRI};border:1px solid {C.PRI};border-radius:3px;")

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log_sig.emit(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _on_file_selected(self, path: str):
        self._current_file = path
        p   = Path(path)
        cat = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Dile a KITT qué hacer con él")
        self._log_sig.emit(f"FILE: {p.name} ({size}) cargado")
        if self.on_text_command:
            msg = (f"[FILE_UPLOADED] path={path} | name={p.name} | "
                   f"type={p.suffix.lstrip('.')} | size={size} | "
                   f"Dile al usuario que ya puedes ver '{p.name}' ({size}) y pregúntale qué quiere hacer.")
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _check_config(self) -> bool:
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key","").strip())
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow = min(560, cw.width()-40); oh = min(660, cw.height()-40)
        ov.setGeometry((cw.width()-ow)//2, (cw.height()-oh)//2, ow, oh)
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        API_FILE.write_text(json.dumps({"gemini_api_key":key,"os_system":os_name,"camera_index":0},indent=4),encoding="utf-8")
        self._ready = True
        if self._overlay:
            self._overlay.hide(); self._overlay.deleteLater(); self._overlay = None
        self._log_sig.emit(f"SYS: Configuración completada. OS={os_name.upper()}.")
        self._log_sig.emit("SYS: ◉ K.I.T.T  INICIADO — Sistema listo.")



class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class JarvisUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")
