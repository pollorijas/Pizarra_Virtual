import os

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from pizarra_virtual.items import ClearItem, ShapeItem, StrokeItem
from pizarra_virtual.tools import Tool


def _overlay(ctrl):
    return next(iter(ctrl.overlays.values()))


def _drag(ov, points, modifier=Qt.KeyboardModifier.NoModifier):
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, modifier, QPoint(*points[0]))
    for x, y in points[1:]:
        QTest.mouseMove(ov, QPoint(x, y), 5)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, modifier, QPoint(*points[-1]))


def _alpha(ov, x, y):
    dpr = ov.canvas.devicePixelRatio()
    return ov.canvas.pixelColor(int(x * dpr), int(y * dpr)).alpha()


def test_overlay_covers_screen(ctrl):
    ov = _overlay(ctrl)
    assert ov.geometry() == ov.screen_ref.geometry()
    assert not ov.canvas.isNull()


def test_draw_undo_redo_clear(ctrl):
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    _drag(ov, [(100, 100), (150, 110), (200, 130), (260, 160)])
    assert len(ctrl.history) == 1
    assert isinstance(ctrl.history[0][1], StrokeItem)
    assert _alpha(ov, 150, 110) > 0

    ctrl.undo()
    assert _alpha(ov, 150, 110) == 0
    ctrl.redo()
    assert _alpha(ov, 150, 110) > 0

    ctrl.clear_all()
    assert isinstance(ctrl.history[-1][1], ClearItem)
    assert _alpha(ov, 150, 110) == 0
    ctrl.undo()
    assert _alpha(ov, 150, 110) > 0


def test_eraser_removes_pixels(ctrl):
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    ctrl.set_size(40)
    _drag(ov, [(100, 300), (200, 300), (300, 300)])
    assert _alpha(ov, 200, 300) > 0
    ctrl.set_tool(Tool.ERASER)
    ctrl.set_size(60)
    _drag(ov, [(200, 250), (200, 300), (200, 350)])
    assert _alpha(ov, 200, 300) == 0
    assert _alpha(ov, 120, 300) > 0
    ctrl.undo()  # deshacer la goma recupera el trazo
    assert _alpha(ov, 200, 300) > 0


def test_shapes_and_shift_constraint(ctrl):
    ov = _overlay(ctrl)
    for tool in (Tool.RECT, Tool.ELLIPSE, Tool.TRIANGLE, Tool.LINE, Tool.ARROW):
        ctrl.set_tool(tool)
        _drag(ov, [(400, 100), (450, 150), (520, 180)])
        item = ctrl.history[-1][1]
        assert isinstance(item, ShapeItem) and item.tool == tool
    ctrl.set_tool(Tool.RECT)
    _drag(ov, [(100, 400), (160, 420), (200, 430)], Qt.KeyboardModifier.ShiftModifier)
    item = ctrl.history[-1][1]
    assert abs(item.x2 - item.x1) == abs(item.y2 - item.y1)


def test_highlighter_is_semitransparent(ctrl):
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.HIGHLIGHTER)
    _drag(ov, [(100, 500), (200, 500), (150, 500), (300, 500)])  # pasa dos veces por el mismo sitio
    a = _alpha(ov, 160, 500)
    assert 60 < a < 140  # ~40 % y sin acumulación


def test_pen_width_varies_with_speed(ctrl):
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.PEN)
    ctrl.set_size(20)
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 600))
    x = 50
    for _ in range(10):  # lento
        x += 2
        QTest.mouseMove(ov, QPoint(x, 600), 30)
    for _ in range(10):  # rápido
        x += 60
        QTest.mouseMove(ov, QPoint(x, 600), 1)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, 600))
    stroke = ctrl.history[-1][1]
    widths = [w for _, _, w in stroke.points]
    assert max(widths[:10]) > min(widths[-5:]) * 1.5, widths


def test_toggle_drawing_and_visibility(ctrl):
    ov = _overlay(ctrl)
    assert ctrl.drawing
    ctrl.toggle_drawing()
    assert not ctrl.drawing
    assert ov.windowHandle().flags() & Qt.WindowType.WindowTransparentForInput
    ctrl.toggle_drawing()
    assert ctrl.drawing
    assert not ov.windowHandle().flags() & Qt.WindowType.WindowTransparentForInput
    ctrl.toggle_visible()
    assert not ov.isVisible()
    ctrl.toggle_visible()
    assert ov.isVisible()


def test_capture_saves_into_pictures_folder(ctrl, qapp, tmp_path):
    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    _drag(ov, [(10, 10), (100, 100)])
    ctrl.capture(with_drawing=True)
    QTest.qWait(600)
    folder = tmp_path / "Pictures" / "Capturas Pizarra"
    files = list(folder.glob("Pizarra_*.png"))
    assert len(files) == 1 and os.path.getsize(files[0]) > 0
    assert ov.isVisible() and ctrl.toolbar.isVisible()


def test_settings_roundtrip(ctrl, qapp):
    from pizarra_virtual.app import Controller

    ctrl.set_tool(Tool.PEN)
    ctrl.set_size(17)
    ctrl._save_settings()
    other = Controller(qapp, settings=ctrl.settings, enable_hotkeys=False, enable_tray=False)
    try:
        assert other.tool == Tool.PEN and other.sizes[Tool.PEN] == 17
    finally:
        other.shutdown()
