"""Temporizador visible en pantalla (cuenta regresiva o cronómetro) para los ejercicios de clase.

Es una ventanita flotante, siempre encima y sin tomar el foco, que se arrastra a cualquier
lugar. Al terminar la cuenta regresiva parpadea en rojo («¡Tiempo!») y suena un aviso.
"""
from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from . import icons

TICK_MS = 200
FLASH_MS = 8000  # cuánto parpadea al terminar
STYLE = """
QWidget#timer { background: #23262c; border: 1px solid #454a53; border-radius: 10px; }
QWidget#timer[finished="true"] { background: #b71c1c; border-color: #ff8a80; }
QLabel { color: #e6e8eb; background: transparent; }
QLabel#title { color: #9aa3ad; font-size: 11px; font-weight: bold; }
QToolButton { color: #e6e8eb; background: #343841; border: none; border-radius: 5px; padding: 2px 6px;
              font-weight: bold; }
QToolButton:hover { background: #454a53; }
"""


def format_time(ms: float) -> str:
    total = max(0, int(round(ms / 1000.0)))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class TimerWindow(QWidget):
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setObjectName("timer")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Temporizador")
        self.clock = clock
        self.beep: Callable[[], None] = QApplication.beep
        self.mode = "down"  # "down" (cuenta regresiva) o "up" (cronómetro)
        self.total_ms = 0.0
        self.initial_ms = 0.0  # tiempo elegido (al volver a empezar se recupera)
        self.running = False
        self.finished = False
        self._elapsed_ms = 0.0  # acumulado mientras estuvo en pausa
        self._started_at = 0.0
        self._finished_at = 0.0
        self._beeps = 0
        self._drag: QPoint | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 8)
        lay.setSpacing(2)
        self.title = QLabel("TEMPORIZADOR")
        self.title.setObjectName("title")
        lay.addWidget(self.title, 0, Qt.AlignmentFlag.AlignHCenter)
        self.label = QLabel("00:00")
        f = QFont()
        f.setFamilies(["Segoe UI", "Arial", "DejaVu Sans"])
        f.setPixelSize(44)
        f.setBold(True)
        self.label.setFont(f)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.label)
        row = QHBoxLayout()
        row.setSpacing(4)

        def button(text: str, tip: str, fn, icon: str | None = None) -> QToolButton:
            b = QToolButton()
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if icon:
                b.setIcon(icons.icon(icon))
                b.setIconSize(QSize(16, 16))
            else:
                b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
            return b

        self.minus_btn = button("−1", "Quitar un minuto", lambda: self.add_minutes(-1))
        self.pause_btn = button("❚❚", "Pausar / continuar", self.toggle_pause)
        self.restart_btn = button("↺", "Volver a empezar", self.restart)
        self.plus_btn = button("+1", "Añadir un minuto", lambda: self.add_minutes(1))
        self.close_btn = button("✕", "Cerrar el temporizador", self.close)
        lay.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.tick)
        self.setFixedWidth(250)

    # ------------------------------------------------------------------ estado
    def _now_ms(self) -> float:
        return self.clock() * 1000.0

    @property
    def elapsed_ms(self) -> float:
        extra = self._now_ms() - self._started_at if self.running else 0.0
        return self._elapsed_ms + extra

    @property
    def remaining_ms(self) -> float:
        return max(0.0, self.total_ms - self.elapsed_ms) if self.mode == "down" else 0.0

    def text(self) -> str:
        if self.finished and self.mode == "down":
            return "¡Tiempo!" if int((self._now_ms() - self._finished_at) / 500) % 2 == 0 else "00:00"
        return format_time(self.remaining_ms if self.mode == "down" else self.elapsed_ms)

    # ------------------------------------------------------------------ acciones
    def start_countdown(self, seconds: float) -> None:
        self.mode = "down"
        self.total_ms = self.initial_ms = max(1.0, seconds) * 1000.0
        self.title.setText("TEMPORIZADOR")
        self._reset_and_run()

    def start_stopwatch(self) -> None:
        self.mode = "up"
        self.total_ms = 0.0
        self.title.setText("CRONÓMETRO")
        self._reset_and_run()

    def _reset_and_run(self) -> None:
        self._elapsed_ms = 0.0
        self._set_finished(False)
        self.running = True
        self._started_at = self._now_ms()
        self._timer.start()
        self.minus_btn.setVisible(self.mode == "down")
        self.plus_btn.setVisible(self.mode == "down")
        self.tick()

    def toggle_pause(self) -> None:
        if self.finished:
            self.restart()
            return
        if self.running:
            self._elapsed_ms = self.elapsed_ms
            self.running = False
        else:
            self._started_at = self._now_ms()
            self.running = True
            self._timer.start()
        self.tick()

    def restart(self) -> None:
        """Vuelve a empezar con el tiempo elegido (sin los minutos añadidos o quitados)."""
        if self.mode == "down":
            self.total_ms = self.initial_ms
        self._reset_and_run()

    def add_minutes(self, n: int) -> None:
        if self.mode != "down":
            return
        # No baja de 10 segundos restantes
        self.total_ms = max(self.elapsed_ms + 10_000.0, self.total_ms + n * 60_000.0)
        if self.finished:
            self._set_finished(False)
            self.running = True
            self._started_at = self._now_ms()
            self._timer.start()
        self.tick()

    def _set_finished(self, on: bool) -> None:
        self.finished = on
        self.setProperty("finished", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if on:
            self._finished_at = self._now_ms()
            self._beeps = 0

    def tick(self) -> None:
        if self.mode == "down" and self.running and self.remaining_ms <= 0:
            self._elapsed_ms = self.total_ms
            self.running = False
            self._set_finished(True)
        if self.finished:
            since = self._now_ms() - self._finished_at
            if self._beeps < 3 and since >= self._beeps * 700:  # tres avisos sonoros
                self._beeps += 1
                self.beep()
            if since > FLASH_MS:  # deja de parpadear y queda en rojo con 00:00
                self._timer.stop()
                self.label.setText("¡Tiempo!")
                return
        elif not self.running:
            self._timer.stop()
        self.label.setText(self.text())
        self.pause_btn.setText("▶" if not self.running or self.finished else "❚❚")
        self.update()  # barra de progreso

    def paintEvent(self, ev):  # noqa: N802
        super().paintEvent(ev)
        if self.mode != "down" or self.total_ms <= 0:
            return
        # Barra fina de progreso en el borde inferior
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        frac = self.remaining_ms / self.total_ms
        color = QColor(67, 160, 71) if frac > 0.25 else QColor(251, 140, 0) if frac > 0.1 else QColor(229, 57, 53)
        r = QRectF(10, self.height() - 5, (self.width() - 20) * frac, 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(r, 1.5, 1.5)
        p.end()

    # ------------------------------------------------------------------ ventana
    def place_on(self, screen) -> None:
        self.adjustSize()
        avail = screen.availableGeometry()
        self.move(avail.right() - self.width() - 24, avail.top() + 24)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._drag = None

    def closeEvent(self, ev):  # noqa: N802
        # Cerrar el temporizador no cierra el programa: solo lo detiene y lo oculta.
        self.running = False
        self._timer.stop()
        ev.accept()
