"""Pruebas de la versión 1.2.2: editar textos ya escritos, foco rectangular y papel milimetrado."""
import json
import os

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QKeyEvent, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pizarra_virtual import render, session
from pizarra_virtual.items import TextEditItem, TextItem, resolve_items
from pizarra_virtual.tools import PATTERNS, Tool


def _ov(ctrl):
    return ctrl.overlay_for_screen(QGuiApplication.primaryScreen())


def _type(widget, text):
    for ch in text:
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.ShortcutOverride, 0, Qt.KeyboardModifier.NoModifier, ch))
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch))


def _key(ctrl, key, mods=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(ctrl.toolbar, key, mods)


def _click(ov, x, y, button=Qt.MouseButton.LeftButton):
    QTest.mouseClick(ov, button, Qt.KeyboardModifier.NoModifier, QPoint(int(x), int(y)))


def _write(ctrl, x, y, text, size=40):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.TEXT)
    ctrl.set_size(size)
    _click(ov, x, y)
    assert ctrl.text_editor is ov
    _type(ctrl.toolbar, text)
    _key(ctrl, Qt.Key.Key_Escape)
    assert ctrl.text_editor is None


def _texts(ctrl):
    return [i for i in ctrl.items_for(_ov(ctrl).key) if isinstance(i, TextItem)]


def _ink(ov, rect):
    """Píxeles pintados del lienzo dentro de un rectángulo lógico."""
    d = ov.canvas.devicePixelRatio()
    n = 0
    for y in range(int(rect.top() * d), int(rect.bottom() * d), 2):
        for x in range(int(rect.left() * d), int(rect.right() * d), 2):
            if 0 <= x < ov.canvas.width() and 0 <= y < ov.canvas.height():
                n += ov.canvas.pixelColor(x, y).alpha() > 0
    return n


def _center(item):
    return render.text_box(item).center()


# ====================================================================== editar textos


def test_click_on_written_text_reopens_it_and_edit_is_undoable(ctrl):
    ov = _ov(ctrl)
    _write(ctrl, 120, 200, "Hola")
    (orig,) = _texts(ctrl)
    box = render.text_box(orig)
    assert _ink(ov, box) > 0
    c = _center(orig)
    _click(ov, c.x(), c.y())  # clic sobre el texto: se abre para editarlo
    assert ctrl.text_editor is ov and ov.editing_text is not None
    assert ov.editing_text.uid == orig.uid and ov.editing_text.text == "Hola"
    assert _ink(ov, box) == 0  # el original se oculta del lienzo mientras se edita
    _key(ctrl, Qt.Key.Key_End)
    _type(ctrl.toolbar, " mundo")
    _key(ctrl, Qt.Key.Key_Escape)
    texts = _texts(ctrl)
    assert [t.text for t in texts] == ["Hola mundo"]  # sustituido, no duplicado
    assert isinstance(ctrl.history[-1][1], TextEditItem)
    assert _ink(ov, render.text_box(texts[0])) > 0
    ctrl.undo()
    assert [t.text for t in _texts(ctrl)] == ["Hola"]
    ctrl.redo()
    assert [t.text for t in _texts(ctrl)] == ["Hola mundo"]


def test_caret_moves_inserts_and_deletes_in_the_middle(ctrl):
    ov = _ov(ctrl)
    _write(ctrl, 120, 200, "abcdef")
    (t,) = _texts(ctrl)
    c = _center(t)
    _click(ov, c.x(), c.y())
    _key(ctrl, Qt.Key.Key_End)
    _key(ctrl, Qt.Key.Key_Left)
    _key(ctrl, Qt.Key.Key_Left)
    _type(ctrl.toolbar, "X")  # abcdXef
    _key(ctrl, Qt.Key.Key_Backspace)  # abcdef
    _key(ctrl, Qt.Key.Key_Backspace)  # abcef
    _key(ctrl, Qt.Key.Key_Delete)  # abcf
    _key(ctrl, Qt.Key.Key_Home)
    _type(ctrl.toolbar, "ñ")
    _key(ctrl, Qt.Key.Key_Escape)
    assert [x.text for x in _texts(ctrl)] == ["ñabcf"]


def test_click_inside_text_places_caret_where_clicked(ctrl):
    ov = _ov(ctrl)
    _write(ctrl, 100, 200, "aaaa bbbb")
    (t,) = _texts(ctrl)
    box = render.text_box(t)
    _click(ov, box.left() + 2, box.center().y())  # al principio
    assert ov._caret == 0
    _type(ctrl.toolbar, ">")
    now = render.text_box(ov.editing_text)  # el texto ya creció con «>»
    _click(ov, now.right() + 3, now.center().y())  # clic al final del mismo texto: sigue editando
    assert ctrl.text_editor is ov
    _type(ctrl.toolbar, "<")
    _key(ctrl, Qt.Key.Key_Escape)
    assert [x.text for x in _texts(ctrl)] == [">aaaa bbbb<"]


def test_up_down_move_between_lines(ctrl):
    ov = _ov(ctrl)
    _write(ctrl, 100, 200, "uno")
    _click(ov, *_center(_texts(ctrl)[0]).toTuple())
    _key(ctrl, Qt.Key.Key_End)
    _key(ctrl, Qt.Key.Key_Return)
    _type(ctrl.toolbar, "dos")
    _key(ctrl, Qt.Key.Key_Up)
    _key(ctrl, Qt.Key.Key_Home)
    _type(ctrl.toolbar, "1 ")
    _key(ctrl, Qt.Key.Key_Down)
    _key(ctrl, Qt.Key.Key_Home)
    _type(ctrl.toolbar, "2 ")
    _key(ctrl, Qt.Key.Key_Escape)
    assert [x.text for x in _texts(ctrl)] == ["1 uno\n2 dos"]


def test_drag_moves_text_and_small_jitter_does_not(ctrl):
    ov = _ov(ctrl)
    _write(ctrl, 120, 200, "Mover")
    (t,) = _texts(ctrl)
    x0, y0 = t.x, t.y
    c = _center(t)
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, c.toPoint())
    QTest.mouseMove(ov, (c + QPointF(2, 1)).toPoint(), 5)  # temblor del clic
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, (c + QPointF(2, 1)).toPoint())
    assert (ov.editing_text.x, ov.editing_text.y) == (x0, y0)
    c = _center(ov.editing_text)
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, c.toPoint())
    for k in range(1, 11):
        QTest.mouseMove(ov, (c + QPointF(15 * k, 8 * k)).toPoint(), 5)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       (c + QPointF(150, 80)).toPoint())
    _key(ctrl, Qt.Key.Key_Escape)
    (moved,) = _texts(ctrl)
    assert abs(moved.x - (x0 + 150)) <= 1 and abs(moved.y - (y0 + 80)) <= 1
    assert moved.text == "Mover"
    assert _ink(ov, render.text_box(t)) == 0  # ya no queda nada en el sitio original
    assert _ink(ov, render.text_box(moved)) > 0
    ctrl.undo()
    assert (_texts(ctrl)[0].x, _texts(ctrl)[0].y) == (x0, y0)


def test_unchanged_reopen_adds_nothing_and_right_click_cancels(ctrl):
    ov = _ov(ctrl)
    _write(ctrl, 120, 200, "Igual")
    n = len(ctrl.history)
    _click(ov, *_center(_texts(ctrl)[0]).toTuple())
    _key(ctrl, Qt.Key.Key_Escape)
    assert len(ctrl.history) == n  # abrir y cerrar sin cambios no ensucia el historial
    _click(ov, *_center(_texts(ctrl)[0]).toTuple())
    _type(ctrl.toolbar, "zzz")
    _click(ov, 600, 600, Qt.MouseButton.RightButton)  # clic derecho: descarta los cambios
    assert ctrl.text_editor is None and len(ctrl.history) == n
    assert [x.text for x in _texts(ctrl)] == ["Igual"]
    assert _ink(ov, render.text_box(_texts(ctrl)[0])) > 0


def test_erasing_all_letters_deletes_text_and_undo_restores(ctrl):
    ov = _ov(ctrl)
    _write(ctrl, 120, 200, "abc")
    box = render.text_box(_texts(ctrl)[0])
    _click(ov, *box.center().toTuple())
    _key(ctrl, Qt.Key.Key_End)
    for _ in range(3):
        _key(ctrl, Qt.Key.Key_Backspace)
    _key(ctrl, Qt.Key.Key_Escape)
    assert _texts(ctrl) == [] and _ink(ov, box) == 0
    ctrl.undo()
    assert [x.text for x in _texts(ctrl)] == ["abc"]


def test_reopened_text_takes_its_style_and_restyle_applies(ctrl):
    ov = _ov(ctrl)
    ctrl.set_color(QColor("#1e88e5"))
    ctrl.set_text_bold(True)
    _write(ctrl, 120, 200, "Estilo", size=52)
    ctrl.set_color(QColor("#000000"))
    ctrl.set_text_bold(False)
    ctrl.set_size(20)
    _click(ov, *_center(_texts(ctrl)[0]).toTuple())
    # la barra muestra el estilo del texto abierto
    assert ctrl.color.name() == "#1e88e5" and ctrl.text_bold and ctrl.sizes[Tool.TEXT] == 52
    ctrl.set_color(QColor("#c62828"))
    ctrl.set_size(30)
    ctrl.set_opacity(50)
    _key(ctrl, Qt.Key.Key_Escape)
    (t,) = _texts(ctrl)
    assert t.rgba[:3] == (198, 40, 40) and t.size == 30 and t.bold and abs(t.opacity - 0.5) < 1e-9


def test_click_on_empty_area_still_creates_new_text_and_texts_are_independent(ctrl):
    ov = _ov(ctrl)
    _write(ctrl, 120, 200, "uno")
    _write(ctrl, 120, 400, "dos")
    _click(ov, *_center(_texts(ctrl)[1]).toTuple())
    _key(ctrl, Qt.Key.Key_End)
    _type(ctrl.toolbar, "!")
    _key(ctrl, Qt.Key.Key_Escape)
    assert [x.text for x in _texts(ctrl)] == ["uno", "dos!"]  # mismo orden (respeta la goma y capas)


def test_edit_keeps_eraser_order(ctrl, qapp):
    """La goma aplicada después del texto sigue borrando la versión editada."""
    from pizarra_virtual.items import StrokeItem

    ov = _ov(ctrl)
    _write(ctrl, 100, 200, "WWWWWW", size=60)
    box = render.text_box(_texts(ctrl)[0])
    y = box.center().y()
    ctrl.push(ov.key, StrokeItem(Tool.ERASER, (0, 0, 0, 255), 80, 1.0,
                                 points=[(box.left() - 5, y, 80), (box.left() + 60, y, 80)]))
    ov.rebuild()
    erased = _ink(ov, box)
    _click(ov, box.right() - 10, y)
    _key(ctrl, Qt.Key.Key_End)
    _type(ctrl.toolbar, "W")
    _key(ctrl, Qt.Key.Key_Escape)
    left = render.text_box(_texts(ctrl)[0])
    left.setWidth(55)
    assert _ink(ov, left) == 0 and erased > 0  # la zona borrada sigue borrada


def test_session_roundtrip_with_edits_and_old_files(ctrl, tmp_path):
    ov = _ov(ctrl)
    _write(ctrl, 120, 200, "antes")
    _click(ov, *_center(_texts(ctrl)[0]).toTuple())
    _key(ctrl, Qt.Key.Key_End)
    _type(ctrl.toolbar, " y después")
    _key(ctrl, Qt.Key.Key_Escape)
    path = str(tmp_path / "clase.pizarra")
    assert ctrl.save_session(path)
    ctrl.dirty = False
    ctrl.open_session(path)
    assert [x.text for x in _texts(ctrl)] == ["antes y después"]
    ctrl.undo()  # el historial se conserva: se puede deshacer la edición tras abrir
    assert [x.text for x in _texts(ctrl)] == ["antes"]
    # archivo de la 1.2.0/1.2.1: textos sin «uid»
    d = session.item_to_dict(TextItem((0, 0, 0, 255), 30, 1.0, 5, 5, "viejo"))
    d.pop("uid")
    old = session.item_from_dict(json.loads(json.dumps(d)))
    assert old.text == "viejo" and old.uid


def test_pdf_and_page_images_use_edited_text(ctrl, tmp_path):
    ov = _ov(ctrl)
    ctrl.set_background("white")
    _write(ctrl, 120, 200, "x")
    _click(ov, *_center(_texts(ctrl)[0]).toTuple())
    for _ in range(3):
        _key(ctrl, Qt.Key.Key_Right)
    _type(ctrl.toolbar, "yz")
    _key(ctrl, Qt.Key.Key_Escape)
    (img,) = ctrl.page_images()
    assert img.width() > 0
    assert ctrl.page.items_for(ov.key)[0].text == "xyz"
    out = ctrl.export_pdf(str(tmp_path / "a.pdf"))
    assert out and os.path.getsize(out) > 0


def test_resolve_items_is_pure():
    a = TextItem((0, 0, 0, 255), 20, 1.0, 0, 0, "a")
    edit = TextEditItem(a.uid, TextItem((0, 0, 0, 255), 20, 1.0, 0, 0, "b", uid=a.uid))
    hist = [a, edit]
    assert [t.text for t in resolve_items(hist)] == ["b"]
    assert [t.text for t in resolve_items(hist, exclude_uid=a.uid)] == []
    assert hist == [a, edit] and a.text == "a"


# ====================================================================== foco rectangular


def _grab(ov) -> QImage:
    QApplication.processEvents()
    img = ov.grab().toImage()
    img.setDevicePixelRatio(1.0)
    return img


def _dark(ov, img, x, y):
    d = ov.devicePixelRatioF()
    return img.pixelColor(round(x * d), round(y * d)).alpha() > 150


def test_rectangular_spotlight_is_a_wide_band(ctrl):
    ov = _ov(ctrl)
    cx, cy = ov.width() // 2, ov.height() // 2
    r = int(min(120, ov.width() / 6, ov.height() / 4))
    QCursor.setPos(ov.mapToGlobal(QPoint(cx, cy)))
    ctrl.spotlight_radius = r
    ctrl.toggle_spotlight()
    ctrl._tick()
    circle = _grab(ov)
    ctrl.set_spotlight_shape("rect")
    ctrl._tick()
    rect = _grab(ov)
    side, below = (cx + 1.6 * r, cy), (cx, cy + 0.7 * r)
    assert not _dark(ov, circle, cx, cy) and not _dark(ov, rect, cx, cy)  # centro visible en ambos
    assert _dark(ov, circle, *side) and not _dark(ov, rect, *side)  # la franja es más ancha
    assert not _dark(ov, circle, *below) and _dark(ov, rect, *below)  # y más baja
    assert _dark(ov, rect, cx, cy + 1.5 * r) and _dark(ov, rect, cx + 2.3 * r, cy)  # fuera: oscuro
    ctrl.toggle_spotlight()


def test_spotlight_shape_shortcut_menu_tray_and_settings(ctrl, qapp, tmp_path):
    from PySide6.QtCore import QSettings

    from pizarra_virtual.app import Controller

    assert ctrl.spotlight_shape == "circle" and not ctrl.spotlight
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier)
    assert ctrl.spotlight_shape == "rect" and ctrl.spotlight  # Shift+F cambia la forma y lo activa
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier)
    assert ctrl.spotlight_shape == "circle"
    menu = ctrl.toolbar.build_spotlight_menu()
    acts = menu.actions()
    assert [a.text() for a in acts] == ["Foco: círculo", "Foco: rectángulo"] and acts[0].isChecked()
    acts[1].trigger()
    assert ctrl.spotlight_shape == "rect"
    ctrl._save_settings()
    other = Controller(qapp, settings=ctrl.settings, enable_hotkeys=False, enable_tray=False)
    try:
        assert other.spotlight_shape == "rect"  # se recuerda
    finally:
        other.shutdown()
    ctrl.settings.setValue("spotlight_shape", "triangulo")
    bad = Controller(qapp, settings=ctrl.settings, enable_hotkeys=False, enable_tray=False)
    try:
        assert bad.spotlight_shape == "circle"
    finally:
        bad.shutdown()


# ====================================================================== milimetrado


def test_millimeter_paper_pattern():
    assert "mm" in PATTERNS
    img = QImage(400, 300, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    render.draw_pattern(p, 400, 300, "mm", "white")
    p.end()

    def dark(x, y):
        c = img.pixelColor(x, y)
        return 255 * 3 - (c.red() + c.green() + c.blue())

    row = 4  # entre líneas horizontales
    fine, mid, major, gap = dark(8, row), dark(40, row), dark(80, row), dark(12, row)
    assert gap == 0 and 0 < fine < mid < major  # tres grosores de línea: 1, 5 y 10 «mm»
    lines = sum(1 for x in range(0, 400) if dark(x, row) > 0)
    assert 45 <= lines <= 60  # una línea cada 8 px
    for bg in ("chalk", "dim", "transparent"):
        img2 = QImage(100, 100, QImage.Format.Format_ARGB32_Premultiplied)
        img2.fill(QColor(0, 0, 0, 0))
        p = QPainter(img2)
        render.draw_pattern(p, 100, 100, "mm", bg)
        p.end()
        assert img2.pixelColor(8, 4).alpha() > 0
