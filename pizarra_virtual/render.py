"""Rasterizado de trazos y figuras con QPainter.

Todas las funciones dibujan en coordenadas lógicas; el QImage destino lleva su
propio devicePixelRatio, así que el resultado es nítido con cualquier escalado.

Los trazos se dibujan segmento a segmento. El mismo código se usa para el
dibujo en vivo (incremental) y para volver a renderizar el historial
(deshacer/rehacer, cambio de DPI), por lo que el resultado es idéntico.
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient

from .items import ClearItem, ShapeItem, StrokeItem
from .tools import FILLABLE_SHAPES, BrushType, Tool

NIB_ANGLE = math.radians(40)      # ángulo de la punta caligráfica
HIGHLIGHTER_RATIO = 0.30          # ancho/alto de la punta biselada del destacador
_CIRCLE_SEGMENTS = 16


class StrokeState:
    """Estado que se arrastra de un segmento al siguiente dentro de un trazo."""

    __slots__ = ("rng", "carry")

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.carry = 0.0


# --------------------------------------------------------------------------- utilidades


def item_color(item) -> QColor:
    return QColor(*item.rgba)


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _circle_points(x, y, r):
    return [
        (x + r * math.cos(2 * math.pi * k / _CIRCLE_SEGMENTS),
         y + r * math.sin(2 * math.pi * k / _CIRCLE_SEGMENTS))
        for k in range(_CIRCLE_SEGMENTS)
    ]


def _fill_hull(p: QPainter, points, color: QColor, outline: float = 0.0):
    hull = convex_hull(points)
    if len(hull) < 3:
        return
    if outline > 0:
        pen = QPen(color, outline)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
    else:
        p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in hull]))


def _dot(p: QPainter, x, y, w, color):
    r = max(w / 2.0, 0.35)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(QPointF(x, y), r, r)


def _round_segment(p: QPainter, x0, y0, x1, y1, w, color):
    if x0 == x1 and y0 == y1:
        _dot(p, x1, y1, w, color)
        return
    pen = QPen(color, max(w, 0.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(x0, y0), QPointF(x1, y1))


def _variable_segment(p: QPainter, x0, y0, w0, x1, y1, w1, color):
    """Segmento con grosor variable: envolvente convexa de dos círculos."""
    if x0 == x1 and y0 == y1:
        _dot(p, x1, y1, max(w0, w1), color)
        return
    pts = _circle_points(x0, y0, max(w0 / 2, 0.3)) + _circle_points(x1, y1, max(w1 / 2, 0.3))
    _fill_hull(p, pts, color)


def _chisel_segment(p: QPainter, x0, y0, x1, y1, w, color):
    """Punta rectangular vertical (destacador)."""
    hx = max(1.0, w * HIGHLIGHTER_RATIO / 2)
    hy = w / 2
    pts = []
    for (x, y) in ((x0, y0), (x1, y1)):
        pts += [(x - hx, y - hy), (x + hx, y - hy), (x + hx, y + hy), (x - hx, y + hy)]
    _fill_hull(p, pts, color)


def _calligraphy_segment(p: QPainter, x0, y0, x1, y1, w, color):
    nx = math.cos(NIB_ANGLE) * w / 2
    ny = -math.sin(NIB_ANGLE) * w / 2
    if x0 == x1 and y0 == y1:
        pen = QPen(color, 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x1 - nx, y1 - ny), QPointF(x1 + nx, y1 + ny))
        return
    pts = [(x0 + nx, y0 + ny), (x0 - nx, y0 - ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny)]
    _fill_hull(p, pts, color, outline=1.0)


def _soft_dab(p: QPainter, x, y, w, color: QColor):
    r = max(w / 2.0, 0.6)
    g = QRadialGradient(QPointF(x, y), r)
    c0 = QColor(color)
    c0.setAlphaF(0.50)
    c1 = QColor(color)
    c1.setAlphaF(0.20)
    c2 = QColor(color)
    c2.setAlpha(0)
    g.setColorAt(0.0, c0)
    g.setColorAt(0.5, c1)
    g.setColorAt(1.0, c2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(x, y), r, r)


def _soft_segment(p, x0, y0, w0, x1, y1, w1, color, state: StrokeState, first: bool):
    spacing = max(1.0, min(w0, w1) * 0.12)
    if first:
        _soft_dab(p, x1, y1, w1, color)
        state.carry = 0.0
        return
    dist = math.hypot(x1 - x0, y1 - y0)
    if dist <= 0:
        return
    t = spacing - state.carry
    last = None
    while t <= dist:
        f = t / dist
        _soft_dab(p, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, w0 + (w1 - w0) * f, color)
        last = t
        t += spacing
    state.carry = dist - last if last is not None else state.carry + dist


def _airbrush_segment(p, x0, y0, x1, y1, w, color, state: StrokeState):
    r = w / 2.0
    dot = max(0.55, w / 45.0)
    dist = math.hypot(x1 - x0, y1 - y0)
    count = int((dist + 2.0) * w * 0.10 / max(1.0, dot * dot))
    count = max(3, min(count, 600))
    rng = state.rng
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    for _ in range(count):
        f = rng.random()
        ang = rng.random() * 2 * math.pi
        rad = r * (rng.random() ** 0.75)
        cx = x0 + (x1 - x0) * f + math.cos(ang) * rad
        cy = y0 + (y1 - y0) * f + math.sin(ang) * rad
        p.drawEllipse(QPointF(cx, cy), dot, dot)



# --------------------------------------------------------------------------- pluma
#
# La pluma se dibuja como una curva suave (Bézier cuadráticas entre los puntos
# medios de la entrada) cuyo contorno se calcula de forma exacta: círculos en
# cada muestra unidos por sus tangentes exteriores. Todo el contorno se rellena
# como un único QPainterPath, así el borde antialias es limpio y no hay "bultos"
# ni esquinas. Los extremos se afinan (entrada y salida de la tinta).

PEN_NIB_ANGLE = math.radians(-45)   # plumín inclinado: trazos en "/" finos, en "\\" gruesos
PEN_DIRECTION_RANGE = 0.30          # cuánto influye la dirección en el grosor (0 = nada)


def pen_taper_length(size: float) -> float:
    return max(6.0, size * 2.5)


def _signed_area(pts) -> float:
    a = 0.0
    for k in range(len(pts)):
        x0, y0 = pts[k]
        x1, y1 = pts[(k + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _add_poly(path: QPainterPath, pts, check: bool = True) -> None:
    # Todas las piezas con la misma orientación: con WindingFill se suman (unión), nunca se restan.
    if check and _signed_area(pts) < 0:
        pts = pts[::-1]
    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
    path.closeSubpath()


def _circle_poly(x, y, r):
    n = max(10, min(40, int(r * 3) + 10))
    return [(x + r * math.cos(2 * math.pi * k / n), y + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _tangent_quad(x0, y0, r0, x1, y1, r1):
    """Cuadrilátero formado por las tangentes exteriores de dos círculos (None si uno contiene al otro)."""
    dx, dy = x1 - x0, y1 - y0
    d = math.hypot(dx, dy)
    if d <= abs(r0 - r1) + 1e-6:
        return None
    ux, uy = dx / d, dy / d
    nx, ny = -uy, ux
    c = (r0 - r1) / d
    s = math.sqrt(max(0.0, 1.0 - c * c))
    ax, ay = ux * c + nx * s, uy * c + ny * s
    bx, by = ux * c - nx * s, uy * c - ny * s
    return [(x0 + r0 * ax, y0 + r0 * ay), (x1 + r1 * ax, y1 + r1 * ay),
            (x1 + r1 * bx, y1 + r1 * by), (x0 + r0 * bx, y0 + r0 * by)]


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


def _pen_step(*widths) -> float:
    # Las muestras se unen con tangentes exactas, así que basta muestrear cada 1-3 px
    # (error de cuerda < 0,2 px incluso en curvas cerradas).
    return max(1.0, min(3.0, min(widths)))


def _sample_line(a, b):
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, min(400, math.ceil(length / _pen_step(a[2], b[2]))))
    return [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)
            for t in (k / n for k in range(n + 1))]


def _sample_quad(a, c, b):
    length = math.hypot(c[0] - a[0], c[1] - a[1]) + math.hypot(b[0] - c[0], b[1] - c[1])
    n = max(1, min(400, math.ceil(length / _pen_step(a[2], b[2], c[2]))))
    out = []
    for k in range(n + 1):
        t = k / n
        u = 1 - t
        out.append(tuple(u * u * a[j] + 2 * u * t * c[j] + t * t * b[j] for j in range(3)))
    return out


def pen_piece(points, i: int):
    """Muestras de la porción de curva que se completa al llegar el punto ``i``."""
    if i == 0:
        return [points[0]]
    if i == 1:
        return _sample_line(points[0], _mid(points[0], points[1]))
    return _sample_quad(_mid(points[i - 2], points[i - 1]), points[i - 1], _mid(points[i - 1], points[i]))


def pen_tail(points):
    """Último tramo (del último punto medio al punto final); se dibuja al soltar."""
    if len(points) < 2:
        return []
    return _sample_line(_mid(points[-2], points[-1]), points[-1])


def _dedupe(samples):
    out = []
    for sm in samples:
        if out and abs(sm[0] - out[-1][0]) < 1e-6 and abs(sm[1] - out[-1][1]) < 1e-6:
            if sm[2] > out[-1][2]:
                out[-1] = sm
            continue
        out.append(sm)
    return out


def pen_outline(samples) -> QPainterPath:
    """Contorno exacto: círculo en cada muestra unido al siguiente por sus tangentes exteriores."""
    pts = _dedupe(samples)
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    if not pts:
        return path
    radii = [max(w / 2.0, 0.25) for _, _, w in pts]
    n = len(pts)
    quads = [_tangent_quad(pts[k][0], pts[k][1], radii[k], pts[k + 1][0], pts[k + 1][1], radii[k + 1])
             for k in range(n - 1)]
    for k in range(n):
        # Círculo en cada muestra: garantiza uniones redondeadas y sin rendijas aunque el
        # grosor cambie de una muestra a la siguiente (las tangentes no coinciden entonces).
        _add_poly(path, _circle_poly(pts[k][0], pts[k][1], radii[k]), check=False)
    for quad in quads:
        if quad is not None:
            _add_poly(path, quad)
    return path


def _fill_pen(p: QPainter, samples, color: QColor) -> None:
    if samples:
        p.fillPath(pen_outline(samples), color)


def pen_stroke_samples(points):
    if len(points) == 1:
        return [points[0]]
    dense = []
    for i in range(1, len(points)):
        dense += pen_piece(points, i)
    dense = _dedupe(dense + pen_tail(points))
    # Diezmado: una muestra cada ~1-3 px basta porque se unen con tangentes exactas.
    out = [dense[0]]
    for sm in dense[1:-1]:
        last = out[-1]
        if math.hypot(sm[0] - last[0], sm[1] - last[1]) >= _pen_step(sm[2], last[2]) * 0.9:
            out.append(sm)
    if len(dense) > 1:
        out.append(dense[-1])
    return out


def finalize_pen(item: StrokeItem) -> None:
    """Afina la salida del trazo (como cuando se levanta la pluma del papel)."""
    pts = item.points
    if not pts:
        return
    total = sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]) for k in range(len(pts) - 1))
    if total < 2.0:  # un toque: punto redondo de tamaño normal
        item.points = [(x, y, item.size * 0.9) for x, y, _ in pts]
        return
    length = min(pen_taper_length(item.size), total / 2.0)
    acc = 0.0
    for k in range(len(pts) - 1, -1, -1):
        if k < len(pts) - 1:
            acc += math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])
        if acc >= length:
            break
        x, y, w = pts[k]
        pts[k] = (x, y, max(0.5, w * (0.35 + 0.65 * acc / length)))


# --------------------------------------------------------------------------- trazos


def draw_segment(p: QPainter, item: StrokeItem, i: int, state: StrokeState) -> None:
    """Dibuja el segmento que termina en el punto ``i`` (``i == 0`` dibuja un punto)."""
    pts = item.points
    x1, y1, w1 = pts[i]
    first = i == 0
    x0, y0, w0 = pts[i] if first else pts[i - 1]
    color = item_color(item)
    tool = item.tool

    if tool in (Tool.ERASER, Tool.PENCIL):
        if abs(w0 - w1) < 0.01:
            _round_segment(p, x0, y0, x1, y1, w1, color)
        else:
            _variable_segment(p, x0, y0, w0, x1, y1, w1, color)
    elif tool == Tool.HIGHLIGHTER:
        _chisel_segment(p, x0, y0, x1, y1, w1, color)
    elif tool == Tool.PEN:
        _fill_pen(p, pen_piece(pts, i), color)
    else:  # pincel
        bt = item.brush
        if bt == BrushType.SOFT:
            _soft_segment(p, x0, y0, w0, x1, y1, w1, color, state, first)
        elif bt == BrushType.AIRBRUSH:
            _airbrush_segment(p, x0, y0, x1, y1, w1, color, state)
        elif bt == BrushType.CALLIGRAPHY:
            _calligraphy_segment(p, x0, y0, x1, y1, w1, color)
        elif abs(w0 - w1) < 0.01:
            _round_segment(p, x0, y0, x1, y1, w1, color)
        else:
            _variable_segment(p, x0, y0, w0, x1, y1, w1, color)


def segment_rect(item: StrokeItem, i: int) -> QRectF:
    pts = item.points
    if item.tool == Tool.PEN:  # la pieza de curva abarca los puntos i-2 .. i
        sub = pts[max(0, i - 2): i + 1]
        m = max(pt[2] for pt in sub) / 2 + 3
        xs = [pt[0] for pt in sub]
        ys = [pt[1] for pt in sub]
        return QRectF(min(xs) - m, min(ys) - m, max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m)
    x1, y1, w1 = pts[i]
    x0, y0, w0 = pts[i - 1] if i > 0 else pts[i]
    m = max(w0, w1) / 2 + 3
    if item.tool == Tool.BRUSH and item.brush == BrushType.AIRBRUSH:
        m += max(0.55, w1 / 45.0)
    return QRectF(min(x0, x1) - m, min(y0, y1) - m, abs(x1 - x0) + 2 * m, abs(y1 - y0) + 2 * m)


def draw_stroke(p: QPainter, item: StrokeItem) -> None:
    if item.tool == Tool.PEN:
        _fill_pen(p, pen_stroke_samples(item.points), item_color(item))
        return
    state = StrokeState(item.seed)
    for i in range(len(item.points)):
        draw_segment(p, item, i, state)


def stroke_rect(item: StrokeItem) -> QRectF:
    if not item.points:
        return QRectF()
    xs = [pt[0] for pt in item.points]
    ys = [pt[1] for pt in item.points]
    m = max(pt[2] for pt in item.points) / 2 + 4
    return QRectF(min(xs) - m, min(ys) - m, max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m)


# --------------------------------------------------------------------------- figuras


def constrain_shape(tool: Tool, x1, y1, x2, y2):
    """Con Mayús: proporciones iguales (cuadrado, círculo) o ángulos de 15° (línea/flecha)."""
    dx, dy = x2 - x1, y2 - y1
    if tool in (Tool.LINE, Tool.ARROW):
        length = math.hypot(dx, dy)
        if length == 0:
            return x2, y2
        step = math.radians(15)
        ang = round(math.atan2(dy, dx) / step) * step
        return x1 + math.cos(ang) * length, y1 + math.sin(ang) * length
    d = max(abs(dx), abs(dy))
    return x1 + math.copysign(d, dx or 1), y1 + math.copysign(d, dy or 1)


def arrow_head_length(size: float) -> float:
    return max(12.0, size * 3.5 + 6)


def draw_shape(p: QPainter, item: ShapeItem) -> None:
    color = item_color(item)
    w = max(item.size, 0.5)
    tool = item.tool
    x1, y1, x2, y2 = item.x1, item.y1, item.x2, item.y2
    rect = QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized()

    join = Qt.PenJoinStyle.RoundJoin if tool == Tool.ELLIPSE else Qt.PenJoinStyle.MiterJoin
    pen = QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, join)
    p.setPen(pen)
    p.setBrush(color if (item.filled and tool in FILLABLE_SHAPES) else Qt.BrushStyle.NoBrush)

    if tool == Tool.RECT:
        p.drawRect(rect)
    elif tool == Tool.ELLIPSE:
        p.drawEllipse(rect)
    elif tool == Tool.TRIANGLE:
        # El vértice queda del lado donde empezó el arrastre.
        apex = QPointF(rect.center().x(), y1)
        p.drawPolygon(QPolygonF([apex, QPointF(rect.left(), y2), QPointF(rect.right(), y2)]))
    elif tool == Tool.LINE:
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif tool == Tool.ARROW:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 0.5:
            return
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        head = min(arrow_head_length(w), length)
        half = head * 0.5
        bx, by = x2 - ux * head, y2 - uy * head
        shaft_end = QPointF(x2 - ux * head * 0.6, y2 - uy * head * 0.6)
        if length > head * 0.6:
            p.drawLine(QPointF(x1, y1), shaft_end)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([
            QPointF(x2, y2),
            QPointF(bx - uy * half, by + ux * half),
            QPointF(bx + uy * half, by - ux * half),
        ]))


def shape_rect(item: ShapeItem) -> QRectF:
    m = item.size * 2 + 6
    if item.tool == Tool.ARROW:
        m += arrow_head_length(item.size)
    return QRectF(QPointF(item.x1, item.y1), QPointF(item.x2, item.y2)).normalized().adjusted(-m, -m, m, m)


# --------------------------------------------------------------------------- genérico


def draw_item(p: QPainter, item) -> None:
    if isinstance(item, StrokeItem):
        draw_stroke(p, item)
    elif isinstance(item, ShapeItem):
        draw_shape(p, item)


def item_rect(item) -> QRectF:
    if isinstance(item, StrokeItem):
        return stroke_rect(item)
    if isinstance(item, ShapeItem):
        return shape_rect(item)
    return QRectF()


def is_eraser(item) -> bool:
    return isinstance(item, StrokeItem) and item.tool == Tool.ERASER


__all__ = [
    "StrokeState", "draw_segment", "segment_rect", "draw_stroke", "draw_shape", "shape_rect",
    "draw_item", "item_rect", "constrain_shape", "is_eraser", "ClearItem",
]
