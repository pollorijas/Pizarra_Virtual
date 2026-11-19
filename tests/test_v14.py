"""Pruebas de la versión 1.4: seleccionar y mover, pegar imágenes, formas perfectas y temporizador."""
import math
import random

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage
from PySide6.QtTest import QTest

from pizarra_virtual import render
from pizarra_virtual.items import (
    DeleteItem, DuplicateItem, ImageItem, ShapeItem, StrokeItem, TextItem, TransformItem, resolve_items, transformed,
)
from pizarra_virtual.shape_recognition import recognize
from pizarra_virtual.tools import Tool


def _ov(ctrl):
    return ctrl.overlay_for_screen(QGuiApplication.primaryScreen())


def _drag(ov, pts, mods=Qt.KeyboardModifier.NoModifier):
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, mods, QPoint(*map(int, pts[0])))
    for x, y in pts[1:]:
        QTest.mouseMove(ov, QPoint(int(x), int(y)), 3)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, mods, QPoint(*map(int, pts[-1])))


def _click(ov, x, y):
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(x), int(y)))


def _ink(ov, x, y, r=3):
    d = ov.canvas.devicePixelRatio()
    return any(ov.canvas.pixelColor(round((x + dx) * d), round((y + dy) * d)).alpha() > 0
               for dx in range(-r, r + 1) for dy in range(-r, r + 1))


def _line(ctrl, y, x0=100, x1=300, tool=Tool.BRUSH, size=10):
    ctrl.set_tool(tool)
    ctrl.set_size(size)
    _drag(_ov(ctrl), [(x, y) for x in range(x0, x1 + 1, 10)])
    return ctrl.history[-1][1]


def _visible(ctrl):
    return ctrl.items_for(_ov(ctrl).key)


# ====================================================================== seleccionar y mover


def test_click_selects_and_drag_moves_with_undo(ctrl):
    ov = _ov(ctrl)
    stroke = _line(ctrl, 150)
    ctrl.set_tool(Tool.SELECT)
    _drag(ov, [(200, 150), (200, 200), (200, 250), (200, 300)])
    assert ov.selection == [stroke.uid]
    assert isinstance(ctrl.history[-1][1], TransformItem)
    assert _ink(ov, 200, 300) and not _ink(ov, 200, 150)
    ctrl.undo()
    assert _ink(ov, 200, 150) and not _ink(ov, 200, 300)
    ctrl.redo()
    assert _ink(ov, 200, 300)


def test_click_on_empty_area_selects_nothing(ctrl):
    ov = _ov(ctrl)
    _line(ctrl, 150)
    ctrl.set_tool(Tool.SELECT)
    _click(ov, 500, 450)
    assert ov.selection == []
    n = len(ctrl.history)
    _click(ov, 200, 150)  # clic sin mover: selecciona pero no añade nada al historial
    assert ov.selection and len(ctrl.history) == n


def test_lasso_selects_only_what_is_inside(ctrl):
    ov = _ov(ctrl)
    a = _line(ctrl, 120, 100, 200)
    b = _line(ctrl, 180, 100, 200)
    c = _line(ctrl, 400, 400, 500)  # fuera del lazo
    ctrl.set_tool(Tool.RECT)
    _drag(ov, [(120, 220), (180, 260)])
    rect = ctrl.history[-1][1]
    ctrl.set_tool(Tool.SELECT)
    lasso = [(80, 90), (240, 90), (240, 290), (80, 290), (80, 92)]
    _drag(ov, lasso)
    assert set(ov.selection) == {a.uid, b.uid, rect.uid}
    assert c.uid not in ov.selection


def test_scale_with_corner_handle(ctrl):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.RECT)
    _drag(ov, [(100, 100), (200, 160)])
    ctrl.set_tool(Tool.SELECT)
    _click(ov, 100, 130)
    box = ov.items_rect(ov.selected_items())
    h = box.bottomRight()
    _drag(ov, [(h.x(), h.y()), (h.x() + 50, h.y() + 30), (h.x() + 100, h.y() + 60)])
    t = ctrl.history[-1][1]
    assert isinstance(t, TransformItem) and t.scale > 1.5
    (shape,) = [i for i in _visible(ctrl) if isinstance(i, ShapeItem)]
    assert (shape.x2 - shape.x1) > 150  # crece desde la esquina superior izquierda del recuadro
    assert abs(ov.items_rect([shape]).left() - box.left()) < 12 and abs(ov.items_rect([shape]).top() - box.top()) < 12


def test_delete_duplicate_select_all_and_escape(ctrl):
    ov, tb = _ov(ctrl), ctrl.toolbar
    a = _line(ctrl, 120)
    _line(ctrl, 300)
    ctrl.set_tool(Tool.SELECT)
    _click(ov, 200, 120)
    QTest.keyClick(tb, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)  # duplicar
    assert isinstance(ctrl.history[-1][1], DuplicateItem)
    copy_uid = ov.selection[0]
    assert copy_uid != a.uid and len(_visible(ctrl)) == 3
    assert _ink(ov, 224, 144)  # la copia aparece desplazada
    QTest.keyClick(tb, Qt.Key.Key_Delete)  # Supr con selección: borra solo la selección
    assert isinstance(ctrl.history[-1][1], DeleteItem) and len(_visible(ctrl)) == 2
    QTest.keyClick(tb, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert len(ov.selection) == 2
    QTest.keyClick(tb, Qt.Key.Key_Escape)  # Esc: primero quita la selección
    assert ov.selection == [] and ctrl.drawing
    QTest.keyClick(tb, Qt.Key.Key_Escape)  # luego, «Ratón libre» como siempre
    assert not ctrl.drawing
    ctrl.set_drawing(True)
    QTest.keyClick(tb, Qt.Key.Key_Delete)  # sin selección: borra la página (como antes)
    assert _visible(ctrl)[-1].__class__.__name__ == "ClearItem"


def test_erased_part_travels_with_moved_stroke(ctrl):
    ov = _ov(ctrl)
    stroke = _line(ctrl, 200, 100, 400, size=14)
    ctrl.set_tool(Tool.ERASER)
    ctrl.set_size(40)
    _drag(ov, [(250, 170), (250, 200), (250, 230)])  # corta la línea por la mitad
    assert not _ink(ov, 250, 200, 1)
    ctrl.set_tool(Tool.SELECT)
    _drag(ov, [(150, 200), (150, 260), (150, 300)])  # clic en la parte izquierda y mover 100 px abajo
    assert ov.selection == [stroke.uid]
    assert _ink(ov, 150, 300) and _ink(ov, 350, 300)
    assert not _ink(ov, 250, 300, 1)  # el corte sigue ahí después de moverla
    assert not _ink(ov, 150, 200)  # y no queda nada en el sitio anterior


def test_fully_erased_items_cannot_be_selected(ctrl):
    ov = _ov(ctrl)
    _line(ctrl, 200, 100, 200)
    ctrl.set_tool(Tool.ERASER)
    ctrl.set_size(80)
    _drag(ov, [(x, 200) for x in range(60, 260, 10)])
    ctrl.set_tool(Tool.SELECT)
    _click(ov, 150, 200)
    assert ov.selection == []
    _drag(ov, [(50, 150), (300, 150), (300, 250), (50, 250), (50, 152)])
    assert ov.selection == []
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert ov.selection == []


def test_moved_text_stays_editable_and_template_parts_move_alone(ctrl):
    ov = _ov(ctrl)
    ctrl.insert_template("concept_map")
    texts = [i for i in _visible(ctrl) if isinstance(i, TextItem)]
    idea = next(t for t in texts if t.text == "Idea 1")
    c = render.text_box(idea).center()
    ctrl.set_tool(Tool.SELECT)
    _drag(ov, [(c.x(), c.y()), (c.x() + 30, c.y() + 40), (c.x() + 60, c.y() + 80)])
    moved = next(t for t in _visible(ctrl) if isinstance(t, TextItem) and t.uid == idea.uid)
    assert abs(moved.x - (idea.x + 60)) < 1 and abs(moved.y - (idea.y + 80)) < 1
    others = [t for t in _visible(ctrl) if isinstance(t, TextItem) and t.uid != idea.uid]
    assert [(t.x, t.y) for t in others] == [(t.x, t.y) for t in texts if t.uid != idea.uid]
    ctrl.set_tool(Tool.TEXT)  # el texto movido se sigue editando con un clic
    _click(ov, *render.text_box(moved).center().toTuple())
    assert ov.editing_text is not None and ov.editing_text.uid == idea.uid
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)


def test_select_tool_toolbar_state(ctrl):
    tb = ctrl.toolbar
    QTest.keyClick(tb, Qt.Key.Key_A)
    assert ctrl.tool == Tool.SELECT and tb.select_btn.isChecked()
    assert tb.size_slider.isHidden() and tb.opacity_slider.isHidden()
    QTest.keyClick(tb, Qt.Key.Key_1)
    assert not tb.select_btn.isChecked() and not tb.size_slider.isHidden()


def test_transform_delete_duplicate_session_roundtrip(ctrl, tmp_path):
    ov = _ov(ctrl)
    _line(ctrl, 120)
    _line(ctrl, 300)
    ctrl.set_tool(Tool.SELECT)
    _drag(ov, [(200, 120), (260, 180)])
    _click(ov, 200, 300)
    ctrl.duplicate_selection()
    ctrl.delete_selection()
    before = [(type(i).__name__, getattr(i, "uid", None)) for i in _visible(ctrl)]
    path = str(tmp_path / "mover.pizarra")
    assert ctrl.save_session(path)
    ctrl.dirty = False
    ctrl.open_session(path)
    after = [(type(i).__name__, getattr(i, "uid", None)) for i in _visible(ctrl)]
    assert before == after
    ctrl.undo()  # deshacer «eliminar» tras abrir la sesión
    assert len(_visible(ctrl)) == len(before) + 1


def test_resolve_moves_to_front_and_carries_erasers():
    a = StrokeItem(Tool.BRUSH, (0, 0, 0, 255), 4, points=[(0, 0, 4), (10, 0, 4)])
    e = StrokeItem(Tool.ERASER, (0, 0, 0, 255), 4, points=[(5, 0, 4)])
    b = StrokeItem(Tool.BRUSH, (0, 0, 0, 255), 4, points=[(0, 5, 4)])
    out = resolve_items([a, e, b, TransformItem([a.uid], 100, 0)])
    assert [type(i).__name__ for i in out] == ["StrokeItem", "StrokeItem", "StrokeItem"]
    assert out[0] is e and out[1] is b and out[2].uid == a.uid  # delante de todo
    assert out[2].points[0][0] == 100 and out[2].mask[0].points[0][0] == 105  # la goma viaja con él
    assert a.points[0][0] == 0 and not a.mask  # el historial no se modifica
    assert transformed(a, scale=2).size == 8


# ====================================================================== pegar


def _set_clipboard(mime):
    QGuiApplication.clipboard().setMimeData(mime)


def _red_image(w=400, h=200):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(220, 30, 30))
    return img


def test_paste_image_at_cursor_selected_and_saved(ctrl, tmp_path):
    ov = _ov(ctrl)
    QCursor.setPos(ov.mapToGlobal(QPoint(300, 250)))
    mime = QMimeData()
    mime.setImageData(_red_image())
    _set_clipboard(mime)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    item = ctrl.history[-1][1]
    assert isinstance(item, ImageItem)
    assert abs(item.x + item.w / 2 - 300) < 2 or item.x == 0  # centrada en el cursor (si cabe)
    assert item.w <= ov.width() * 0.5 + 1 and item.h <= ov.height() * 0.5 + 1
    assert ctrl.tool == Tool.SELECT and ov.selection == [item.uid]
    d = ov.canvas.devicePixelRatio()
    c = ov.canvas.pixelColor(round((item.x + item.w / 2) * d), round((item.y + item.h / 2) * d))
    assert c.red() > 200 and c.green() < 60
    path = str(tmp_path / "imagen.pizarra")
    assert ctrl.save_session(path)
    ctrl.dirty = False
    ctrl.open_session(path)
    (img,) = [i for i in _visible(ctrl) if isinstance(i, ImageItem)]
    assert not render.image_of(img).isNull() and (img.w, img.h) == (item.w, item.h)
    assert ctrl.export_pdf(str(tmp_path / "con_imagen.pdf"))


def test_big_image_is_reduced_to_fit(ctrl):
    ov = _ov(ctrl)
    ctrl.paste_image(_red_image(4000, 3000))
    item = ctrl.history[-1][1]
    assert item.w <= ov.width() * 0.5 + 1 and item.h <= ov.height() * 0.5 + 1
    stored = QImage.fromData(item.data)
    assert stored.width() <= round(item.w * ov.devicePixelRatioF() * 2) + 1  # no guarda más de lo necesario


def test_paste_image_file_and_text_and_nothing(ctrl, tmp_path):
    ov = _ov(ctrl)
    QCursor.setPos(ov.mapToGlobal(QPoint(200, 200)))
    f = tmp_path / "foto.png"
    _red_image(120, 80).save(str(f))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(f))])
    _set_clipboard(mime)
    assert ctrl.paste() and isinstance(ctrl.history[-1][1], ImageItem)
    mime = QMimeData()
    mime.setText("Hola\r\nclase")
    _set_clipboard(mime)
    assert ctrl.paste()
    t = ctrl.history[-1][1]
    assert isinstance(t, TextItem) and t.text == "Hola\nclase"
    _set_clipboard(QMimeData())
    n = len(ctrl.history)
    assert not ctrl.paste() and len(ctrl.history) == n


def test_ctrl_v_while_typing_still_pastes_into_the_text(ctrl):
    ov = _ov(ctrl)
    mime = QMimeData()
    mime.setText("pegado")
    _set_clipboard(mime)
    ctrl.set_tool(Tool.TEXT)
    _click(ov, 200, 200)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    texts = [i for i in _visible(ctrl) if isinstance(i, TextItem)]
    assert [t.text for t in texts] == ["pegado"] and ctrl.tool == Tool.TEXT


# ====================================================================== formas perfectas


def _jitter(pts, amp=2.5, seed=1):
    r = random.Random(seed)
    return [(x + r.uniform(-amp, amp), y + r.uniform(-amp, amp)) for x, y in pts]


def _poly(vs, close=True, step=3):
    loop = vs + ([vs[0]] if close else [])
    out = []
    for a, b in zip(loop, loop[1:]):
        n = max(1, int(math.dist(a, b) // step))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    return out + [loop[-1]]


def _ell(cx, cy, rx, ry, turn=1.0, n=120):
    return [(cx + rx * math.cos(0.3 + 2 * math.pi * turn * k / n), cy + ry * math.sin(0.3 + 2 * math.pi * turn * k / n))
            for k in range(n + 1)]


CASES = [
    ("línea", _poly([(100, 100), (400, 130)], close=False), "line"),
    ("línea casi horizontal", _poly([(100, 100), (400, 112)], close=False), "line"),
    ("círculo", _ell(300, 300, 100, 100), "ellipse"),
    ("círculo que se pasa del inicio", _ell(300, 300, 100, 100, turn=1.08), "ellipse"),
    ("elipse", _ell(300, 300, 160, 80), "ellipse"),
    ("cuadrado", _poly([(100, 100), (300, 100), (300, 300), (100, 300)]), "rect"),
    ("rectángulo desde la mitad de un lado", _poly([(200, 100), (400, 100), (400, 250), (100, 250), (100, 100)]),
     "rect"),
    ("rombo", _poly([(250, 100), (400, 250), (250, 400), (100, 250)]), "polygon"),
    ("triángulo", _poly([(250, 100), (400, 350), (100, 350)]), "polygon"),
    ("pentágono", _poly([(250 + 150 * math.cos(-math.pi / 2 + k * 2 * math.pi / 5),
                          250 + 150 * math.sin(-math.pi / 2 + k * 2 * math.pi / 5)) for k in range(5)]), "polygon"),
    ("arco abierto", _ell(300, 300, 100, 100, turn=0.5), None),
    ("V abierta", _poly([(100, 100), (200, 300), (300, 100)], close=False), None),
    ("zigzag", _poly([(100, 100), (150, 200), (200, 100), (250, 200), (300, 100)], close=False), None),
    ("punto", [(100, 100), (101, 101), (102, 100), (101, 99)], None),
]


@pytest.mark.parametrize("name,pts,want", CASES, ids=[c[0] for c in CASES])
def test_recognition_of_hand_drawn_strokes(name, pts, want):
    for seed in range(4):
        for amp in (1.5, 4.0):
            s = StrokeItem(Tool.PEN, (0, 0, 0, 255), 4, points=[(x, y, 4) for x, y in _jitter(pts, amp, seed)])
            r = recognize(s)
            got = None if r is None else (r.tool.value if isinstance(r, ShapeItem) else "polygon")
            assert got == want, (name, seed, amp)


def test_recognized_shapes_are_clean():
    line = recognize(StrokeItem(Tool.PEN, (0, 0, 0, 255), 4, points=[(x, 100 + x * 0.05, 4) for x in range(100, 400, 3)]))
    assert line.y1 == pytest.approx(line.y2)  # casi horizontal: se endereza
    circ = recognize(StrokeItem(Tool.BRUSH, (0, 0, 0, 255), 6, points=[(x, y, 6) for x, y in _ell(300, 300, 100, 94)]))
    assert circ.x2 - circ.x1 == pytest.approx(circ.y2 - circ.y1)  # casi redondo: círculo
    tri = recognize(StrokeItem(Tool.PENCIL, (0, 0, 0, 255), 3,
                               points=[(x, y, 3) for x, y in _poly([(250, 100), (400, 350), (100, 350)])]))
    corners = {(round(x), round(y)) for x, y, _w in tri.points}
    for v in ((250, 100), (400, 350), (100, 350)):
        assert min(math.dist(v, c) for c in corners) < 6  # respeta las esquinas dibujadas


def test_recognition_is_off_by_default_and_toggles(ctrl, qapp):
    from pizarra_virtual.app import Controller

    ov, tb = _ov(ctrl), ctrl.toolbar
    assert not ctrl.recognize_shapes
    ctrl.set_tool(Tool.PEN)
    assert not tb.recognize_btn.isHidden() and not tb.recognize_btn.isChecked()
    circle = _ell(300, 300, 80, 80, n=60)
    _drag(ov, circle)
    assert isinstance(ctrl.history[-1][1], StrokeItem)  # desactivado: el trazo queda tal cual
    QTest.keyClick(tb, Qt.Key.Key_G)
    assert ctrl.recognize_shapes and tb.recognize_btn.isChecked()
    _drag(ov, circle)
    shape = ctrl.history[-1][1]
    assert isinstance(shape, ShapeItem) and shape.tool == Tool.ELLIPSE
    assert _ink(ov, 380, 300) and not _ink(ov, 300, 300)
    ctrl.set_tool(Tool.HIGHLIGHTER)  # el destacador no se transforma
    assert tb.recognize_btn.isHidden()
    _drag(ov, circle)
    assert isinstance(ctrl.history[-1][1], StrokeItem)
    ctrl._save_settings()
    other = Controller(qapp, settings=ctrl.settings, enable_hotkeys=False, enable_tray=False)
    try:
        assert other.recognize_shapes
    finally:
        other.shutdown()


# ====================================================================== temporizador


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _timer(ctrl, seconds=60):
    ctrl.start_timer(seconds)
    w = ctrl.timer_window
    clock = FakeClock()
    w.clock = clock
    beeps = []
    w.beep = lambda: beeps.append(1)
    w.start_countdown(seconds)
    return w, clock, beeps


def test_countdown_pause_add_minutes_and_finish(ctrl, qapp):
    w, clock, beeps = _timer(ctrl, 60)
    assert w.isVisible() and w.label.text() == "01:00"
    clock.t += 30
    w.tick()
    assert w.label.text() == "00:30"
    w.toggle_pause()
    clock.t += 100
    w.tick()
    assert w.label.text() == "00:30"  # en pausa no avanza
    w.toggle_pause()
    w.add_minutes(1)
    w.tick()
    assert w.label.text() == "01:30"
    w.add_minutes(-5)
    w.tick()
    assert w.label.text() == "00:10"  # nunca baja de 10 segundos
    clock.t += 11
    w.tick()
    assert w.finished and w.label.text() == "¡Tiempo!" and len(beeps) == 1
    for _ in range(4):
        clock.t += 0.8
        w.tick()
    assert len(beeps) == 3  # tres avisos, ni uno más
    clock.t += 20
    w.tick()
    assert w.label.text() == "¡Tiempo!"
    w.restart()
    assert not w.finished and w.label.text() == "01:00"


def test_stopwatch_counts_up(ctrl):
    ctrl.start_stopwatch()
    w = ctrl.timer_window
    clock = FakeClock()
    w.clock = clock
    w.start_stopwatch()
    clock.t += 125
    w.tick()
    assert w.label.text() == "02:05" and w.title.text() == "CRONÓMETRO"
    assert w.plus_btn.isHidden() and w.minus_btn.isHidden()


def test_closing_timer_does_not_close_the_program(ctrl, qapp, monkeypatch):
    calls = []
    monkeypatch.setattr(qapp, "quit", lambda: calls.append(1))
    w, clock, _ = _timer(ctrl, 300)
    w.close()
    qapp.processEvents()
    assert not w.isVisible() and calls == [] and not ctrl.shutting_down
    assert ctrl.toolbar.isVisible() and all(ov.isVisible() for ov in ctrl.overlays.values())


def test_timer_menu_and_hidden_during_capture(ctrl, qapp, monkeypatch):
    from pizarra_virtual import capture

    menu = ctrl.toolbar.build_timer_menu()
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels[:3] == ["1 minuto", "2 minutos", "3 minutos"] and "Cronómetro (cuenta hacia arriba)" in labels
    menu.actions()[3].trigger()  # 5 minutos
    w = ctrl.timer_window
    assert w.isVisible() and w.mode == "down" and abs(w.total_ms - 300_000) < 1
    seen = {}
    monkeypatch.setattr(capture, "grab_screen", lambda s: (seen.setdefault("timer", w.isVisible()), QImage(10, 10, QImage.Format.Format_RGB32))[1])
    monkeypatch.setattr(capture, "save_capture", lambda img, *a: "x.png")
    ctrl.capture(with_drawing=False)
    QTest.qWait(400)
    assert seen.get("timer") is False and w.isVisible()  # oculto en la captura y vuelve a verse
    assert "Cerrar el temporizador" in [a.text() for a in ctrl.toolbar.build_timer_menu().actions()]


def test_new_toolbar_buttons(ctrl):
    tb = ctrl.toolbar
    for b in (tb.select_btn, tb.timer_btn, tb.paste_btn):
        assert not b.isHidden()
    mime = QMimeData()
    mime.setText("desde el botón")
    _set_clipboard(mime)
    tb.paste_btn.click()
    assert isinstance(ctrl.history[-1][1], TextItem)


def test_workflow_uses_current_actions():
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".github", "workflows",
                        "build.yml")
    text = open(path, encoding="utf-8").read()
    for old in ("checkout@v4", "setup-python@v5", "upload-artifact@v4", "action-gh-release@v2"):
        assert old not in text
