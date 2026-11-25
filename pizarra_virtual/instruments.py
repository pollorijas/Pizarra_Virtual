"""Instrumentos de geometría: regla, transportador y compás.

No forman parte del dibujo ni del historial: se colocan encima de la pizarra y se mueven,
giran o abren arrastrando sus partes. Sirven de guía para dibujar:

* Regla: un trazo (pincel, lápiz, pluma o destacador) que empieza junto a uno de sus bordes
  largos sale recto, pegado al borde. Tiene escala en centímetros reales de la pantalla.
* Transportador: mide ángulos con su aguja (el número grande indica los grados). Un trazo que
  empieza junto al arco sigue el arco y uno que empieza junto a la base sale recto.
* Compás: se abre arrastrando la pata del lápiz; al girar la punta del lápiz dibuja un arco o
  una circunferencia alrededor de la aguja.

Cada instrumento usa su propio sistema de coordenadas («local»), girado ``angle`` grados
alrededor de su punto (x, y); las coordenadas de la pizarra se convierten con ``to_local``.
Los tamaños de agarre se multiplican por ``k`` (1 normalmente, más en el modo táctil).
"""
from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF, QTransform

INSTRUMENTS = {"ruler": "Regla", "protractor": "Transportador", "compass": "Compás"}
DEFAULT_PPCM = 96 / 2.54  # píxeles por centímetro si la pantalla no informa su tamaño físico

KNOB = 12.0        # radio de los botones (girar, cerrar, cambiar tamaño)
SNAP_BAND = 28.0   # px junto al borde en los que un trazo empieza a seguirlo
ANGLE_SNAP = 15.0  # al girar, los múltiplos de 15° «atraen»...
ANGLE_SNAP_TOL = 2.0  # ...si se está a menos de estos grados

BODY = QColor(250, 250, 246, 175)
BODY_EDGE = QColor(40, 60, 90, 235)
TICK = QColor(25, 30, 40)
ACCENT = QColor(47, 111, 209)
ACCENT_SOFT = QColor(47, 111, 209, 60)
LABEL_BG = QColor(20, 22, 26, 215)


def px_per_cm(screen) -> float:
    """Píxeles lógicos por centímetro real de la pantalla (si no se sabe, los de 96 ppp)."""
    try:
        mm = screen.physicalSize().width()
        px = screen.geometry().width()
        ppcm = px / (mm / 10.0) if mm > 0 else 0.0
    except Exception:  # pragma: no cover
        ppcm = 0.0
    return ppcm if 8.0 <= ppcm <= 200.0 else DEFAULT_PPCM


def snap_angle(deg: float) -> float:
    near = round(deg / ANGLE_SNAP) * ANGLE_SNAP
    return near if abs(deg - near) <= ANGLE_SNAP_TOL else deg


def shown_angle(deg: float) -> int:
    """Inclinación que ve el alumno (0°…179°, en sentido antihorario: la pantalla tiene la y hacia abajo)."""
    return int(round(-deg)) % 180


def shown_turn(deg: float) -> int:
    """Giro de un instrumento que no es simétrico (0°…359°, en sentido antihorario)."""
    return int(round(-deg)) % 360


def _wrap(deg: float) -> float:
    """Ángulo equivalente en (-180, 180]."""
    deg = math.fmod(deg, 360.0)
    if deg <= -180:
        deg += 360
    elif deg > 180:
        deg -= 360
    return deg


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def _seg_dist(p: QPointF, a: QPointF, b: QPointF) -> float:
    """Distancia del punto ``p`` al segmento a-b."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / n))
    return math.hypot(p.x() - (a.x() + t * dx), p.y() - (a.y() + t * dy))


def _font(px: float, bold: bool = False) -> QFont:
    f = QFont()
    f.setPixelSize(max(6, int(round(px))))
    f.setBold(bold)
    return f


def _knob(p: QPainter, c: QPointF, r: float, kind: str) -> None:
    """Botón redondo con su símbolo dibujado (no depende de las fuentes instaladas)."""
    p.save()
    p.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
    p.setBrush(QColor(200, 50, 50) if kind == "close" else ACCENT)
    p.drawEllipse(c, r, r)
    pen = QPen(QColor(255, 255, 255), max(1.5, r * 0.16))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    s = r * 0.42
    x, y = c.x(), c.y()
    if kind == "close":
        p.drawLine(QPointF(x - s, y - s), QPointF(x + s, y + s))
        p.drawLine(QPointF(x - s, y + s), QPointF(x + s, y - s))
    elif kind == "rotate":
        p.drawArc(QRectF(x - s, y - s, 2 * s, 2 * s), 90 * 16, 270 * 16)
        p.setBrush(QColor(255, 255, 255))
        p.drawPolygon(QPolygonF([QPointF(x, y - s - s * 0.55), QPointF(x + s * 0.7, y - s),
                                 QPointF(x, y - s + s * 0.55)]))
    elif kind == "resize":
        a, b = QPointF(x - s, y + s), QPointF(x + s, y - s)
        p.drawLine(a, b)
        h = s * 0.6
        p.drawLine(b, QPointF(b.x() - h, b.y()))
        p.drawLine(b, QPointF(b.x(), b.y() + h))
        p.drawLine(a, QPointF(a.x() + h, a.y()))
        p.drawLine(a, QPointF(a.x(), a.y() - h))
    p.restore()


def _label(p: QPainter, center: QPointF, text: str, px: float) -> QRectF:
    """Etiqueta oscura (en coordenadas de la pizarra, sin girar) centrada en ``center``."""
    f = _font(px, bold=True)
    fm = QFontMetricsF(f)
    w, h = fm.horizontalAdvance(text) + px, fm.height() + px * 0.35
    box = QRectF(center.x() - w / 2, center.y() - h / 2, w, h)
    p.save()
    p.setFont(f)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(LABEL_BG)
    p.drawRoundedRect(box, h / 3, h / 3)
    p.setPen(QColor(255, 255, 255))
    p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
    p.restore()
    return box


class Instrument:
    """Base común: posición, giro, arrastre de sus partes y guía para los trazos."""

    kind = ""

    def __init__(self, x: float, y: float, angle: float = 0.0, ppcm: float = DEFAULT_PPCM):
        self.x, self.y, self.angle = float(x), float(y), float(angle)
        self.ppcm = ppcm
        self._drag: dict | None = None

    # ---- coordenadas

    @property
    def origin(self) -> QPointF:
        return QPointF(self.x, self.y)

    def transform(self) -> QTransform:
        t = QTransform()
        t.translate(self.x, self.y)
        t.rotate(self.angle)
        return t

    def to_local(self, pos: QPointF) -> QPointF:
        inv, _ok = self.transform().inverted()
        return inv.map(QPointF(pos))

    def to_canvas(self, local: QPointF) -> QPointF:
        return self.transform().map(QPointF(local))

    # ---- geometría (en coordenadas locales; la definen las subclases)

    def outline(self, k: float) -> QPainterPath:
        raise NotImplementedError

    def knobs(self, k: float) -> dict[str, QPointF]:
        """Botones: nombre de la parte -> centro (local)."""
        return {}

    def bounds(self, k: float) -> QRectF:
        """Rectángulo (en la pizarra) que hay que repintar: el cuerpo, los botones y las etiquetas."""
        path = QPainterPath(self.outline(k))
        r = KNOB * k
        for c in self.knobs(k).values():
            path.addEllipse(c, r, r)
        m = 70 * k
        return self.transform().map(path).boundingRect().adjusted(-m, -m, m, m)

    def hit(self, pos: QPointF, k: float) -> str | None:
        """Parte del instrumento bajo ``pos``: un botón, «move» (el cuerpo) o None."""
        local = self.to_local(pos)
        r = KNOB * k * 1.3
        for part, c in self.knobs(k).items():
            if _dist(local, c) <= r:
                return part
        return "move" if self.outline(k).contains(local) else None

    # ---- arrastre

    def press(self, part: str, pos: QPointF) -> None:
        self._drag = {"part": part, "from": QPointF(pos), "x": self.x, "y": self.y, "angle": self.angle}

    def drag(self, pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier) -> list[QPointF]:
        """Sigue el arrastre; devuelve los puntos que hay que dibujar (solo el compás dibuja)."""
        d = self._drag
        if d is None:
            return []
        if d["part"] == "move":
            self.x = d["x"] + pos.x() - d["from"].x()
            self.y = d["y"] + pos.y() - d["from"].y()
        elif d["part"] == "rotate":
            c = self.rotation_center()
            a0 = math.degrees(math.atan2(d["from"].y() - c.y(), d["from"].x() - c.x()))
            a1 = math.degrees(math.atan2(pos.y() - c.y(), pos.x() - c.x()))
            self.set_angle(d["angle"] + a1 - a0, around=c, free=bool(modifiers & Qt.KeyboardModifier.ShiftModifier))
        return []

    def release(self) -> None:
        self._drag = None

    def cancel(self) -> None:
        """Termina el arrastre devolviendo el instrumento a como estaba al empezarlo."""
        d = self._drag
        if d is not None:
            self.x, self.y, self.angle = d["x"], d["y"], d["angle"]
            for attr in ("radius", "measure"):
                if attr in d:
                    setattr(self, attr, d[attr])
        self._drag = None

    @property
    def dragging(self) -> str | None:
        return self._drag["part"] if self._drag else None

    def rotation_center(self) -> QPointF:
        return self.origin

    def set_angle(self, deg: float, around: QPointF | None = None, free: bool = False) -> None:
        """Gira hasta ``deg`` grados alrededor de ``around`` (los múltiplos de 15° atraen, salvo con Mayús)."""
        deg = _wrap(deg if free else snap_angle(deg))
        if around is not None:
            # El punto ``around`` debe quedar donde estaba: se recoloca el origen.
            local = self.to_local(around)
            self.angle = deg
            moved = self.to_canvas(local)
            self.x += around.x() - moved.x()
            self.y += around.y() - moved.y()
        else:
            self.angle = deg

    def rotate_by(self, deg: float) -> None:
        self.set_angle(self.angle + deg, around=self.rotation_center(), free=True)

    # ---- guía de los trazos

    def guide(self, pos: QPointF, k: float, width: float):
        """Si ``pos`` está junto a un borde que guía, función que lleva cada punto del trazo a ese borde."""
        return None

    # ---- pintado

    def paint(self, p: QPainter, k: float) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------- regla


class Ruler(Instrument):
    """Regla con escala en centímetros (y milímetros si caben). (x, y) es su centro."""

    kind = "ruler"

    def __init__(self, x: float, y: float, ppcm: float = DEFAULT_PPCM, length_cm: int = 30, k: float = 1.0):
        super().__init__(x, y, 0.0, ppcm)
        self.length_cm = max(5, int(length_cm))
        self.margin = max(0.5 * ppcm, 12.0)
        self.width = max(2.4 * ppcm, 78.0 * k)

    @property
    def length(self) -> float:
        return self.length_cm * self.ppcm + 2 * self.margin

    def outline(self, k: float) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(QRectF(-self.length / 2, -self.width / 2, self.length, self.width), 6, 6)
        return path

    def knobs(self, k: float) -> dict[str, QPointF]:
        r = KNOB * k
        y = self.width / 2 - r - 6
        return {"close": QPointF(-self.length / 2 + r + 8, y), "rotate": QPointF(self.length / 2 - r - 8, y)}

    def guide(self, pos: QPointF, k: float, width: float):
        local = self.to_local(pos)
        half_l, half_w, band = self.length / 2, self.width / 2, SNAP_BAND * k
        if not -half_l <= local.x() <= half_l:
            return None
        if -half_w - band <= local.y() <= -half_w + 1:
            y = -half_w - width / 2  # el trazo va por fuera del borde (como el lápiz contra la regla)
        elif half_w - 1 <= local.y() <= half_w + band:
            y = half_w + width / 2
        else:
            return None

        def follow(q: QPointF) -> QPointF:
            lq = self.to_local(q)
            return self.to_canvas(QPointF(max(-half_l, min(half_l, lq.x())), y))
        return follow

    def paint(self, p: QPainter, k: float) -> None:
        L, W = self.length, self.width
        p.save()
        p.setTransform(self.transform(), True)
        p.setPen(QPen(BODY_EDGE, 1.5))
        p.setBrush(BODY)
        p.drawPath(self.outline(k))
        top = -W / 2
        x0 = -L / 2 + self.margin
        ppcm = self.ppcm
        mm = ppcm >= 25  # milímetros solo si quedan separados
        half = ppcm >= 12
        label_step = next(s for s in (1, 2, 5, 10, 20) if s * ppcm >= 22)
        fpx = max(9.0, min(17.0, W * 0.19))
        p.setFont(_font(fpx))
        fm = QFontMetricsF(p.font())
        tick = QPen(TICK, 1.1)
        p.setPen(tick)
        for i in range(self.length_cm * 10 + 1):
            if i % 10 == 0:
                h = W * 0.30
            elif i % 5 == 0:
                if not half:
                    continue
                h = W * 0.21
            else:
                if not mm:
                    continue
                h = W * 0.12
            x = x0 + i * ppcm / 10
            p.drawLine(QPointF(x, top), QPointF(x, top + h))
            if i % 10 == 0 and (i // 10) % label_step == 0:
                text = str(i // 10)
                tw = fm.horizontalAdvance(text)
                p.drawText(QPointF(x - tw / 2, top + W * 0.32 + fm.ascent()), text)
        p.drawText(QPointF(-L / 2 + 2 * KNOB * k + 16, W / 2 - KNOB * k - 6 + fm.ascent() / 2 - 1), "cm")
        for part, c in self.knobs(k).items():
            _knob(p, c, KNOB * k, part)
        p.restore()
        if self.dragging == "rotate" or shown_angle(self.angle) != 0:
            # Inclinación de la regla (al girarla o si no está horizontal)
            c = self.to_canvas(QPointF(0, W / 2 - KNOB * k - 6))
            _label(p, c, f"{shown_angle(self.angle)}°", 13 * k)


# ---------------------------------------------------------------------- transportador


class Protractor(Instrument):
    """Transportador de 180°. (x, y) es el vértice (el centro de la base), donde va el ángulo."""

    kind = "protractor"

    def __init__(self, x: float, y: float, radius: float = 220.0):
        super().__init__(x, y, 0.0)
        self.radius = float(radius)
        self.measure = 60.0  # grados que marca la aguja

    def base(self, k: float) -> float:
        return max(0.12 * self.radius, 2 * KNOB * k + 10)

    def outline(self, k: float) -> QPainterPath:
        R = self.radius
        path = QPainterPath(QPointF(R, 0))
        path.arcTo(QRectF(-R, -R, 2 * R, 2 * R), 0, 180)
        path.lineTo(-R, self.base(k))
        path.lineTo(R, self.base(k))
        path.closeSubpath()
        return path

    def needle_tip(self, k: float) -> QPointF:
        a = math.radians(self.measure)
        r = self.radius + KNOB * k + 8
        return QPointF(r * math.cos(a), -r * math.sin(a))

    def knobs(self, k: float) -> dict[str, QPointF]:
        r, R, y = KNOB * k, self.radius, self.base(k) / 2
        return {"close": QPointF(-R + r + 8, y), "resize": QPointF(R - 3 * r - 16, y),
                "rotate": QPointF(R - r - 8, y), "needle": self.needle_tip(k)}

    def press(self, part: str, pos: QPointF) -> None:
        super().press(part, pos)
        self._drag.update(radius=self.radius, measure=self.measure)

    def drag(self, pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier) -> list[QPointF]:
        d = self._drag
        if d is None:
            return []
        if d["part"] == "needle":
            local = self.to_local(pos)
            deg = math.degrees(math.atan2(-local.y(), local.x()))
            if deg < -90:  # por debajo de la base, a la izquierda: 180°
                deg = 180.0
            self.measure = float(max(0, min(180, round(deg))))
        elif d["part"] == "resize":
            r0 = max(1.0, _dist(d["from"], self.origin))
            self.radius = max(60.0, min(1400.0, d["radius"] * _dist(pos, self.origin) / r0))
        else:
            return super().drag(pos, modifiers)
        return []

    def guide(self, pos: QPointF, k: float, width: float):
        local = self.to_local(pos)
        R, band, s = self.radius, SNAP_BAND * k, self.base(k)
        d = math.hypot(local.x(), local.y())
        if local.y() <= 0 and R - 1 <= d <= R + band:  # junto al arco: el trazo sigue el arco
            r = R + width / 2

            def on_arc(q: QPointF) -> QPointF:
                lq = self.to_local(q)
                a = math.atan2(-lq.y(), lq.x())
                if a < -math.pi / 2:
                    a = math.pi
                a = max(0.0, min(math.pi, a))
                return self.to_canvas(QPointF(r * math.cos(a), -r * math.sin(a)))
            return on_arc
        if abs(local.x()) <= R and s - 1 <= local.y() <= s + band:  # junto a la base: recto
            y = s + width / 2

            def on_base(q: QPointF) -> QPointF:
                lq = self.to_local(q)
                return self.to_canvas(QPointF(max(-R, min(R, lq.x())), y))
            return on_base
        return None

    def paint(self, p: QPainter, k: float) -> None:
        R = self.radius
        p.save()
        p.setTransform(self.transform(), True)
        p.setPen(QPen(BODY_EDGE, 1.5))
        p.setBrush(BODY)
        p.drawPath(self.outline(k))
        # Ángulo medido: sector suave entre la base y la aguja
        a = self.measure
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ACCENT_SOFT)
        rs = R * 0.3
        sector = QPainterPath(QPointF(0, 0))
        sector.arcTo(QRectF(-rs, -rs, 2 * rs, 2 * rs), 0, a)
        sector.closeSubpath()
        p.drawPath(sector)
        # Graduación
        fpx = max(8.0, min(16.0, R * 0.055))
        p.setFont(_font(fpx))
        fm = QFontMetricsF(p.font())
        p.setPen(QPen(TICK, 1.0))
        degrees = R * math.pi / 180 >= 2.6  # marcas de cada grado solo si quedan separadas
        for deg in range(181):
            if deg % 10 == 0:
                h = R * 0.10
            elif deg % 5 == 0:
                h = R * 0.065
            elif degrees:
                h = R * 0.035
            else:
                continue
            c, s = math.cos(math.radians(deg)), -math.sin(math.radians(deg))
            p.drawLine(QPointF(R * c, R * s), QPointF((R - h) * c, (R - h) * s))
            if deg % 10 == 0:
                labels = [(str(deg), R - R * 0.10 - fpx * 0.9)]
                if deg not in (0, 180):  # en la base las dos escalas quedarían pegadas
                    labels.append((str(180 - deg), R - R * 0.10 - fpx * 2.1))
                for text, rr in labels:
                    tw = fm.horizontalAdvance(text)
                    pt = QPointF(rr * c, rr * s - (fpx * 0.6 if deg in (0, 180) else 0))
                    p.drawText(QPointF(pt.x() - tw / 2, pt.y() + fm.ascent() / 2 - 1), text)
        inner = R * 0.10 + fpx * 2.9
        p.setPen(QPen(TICK, 0.8))
        p.drawArc(QRectF(-(R - inner), -(R - inner), 2 * (R - inner), 2 * (R - inner)), 0, 180 * 16)
        p.drawLine(QPointF(-R, 0), QPointF(R, 0))
        # Vértice
        p.setPen(QPen(ACCENT, 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0, 0), 5, 5)
        p.drawLine(QPointF(-9, 0), QPointF(9, 0))
        p.drawLine(QPointF(0, -9), QPointF(0, 9))
        # Aguja
        tip = self.needle_tip(k)
        p.setPen(QPen(ACCENT, 2.2))
        p.drawLine(QPointF(0, 0), tip)
        for part, c in self.knobs(k).items():
            if part != "needle":
                _knob(p, c, KNOB * k, part)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(ACCENT)
        p.drawEllipse(tip, KNOB * k * 0.8, KNOB * k * 0.8)
        p.restore()
        # Ángulo medido, en grande, sobre la bisectriz
        b = math.radians(a / 2)
        pos = self.to_canvas(QPointF(R * 0.45 * math.cos(b), -R * 0.45 * math.sin(b)))
        _label(p, pos, f"{int(round(a))}°", max(14.0, R * 0.075) * min(k, 1.2))
        if self.dragging == "rotate":
            _label(p, self.to_canvas(QPointF(0, self.base(k) + 22 * k)), f"{shown_turn(self.angle)}°", 13 * k)


# ---------------------------------------------------------------------- compás


class Compass(Instrument):
    """Compás: aguja en (x, y); la punta del lápiz está a ``radius`` px en la dirección ``angle``."""

    kind = "compass"

    def __init__(self, x: float, y: float, radius: float = 150.0, ppcm: float = DEFAULT_PPCM):
        super().__init__(x, y, 0.0, ppcm)
        self.radius = float(radius)

    def hinge(self) -> QPointF:
        """Bisagra (local): las dos patas miden lo mismo y crecen con la abertura."""
        leg = max(0.8 * self.radius, 70.0)
        h = math.sqrt(max(0.0, leg * leg - (self.radius / 2) ** 2))
        return QPointF(self.radius / 2, -h)

    def pencil(self) -> QPointF:
        """Punta del lápiz (en la pizarra)."""
        return self.to_canvas(QPointF(self.radius, 0))

    def outline(self, k: float) -> QPainterPath:
        h = self.hinge()
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(0, 0), h, QPointF(self.radius, 0)]))
        return path

    def knobs(self, k: float) -> dict[str, QPointF]:
        h = self.hinge()
        return {"close": QPointF(h.x(), h.y() - 2 * KNOB * k - 14)}

    def hit(self, pos: QPointF, k: float) -> str | None:
        local = self.to_local(pos)
        h, q = self.hinge(), QPointF(self.radius, 0)
        if _dist(local, self.knobs(k)["close"]) <= KNOB * k * 1.3:
            return "close"
        if _dist(local, q) <= 18 * k:
            return "draw"  # la punta del lápiz: girarla dibuja
        if _dist(local, h) <= 16 * k or _dist(local, QPointF(0, 0)) <= 16 * k:
            return "move"
        if _seg_dist(local, h, q) <= 11 * k:
            return "open"  # la pata del lápiz: abre o cierra el compás
        if _seg_dist(local, QPointF(0, 0), h) <= 11 * k:
            return "move"
        return None

    def press(self, part: str, pos: QPointF) -> None:
        super().press(part, pos)
        self._drag.update(radius=self.radius, pencil=self.pencil(), sweep=0.0,
                          prev=math.degrees(math.atan2(pos.y() - self.y, pos.x() - self.x)))

    def drag(self, pos: QPointF, modifiers=Qt.KeyboardModifier.NoModifier) -> list[QPointF]:
        d = self._drag
        if d is None:
            return []
        if d["part"] == "open":
            q = QPointF(d["pencil"].x() + pos.x() - d["from"].x(), d["pencil"].y() + pos.y() - d["from"].y())
            self.radius = max(12.0, min(3000.0, _dist(q, self.origin)))
            self.angle = math.degrees(math.atan2(q.y() - self.y, q.x() - self.x))
            return []
        if d["part"] != "draw":
            return super().drag(pos, modifiers)
        # Dibujar: el lápiz gira alrededor de la aguja tanto como gire el puntero (una vuelta como máximo)
        now = math.degrees(math.atan2(pos.y() - self.y, pos.x() - self.x))
        step = _wrap(now - d["prev"])
        d["prev"] = now
        if _dist(pos, self.origin) < max(0.25 * self.radius, 12.0):
            return []  # junto a la aguja el ángulo salta con cualquier temblor: no se cuenta
        start = d["sweep"]
        end = max(-360.0, min(360.0, start + step))
        d["sweep"] = end
        if end == start:
            return []
        a0 = d["angle"]
        # Puntos cada 1,5° como mucho (y cada ~3 px en circunferencias grandes)
        max_step = min(1.5, math.degrees(3.0 / max(1.0, self.radius)))
        n = max(1, math.ceil(abs(end - start) / max_step))
        pts = []
        for i in range(1, n + 1):
            a = math.radians(a0 + start + (end - start) * i / n)
            pts.append(QPointF(self.x + self.radius * math.cos(a), self.y + self.radius * math.sin(a)))
        self.angle = a0 + end
        return pts

    @property
    def sweep(self) -> float:
        return self._drag["sweep"] if self._drag else 0.0

    def rotate_by(self, deg: float) -> None:
        self.angle = _wrap(self.angle + deg)

    def bounds(self, k: float) -> QRectF:
        r = self.radius + 30 * k
        legs = super().bounds(k)
        return legs.united(QRectF(self.x - r, self.y - r, 2 * r, 2 * r))

    def paint(self, p: QPainter, k: float) -> None:
        h, r = self.hinge(), self.radius
        q = QPointF(r, 0)
        p.save()
        p.setTransform(self.transform(), True)
        if self.dragging in ("draw", "open"):
            # Circunferencia que dibujaría (guía tenue)
            pen = QPen(ACCENT, 1.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(0, 0), r, r)
        w = 9 * k

        def leg(a: QPointF, b: QPointF, color: QColor) -> None:
            line = QLineF(b, a)
            n = line.normalVector().unitVector()
            nx, ny = (n.p2().x() - n.p1().x()) * w / 2, (n.p2().y() - n.p1().y()) * w / 2
            poly = QPolygonF([QPointF(b.x() + nx, b.y() + ny), QPointF(b.x() - nx, b.y() - ny),
                              QPointF(a.x() - nx * 0.4, a.y() - ny * 0.4), QPointF(a.x() + nx * 0.4, a.y() + ny * 0.4)])
            p.setPen(QPen(BODY_EDGE, 1.3))
            p.setBrush(color)
            p.drawPolygon(poly)

        # Pata de la aguja (metálica) y pata del lápiz
        needle_end = QPointF(h.x() * 0.12, h.y() * 0.12)
        leg(needle_end, h, QColor(176, 184, 196))
        p.setPen(QPen(TICK, 1.6))
        p.drawLine(QPointF(0, 0), needle_end)
        pencil_end = QPointF(h.x() + (q.x() - h.x()) * 0.86, h.y() + (q.y() - h.y()) * 0.86)
        leg(pencil_end, h, QColor(255, 196, 70))
        p.setPen(QPen(BODY_EDGE, 1.2))
        p.setBrush(QColor(60, 60, 60))
        p.drawPolygon(QPolygonF([QPointF(pencil_end.x() - 3 * k, pencil_end.y()),
                                 QPointF(pencil_end.x() + 3 * k, pencil_end.y()), q]))
        # Punta del lápiz (zona para girar y dibujar) y aguja
        p.setPen(QPen(ACCENT, 2.0))
        p.setBrush(ACCENT_SOFT)
        p.drawEllipse(q, 14 * k, 14 * k)
        p.setPen(QPen(TICK, 1.5))
        p.drawEllipse(QPointF(0, 0), 4, 4)
        # Bisagra con su asa
        p.setPen(QPen(BODY_EDGE, 1.5))
        p.setBrush(QColor(120, 128, 140))
        p.drawRoundedRect(QRectF(h.x() - 5 * k, h.y() - 22 * k, 10 * k, 20 * k), 3, 3)
        p.setBrush(QColor(210, 214, 220))
        p.drawEllipse(h, 9 * k, 9 * k)
        for part, c in self.knobs(k).items():
            _knob(p, c, KNOB * k, part)
        p.restore()
        # Radio (en centímetros) junto a la línea aguja-lápiz
        mid = self.to_canvas(QPointF(r / 2, 0))
        side = self.to_canvas(QPointF(r / 2, 26 * k))
        text = f"r = {r / self.ppcm:.1f} cm".replace(".", ",")
        if self.dragging == "draw" and abs(self.sweep) >= 1:
            text += f"   ·   {int(round(abs(self.sweep)))}°"
        _label(p, side if r > 60 else mid, text, 12 * k)


KINDS = {"ruler": Ruler, "protractor": Protractor, "compass": Compass}


def create(kind: str, center: QPointF, screen_w: float, screen_h: float, ppcm: float, k: float = 1.0) -> Instrument:
    """Instrumento nuevo, de un tamaño cómodo para la pantalla, centrado en ``center``."""
    if kind == "ruler":
        cm = int(max(5, min(100, (0.6 * screen_w) // ppcm)))
        return Ruler(center.x(), center.y(), ppcm, cm, k)
    if kind == "protractor":
        radius = max(60.0, min(0.3 * min(screen_w, screen_h), 420.0))
        return Protractor(center.x(), center.y() + radius / 2, radius)
    if kind == "compass":
        radius = max(40.0, min(5 * ppcm, 0.3 * min(screen_w, screen_h)))  # 5 cm si caben
        return Compass(center.x() - radius / 2, center.y() + radius / 3, radius, ppcm)
    raise ValueError(kind)


__all__ = ["INSTRUMENTS", "Instrument", "Ruler", "Protractor", "Compass", "create", "px_per_cm"]
