"""Pruebas de: barra plegable, pluma precisa y zoom."""
import math
import os

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pizarra_virtual import render
from pizarra_virtual.items import StrokeItem
from pizarra_virtual.tools import Tool


def _overlay(ctrl):
    return next(iter(ctrl.overlays.values()))


def _wheel(widget, pos: QPointF, delta: int, mods=Qt.KeyboardModifier.NoModifier):
    ev = QWheelEvent(pos, widget.mapToGlobal(pos), QPoint(0, 0), QPoint(0, delta),
                     Qt.MouseButton.NoButton, mods, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


# ---------------------------------------------------------------------- 1. barra plegable


def test_collapse_shrinks_the_window_itself(ctrl, qapp):
    tb = ctrl.toolbar
    qapp.processEvents()
    full = tb.frameGeometry()
    assert full.height() > 300
    tb.toggle_collapsed()
    qapp.processEvents()
    small = tb.frameGeometry()
    # La VENTANA (no solo su contenido) se reduce a la cabecera.
    assert small.height() < 60, small
    assert tb.windowHandle().geometry().height() < 60
    if not tb.horizontal:
        assert small.width() == full.width()
    assert small.topLeft() == full.topLeft()
    tb.toggle_collapsed()
    qapp.processEvents()
    assert tb.frameGeometry().height() == full.height()


def test_toolbar_resizes_even_with_stale_cached_sizes(ctrl, qapp):
    """Regresión: si el tamaño preferido se consultó antes (como hace Windows), la ventana
    debe seguir ajustándose al plegar/desplegar y al mostrar u ocultar secciones."""
    tb = ctrl.toolbar

    def poke():  # deja en caché los tamaños actuales, como haría el sistema
        tb.sizeHint()
        tb.adjustSize()
        tb.panel.sizeHint()
        tb.body.sizeHint()

    sizes = {}
    for name, tool in (("pluma", Tool.PEN), ("rect", Tool.RECT), ("pincel", Tool.BRUSH), ("pluma2", Tool.PEN)):
        poke()
        ctrl.set_tool(tool)
        sizes[name] = tb.height()
        qapp.processEvents()
        assert tb.height() == sizes[name]
    assert sizes["pluma"] == sizes["pluma2"]
    assert sizes["pluma"] < sizes["pincel"] and sizes["pluma"] < sizes["rect"]
    poke()
    tb.toggle_collapsed()
    assert tb.height() < 60
    poke()
    tb.toggle_collapsed()
    assert tb.height() == sizes["pluma"]


def test_collapse_state_is_remembered_and_stays_on_screen(ctrl, qapp):
    tb = ctrl.toolbar
    tb.set_collapsed(True)
    avail = tb.screen().availableGeometry()
    tb.move(avail.left() + 10, avail.bottom() - 60)  # plegada, abajo del todo
    qapp.processEvents()
    tb.set_collapsed(False)  # al desplegar no debe salirse de la pantalla
    qapp.processEvents()
    assert tb.frameGeometry().bottom() <= avail.bottom()
    assert tb.frameGeometry().top() >= avail.top()
    tb.set_collapsed(True)
    assert str(ctrl.settings.value("toolbar/collapsed")) == "true"


# ---------------------------------------------------------------------- 2. pluma


def _pen_stroke(ov, path, dt=8):
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*path[0]))
    for x, y in path[1:]:
        QTest.mouseMove(ov, QPoint(x, y), dt)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*path[-1]))


def test_pen_ends_exactly_where_released_and_is_tapered(ctrl):
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.PEN)
    ctrl.set_size(8)
    path = [(100 + i * 4, 300) for i in range(60)]
    _pen_stroke(ov, path)
    item = ctrl.history[-1][1]
    assert item.tool == Tool.PEN
    assert item.points[0][:2] == (100, 300)
    assert item.points[-1][:2] == (path[-1][0], 300)  # termina donde se soltó
    widths = [w for _, _, w in item.points]
    middle = max(widths[len(widths) // 3: 2 * len(widths) // 3])
    assert widths[0] < middle * 0.6 and widths[-1] < middle * 0.6  # entrada y salida afinadas
    assert max(widths) <= 8 * 1.01  # nunca más gruesa que el tamaño elegido


def test_pen_smooths_mouse_jitter(ctrl):
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.PEN)
    ctrl.set_size(4)
    # línea horizontal con temblor de ±2 px
    path = [(100 + i * 3, 400 + (2 if i % 2 else -2)) for i in range(80)]
    _pen_stroke(ov, path)
    item = ctrl.history[-1][1]
    inner = item.points[5:-5]
    dev = max(abs(y - 400) for _, y, _ in inner)
    assert dev < 1.2, dev  # el estabilizador reduce el temblor a menos de la mitad


def test_pen_width_varies_with_speed_without_tablet(ctrl):
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.PEN)
    ctrl.set_size(20)
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 600))
    x = 50
    for _ in range(40):  # lento
        x += 3
        QTest.mouseMove(ov, QPoint(x, 600), 40)
    for _ in range(25):  # rápido
        x += 40
        QTest.mouseMove(ov, QPoint(x, 600), 2)
    for _ in range(40):  # lento otra vez (para que el afinado final no afecte a la zona rápida)
        x += 3
        QTest.mouseMove(ov, QPoint(x, 600), 40)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, 600))
    w = [p[2] for p in ctrl.history[-1][1].points]
    slow = w[30]
    fast = min(w[45:65])
    assert slow > fast * 1.4, (slow, fast)
    # el cambio de grosor es gradual: nunca salta más de un 25 % entre puntos
    assert all(abs(b - a) <= max(a, b) * 0.25 + 0.2 for a, b in zip(w[8:-8], w[9:-7]))


def test_pen_click_draws_round_dot(ctrl):
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.PEN)
    ctrl.set_size(10)
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 300))
    item = ctrl.history[-1][1]
    assert len(item.points) == 1 and abs(item.points[0][2] - 9) < 1e-6
    dpr = ov.canvas.devicePixelRatio()
    assert ov.canvas.pixelColor(int(300 * dpr), int(300 * dpr)).alpha() > 0


def test_pen_live_and_replayed_render_match(ctrl):
    """Lo que queda en el lienzo al soltar es idéntico a lo que se re-dibuja al deshacer/rehacer."""
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.PEN)
    ctrl.set_size(6)
    path = [(200 + int(80 * math.cos(a / 10)), 300 + int(80 * math.sin(a / 10))) for a in range(60)]
    _pen_stroke(ov, path)
    live = ov.canvas.copy()
    ctrl.undo()
    ctrl.redo()
    assert ov.canvas == live


def test_pen_outline_has_no_holes(qapp):
    """Trazos finos y gruesos con giros cerrados se rellenan enteros (sin huecos por orientación)."""
    from PySide6.QtGui import QImage, QPainter

    assert render._signed_area(render._circle_poly(0, 0, 5)) > 0
    for width in (2.0, 3.0, 24.0):
        pts = [(100 + 40 * math.cos(a / 8), 100 + 40 * math.sin(a / 8), width) for a in range(120)]
        item = StrokeItem(Tool.PEN, (0, 0, 0, 255), width, 1.0, points=pts)
        img = QImage(220, 220, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        render.draw_stroke(p, item)
        p.end()
        weak = 0
        for k in range(720):  # recorre el eje del anillo cada medio grado
            x = 100 + 40 * math.cos(math.radians(k / 2))
            y = 100 + 40 * math.sin(math.radians(k / 2))
            if img.pixelColor(round(x - 0.5), round(y - 0.5)).alpha() < 128:
                weak += 1
        assert weak == 0, (width, weak)


# ---------------------------------------------------------------------- 3. zoom


def _start_zoom(ctrl, qapp, at=QPoint(400, 300)):
    ov = _overlay(ctrl)
    from PySide6.QtGui import QCursor

    QCursor.setPos(ov.mapToGlobal(at))
    ctrl.start_zoom()
    QTest.qWait(500)
    qapp.processEvents()
    assert ov.zoom_active
    return ov


def test_zoom_maps_drawing_to_real_screen_coordinates(ctrl, qapp):
    ov = _start_zoom(ctrl, qapp)
    assert ov.zoom_factor == 2.0
    assert ctrl.toolbar.zoom_btn.isChecked()
    ctrl.set_tool(Tool.LINE)
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 100))
    QTest.mouseMove(ov, QPoint(300, 100), 5)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 100))
    line = ctrl.history[-1][1]
    tl = ov._zoom_tl
    assert math.isclose(line.x1, tl.x() + 50) and math.isclose(line.x2, tl.x() + 150)
    assert math.isclose(line.y1, tl.y() + 50)
    ctrl.escape()  # Esc sale del zoom...
    assert not ov.zoom_active and ctrl.drawing
    ctrl.escape()  # ...y la segunda vez pasa a «Ratón libre»
    assert not ctrl.drawing


def test_zoom_wheel_keeps_point_under_cursor_and_clamps(ctrl, qapp):
    ov = _start_zoom(ctrl, qapp)
    anchor = QPointF(250, 180)
    before = ov.to_canvas(anchor)
    _wheel(ov, anchor, 120)
    assert math.isclose(ov.zoom_factor, 2.5)
    after = ov.to_canvas(anchor)
    assert abs(before.x() - after.x()) < 1e-6 and abs(before.y() - after.y()) < 1e-6
    for _ in range(30):
        _wheel(ov, QPointF(ov.width() - 1, ov.height() - 1), 120)  # en la esquina
    assert ov.zoom_factor == 10.0
    # la vista nunca se sale de la imagen
    br = ov.to_canvas(QPointF(ov.width(), ov.height()))
    assert br.x() <= ov.width() + 1e-6 and br.y() <= ov.height() + 1e-6
    for _ in range(30):
        _wheel(ov, anchor, -120)
    assert ov.zoom_factor == 1.0
    assert ov._zoom_tl == QPointF(0, 0)  # a 1× se ve la pantalla completa
    # Ctrl + rueda cambia el grosor, no el zoom
    ctrl.set_tool(Tool.BRUSH)
    size = ctrl.sizes[Tool.BRUSH]
    _wheel(ov, anchor, 120, Qt.KeyboardModifier.ControlModifier)
    assert ov.zoom_factor == 1.0 and ctrl.sizes[Tool.BRUSH] > size


def test_zoom_pan_with_right_button(ctrl, qapp):
    ov = _start_zoom(ctrl, qapp)
    tl0 = QPointF(ov._zoom_tl)
    QTest.mousePress(ov, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 300))
    QTest.mouseMove(ov, QPoint(200, 260), 5)
    QTest.mouseRelease(ov, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 260))
    assert math.isclose(ov._zoom_tl.x(), tl0.x() + 50) and math.isclose(ov._zoom_tl.y(), tl0.y() + 20)
    QTest.mousePress(ov, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(10, 10))
    QTest.mouseMove(ov, QPoint(5000, 5000), 5)  # no puede salirse de la imagen
    QTest.mouseRelease(ov, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(5000, 5000))
    assert ov._zoom_tl.x() == 0 and ov._zoom_tl.y() == 0
    assert not ctrl.history  # desplazar no dibuja nada


def test_zoom_capture_saves_the_zoomed_view(ctrl, qapp, tmp_path):
    ov = _start_zoom(ctrl, qapp)
    ctrl.set_tool(Tool.BRUSH)
    ctrl.set_size(10)
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 100))
    QTest.mouseMove(ov, QPoint(200, 100), 5)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 100))
    view = ov.render_view(True)
    assert view.size() == ov.canvas.size()
    d = ov.devicePixelRatioF()  # la vista está en píxeles físicos
    # el trazo de 10 px se ve de 20 px en la vista ampliada
    assert view.pixelColor(round(150 * d), round(100 * d)).red() > 200
    assert view.pixelColor(round(150 * d), round(108 * d)).red() > 200
    ctrl.capture(with_drawing=True)
    QTest.qWait(600)
    files = list((tmp_path / "Pictures" / "Capturas Pizarra").glob("*.png"))
    assert len(files) == 1 and os.path.getsize(files[0]) > 0
    assert ov.zoom_active  # la captura no saca del zoom


def test_hiding_or_mouse_mode_ends_zoom(ctrl, qapp):
    ov = _start_zoom(ctrl, qapp)
    ctrl.toggle_visible()
    assert not ov.zoom_active
    ctrl.toggle_visible()
    ov = _start_zoom(ctrl, qapp)
    ctrl.set_drawing(False)
    assert not ov.zoom_active
    ov = _start_zoom(ctrl, qapp)  # el zoom reactiva el dibujo
    assert ctrl.drawing
    ctrl.toggle_zoom()
    assert not ov.zoom_active


def test_toolbar_uses_two_columns_when_screen_is_short(ctrl, qapp, monkeypatch):
    """En pantallas bajas (p. ej. 1366x768 al 150 %) la barra pasa a dos columnas y cabe entera."""
    from PySide6.QtCore import QRect

    tb = ctrl.toolbar
    screen = tb._current_screen()
    real = screen.availableGeometry()
    from pizarra_virtual.toolbar import COL_WIDTH

    short = QRect(real.left(), real.top(), real.width(), min(real.height(), 470))
    monkeypatch.setattr(type(screen), "availableGeometry", lambda self: short)
    tb.update_orientation()
    assert tb.horizontal
    geo = tb.frameGeometry()
    assert geo.height() <= short.height() and geo.top() >= short.top() and geo.bottom() <= short.bottom()
    assert geo.width() > 2 * COL_WIDTH  # dos columnas lado a lado
    # plegar y desplegar sigue funcionando en dos columnas
    tb.toggle_collapsed()
    assert tb.height() < 60
    tb.toggle_collapsed()
    assert tb.horizontal and tb.frameGeometry().height() <= short.height()
    # cambiar de herramienta no cambia la disposición
    ctrl.set_tool(Tool.RECT)
    ctrl.set_tool(Tool.BRUSH)
    assert tb.horizontal and tb.frameGeometry().bottom() <= short.bottom()
    monkeypatch.undo()
    tb.update_orientation()
    assert not tb.horizontal or real.height() < 700
