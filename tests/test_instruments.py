"""Instrumentos de geometría: regla, transportador y compás."""
import math

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pizarra_virtual import instruments
from pizarra_virtual.instruments import Compass, Protractor, Ruler
from pizarra_virtual.items import ShapeItem, StrokeItem
from pizarra_virtual.tools import Tool

from test_v15 import _drag, _grab, _ov, _px


def _show(ctrl, kind):
    ctrl.toggle_instrument(kind)
    return _ov(ctrl).instruments[kind]


def _place(inst, x, y, angle=0.0):
    inst.x, inst.y = float(x), float(y)
    inst.set_angle(angle, free=True)


def _strokes(ctrl, ov):
    return [it for it in ctrl.items_for(ov.key) if isinstance(it, StrokeItem)]


def _line_dist(inst, x, y):
    """Distancia (con signo, eje local y) de un punto al centro de la regla."""
    return inst.to_local(QPointF(x, y)).y()


# ---------------------------------------------------------------------- mostrar y quitar


def test_toggle_instruments_and_toolbar(ctrl, qapp):
    ctrl.set_drawing(False)
    assert not ctrl.any_instrument
    ctrl.toggle_instrument("ruler")
    ov = _ov(ctrl)
    assert "ruler" in ov.instruments and ctrl.drawing  # se usa dibujando
    assert ctrl.toolbar.instruments_btn.isChecked()
    menu = ctrl.toolbar.build_instruments_menu()
    checked = {a.text().split("\t")[0]: a.isChecked() for a in menu.actions() if a.isCheckable()}
    assert checked == {"Regla": True, "Transportador": False, "Compás": False}
    ctrl.toggle_instrument("protractor")
    ctrl.toggle_instrument("compass")
    assert list(ov.instruments) == ["ruler", "protractor", "compass"]
    ctrl.toggle_instrument("ruler")  # otra vez: se quita
    assert "ruler" not in ov.instruments
    ctrl.hide_instruments()
    assert not ctrl.any_instrument and not ctrl.toolbar.instruments_btn.isChecked()
    ctrl.toggle_instrument("nada")  # tipo desconocido: no hace nada
    assert not ctrl.any_instrument


def test_instrument_shortcuts(ctrl, qapp):
    from PySide6.QtGui import QKeySequence

    seqs = {sc.key().toString(): sc for sc in ctrl.toolbar._shortcuts}
    for key, kind in (("I", "ruler"), ("Y", "protractor"), (QKeySequence("Shift+C").toString(), "compass")):
        seqs[key].activated.emit()
        assert ctrl.instrument_visible(kind)


def test_close_button_hides_instrument(ctrl, qapp):
    ov = _ov(ctrl)
    ruler = _show(ctrl, "ruler")
    _place(ruler, 400, 300)
    close = ruler.to_canvas(ruler.knobs(1.0)["close"])
    _drag(ov, [(close.x(), close.y()), (close.x(), close.y())])
    assert not ctrl.any_instrument and not _strokes(ctrl, ov)
    assert not ctrl.toolbar.instruments_btn.isChecked()


def test_instruments_are_not_drawing(ctrl, qapp):
    """No entran en el historial: borrar todo o deshacer no los quita."""
    ov = _ov(ctrl)
    _show(ctrl, "ruler")
    ctrl.clear_all()
    ctrl.undo()
    assert "ruler" in ov.instruments and ctrl.items_for(ov.key) == []


def test_px_per_cm():
    class Size:
        def __init__(self, w):
            self._w = w

        def width(self):
            return self._w

    class Screen:
        def __init__(self, mm, px):
            self.mm, self.px = mm, px

        def physicalSize(self):
            return Size(self.mm)

        def geometry(self):
            return Size(self.px)

    assert instruments.px_per_cm(Screen(500, 1920)) == pytest.approx(38.4)
    assert instruments.px_per_cm(Screen(0, 1920)) == pytest.approx(instruments.DEFAULT_PPCM)  # sin dato
    assert instruments.px_per_cm(Screen(5, 1920)) == pytest.approx(instruments.DEFAULT_PPCM)  # absurdo


# ---------------------------------------------------------------------- regla


def test_ruler_move_rotate_and_snap(ctrl, qapp):
    ov = _ov(ctrl)
    ruler = _show(ctrl, "ruler")
    _place(ruler, 400, 300)
    _drag(ov, [(400, 300), (450, 320), (460, 330)])  # arrastrar el cuerpo
    assert (ruler.x, ruler.y) == (460, 330)
    assert not _strokes(ctrl, ov)
    knob = ruler.to_canvas(ruler.knobs(1.0)["rotate"])
    c = ruler.origin
    # Girar unos 31°: los múltiplos de 15° atraen a menos de 2°
    a = math.radians(31)
    r = math.hypot(knob.x() - c.x(), knob.y() - c.y())
    base = math.atan2(knob.y() - c.y(), knob.x() - c.x())
    end = (c.x() + r * math.cos(base + a), c.y() + r * math.sin(base + a))
    _drag(ov, [(knob.x(), knob.y()), end])
    assert ruler.angle == pytest.approx(30.0)
    assert (ruler.x, ruler.y) == pytest.approx((460, 330))  # gira sobre su centro
    assert instruments.shown_angle(ruler.angle) == 150
    # Lejos de un múltiplo de 15°, el ángulo es libre
    ruler.press("rotate", knob)
    ruler.set_angle(37.0)
    assert ruler.angle == pytest.approx(37.0)


def test_stroke_along_ruler_is_straight(ctrl, qapp):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    size = ctrl.size_for(Tool.BRUSH)
    ruler = _show(ctrl, "ruler")
    _place(ruler, 400, 300, angle=-25)
    edge = -ruler.width / 2
    # Trazo tembloroso que empieza junto al borde superior (por fuera) y se aleja un poco
    pts = []
    for i in range(25):
        local = QPointF(-150 + i * 12, edge - 12 - (i % 4) * 5)
        q = ruler.to_canvas(local)
        pts.append((q.x(), q.y()))
    _drag(ov, pts)
    (stroke,) = _strokes(ctrl, ov)
    ys = [_line_dist(ruler, x, y) for x, y, _w in stroke.points]
    assert max(ys) - min(ys) < 0.6  # recto, sobre una sola línea
    assert sum(ys) / len(ys) == pytest.approx(edge - size / 2, abs=0.6)  # por fuera del borde


def test_stroke_far_from_ruler_is_free(ctrl, qapp):
    ov = _ov(ctrl)
    ruler = _show(ctrl, "ruler")
    _place(ruler, 400, 200)
    _drag(ov, [(100, 500), (150, 520), (200, 480), (250, 530)])
    (stroke,) = _strokes(ctrl, ov)
    ys = [y for _x, y, _w in stroke.points]
    assert max(ys) - min(ys) > 30


def test_guided_stroke_is_not_recognized_as_shape(ctrl, qapp):
    """Con «Formas perfectas» activo, el trazo de la regla queda como trazo (no se convierte)."""
    ov = _ov(ctrl)
    ctrl.set_recognize_shapes(True)
    ruler = _show(ctrl, "ruler")
    _place(ruler, 400, 300)
    y = 300 + ruler.width / 2 + 8
    _drag(ov, [(250 + i * 15, y + (i % 2) * 3) for i in range(20)])
    items = ctrl.items_for(ov.key)
    assert len(items) == 1 and isinstance(items[0], StrokeItem)


def test_eraser_and_shapes_ignore_ruler(ctrl, qapp):
    ov = _ov(ctrl)
    ruler = _show(ctrl, "ruler")
    _place(ruler, 400, 300)
    y = 300 + ruler.width / 2 + 8
    ctrl.set_tool(Tool.LINE)
    _drag(ov, [(250, y), (500, y + 40)])
    (line,) = [it for it in ctrl.items_for(ov.key) if isinstance(it, ShapeItem)]
    assert line.y2 == pytest.approx(y + 40, abs=1)


def test_wheel_rotates_instrument(ctrl, qapp):
    ov = _ov(ctrl)
    ruler = _show(ctrl, "ruler")
    _place(ruler, 400, 300)
    size = ctrl.size_for(ctrl.tool)
    pos = QPointF(400, 300)
    ev = QWheelEvent(pos, ov.mapToGlobal(pos), QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(ov, ev)
    assert ruler.angle == pytest.approx(-1.0)  # hacia arriba: antihorario
    assert ctrl.size_for(ctrl.tool) == size  # no cambia el grosor


# ---------------------------------------------------------------------- transportador


def test_protractor_needle_resize_and_arc(ctrl, qapp):
    ov = _ov(ctrl)
    pr = _show(ctrl, "protractor")
    _place(pr, 400, 450)
    pr.radius = 200
    tip = pr.to_canvas(pr.needle_tip(1.0))
    a = math.radians(125)
    _drag(ov, [(tip.x(), tip.y()), (400 + 150 * math.cos(a), 450 - 150 * math.sin(a))])
    assert pr.measure == 125
    # Por debajo de la base a la izquierda: 180°; a la derecha: 0°
    pr.press("needle", tip)
    pr.drag(QPointF(300, 470))
    assert pr.measure == 180
    pr.drag(QPointF(500, 470))
    assert pr.measure == 0
    pr.release()
    # Cambiar el tamaño
    knob = pr.to_canvas(pr.knobs(1.0)["resize"])
    _drag(ov, [(knob.x(), knob.y()), (400 + (knob.x() - 400) * 1.5, 450 + (knob.y() - 450) * 1.5)])
    assert pr.radius == pytest.approx(300, abs=1)
    # Trazo junto al arco: sigue el arco
    size = ctrl.size_for(Tool.BRUSH)
    pts = [(400 + (pr.radius + 10 + (i % 3) * 4) * math.cos(math.radians(30 + i * 4)),
            450 - (pr.radius + 10 + (i % 3) * 4) * math.sin(math.radians(30 + i * 4))) for i in range(20)]
    _drag(ov, pts)
    (stroke,) = _strokes(ctrl, ov)
    for x, y, _w in stroke.points:
        assert math.hypot(x - 400, y - 450) == pytest.approx(pr.radius + size / 2, abs=0.6)


def test_protractor_base_is_straight(ctrl, qapp):
    ov = _ov(ctrl)
    pr = _show(ctrl, "protractor")
    _place(pr, 400, 300, angle=15)
    pr.radius = 200
    base = pr.base(1.0)
    pts = [pr.to_canvas(QPointF(-150 + i * 15, base + 10 + (i % 3) * 4)) for i in range(20)]
    _drag(ov, [(q.x(), q.y()) for q in pts])
    (stroke,) = _strokes(ctrl, ov)
    ys = [pr.to_local(QPointF(x, y)).y() for x, y, _w in stroke.points]
    assert max(ys) - min(ys) < 0.6


def test_protractor_rotates_around_vertex(ctrl, qapp):
    ov = _ov(ctrl)
    pr = _show(ctrl, "protractor")
    _place(pr, 400, 400)
    knob = pr.to_canvas(pr.knobs(1.0)["rotate"])
    r = math.hypot(knob.x() - 400, knob.y() - 400)
    base = math.atan2(knob.y() - 400, knob.x() - 400)
    a = base + math.radians(-45)
    _drag(ov, [(knob.x(), knob.y()), (400 + r * math.cos(a), 400 + r * math.sin(a))])
    assert pr.angle == pytest.approx(-45)
    assert (pr.x, pr.y) == pytest.approx((400, 400))


# ---------------------------------------------------------------------- compás


def _compass(ctrl, x=400, y=420, r=120):
    c = _show(ctrl, "compass")
    _place(c, x, y)
    c.radius = r
    return c


def test_compass_draws_arc_around_needle(ctrl, qapp):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.PENCIL)
    c = _compass(ctrl)
    q = c.pencil()
    pts = [(q.x(), q.y())]
    for i in range(1, 19):  # el puntero gira 90° (en sentido horario en la pantalla)
        a = math.radians(i * 5)
        pts.append((400 + 200 * math.cos(a), 420 + 200 * math.sin(a)))
    _drag(ov, pts)
    (stroke,) = _strokes(ctrl, ov)
    assert stroke.tool == Tool.PENCIL
    for x, y, _w in stroke.points:
        assert math.hypot(x - 400, y - 420) == pytest.approx(120, abs=0.01)
    end = stroke.points[-1]
    assert math.degrees(math.atan2(end[1] - 420, end[0] - 400)) == pytest.approx(90, abs=0.5)
    assert c.angle == pytest.approx(90, abs=0.5)  # el compás quedó girado
    assert c.dragging is None
    ctrl.undo()  # el arco es un trazo más: se deshace
    assert not _strokes(ctrl, ov)


def test_compass_full_circle_stops_at_one_turn(ctrl, qapp):
    c = _compass(ctrl)
    c.press("draw", c.pencil())
    pts = []
    for i in range(1, 100):  # una vuelta y media
        a = math.radians(i * 5.5)
        pts += c.drag(QPointF(400 + 50 * math.cos(a), 420 + 50 * math.sin(a)))
    c.release()
    swept = math.degrees(math.atan2(pts[-1].y() - 420, pts[-1].x() - 400)) % 360
    assert swept == pytest.approx(0, abs=0.01) or swept == pytest.approx(360, abs=0.01)
    assert len(pts) >= 240  # puntos cada 1,5° como mucho


def test_compass_open_and_move(ctrl, qapp):
    ov = _ov(ctrl)
    c = _compass(ctrl)
    h = c.to_canvas(c.hinge())
    q = c.pencil()
    mid = QPointF((h.x() + q.x()) / 2, (h.y() + q.y()) / 2)  # la pata del lápiz
    assert c.hit(mid, 1.0) == "open"
    _drag(ov, [(mid.x(), mid.y()), (mid.x() + 60, mid.y())])
    assert c.radius == pytest.approx(180, abs=0.5) and (c.x, c.y) == (400, 420)
    assert not _strokes(ctrl, ov)
    _drag(ov, [(h.x(), h.y()), (h.x() - 50, h.y() + 10)])  # la bisagra: mover
    assert (c.x, c.y) == pytest.approx((350, 430))


def test_compass_with_non_drawing_tool_uses_brush(ctrl, qapp):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.ERASER)
    c = _compass(ctrl)
    q = c.pencil()
    _drag(ov, [(q.x(), q.y()), (400 + 100, 420 + 100), (400, 420 + 150)])
    (stroke,) = _strokes(ctrl, ov)
    assert stroke.tool == Tool.BRUSH


def test_mouse_mode_ends_instrument_drag(ctrl, qapp):
    ov = _ov(ctrl)
    c = _compass(ctrl)
    q = c.pencil()
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, q.toPoint())
    QTest.mouseMove(ov, QPoint(500, 520), 3)
    assert c.dragging == "draw" and ov.busy
    ctrl.set_drawing(False)
    assert c.dragging is None and not ov.busy
    assert len(_strokes(ctrl, ov)) == 1  # lo dibujado hasta ahí se conserva
    assert ov.instrument_at(QPointF(400, 420)) is None  # en «Ratón libre» no se agarran


def test_two_fingers_cancel_compass_stroke(ctrl, qapp, touch):
    ov = _ov(ctrl)
    c = _compass(ctrl)
    q = c.pencil().toPoint()
    QTest.touchEvent(ov, touch).press(0, q).commit()
    QTest.touchEvent(ov, touch).stationary(0).press(1, QPoint(100, 100)).commit()
    QTest.touchEvent(ov, touch).release(0, q).release(1, QPoint(100, 100)).commit()
    assert not _strokes(ctrl, ov) and c.dragging is None


# ---------------------------------------------------------------------- pintado y zoom


def test_instruments_are_painted_and_follow_zoom(ctrl, qapp):
    ov = _ov(ctrl)
    ctrl.set_background("white")
    ruler = _show(ctrl, "ruler")
    _place(ruler, 300, 300)
    img = _grab(ov)
    edge = _px(ov, img, 300, 300 - ruler.width / 2)
    assert edge.red() < 120 and edge.blue() < 160  # borde oscuro de la regla
    # Con zoom el instrumento se amplía con la pizarra y se agarra donde se ve
    shot = QImage(ov.canvas.size(), QImage.Format.Format_ARGB32_Premultiplied)
    shot.fill(QColor("white"))
    ov.start_zoom(shot, QPointF(300, 300), 2.0)
    view = QPointF((300 - ov._zoom_tl.x()) * 2, (300 - ov._zoom_tl.y()) * 2)
    assert ov.instrument_at(view)[1] == "move"
    img = _grab(ov)
    edge = _px(ov, img, view.x(), view.y() - ruler.width)  # el borde, el doble de lejos
    assert edge.red() < 120 and edge.blue() < 160
    ov.end_zoom()


def test_new_instrument_fits_screen(ctrl, qapp):
    ov = _ov(ctrl)
    for kind in instruments.INSTRUMENTS:
        inst = _show(ctrl, kind)
        box = inst.transform().map(inst.outline(1.0)).boundingRect()
        assert box.left() >= 0 and box.top() >= 0, kind
        assert box.right() <= ov.width() and box.bottom() <= ov.height(), kind
    assert isinstance(ov.instruments["ruler"], Ruler)
    assert isinstance(ov.instruments["protractor"], Protractor)
    assert isinstance(ov.instruments["compass"], Compass)
