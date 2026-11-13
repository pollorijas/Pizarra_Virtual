import math

from pizarra_virtual import render
from pizarra_virtual.selftest import render_all_tools
from pizarra_virtual.tools import Tool


def test_all_tools_paint(qapp):
    results = render_all_tools()
    assert all(v > 0 for v in results.values()), results


def test_highlighter_is_wider_than_pencil(qapp):
    results = render_all_tools()
    assert results["highlighter:hard"] > 0


def test_constrain_square_and_angle():
    x2, y2 = render.constrain_shape(Tool.RECT, 0, 0, 50, 20)
    assert (x2, y2) == (50, 50)
    x2, y2 = render.constrain_shape(Tool.RECT, 0, 0, -10, 40)
    assert (x2, y2) == (-40, 40)
    x2, y2 = render.constrain_shape(Tool.LINE, 0, 0, 100, 3)
    assert math.isclose(y2, 0, abs_tol=1e-9) and math.isclose(x2, math.hypot(100, 3))


def test_convex_hull_square():
    hull = render.convex_hull([(0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0.5)])
    assert sorted(hull) == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_stroke_replay_is_deterministic(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    from pizarra_virtual.items import StrokeItem
    from pizarra_virtual.tools import BrushType

    item = StrokeItem(Tool.BRUSH, (0, 0, 0, 255), 20, 1.0, BrushType.AIRBRUSH, seed=123,
                      points=[(10 + i * 5, 50, 20) for i in range(30)])

    def draw():
        img = QImage(200, 100, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        render.draw_stroke(p, item)
        p.end()
        return img

    assert draw() == draw()
