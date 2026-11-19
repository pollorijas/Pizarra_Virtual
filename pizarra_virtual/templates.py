"""Plantillas para la clase: mapa conceptual, línea de tiempo, diagramas de Venn, tablas, etc.

Cada plantilla se construye con elementos normales (figuras y textos) dentro de un GroupItem:
se inserta y se deshace de una vez, y cada texto se puede editar después con la herramienta
Texto (clic sobre él), moverse o borrarse con la goma como cualquier otro texto.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF

from . import render
from .items import GroupItem, ShapeItem, TextItem
from .tools import Tool

Rgba = tuple[int, int, int, int]

VENN_COLORS = [(30, 136, 229, 255), (229, 57, 53, 255), (67, 160, 71, 255)]


class _Builder:
    def __init__(self, area: QRectF, rgba: Rgba, line: float):
        self.area = area
        self.rgba = rgba
        self.line = max(1.0, line)
        self.text_size = max(16.0, min(44.0, area.height() / 16))
        self.items: list = []

    # --- piezas
    def text(self, cx: float, cy: float, text: str, size: float | None = None, bold: bool = False,
             rgba: Rgba | None = None, max_width: float | None = None) -> TextItem:
        """Texto centrado en (cx, cy); si no cabe en ``max_width``, se reduce la letra."""
        item = TextItem(rgba or self.rgba, size or self.text_size, 1.0, 0, 0, text, bold)
        while max_width and item.size > 10 and render.text_box(item).width() > max_width:
            item.size = max(10.0, item.size * 0.92)
        box = render.text_box(item)
        item.x, item.y = cx - box.width() / 2, cy - box.height() / 2
        self.items.append(item)
        return item

    def shape(self, tool: Tool, x1, y1, x2, y2, rgba: Rgba | None = None, size: float | None = None):
        item = ShapeItem(tool, rgba or self.rgba, size or self.line, 1.0, x1, y1, x2, y2)
        self.items.append(item)
        return item

    def box(self, rect: QRectF, label: str = "", bold: bool = False, rounded: bool = True,
            size: float | None = None) -> QRectF:
        if label:  # el recuadro crece si el texto no cabe
            probe = TextItem(self.rgba, size or self.text_size, 1.0, 0, 0, label, bold)
            need = render.text_box(probe).width() + (size or self.text_size) * 1.2
            if need > rect.width():
                rect = QRectF(rect.center().x() - need / 2, rect.top(), need, rect.height())
        self.shape(Tool.ROUNDED_RECT if rounded else Tool.RECT, rect.left(), rect.top(), rect.right(), rect.bottom())
        if label:
            self.text(rect.center().x(), rect.center().y(), label, size, bold)
        return rect

    def connect(self, a: QRectF, b: QRectF, arrow: bool = False) -> None:
        """Línea (o flecha) entre los bordes de dos recuadros, en la dirección de sus centros."""
        p1 = _edge_point(a, b.center())
        p2 = _edge_point(b, a.center())
        self.shape(Tool.ARROW if arrow else Tool.LINE, p1.x(), p1.y(), p2.x(), p2.y())

    def group(self) -> GroupItem:
        return GroupItem(self.items)


def _edge_point(rect: QRectF, toward: QPointF) -> QPointF:
    """Punto del borde de ``rect`` en la recta que va de su centro a ``toward``."""
    c = rect.center()
    dx, dy = toward.x() - c.x(), toward.y() - c.y()
    if dx == 0 and dy == 0:
        return c
    sx = (rect.width() / 2) / abs(dx) if dx else math.inf
    sy = (rect.height() / 2) / abs(dy) if dy else math.inf
    s = min(sx, sy)
    return QPointF(c.x() + dx * s, c.y() + dy * s)


def _rect(cx, cy, w, h) -> QRectF:
    return QRectF(cx - w / 2, cy - h / 2, w, h)


# ---------------------------------------------------------------------------- plantillas

def concept_map(b: _Builder) -> None:
    a = b.area
    cw, ch = a.width() * 0.26, a.height() * 0.17
    center = b.box(_rect(a.center().x(), a.center().y(), cw, ch), "Tema central", bold=True,
                   size=b.text_size * 1.15)
    w, h = a.width() * 0.2, a.height() * 0.14
    spots = [(0.16, 0.14), (0.84, 0.14), (0.16, 0.86), (0.84, 0.86), (0.5, 0.1), (0.5, 0.9)]
    for i, (fx, fy) in enumerate(spots[:4]):
        idea = b.box(_rect(a.left() + a.width() * fx, a.top() + a.height() * fy, w, h), f"Idea {i + 1}")
        b.connect(center, idea)


def timeline(b: _Builder) -> None:
    a = b.area
    y = a.center().y()
    x0, x1 = a.left() + a.width() * 0.03, a.right() - a.width() * 0.02
    b.shape(Tool.ARROW, x0, y, x1, y, size=b.line * 1.4)
    n = 5
    span = (x1 - x0) * 0.9
    tick = a.height() * 0.05
    for i in range(n):
        x = x0 + span * (i + 0.5) / n
        b.shape(Tool.LINE, x, y - tick, x, y + tick)
        room = span / n * 0.92
        b.text(x, y - tick - b.text_size * 0.9, f"Fecha {i + 1}", bold=True, max_width=room)
        up = i % 2 == 0
        b.text(x, y + tick + b.text_size * (1.0 if up else 2.4), "Evento", max_width=room * 1.8)


def venn(b: _Builder, sets: int) -> None:
    a = b.area
    labels = ["Conjunto A", "Conjunto B", "Conjunto C"]
    if sets == 2:
        r = min(a.width() * 0.26, a.height() * 0.46)
        cy = a.center().y() + b.text_size * 0.6
        centers = [QPointF(a.center().x() - r * 0.55, cy), QPointF(a.center().x() + r * 0.55, cy)]
    else:
        r = min(a.width() * 0.2, a.height() * 0.3)
        cx, cy = a.center().x(), a.center().y() + b.text_size * 0.5
        centers = [QPointF(cx - r * 0.55, cy - r * 0.38), QPointF(cx + r * 0.55, cy - r * 0.38),
                   QPointF(cx, cy + r * 0.55)]
    for i, c in enumerate(centers):
        b.shape(Tool.ELLIPSE, c.x() - r, c.y() - r, c.x() + r, c.y() + r, rgba=VENN_COLORS[i])
    if sets == 2:
        for c, lab, sx in zip(centers, labels, (-1, 1)):
            b.text(c.x() + sx * r * 0.45, c.y(), lab.split()[-1], size=b.text_size * 1.2, bold=True,
                   rgba=VENN_COLORS[(sx + 1) // 2])
            b.text(c.x() + sx * r * 0.2, c.y() - r - b.text_size * 0.9, lab, bold=True,
                   rgba=VENN_COLORS[(sx + 1) // 2])
        b.text((centers[0].x() + centers[1].x()) / 2, centers[0].y(), "Ambos")
    else:
        for i, (c, lab) in enumerate(zip(centers, labels)):
            ox, oy = [(-0.45, -0.3), (0.45, -0.3), (0, 0.45)][i]
            b.text(c.x() + ox * r, c.y() + oy * r, lab.split()[-1], size=b.text_size * 1.2, bold=True,
                   rgba=VENN_COLORS[i])
        mid = QPointF(sum(c.x() for c in centers) / 3, sum(c.y() for c in centers) / 3)
        b.text(mid.x(), mid.y(), "Todos", size=b.text_size * 0.8)


def t_chart(b: _Builder) -> None:
    a = b.area
    # Posiciones a partir de la altura real del texto (cambia según la fuente: Segoe UI es más alta)
    title = b.text(a.center().x(), 0, "Título", size=b.text_size * 1.2, bold=True)
    title.y = a.top() + a.height() * 0.04
    labels = []
    for fx, label in ((0.275, "Ventajas"), (0.725, "Desventajas")):
        labels.append(b.text(a.left() + a.width() * fx, 0, label, bold=True, max_width=a.width() * 0.42))
    header_top = render.text_box(title).bottom() + b.text_size * 0.35
    for item in labels:
        item.y = header_top
    head = max(render.text_box(i).bottom() for i in labels) + b.text_size * 0.3
    b.shape(Tool.LINE, a.left() + a.width() * 0.05, head, a.right() - a.width() * 0.05, head, size=b.line * 1.3)
    b.shape(Tool.LINE, a.center().x(), head, a.center().x(), a.bottom() - a.height() * 0.04, size=b.line * 1.3)


def kwl_chart(b: _Builder) -> None:
    a = b.area
    r = QRectF(a.left() + a.width() * 0.03, a.top() + a.height() * 0.05, a.width() * 0.94, a.height() * 0.9)
    b.shape(Tool.RECT, r.left(), r.top(), r.right(), r.bottom())
    head = r.top() + b.text_size * 2.4
    b.shape(Tool.LINE, r.left(), head, r.right(), head)
    titles = ["Lo que sé", "Lo que quiero saber", "Lo que aprendí"]
    # el mismo tamaño de letra en los tres encabezados: el que permite que quepa el más largo
    size = b.text_size
    while size > 10 and any(render.text_box(TextItem(b.rgba, size, 1.0, 0, 0, t, True)).width() > r.width() / 3 * 0.9
                            for t in titles):
        size *= 0.92
    for i in range(3):
        if i:
            x = r.left() + r.width() * i / 3
            b.shape(Tool.LINE, x, r.top(), x, r.bottom())
        b.text(r.left() + r.width() * (i + 0.5) / 3, (r.top() + head) / 2, titles[i], size=size, bold=True)


def essay_outline(b: _Builder) -> None:
    a = b.area
    w = a.width() * 0.62
    parts = [("Introducción", 0.2), ("Desarrollo", 0.36), ("Conclusión", 0.2)]
    gap = a.height() * 0.07
    total = sum(f for _, f in parts) * a.height() + gap * 2
    y = a.center().y() - total / 2
    boxes = []
    for name, f in parts:
        h = a.height() * f
        boxes.append(b.box(QRectF(a.center().x() - w / 2, y, w, h), name, bold=True))
        y += h + gap
    for top, bottom in zip(boxes, boxes[1:]):
        b.connect(top, bottom, arrow=True)


def cycle(b: _Builder) -> None:
    a = b.area
    c = a.center()
    rx, ry = a.width() * 0.3, a.height() * 0.34
    w, h = a.width() * 0.2, a.height() * 0.15
    pts = [QPointF(c.x(), c.y() - ry), QPointF(c.x() + rx, c.y()), QPointF(c.x(), c.y() + ry),
           QPointF(c.x() - rx, c.y())]
    boxes = [b.box(_rect(p.x(), p.y(), w, h), f"Etapa {i + 1}") for i, p in enumerate(pts)]
    for i in range(4):
        r1, r2 = boxes[i], boxes[(i + 1) % 4]
        p1 = _edge_point(r1, r2.center())
        p2 = _edge_point(r2, r1.center())
        # flecha curva en sentido horario: se curva a su izquierda, es decir, hacia fuera del ciclo
        b.shape(Tool.CURVED_ARROW, p1.x(), p1.y(), p2.x(), p2.y())


def cause_effect(b: _Builder) -> None:
    a = b.area
    w, h = a.width() * 0.28, a.height() * 0.3
    left = b.box(_rect(a.left() + a.width() * 0.2, a.center().y(), w, h), "Causa", bold=True)
    right = b.box(_rect(a.right() - a.width() * 0.2, a.center().y(), w, h), "Efecto", bold=True)
    b.connect(left, right, arrow=True)
    b.text(a.center().x(), a.center().y() - b.text_size * 1.1, "porque…", size=b.text_size * 0.85)


TEMPLATES = {
    "concept_map": ("Mapa conceptual", concept_map),
    "timeline": ("Línea de tiempo", timeline),
    "venn2": ("Diagrama de Venn (2 conjuntos)", lambda b: venn(b, 2)),
    "venn3": ("Diagrama de Venn (3 conjuntos)", lambda b: venn(b, 3)),
    "t_chart": ("Tabla de dos columnas (ventajas / desventajas)", t_chart),
    "kwl": ("Tabla S-Q-A (sé / quiero saber / aprendí)", kwl_chart),
    "essay": ("Esquema de redacción", essay_outline),
    "cycle": ("Ciclo (4 etapas)", cycle),
    "cause_effect": ("Causa y efecto", cause_effect),
}


def build(key: str, area: QRectF, rgba: Rgba, line: float = 3.0) -> GroupItem:
    """Construye la plantilla ``key`` dentro del área indicada (coordenadas lógicas de la pantalla)."""
    _, fn = TEMPLATES[key]
    b = _Builder(QRectF(area), tuple(rgba), line)
    fn(b)
    return b.group()
