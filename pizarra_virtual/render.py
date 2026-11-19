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
from dataclasses import replace

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient,
)

from .items import ClearItem, GroupItem, ShapeItem, StampItem, StrokeItem, TextItem
from .tools import FILLABLE_SHAPES, LINEAR_SHAPES, POLYGON_SIDES, BrushType, Tool

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
    if tool in LINEAR_SHAPES:
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

    rounded = (Tool.ELLIPSE, Tool.STAR, Tool.ROUNDED_RECT, Tool.CURVED_ARROW, Tool.BRACE)
    join = Qt.PenJoinStyle.RoundJoin if tool in rounded else Qt.PenJoinStyle.MiterJoin
    pen = QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, join)
    p.setPen(pen)
    p.setBrush(color if (item.filled and tool in FILLABLE_SHAPES) else Qt.BrushStyle.NoBrush)

    if tool in EXTRA_DRAWERS:
        EXTRA_DRAWERS[tool](p, item, rect, color, w)
    elif tool == Tool.RECT:
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
        head = min(arrow_head_length(w), length)
        if length > head * 0.6:
            p.drawLine(QPointF(x1, y1), _toward(QPointF(x2, y2), QPointF(x1, y1), head * 0.6))
        _arrow_head(p, QPointF(x1, y1), QPointF(x2, y2), head, color)


def _toward(tip: QPointF, origin: QPointF, dist: float) -> QPointF:
    """Punto a ``dist`` de ``tip`` en dirección a ``origin``."""
    dx, dy = origin.x() - tip.x(), origin.y() - tip.y()
    n = math.hypot(dx, dy) or 1.0
    return QPointF(tip.x() + dx / n * dist, tip.y() + dy / n * dist)


def _arrow_head(p: QPainter, frm: QPointF, tip: QPointF, head: float, color: QColor) -> None:
    """Punta de flecha rellena en ``tip`` orientada según la dirección frm → tip."""
    dx, dy = tip.x() - frm.x(), tip.y() - frm.y()
    n = math.hypot(dx, dy)
    if n < 1e-6:
        return
    ux, uy = dx / n, dy / n
    half = head * 0.5
    bx, by = tip.x() - ux * head, tip.y() - uy * head
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPolygon(QPolygonF([tip, QPointF(bx - uy * half, by + ux * half), QPointF(bx + uy * half, by - ux * half)]))
    p.restore()


def _regular_polygon(rect: QRectF, sides: int, inner: float = 0.0) -> QPolygonF:
    """Polígono regular inscrito en el rectángulo (con ``inner`` > 0, estrella de ``sides`` puntas)."""
    cx, cy, rx, ry = rect.center().x(), rect.center().y(), rect.width() / 2, rect.height() / 2
    pts = []
    n = sides * 2 if inner else sides
    for k in range(n):
        a = -math.pi / 2 + k * 2 * math.pi / n
        f = inner if (inner and k % 2) else 1.0
        pts.append(QPointF(cx + rx * f * math.cos(a), cy + ry * f * math.sin(a)))
    return QPolygonF(pts)


def _draw_polygon(p, item, rect, color, w):
    p.drawPolygon(_regular_polygon(rect, POLYGON_SIDES[item.tool]))


def _draw_diamond(p, item, rect, color, w):
    c = rect.center()
    p.drawPolygon(QPolygonF([QPointF(c.x(), rect.top()), QPointF(rect.right(), c.y()),
                             QPointF(c.x(), rect.bottom()), QPointF(rect.left(), c.y())]))


def _draw_star(p, item, rect, color, w):
    p.drawPolygon(_regular_polygon(rect, 5, inner=0.42))


def _draw_rounded_rect(p, item, rect, color, w):
    r = min(rect.width(), rect.height()) * 0.2
    p.drawRoundedRect(rect, r, r)


def _draw_double_arrow(p, item, rect, color, w):
    a, b = QPointF(item.x1, item.y1), QPointF(item.x2, item.y2)
    length = math.hypot(b.x() - a.x(), b.y() - a.y())
    if length < 0.5:
        return
    head = min(arrow_head_length(w), length / 2)
    if length > head * 1.2:
        p.drawLine(_toward(a, b, head * 0.6), _toward(b, a, head * 0.6))
    _arrow_head(p, b, a, head, color)
    _arrow_head(p, a, b, head, color)


def curved_control(item) -> QPointF:
    """Punto de control de la flecha curva: se curva hacia la izquierda del sentido del trazo."""
    mx, my = (item.x1 + item.x2) / 2, (item.y1 + item.y2) / 2
    dx, dy = item.x2 - item.x1, item.y2 - item.y1
    return QPointF(mx + dy * 0.35, my - dx * 0.35)


def _draw_curved_arrow(p, item, rect, color, w):
    a, b = QPointF(item.x1, item.y1), QPointF(item.x2, item.y2)
    length = math.hypot(b.x() - a.x(), b.y() - a.y())
    if length < 0.5:
        return
    ctrl = curved_control(item)
    head = min(arrow_head_length(w), length * 0.6)
    path = QPainterPath(a)
    path.quadTo(ctrl, b)
    # el trazo termina un poco antes de la punta para que no asome por ella
    t_end = max(0.0, 1.0 - (head * 0.6) / max(path.length(), 1.0))
    trimmed = QPainterPath(a)
    steps = 48
    for i in range(1, steps + 1):
        trimmed.lineTo(path.pointAtPercent(t_end * i / steps))
    p.save()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(trimmed)
    p.restore()
    # dirección de la punta: tangente al final de la curva
    _arrow_head(p, path.pointAtPercent(max(0.0, 1.0 - head / max(path.length(), 1.0))), b, head, color)


def _draw_axes(p, item, rect, color, w):
    """Ejes de coordenadas: se cruzan en el centro del recuadro, con flechas, marcas y «x», «y»."""
    if rect.width() < 4 or rect.height() < 4:
        return
    c = rect.center()
    head = arrow_head_length(w)
    p.drawLine(QPointF(rect.left(), c.y()), QPointF(rect.right() - head * 0.6, c.y()))
    p.drawLine(QPointF(c.x(), rect.bottom()), QPointF(c.x(), rect.top() + head * 0.6))
    _arrow_head(p, QPointF(rect.left(), c.y()), QPointF(rect.right(), c.y()), head, color)
    _arrow_head(p, QPointF(c.x(), rect.bottom()), QPointF(c.x(), rect.top()), head, color)
    step = max(18.0, w * 6)
    tick = max(4.0, w * 1.6)
    thin = QPen(p.pen())
    thin.setWidthF(max(1.0, w * 0.6))
    p.save()
    p.setPen(thin)
    k = 1
    while c.x() + k * step < rect.right() - head * 1.5 or c.x() - k * step > rect.left() + 2:
        for x in (c.x() + k * step, c.x() - k * step):
            if rect.left() + 2 < x < rect.right() - head * 1.5:
                p.drawLine(QPointF(x, c.y() - tick), QPointF(x, c.y() + tick))
        k += 1
    k = 1
    while c.y() - k * step > rect.top() + head * 1.5 or c.y() + k * step < rect.bottom() - 2:
        for y in (c.y() - k * step, c.y() + k * step):
            if rect.top() + head * 1.5 < y < rect.bottom() - 2:
                p.drawLine(QPointF(c.x() - tick, y), QPointF(c.x() + tick, y))
        k += 1
    f = QFont()
    f.setFamilies(TEXT_FAMILIES)
    f.setItalic(True)
    f.setPixelSize(int(max(13, w * 5)))
    p.setFont(f)
    p.drawText(QPointF(rect.right() - f.pixelSize() * 0.7, c.y() + head + f.pixelSize()), "x")
    p.drawText(QPointF(c.x() + head * 0.8, rect.top() + f.pixelSize()), "y")
    p.restore()


def _draw_brace(p, item, rect, color, w):
    """Llave «{»: a lo largo del lado largo del recuadro; el pico apunta al lado donde empezó el arrastre."""
    p.save()
    p.setBrush(Qt.BrushStyle.NoBrush)
    vertical = rect.height() >= rect.width()
    if vertical:
        tip, back = (rect.left(), rect.right()) if item.x1 <= item.x2 else (rect.right(), rect.left())
        a, b = rect.top(), rect.bottom()
    else:
        tip, back = (rect.top(), rect.bottom()) if item.y1 <= item.y2 else (rect.bottom(), rect.top())
        a, b = rect.left(), rect.right()
    mid = (tip + back) / 2
    m = (a + b) / 2
    r = min((b - a) / 4, abs(back - tip))

    def pt(u, v):  # u: coordenada a lo largo de la llave; v: hacia el pico
        return QPointF(v, u) if vertical else QPointF(u, v)

    path = QPainterPath(pt(a, back))
    path.quadTo(pt(a, mid), pt(a + r, mid))
    path.lineTo(pt(m - r, mid))
    path.quadTo(pt(m, mid), pt(m, tip))
    path.quadTo(pt(m, mid), pt(m + r, mid))
    path.lineTo(pt(b - r, mid))
    path.quadTo(pt(b, mid), pt(b, back))
    p.drawPath(path)
    p.restore()


EXTRA_DRAWERS = {
    Tool.PENTAGON: _draw_polygon, Tool.HEXAGON: _draw_polygon, Tool.OCTAGON: _draw_polygon,
    Tool.DIAMOND: _draw_diamond, Tool.STAR: _draw_star, Tool.ROUNDED_RECT: _draw_rounded_rect,
    Tool.AXES: _draw_axes, Tool.DOUBLE_ARROW: _draw_double_arrow, Tool.CURVED_ARROW: _draw_curved_arrow,
    Tool.BRACE: _draw_brace,
}


def shape_rect(item: ShapeItem) -> QRectF:
    m = item.size * 2 + 6
    if item.tool in (Tool.ARROW, Tool.DOUBLE_ARROW, Tool.CURVED_ARROW, Tool.AXES):
        m += arrow_head_length(item.size)
    if item.tool == Tool.AXES:
        m += max(13, item.size * 5) * 2  # rótulos «x» e «y»
    rect = QRectF(QPointF(item.x1, item.y1), QPointF(item.x2, item.y2)).normalized()
    if item.tool == Tool.CURVED_ARROW:
        rect = rect.united(QRectF(curved_control(item), QSizeF(1, 1)))
    return rect.adjusted(-m, -m, m, m)


# --------------------------------------------------------------------------- texto

TEXT_FAMILIES = ["Segoe UI", "Arial", "Helvetica", "DejaVu Sans", "sans-serif"]


def text_font(item: TextItem) -> QFont:
    f = QFont()
    f.setFamilies(TEXT_FAMILIES)
    f.setPixelSize(max(4, int(round(item.size))))
    f.setBold(item.bold)
    return f


def text_lines(item: TextItem) -> list[str]:
    return item.text.split("\n") if item.text else [""]


def text_box(item: TextItem) -> QRectF:
    """Rectángulo que ocupa el texto (sin márgenes)."""
    fm = QFontMetricsF(text_font(item))
    lines = text_lines(item)
    width = max([fm.horizontalAdvance(line) for line in lines] + [fm.averageCharWidth()])
    return QRectF(item.x, item.y, width, fm.lineSpacing() * len(lines))


def text_caret(item: TextItem, index: int | None = None) -> tuple[QPointF, QPointF]:
    """Extremos del cursor de escritura en la posición ``index`` del texto (por defecto, al final)."""
    fm = QFontMetricsF(text_font(item))
    index = len(item.text) if index is None else max(0, min(len(item.text), index))
    before = item.text[:index].split("\n")
    x = item.x + fm.horizontalAdvance(before[-1])
    top = item.y + fm.lineSpacing() * (len(before) - 1)
    return QPointF(x + 1, top + 2), QPointF(x + 1, top + fm.height() - 2)


def text_line_col(text: str, index: int) -> tuple[int, int]:
    before = text[:index].split("\n")
    return len(before) - 1, len(before[-1])


def text_index(text: str, line: int, col: int) -> int:
    """Posición absoluta de (línea, columna), ajustada a los límites del texto."""
    lines = text.split("\n")
    line = max(0, min(len(lines) - 1, line))
    col = max(0, min(len(lines[line]), col))
    return sum(len(ln) + 1 for ln in lines[:line]) + col


def text_index_at(item: TextItem, pos: QPointF) -> int:
    """Posición del texto más cercana a un punto (para colocar el cursor con un clic)."""
    fm = QFontMetricsF(text_font(item))
    lines = text_lines(item)
    line = max(0, min(len(lines) - 1, int((pos.y() - item.y) // fm.lineSpacing())))
    dx = pos.x() - item.x
    text = lines[line]
    col = min(range(len(text) + 1), key=lambda k: abs(fm.horizontalAdvance(text[:k]) - dx))
    return text_index(item.text, line, col)


def erasers_after(items: list, index: int) -> list | None:
    """Gomas aplicadas después del elemento ``index``; None si después hubo «Borrar todo»."""
    later = items[index + 1:]
    if any(isinstance(i, ClearItem) for i in later):
        return None
    return [i for i in later if is_eraser(i)]


def apply_erasers(p: QPainter, erasers) -> None:
    """Borra con las gomas indicadas lo pintado en ``p`` (DestinationOut)."""
    if not erasers:
        return
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    for e in erasers:
        draw_item(p, e)
    p.restore()


def text_ink_near(item: TextItem, erasers, pos: QPointF, radius: float) -> bool:
    """¿Queda tinta visible de este texto (tras las gomas) a menos de ``radius`` del punto?

    Así un texto borrado con la goma deja de poder abrirse para editarlo, y en uno borrado a
    medias solo cuenta la parte que todavía se ve.
    """
    if erasers is None:
        return False
    side = int(math.ceil(2 * radius)) + 2
    img = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(side / 2 - pos.x(), side / 2 - pos.y())
    draw_text(p, replace(item, opacity=1.0))
    apply_erasers(p, erasers)
    p.end()
    c = side / 2
    r2 = radius * radius
    for y in range(side):
        for x in range(side):
            if (x - c) ** 2 + (y - c) ** 2 <= r2 and img.pixelColor(x, y).alpha() > 40:
                return True
    return False


def text_hit_rect(item: TextItem) -> QRectF:
    """Zona donde un clic con la herramienta Texto abre ese texto para editarlo."""
    return text_box(item).adjusted(-6, -6, 6, 6)


def draw_text(p: QPainter, item: TextItem) -> None:
    font = text_font(item)
    fm = QFontMetricsF(font)
    p.setFont(font)
    p.setPen(item_color(item))
    for i, line in enumerate(text_lines(item)):
        if line:
            p.drawText(QPointF(item.x, item.y + fm.ascent() + i * fm.lineSpacing()), line)


# --------------------------------------------------------------------------- pautas de fondo

PAPER_COLORS = {"white": QColor(255, 255, 255), "chalk": QColor(31, 58, 46)}


def pattern_colors(background: str) -> tuple[QColor, QColor]:
    """(línea suave, línea marcada) según el fondo, para que la pauta se vea en todos."""
    if background == "white":
        return QColor(120, 150, 190, 120), QColor(60, 90, 140, 220)
    if background in ("chalk", "dim"):
        return QColor(255, 255, 255, 70), QColor(255, 255, 255, 170)
    return QColor(70, 110, 170, 110), QColor(40, 80, 150, 210)  # sobre el escritorio


def draw_pattern(p: QPainter, w: float, h: float, pattern: str, background: str) -> None:
    """Dibuja la pauta en un área de w x h píxeles lógicos."""
    if pattern in (None, "", "none"):
        return
    soft, strong = pattern_colors(background)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def hline(y, color, width=1.0, x0=0.0, x1=None, dash=False):
        pen = QPen(color, width)
        if dash:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(x0, y), QPointF(w if x1 is None else x1, y))

    def vline(x, color, width=1.0):
        p.setPen(QPen(color, width))
        p.drawLine(QPointF(x, 0), QPointF(x, h))

    if pattern == "grid":
        step = 32
        for i in range(0, int(w // step) + 1):
            vline(i * step + 0.5, strong if i % 5 == 0 else soft)
        for i in range(0, int(h // step) + 1):
            hline(i * step + 0.5, strong if i % 5 == 0 else soft)
    elif pattern == "mm":
        # Milimetrado: líneas finas cada 8 px, intermedias cada 5 y marcadas cada 10 (como 1, 5 y 10 mm).
        step = 8
        fine = QColor(soft)
        fine.setAlpha(max(25, soft.alpha() // 2))
        for i in range(0, int(w // step) + 1):
            vline(i * step + 0.5, strong if i % 10 == 0 else soft if i % 5 == 0 else fine,
                  1.4 if i % 10 == 0 else 1.0)
        for i in range(0, int(h // step) + 1):
            hline(i * step + 0.5, strong if i % 10 == 0 else soft if i % 5 == 0 else fine,
                  1.4 if i % 10 == 0 else 1.0)
    elif pattern == "ruled":
        y = 96.5
        while y < h:
            hline(y, soft, 1.2)
            y += 36
        p.setPen(QPen(QColor(220, 70, 70, 170), 1.5))
        p.drawLine(QPointF(96.5, 0), QPointF(96.5, h))
    elif pattern == "calligraphy":
        # Pauta de 4 líneas: ascendentes, altura de la x (discontinua), base (marcada), descendentes.
        unit, gap = 30, 34
        y = 70.5 if h >= 300 else 10.5  # en áreas pequeñas empieza más arriba para que quepa
        while y + 3 * unit < h:
            hline(y, soft)
            hline(y + unit, soft, 1.0, dash=True)
            hline(y + 2 * unit, strong, 1.6)
            hline(y + 3 * unit, soft)
            y += 3 * unit + gap
    elif pattern == "staff":
        line_gap, group_gap = 14, 74
        y = 80.5 if h >= 300 else 10.5
        while y + 4 * line_gap < h:
            for k in range(5):
                hline(y + k * line_gap, strong, 1.2, x0=48, x1=w - 48)
            y += 4 * line_gap + group_gap
    elif pattern == "cartesian":
        unit = 40
        cx, cy = round(w / 2) + 0.5, round(h / 2) + 0.5
        k = 0
        while cx + k * unit < w or cx - k * unit > 0:
            for x in (cx + k * unit, cx - k * unit):
                vline(x, soft)
            k += 1
        k = 0
        while cy + k * unit < h or cy - k * unit > 0:
            for y in (cy + k * unit, cy - k * unit):
                hline(y, soft)
            k += 1
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        axis = QPen(strong, 2.0)
        p.setPen(axis)
        p.drawLine(QPointF(0, cy), QPointF(w - 4, cy))
        p.drawLine(QPointF(cx, h), QPointF(cx, 4))
        p.setBrush(strong)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(w - 2, cy), QPointF(w - 14, cy - 6), QPointF(w - 14, cy + 6)]))
        p.drawPolygon(QPolygonF([QPointF(cx, 2), QPointF(cx - 6, 14), QPointF(cx + 6, 14)]))
        f = QFont()
        f.setFamilies(TEXT_FAMILIES)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(strong)
        n = 1
        while cx + n * unit < w - 20 or cy - n * unit > 20:
            for val, x, y in ((n, cx + n * unit, cy), (-n, cx - n * unit, cy)):
                if 4 < x < w - 20:
                    p.drawText(QRectF(x - 15, y + 3, 30, 14), Qt.AlignmentFlag.AlignHCenter, str(val))
            for val, x, y in ((n, cx, cy - n * unit), (-n, cx, cy + n * unit)):
                if 20 < y < h - 8:
                    p.drawText(QRectF(x - 34, y - 7, 30, 14), Qt.AlignmentFlag.AlignRight, str(val))
            n += 1
        p.drawText(QRectF(w - 22, cy + 6, 16, 14), Qt.AlignmentFlag.AlignHCenter, "x")
        p.drawText(QRectF(cx + 8, 6, 16, 14), Qt.AlignmentFlag.AlignLeft, "y")
    p.restore()


# --------------------------------------------------------------------------- genérico


# --------------------------------------------------------------------------- sellos

STAMP_COLORS = {
    "check": QColor(46, 125, 50), "cross": QColor(198, 40, 40), "star": QColor(251, 192, 45),
    "smiley": QColor(253, 216, 53), "question": QColor(30, 136, 229),
}


def _stamp_stroke(p: QPainter, path: QPainterPath, color: QColor, width: float) -> None:
    """Trazo grueso con borde blanco, visible sobre fondos claros y oscuros."""
    for col, w in ((QColor(255, 255, 255, 235), width * 1.55), (color, width)):
        p.setPen(QPen(col, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


def _badge(p: QPainter, c: QPointF, r: float, fill: QColor, text: str) -> None:
    p.setPen(QPen(QColor(255, 255, 255), max(1.5, r * 0.12)))
    p.setBrush(fill)
    p.drawEllipse(c, r, r)
    f = QFont()
    f.setFamilies(TEXT_FAMILIES)
    f.setBold(True)
    f.setPixelSize(max(6, int(r * (1.15 if len(text) < 2 else 0.9 if len(text) < 3 else 0.7))))
    p.setFont(f)
    p.setPen(QColor(255, 255, 255))
    p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, text)


def draw_stamp(p: QPainter, item: StampItem) -> None:
    s = max(4.0, item.size)
    c = QPointF(item.x, item.y)
    k = item.kind
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if k == "check":
        path = QPainterPath(QPointF(c.x() - s * 0.36, c.y() + s * 0.02))
        path.lineTo(c.x() - s * 0.1, c.y() + s * 0.28)
        path.lineTo(c.x() + s * 0.4, c.y() - s * 0.3)
        _stamp_stroke(p, path, STAMP_COLORS["check"], s * 0.14)
    elif k == "cross":
        d = s * 0.3
        path = QPainterPath(QPointF(c.x() - d, c.y() - d))
        path.lineTo(c.x() + d, c.y() + d)
        path.moveTo(c.x() + d, c.y() - d)
        path.lineTo(c.x() - d, c.y() + d)
        _stamp_stroke(p, path, STAMP_COLORS["cross"], s * 0.14)
    elif k == "star":
        star = _regular_polygon(QRectF(c.x() - s / 2, c.y() - s / 2 + s * 0.03, s, s), 5, inner=0.45)
        p.setPen(QPen(QColor(230, 81, 0), max(1.0, s * 0.045), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(STAMP_COLORS["star"])
        p.drawPolygon(star)
    elif k == "smiley":
        r = s / 2
        p.setPen(QPen(QColor(249, 168, 37), max(1.0, s * 0.045)))
        p.setBrush(STAMP_COLORS["smiley"])
        p.drawEllipse(c, r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(60, 45, 30))
        for dx in (-0.17, 0.17):
            p.drawEllipse(QPointF(c.x() + dx * s, c.y() - 0.1 * s), s * 0.055, s * 0.085)
        smile = QPainterPath(QPointF(c.x() - 0.24 * s, c.y() + 0.08 * s))
        smile.quadTo(QPointF(c.x(), c.y() + 0.38 * s), QPointF(c.x() + 0.24 * s, c.y() + 0.08 * s))
        p.setPen(QPen(QColor(60, 45, 30), max(1.0, s * 0.055), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(smile)
    elif k == "number":
        _badge(p, c, s / 2, QColor(*item.rgba[:3]), item.label or "1")
    elif k == "question":
        _badge(p, c, s / 2, STAMP_COLORS["question"], "?")
    p.restore()


def draw_item(p: QPainter, item) -> None:
    if isinstance(item, StrokeItem):
        draw_stroke(p, item)
    elif isinstance(item, ShapeItem):
        draw_shape(p, item)
    elif isinstance(item, TextItem):
        draw_text(p, item)
    elif isinstance(item, StampItem):
        draw_stamp(p, item)
    elif isinstance(item, GroupItem):
        for sub in item.items:
            draw_item(p, sub)


def item_rect(item) -> QRectF:
    if isinstance(item, StrokeItem):
        return stroke_rect(item)
    if isinstance(item, ShapeItem):
        return shape_rect(item)
    if isinstance(item, TextItem):
        return text_box(item).adjusted(-4, -4, item.size + 8, 6)
    if isinstance(item, StampItem):
        r = item.size * 0.62 + 4
        return QRectF(item.x - r, item.y - r, 2 * r, 2 * r)
    if isinstance(item, GroupItem):
        rect = QRectF()
        for sub in item.items:
            rect = rect.united(item_rect(sub))
        return rect
    return QRectF()


def is_eraser(item) -> bool:
    return isinstance(item, StrokeItem) and item.tool == Tool.ERASER


def apply_item_to_canvas(canvas: QImage, layer: QImage, item) -> None:
    """Aplica un elemento del historial al lienzo.

    ``layer`` es una imagen auxiliar transparente del mismo tamaño: cada trazo se pinta
    primero opaco en ella y luego se compone con su opacidad, así un destacador no se
    oscurece donde el propio trazo se superpone. Al terminar, ``layer`` queda limpia.
    """
    if isinstance(item, ClearItem):
        canvas.fill(Qt.GlobalColor.transparent)
        return
    if isinstance(item, GroupItem):  # cada elemento con su propia opacidad
        for sub in item.items:
            apply_item_to_canvas(canvas, layer, sub)
        return
    if is_eraser(item):
        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        draw_item(p, item)
        p.end()
        return
    rect = item_rect(item).adjusted(-2, -2, 2, 2)
    p = QPainter(layer)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_item(p, item)
    p.end()
    p = QPainter(canvas)
    p.setClipRect(rect)
    p.setOpacity(max(0.0, min(1.0, item.opacity)))
    p.drawImage(QPointF(0, 0), layer)
    p.end()
    p = QPainter(layer)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    p.fillRect(rect, Qt.GlobalColor.transparent)
    p.end()


__all__ = [
    "StrokeState", "draw_segment", "segment_rect", "draw_stroke", "draw_shape", "shape_rect",
    "draw_item", "item_rect", "constrain_shape", "is_eraser", "ClearItem", "apply_item_to_canvas",
    "draw_pattern", "draw_text", "text_box", "text_caret",
]
