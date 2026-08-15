"""
sound_detector.py — Detector inteligente de sonidos del entorno
Si no puede identificar el sonido con certeza, pregunta al usuario.

Autor: PERCI OLID TERAN CABANILLAS
KITT — KITT
"""

import numpy as np
import threading
import time
from collections import deque


class SoundDetector:
    """
    Analiza el audio del micrófono en tiempo real.
    
    IMPORTANTE: Solo notifica cuando está SEGURO del tipo de sonido.
    Si detecta algo pero no puede clasificarlo, pregunta al usuario.
    Si hay silencio o voz normal, NO interrumpe.
    """

    # ── Umbrales de energía ────────────────────────────────────────────────
    SILENCE_THRESHOLD  = 0.003   # Por debajo = silencio total
    VOICE_THRESHOLD    = 0.012   # Energía típica de voz hablando
    SOUND_MIN_ENERGY   = 0.035   # Mínimo para considerar que "pasó algo"
    CLAP_ENERGY        = 0.075   # Aplauso individual bien fuerte
    LOUD_IMPACT        = 0.12    # Golpe / impacto fuerte

    # ── Cooldowns entre notificaciones (segundos) ─────────────────────────
    COOLDOWN = {
        "aplausos":  15,
        "tos":        8,
        "silbido":   10,
        "golpe":      8,
        "desconocido": 20,   # Pregunta "¿qué fue ese sonido?"
    }

    def __init__(self, sample_rate=16000, callback=None):
        self._sr         = sample_rate
        self._callback   = callback
        self._buffer     = deque(maxlen=sample_rate * 2)  # 2 segundos
        self._lock       = threading.Lock()
        self._running    = False
        self._thread     = None
        self._last_notif = {}

        # Historial de energía para detectar cambios bruscos
        self._energy_history = deque(maxlen=40)

    # ── API pública ────────────────────────────────────────────────────────

    def feed(self, pcm_bytes: bytes):
        """Alimentar con PCM int16 del micrófono."""
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            with self._lock:
                self._buffer.extend(samples)
        except Exception:
            pass

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True, name="SoundDetector")
        self._thread.start()

    def stop(self):
        self._running = False

    # ── Loop principal ─────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            time.sleep(0.4)
            try:
                with self._lock:
                    if len(self._buffer) < self._sr // 2:
                        continue
                    data = np.array(list(self._buffer))
                self._analyze(data)
            except Exception:
                pass

    def _analyze(self, data: np.ndarray):
        energy = float(np.sqrt(np.mean(data ** 2)))
        self._energy_history.append(energy)

        # ── Ignorar silencio y voz normal ─────────────────────────────────
        if energy < self.SOUND_MIN_ENERGY:
            return

        # Calcular promedio histórico para detectar cambios bruscos
        hist = list(self._energy_history)
        avg_hist = float(np.mean(hist[:-3])) if len(hist) > 3 else energy

        # ── 1. APLAUSOS ────────────────────────────────────────────────────
        # Patrón: múltiples picos cortos de alta energía alternados con silencios
        frame_ms  = self._sr // 8   # frames de 125ms
        frames    = [data[i:i+frame_ms] for i in range(0, len(data)-frame_ms, frame_ms)]
        energies  = [float(np.sqrt(np.mean(f**2))) for f in frames]
        peaks     = [e > self.CLAP_ENERGY for e in energies]
        silences  = [e < self.VOICE_THRESHOLD for e in energies]
        
        n_peaks   = sum(peaks)
        n_silence = sum(silences)
        
        # Aplausos = al menos 3 picos fuertes + silencios entre ellos
        if n_peaks >= 3 and n_silence >= 2:
            transitions = sum(1 for i in range(1, len(peaks)) if peaks[i] != peaks[i-1])
            if transitions >= 4:
                self._notify("aplausos", "aplausos")
                return

        # ── 2. TOS ────────────────────────────────────────────────────────
        # Patrón: burst corto muy energético seguido de caída rápida
        if energy > 0.055:
            primer_tercio = data[:len(data)//3]
            resto         = data[len(data)//3:]
            e1 = float(np.sqrt(np.mean(primer_tercio**2)))
            e2 = float(np.sqrt(np.mean(resto**2))) if len(resto) > 0 else 0
            # La tos tiene energía alta al inicio y baja después
            if e1 > 0.07 and e2 < e1 * 0.35 and energy > avg_hist * 2.5:
                self._notify("tos", "tos")
                return

        # ── 3. SILBIDO ─────────────────────────────────────────────────────
        # Patrón: frecuencias dominantes entre 1500-4000 Hz sostenidas
        if 0.018 < energy < 0.08:
            whistle = self._whistle_ratio(data)
            if whistle > 0.60:
                self._notify("silbido", "silbido")
                return

        # ── 4. GOLPE / IMPACTO ────────────────────────────────────────────
        # Patrón: pico de energía muy brusco y breve
        if energy > self.LOUD_IMPACT and energy > avg_hist * 5:
            self._notify("golpe", "golpe fuerte o impacto")
            return

        # ── 5. SONIDO NO IDENTIFICADO ─────────────────────────────────────
        # Hay algo pero no podemos clasificarlo — preguntar al usuario
        # Solo si es significativamente más fuerte que el fondo normal
        if energy > self.SOUND_MIN_ENERGY * 2 and energy > avg_hist * 3:
            self._notify("desconocido", "desconocido")

    def _whistle_ratio(self, data: np.ndarray) -> float:
        """Proporción de energía en rango de silbido (1500-4000Hz)."""
        try:
            fft   = np.abs(np.fft.rfft(data))
            freqs = np.fft.rfftfreq(len(data), 1.0/self._sr)
            mask  = (freqs >= 1500) & (freqs <= 4000)
            return float(np.sum(fft[mask]) / (np.sum(fft) + 1e-10))
        except Exception:
            return 0.0

    def _notify(self, sound_type: str, label: str):
        now      = time.time()
        cooldown = self.COOLDOWN.get(sound_type, 12)
        if now - self._last_notif.get(sound_type, 0) >= cooldown:
            self._last_notif[sound_type] = now
            if self._callback:
                self._callback(sound_type, label)
