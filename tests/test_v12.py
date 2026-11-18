"""Pruebas de la versión 1.2: texto, láser, foco, cortina, resaltado del cursor, pautas,
páginas, sesiones y exportación a PDF."""
import math
import os
import re

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QKeyEvent, QPainter, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pizarra_virtual import render, session
from pizarra_virtual.items import ShapeItem, StrokeItem, TextItem
from pizarra_virtual.tools import PATTERNS, Tool


def _ov(ctrl):
    return ctrl.overlay_for_screen(QGuiApplication.primaryScreen())


def _type(widget, text):
    """Escribe texto (también ñ y tildes) como lo haría el teclado."""
    for ch in text:
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.ShortcutOverride, 0, Qt.KeyboardModifier.NoModifier, ch))
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch))


def _key(widget, key, mods=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(widget, key, mods)


def _grab(ov) -> QImage:
    QApplication.processEvents()
    img = ov.grab().toImage()
    img.setDevicePixelRatio(1.0)
    return img


def _px(ov, img, x, y) -> QColor:
    d = ov.devicePixelRatioF()
    return img.pixelColor(round(x * d), round(y * d))


def _canvas_alpha(ov, x, y):
    d = ov.canvas.devicePixelRatio()
    return ov.canvas.pixelColor(round(x * d), round(y * d)).alpha()


def _drag(ov, pts):
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*pts[0]))
    for x, y in pts[1:]:
        QTest.mouseMove(ov, QPoint(x, y), 5)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*pts[-1]))


def _cursor_to(ov, x, y):
    QCursor.setPos(ov.mapToGlobal(QPoint(x, y)))


# ====================================================================== texto


def test_text_typing_ignores_shortcuts_and_commits(ctrl):
    ov, tb = _ov(ctrl), ctrl.toolbar
    ctrl.set_tool(Tool.TEXT)
    ctrl.set_size(40)
    size_before = ctrl.sizes[Tool.TEXT]
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 200))
    assert ctrl.text_editor is ov
    QTest.keyClicks(tb, "Clase 1 + 2 = 3 (T, L, F, V, Z)")
    _key(tb, Qt.Key.Key_Return)
    _type(tb, "ñandú ÁÉÍÓÚ ¿?")
    _key(tb, Qt.Key.Key_Backspace)
    # ninguna tecla disparó un atajo: misma herramienta, tamaño, sin foco/cortina/zoom
    assert ctrl.tool == Tool.TEXT and ctrl.sizes[Tool.TEXT] == size_before
    assert not ctrl.spotlight and not ctrl.curtain_active and not ctrl.zoom_active
    assert not ctrl.history  # aún se está escribiendo
    _key(tb, Qt.Key.Key_Escape)  # Esc termina el texto (no sale del modo dibujo)
    assert ctrl.drawing and ctrl.text_editor is None
    item = ctrl.history[-1][1]
    assert isinstance(item, TextItem)
    assert item.text == "Clase 1 + 2 = 3 (T, L, F, V, Z)\nñandú ÁÉÍÓÚ ¿"
    box = render.text_box(item)
    assert box.width() > 200 and box.height() > 80
    assert _canvas_alpha(ov, box.left() + 10, box.top() + item.size * 0.6) > 0 or \
        any(_canvas_alpha(ov, box.left() + dx, box.top() + dy) > 0 for dx in range(0, 60, 3) for dy in range(5, 45, 3))


def test_text_click_elsewhere_commits_and_empty_text_is_discarded(ctrl):
    ov, tb = _ov(ctrl), ctrl.toolbar
    ctrl.set_tool(Tool.TEXT)
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 100))
    QTest.keyClicks(tb, "uno")
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 300))
    assert [i.text for _, i in ctrl.history] == ["uno"]
    assert ctrl.text_editor is ov  # empezó un texto nuevo
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 300))
    assert len(ctrl.history) == 1  # el texto vacío no se guarda
    ctrl.set_tool(Tool.BRUSH)  # cambiar de herramienta también termina el texto
    assert ctrl.text_editor is None


def test_text_style_paste_undo_and_zoom(ctrl, qapp):
    ov, tb = _ov(ctrl), ctrl.toolbar
    QGuiApplication.clipboard().setText("pegado\r\nlínea 2")
    ctrl.set_tool(Tool.TEXT)
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(80, 120))
    _key(tb, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    ctrl.set_size(60)
    ctrl.set_color(QColor("#00aa00"))
    ctrl.set_text_bold(True)
    _key(tb, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)  # Ctrl+Intro también termina
    item = ctrl.history[-1][1]
    assert item.text == "pegado\nlínea 2" and item.size == 60 and item.bold and item.rgba[:3] == (0, 170, 0)
    ctrl.undo()
    assert not ctrl.history
    ctrl.redo()
    assert ctrl.history[-1][1] is item


def test_text_in_zoom_lands_on_real_coordinates(ctrl, qapp):
    ov = _ov(ctrl)
    _cursor_to(ov, 400, 300)
    ctrl.start_zoom()
    QTest.qWait(500)
    assert ov.zoom_active
    ctrl.set_tool(Tool.TEXT)
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 200))
    QTest.keyClicks(ctrl.toolbar, "zoom")
    _key(ctrl.toolbar, Qt.Key.Key_Escape)  # termina el texto...
    assert ov.zoom_active                   # ...sin salir del zoom
    item = ctrl.history[-1][1]
    tl = ov._zoom_tl
    assert math.isclose(item.x, tl.x() + 100)


# ====================================================================== láser


def test_laser_draws_temporary_ink_not_saved(ctrl, qapp):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.LASER)
    assert ov.cursor().shape() == Qt.CursorShape.BlankCursor
    _drag(ov, [(100 + i * 10, 300) for i in range(20)])
    assert not ctrl.history  # la tinta del láser no se guarda
    assert len(ov._trails) == 1
    img = _grab(ov)
    assert _px(ov, img, 190, 300).red() > 200  # se ve mientras dura
    ov._trails[0].released -= 5000  # pasa el tiempo
    ctrl._tick()
    assert not ov._trails
    img = _grab(ov)
    assert _px(ov, img, 190, 300).alpha() < 10  # se desvaneció


# ====================================================================== foco, cortina, resaltado


def test_spotlight_darkens_all_but_cursor_area(ctrl, qapp):
    ov = _ov(ctrl)
    _cursor_to(ov, 300, 250)
    ctrl.toggle_spotlight()
    ctrl._tick()
    img = _grab(ov)
    assert _px(ov, img, 300, 250).alpha() < 30            # claro bajo el cursor
    assert _px(ov, img, 300 + ctrl.spotlight_radius + 40, 250).alpha() > 150  # oscuro fuera
    r = ctrl.spotlight_radius
    ev = QWheelEvent(QPointF(300, 250), QPointF(ov.mapToGlobal(QPoint(300, 250))), QPoint(), QPoint(0, 120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.AltModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(ov, ev)
    assert ctrl.spotlight_radius > r
    ctrl.toggle_spotlight()
    assert _px(ov, _grab(ov), 300 + r + 40, 250).alpha() < 10


def test_curtain_covers_reveals_and_drags(ctrl, qapp):
    ov = _ov(ctrl)
    _cursor_to(ov, 100, 100)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_V)  # atajo V
    assert ctrl.curtain_active and ov.curtain_y == 0
    img = _grab(ov)
    assert _px(ov, img, 200, 200).alpha() == 255
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Down)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Down)
    assert math.isclose(ov.curtain_y, ov.height() * 0.2)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Up)
    assert math.isclose(ov.curtain_y, ov.height() * 0.1)
    # arrastrar la cortina (no dibuja)
    y0 = ov.curtain_y
    ctrl.set_tool(Tool.BRUSH)
    _drag(ov, [(200, int(y0) + 60), (200, int(y0) + 160)])
    assert math.isclose(ov.curtain_y, y0 + 100, abs_tol=1)
    assert not ctrl.history
    # por encima de la cortina se sigue dibujando
    _drag(ov, [(100, 20), (200, 20)])
    assert len(ctrl.history) == 1
    ctrl.toggle_curtain()
    assert not ctrl.curtain_active


def test_highlight_cursor_and_click_ripples(ctrl, qapp):
    ov = _ov(ctrl)
    _cursor_to(ov, 250, 250)
    ctrl.toggle_highlight()
    state = {"b": (False, False)}
    ctrl.button_state = lambda: state["b"]
    ctrl._tick()
    img = _grab(ov)
    halo = _px(ov, img, 250, 250 - 10)
    assert halo.red() > 200 and halo.green() > 150 and halo.blue() < 100 and halo.alpha() > 50
    state["b"] = (True, False)   # clic izquierdo (en cualquier aplicación)
    ctrl._tick()
    state["b"] = (False, True)   # clic derecho
    ctrl._tick()
    assert [c.red() > c.blue() for _, _, c in ov._ripples] == [True, False]
    QTest.qWait(500)
    ctrl._tick()
    assert not ov._ripples  # las ondas desaparecen solas
    ctrl.toggle_highlight()
    assert not ctrl.highlight


# ====================================================================== pautas


@pytest.mark.parametrize("pattern", [p for p in PATTERNS if p != "none"])
@pytest.mark.parametrize("background", ["transparent", "white", "chalk", "dim"])
def test_patterns_draw_on_every_background(qapp, pattern, background):
    img = QImage(640, 480, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    render.draw_pattern(p, 640, 480, pattern, background)
    p.end()
    painted = sum(1 for y in range(0, 480, 4) for x in range(0, 640, 4) if img.pixelColor(x, y).alpha() > 0)
    assert painted > 100, painted


def test_pattern_is_per_page_and_in_captures(ctrl, qapp, tmp_path):
    ov = _ov(ctrl)
    ctrl.set_background("white")
    ctrl.set_pattern("grid")
    assert ov.pattern_image() is not None
    ctrl.new_page()
    assert ctrl.pattern == "grid"  # la página nueva hereda la pauta
    ctrl.set_pattern("none")
    ctrl.prev_page()
    assert ctrl.pattern == "grid"
    _cursor_to(ov, 50, 50)
    ctrl.capture(with_drawing=True)
    QTest.qWait(600)
    files = list((tmp_path / "Pictures" / "Capturas Pizarra").glob("*.png"))
    shot = QImage(str(files[0]))
    d = ov.devicePixelRatioF()
    line = shot.pixelColor(round(64 * d), round(10 * d))  # línea de la cuadrícula
    blank = shot.pixelColor(round(80 * d), round(10 * d))
    assert line != blank


# ====================================================================== páginas


def test_pages_keep_separate_drawings_and_history(ctrl):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    _drag(ov, [(100, 100), (200, 100)])
    assert _canvas_alpha(ov, 150, 100) > 0
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_N)  # página nueva
    assert ctrl.page_index == 1 and len(ctrl.pages) == 2
    assert _canvas_alpha(ov, 150, 100) == 0
    _drag(ov, [(100, 300), (200, 300)])
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_PageUp)
    assert ctrl.page_index == 0
    assert _canvas_alpha(ov, 150, 100) > 0 and _canvas_alpha(ov, 150, 300) == 0
    ctrl.undo()  # deshacer solo afecta a la página actual
    assert _canvas_alpha(ov, 150, 100) == 0
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_PageDown)
    assert ctrl.page_index == 1 and _canvas_alpha(ov, 150, 300) > 0 and len(ctrl.history) == 1
    assert "2 DE 2" in ctrl.toolbar.page_label.text()
    ctrl.delete_page()
    assert len(ctrl.pages) == 1 and ctrl.page_index == 0
    assert "1 DE 1" in ctrl.toolbar.page_label.text()


# ====================================================================== sesiones y PDF


def _sample_session(ctrl):
    ov = _ov(ctrl)
    ctrl.set_background("white")
    ctrl.set_pattern("ruled")
    ctrl.set_tool(Tool.PEN)
    _drag(ov, [(100 + i * 6, 150 + int(20 * math.sin(i / 3))) for i in range(30)])
    ctrl.set_tool(Tool.RECT)
    _drag(ov, [(300, 300), (420, 380)])
    ctrl.set_tool(Tool.TEXT)
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 450))
    _type(ctrl.toolbar, "Sesión ñ")
    _key(ctrl.toolbar, Qt.Key.Key_Escape)
    ctrl.new_page()
    ctrl.set_pattern("cartesian")
    ctrl.set_tool(Tool.HIGHLIGHTER)
    _drag(ov, [(50, 50), (250, 50)])


def test_save_and_open_session_roundtrip(ctrl, tmp_path):
    ov = _ov(ctrl)
    _sample_session(ctrl)
    assert ctrl.dirty
    page1 = ov.canvas.copy()
    ctrl.prev_page()
    page0 = ov.canvas.copy()
    path = str(tmp_path / "mi clase")
    assert ctrl.save_session(path)
    assert ctrl.session_path.endswith(".pizarra") and not ctrl.dirty and os.path.getsize(ctrl.session_path) > 0

    ctrl.delete_page()
    ctrl.delete_page()
    assert len(ctrl.pages) == 1 and not ctrl.page.has_content()
    ctrl.dirty = False
    assert ctrl.open_session(ctrl.session_path)
    assert len(ctrl.pages) == 2 and ctrl.page_index == 0
    assert [p.pattern for p in ctrl.pages] == ["ruled", "cartesian"]
    assert ov.canvas == page0
    ctrl.next_page()
    assert ov.canvas == page1
    kinds = [type(i) for _, i in ctrl.pages[0].history]
    assert kinds == [StrokeItem, ShapeItem, TextItem]
    assert ctrl.pages[0].history[2][1].text == "Sesión ñ"


def test_session_from_another_computer_maps_screens(qapp, tmp_path):
    pages = [session.Page(history=[("\\\\.\\DISPLAY9", ShapeItem(Tool.LINE, (0, 0, 0, 255), 3, 1, 0, 0, 10, 10)),
                                   (None, TextItem((0, 0, 0, 255), 20, 1, 5, 5, "x"))])]
    path = session.save_session(str(tmp_path / "otra"), pages, ["\\\\.\\DISPLAY9"])
    loaded = session.load_session(path, ["PANTALLA-A", "PANTALLA-B"])
    assert [k for k, _ in loaded[0].history] == ["PANTALLA-A", None]


def test_open_invalid_session_fails_cleanly(ctrl, tmp_path, monkeypatch):
    bad = tmp_path / "roto.pizarra"
    bad.write_text("esto no es una sesión", encoding="utf-8")
    errors = []
    monkeypatch.setattr(ctrl, "_error", lambda title, text: errors.append(title))
    assert not ctrl.open_session(str(bad))
    assert errors and len(ctrl.pages) == 1


def test_export_pdf_one_page_per_page(ctrl, tmp_path):
    _sample_session(ctrl)
    out = ctrl.export_pdf(str(tmp_path / "apuntes"))
    assert out.endswith(".pdf")
    data = open(out, "rb").read()
    assert data.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page[^s]", data)) == 2


def test_rendered_page_uses_white_paper_for_transparent_background(ctrl):
    page = session.Page(background="transparent", pattern="none",
                        history=[(None, ShapeItem(Tool.RECT, (255, 0, 0, 255), 6, 1, 20, 20, 80, 80, True))])
    img = session.render_page(page, [i for _, i in page.history], 200, 120, scale=1.0)
    assert img.pixelColor(150, 100) == QColor(255, 255, 255)
    assert img.pixelColor(50, 50).red() > 200 and img.pixelColor(50, 50).green() < 50


def test_unsaved_changes_flag(ctrl):
    assert not ctrl.dirty and ctrl.confirm_discard("salir")  # sin cambios no pregunta
    ctrl.set_tool(Tool.BRUSH)
    _drag(_ov(ctrl), [(10, 10), (60, 10)])
    assert ctrl.dirty


# ====================================================================== atajos


def test_new_shortcuts(ctrl):
    tb = ctrl.toolbar
    QTest.keyClick(tb, Qt.Key.Key_T)
    assert ctrl.tool == Tool.TEXT
    QTest.keyClick(tb, Qt.Key.Key_L)
    assert ctrl.tool == Tool.LASER
    QTest.keyClick(tb, Qt.Key.Key_R)
    assert ctrl.fill_shapes
    QTest.keyClick(tb, Qt.Key.Key_F)
    assert ctrl.spotlight
    QTest.keyClick(tb, Qt.Key.Key_F)
    QTest.keyClick(tb, Qt.Key.Key_M)
    assert ctrl.highlight
    QTest.keyClick(tb, Qt.Key.Key_M)
    assert not ctrl.spotlight and not ctrl.highlight
