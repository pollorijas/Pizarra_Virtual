"""«Ratón libre» con una hoja (pizarra blanca, verde, oscurecida o con pauta).

Antes la hoja seguía tapando la pantalla en «Ratón libre» (los clics la atravesaban pero
no se veía nada debajo) y la barra podía quedar debajo de la hoja, sin forma de volver.
"""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pizarra_virtual import capture
from pizarra_virtual.tools import Tool


def _grab(ov) -> QImage:
    QApplication.processEvents()
    img = ov.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    img.setDevicePixelRatio(1.0)
    return img


def _px(ov, img, x, y) -> QColor:
    d = ov.devicePixelRatioF()
    return img.pixelColor(round(x * d), round(y * d))


def _sheet_pixels(ov, img):
    """Píxeles cubiertos (alfa > 10) a lo largo de una columna y una fila completas, lejos del trazo."""
    x0, y0 = ov.width() - 60, ov.height() - 60
    col = sum(_px(ov, img, x0, y).alpha() > 10 for y in range(10, ov.height() - 10))
    row = sum(_px(ov, img, x, y0).alpha() > 10 for x in range(10, ov.width() - 10))
    return col + row


def _draw_line(ov):
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 200))
    for x in range(110, 400, 10):
        QTest.mouseMove(ov, QPoint(x, 200), 2)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(400, 200))


def test_sheet_steps_aside_in_mouse_mode_and_returns(ctrl, qapp):
    ov = next(iter(ctrl.overlays.values()))
    ctrl.set_tool(Tool.PEN)
    ctrl.set_size(6)
    ctrl.set_color(QColor("#d32f2f"))
    _draw_line(ov)
    for bg, pattern in [("white", "cartesian"), ("chalk", "grid"), ("dim", "none"), ("transparent", "ruled")]:
        ctrl.set_background(bg)
        ctrl.set_pattern(pattern)
        ctrl.set_drawing(True)
        drawing = _grab(ov)
        covered = _sheet_pixels(ov, drawing)
        assert covered > 0, (bg, pattern)
        ctrl.set_drawing(False)
        free = _grab(ov)
        assert _sheet_pixels(ov, free) == 0, (bg, pattern)  # se ve el escritorio
        assert _px(ov, free, 250, 200).red() > 150 and _px(ov, free, 250, 200).alpha() > 200  # el trazo sigue
        ctrl.set_drawing(True)
        assert _sheet_pixels(ov, _grab(ov)) == covered, (bg, pattern)  # la hoja vuelve igual
    assert ctrl.background == "transparent" and ctrl.pattern == "ruled"  # no se pierde la elección


def test_toolbar_raised_when_leaving_drawing_mode(ctrl, qapp, monkeypatch):
    raised = []
    monkeypatch.setattr(ctrl.toolbar, "raise_", lambda: raised.append(1))
    ctrl.set_background("white")
    ctrl.set_pattern("cartesian")
    ctrl.set_drawing(False)
    assert raised  # inmediatamente
    n = len(raised)
    QTest.qWait(20)
    assert len(raised) > n  # y otra vez tras procesar el cambio de modo de las ventanas
    assert ctrl.toolbar.isVisible()


def test_capture_in_mouse_mode_does_not_include_hidden_sheet(ctrl, qapp, monkeypatch):
    ov = next(iter(ctrl.overlays.values()))
    ctrl.set_background("white")
    ctrl.set_pattern("grid")
    seen = {}

    def fake_compose(shot, canvas, background, pattern=None):
        seen["bg"], seen["pattern"] = background, pattern
        return shot

    def fake_grab(screen):
        img = QImage(50, 50, QImage.Format.Format_RGB32)
        img.fill(QColor(10, 20, 30))
        return img

    monkeypatch.setattr(capture, "compose_drawing", fake_compose)
    monkeypatch.setattr(capture, "grab_screen", fake_grab)
    monkeypatch.setattr(capture, "save_capture", lambda img, *a: "x.png")
    restore = (True, True)
    ctrl.set_drawing(False)
    ctrl._do_capture([ov.screen()], True, restore)
    assert seen["bg"].alpha() == 0 and seen["pattern"] is None
    ctrl.set_drawing(True)
    ctrl._do_capture([ov.screen()], True, restore)
    assert seen["bg"] == QColor(255, 255, 255) and seen["pattern"] is not None
