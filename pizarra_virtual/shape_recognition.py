"""Reconocimiento de formas: convierte un trazo a mano alzada en una figura perfecta.

Es una opción que se activa o desactiva («Formas perfectas», tecla G). Al soltar el trazo:

- una recta se convierte en una línea (y se endereza a 0°, 45°, 90°… si está cerca);
- un trazo cerrado redondeado, en una elipse o un círculo;
- un trazo cerrado con 4 esquinas en ángulo recto y lados horizontales y verticales, en un
  rectángulo (o cuadrado);
- otro trazo cerrado con 3 a 6 esquinas (triángulo, rombo, rectángulo girado, pentágono…), en
  un polígono de lados rectos que respeta las esquinas dibujadas.

Si el trazo no se parece a ninguna forma se deja tal cual.
"""
from __future__ import annotations

import math

from .items import ShapeItem, StrokeItem
from .tools import BrushType, Tool

Point = tuple[float, float]

ANGLE_SNAP = math.radians(7)  # una línea casi horizontal/vertical/45° se endereza


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _seg_dist(p: Point, a: Point, b: Point) -> float:
    """Distancia del punto p al segmento ab."""
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    d2 = vx * vx + vy * vy
    if d2 == 0:
        return _dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * vx + (p[1] - ay) * vy) / d2))
    return math.hypot(p[0] - (ax + t * vx), p[1] - (ay + t * vy))


def _rdp(points: list[Point], eps: float) -> list[Point]:
    """Simplificación de Ramer-Douglas-Peucker (deja las esquinas)."""
    if len(points) < 3:
        return list(points)
    a, b = points[0], points[-1]
    idx, dmax = 0, -1.0
    for i in range(1, len(points) - 1):
        d = _seg_dist(points[i], a, b)
        if d > dmax:
            idx, dmax = i, d
    if dmax <= eps:
        return [a, b]
    left = _rdp(points[: idx + 1], eps)
    right = _rdp(points[idx:], eps)
    return left[:-1] + right


def _path_length(points: list[Point]) -> float:
    return sum(_dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def _stroke_width(stroke: StrokeItem) -> float:
    widths = [w for _x, _y, w in stroke.points if w > 0]
    if stroke.tool == Tool.PEN and widths:
        return max(1.0, sum(widths) / len(widths))
    return max(1.0, float(stroke.size))


def _snap_angle(a: Point, b: Point) -> Point:
    length = _dist(a, b)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    step = math.pi / 4
    target = round(ang / step) * step
    if abs(ang - target) <= ANGLE_SNAP:
        ang = target
    return a[0] + math.cos(ang) * length, a[1] + math.sin(ang) * length


def _corners(closed: list[Point], diag: float) -> list[Point]:
    """Esquinas de un trazo cerrado (sin repetir el punto inicial)."""
    # Empezar en el punto más alejado del inicio evita perder la esquina donde empezó el trazo.
    far = max(range(len(closed)), key=lambda i: _dist(closed[i], closed[0]))
    loop = closed[far:] + closed[1:far + 1]
    simple = _rdp(loop, max(4.0, diag * 0.07))[:-1]
    # Junta esquinas casi superpuestas y quita las que están en medio de un lado recto
    changed = True
    while changed and len(simple) > 3:
        changed = False
        for i in range(len(simple)):
            a, b, c = simple[i - 1], simple[i], simple[(i + 1) % len(simple)]
            if _dist(a, b) < diag * 0.12 or _seg_dist(b, a, c) < diag * 0.05:
                del simple[i]
                changed = True
                break
    return simple


def _polygon_error(points: list[Point], poly: list[Point]) -> float:
    edges = list(zip(poly, poly[1:] + poly[:1]))
    return sum(min(_seg_dist(p, a, b) for a, b in edges) for p in points) / len(points)


def _ellipse_error(points: list[Point]) -> tuple[float, tuple[float, float, float, float]]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, max(1.0, (x1 - x0) / 2), max(1.0, (y1 - y0) / 2)
    err = sum(abs(math.hypot((x - cx) / rx, (y - cy) / ry) - 1.0) for x, y in points) / len(points)
    # El trazo debe dar la vuelta completa (sin grandes huecos de ángulo)
    angles = sorted(math.atan2((y - cy) / ry, (x - cx) / rx) for x, y in points)
    gaps = [b - a for a, b in zip(angles, angles[1:])] + [angles[0] + 2 * math.pi - angles[-1]]
    if max(gaps) > math.radians(75):
        err = 1.0
    return err, (x0, y0, x1, y1)


def _angle_at(a: Point, b: Point, c: Point) -> float:
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n = math.hypot(*v1) * math.hypot(*v2)
    if n == 0:
        return 0.0
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))
    return math.degrees(math.acos(cos))


def _is_axis_rectangle(poly: list[Point]) -> bool:
    if len(poly) != 4:
        return False
    for i in range(4):
        if abs(_angle_at(poly[i - 1], poly[i], poly[(i + 1) % 4]) - 90) > 18:
            return False
        a, b = poly[i], poly[(i + 1) % 4]
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90
        if min(ang, 90 - ang) > 12:
            return False
    return True


def _polyline_stroke(stroke: StrokeItem, poly: list[Point], width: float) -> StrokeItem:
    """Polígono de lados rectos dibujado como trazo uniforme (respeta las esquinas dibujadas)."""
    pts = []
    loop = poly + poly[:1]
    for a, b in zip(loop, loop[1:]):
        n = max(1, int(_dist(a, b) // 3))
        for k in range(n):
            t = k / n
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, width))
    pts.append((loop[-1][0], loop[-1][1], width))
    return StrokeItem(Tool.BRUSH, stroke.rgba, width, stroke.opacity, BrushType.HARD, stroke.seed, pts)


def _smooth(points: list[Point], k: int = 2) -> list[Point]:
    """Media móvil: quita el temblor del pulso, que alargaría la longitud medida del trazo."""
    out = []
    for i in range(len(points)):
        win = points[max(0, i - k): i + k + 1]
        out.append((sum(p[0] for p in win) / len(win), sum(p[1] for p in win) / len(win)))
    out[0], out[-1] = points[0], points[-1]
    return out


def recognize(stroke: StrokeItem):
    """Figura perfecta equivalente al trazo, o None si no se parece a ninguna."""
    raw: list[Point] = []
    for x, y, _w in stroke.points:
        if not raw or _dist(raw[-1], (x, y)) >= 1.0:
            raw.append((x, y))
    if len(raw) < 4:
        return None
    pts = _smooth(raw)
    length = _path_length(pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    diag = math.hypot(w, h)
    if length < 30 or diag < 20:
        return None  # puntos, garabatos pequeños o letras: se dejan como están
    width = _stroke_width(stroke)
    start, end = pts[0], pts[-1]
    chord = _dist(start, end)

    # Recta: casi no se aparta de la cuerda y no vuelve atrás
    if chord >= length * 0.9 and max(_seg_dist(p, start, end) for p in pts) <= max(5.0, chord * 0.045):
        x2, y2 = _snap_angle(start, end)
        return ShapeItem(Tool.LINE, stroke.rgba, width, stroke.opacity, start[0], start[1], x2, y2)

    size = max(w, h)
    # Cerrado: el final vuelve cerca del inicio (también si se pasa un poco, como al dibujar
    # un círculo, que suele terminar más allá de donde empezó)
    tail = pts[int(len(pts) * 0.8):]
    returns = min(_dist(p, start) for p in tail) <= max(14.0, 0.12 * size)
    closed = (chord <= max(18.0, 0.25 * size) or returns) and length > 2.2 * size
    if not closed or min(w, h) < 12:
        return None
    loop = pts + [pts[0]]
    poly = _corners(loop, diag)
    poly_err = _polygon_error(pts, poly) / diag if len(poly) >= 3 else 1.0
    ell_err, (x0, y0, x1, y1) = _ellipse_error(pts)

    if 5 <= len(poly) <= 6 and poly_err < 0.02:  # pentágono, hexágono (antes que la elipse)
        return _polyline_stroke(stroke, poly, width)
    if len(poly) in (3, 4) and poly_err < 0.035 and not (len(poly) == 4 and ell_err < poly_err * 0.6):
        if _is_axis_rectangle(poly):
            px = [p[0] for p in poly]
            py = [p[1] for p in poly]
            return ShapeItem(Tool.RECT, stroke.rgba, width, stroke.opacity, min(px), min(py), max(px), max(py))
        return _polyline_stroke(stroke, poly, width)
    if ell_err < 0.11:
        if abs((x1 - x0) - (y1 - y0)) <= 0.15 * max(x1 - x0, y1 - y0):  # casi redondo: círculo
            cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, ((x1 - x0) + (y1 - y0)) / 4
            x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r
        return ShapeItem(Tool.ELLIPSE, stroke.rgba, width, stroke.opacity, x0, y0, x1, y1)
    return None
