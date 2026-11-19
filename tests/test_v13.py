"""Pruebas de la versión 1.3: textos borrados con la goma, figuras nuevas, sellos y plantillas."""
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pizarra_virtual import render
from pizarra_virtual.items import TextItem
from pizarra_virtual.tools import Tool


def _ov(ctrl):
    return ctrl.overlay_for_screen(QGuiApplication.primaryScreen())


def _type(widget, text):
    for ch in text:
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.ShortcutOverride, 0, Qt.KeyboardModifier.NoModifier, ch))
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch))


def _click(ov, x, y, button=Qt.MouseButton.LeftButton):
    QTest.mouseClick(ov, button, Qt.KeyboardModifier.NoModifier, QPoint(int(x), int(y)))


def _drag(ov, pts):
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*map(int, pts[0])))
    for x, y in pts[1:]:
        QTest.mouseMove(ov, QPoint(int(x), int(y)), 3)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*map(int, pts[-1])))


def _write(ctrl, x, y, text, size=48):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.TEXT)
    ctrl.set_size(size)
    _click(ov, x, y)
    _type(ctrl.toolbar, text)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    return [i for i in ctrl.items_for(ov.key) if isinstance(i, TextItem)][-1]


def _erase(ctrl, x0, x1, y, size=120):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.ERASER)
    ctrl.set_size(size)
    _drag(ov, [(x, y) for x in range(int(x0), int(x1) + 1, 8)])


def _texts(ctrl):
    return [i for i in ctrl.items_for(_ov(ctrl).key) if isinstance(i, TextItem)]


# ====================================================================== textos borrados


def test_text_fully_erased_cannot_be_reopened(ctrl):
    ov = _ov(ctrl)
    t = _write(ctrl, 150, 200, "Borrar")
    box = render.text_box(t)
    _erase(ctrl, box.left() - 40, box.right() + 40, box.center().y())
    ctrl.set_tool(Tool.TEXT)
    _click(ov, *box.center().toTuple())
    # el clic empieza un texto nuevo; el borrado no se reabre
    assert ov.editing_text is not None and ov.editing_text.uid != t.uid and ov.editing_text.text == ""
    _type(ctrl.toolbar, "nuevo")
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    assert [x.text for x in _texts(ctrl)] == ["Borrar", "nuevo"]  # el borrado sigue en el historial (deshacer)


def test_text_after_clear_all_cannot_be_reopened(ctrl):
    ov = _ov(ctrl)
    t = _write(ctrl, 150, 200, "Antes")
    ctrl.clear_all()
    ctrl.set_tool(Tool.TEXT)
    _click(ov, *render.text_box(t).center().toTuple())
    assert ov.editing_text.uid != t.uid
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    ctrl.undo()  # al deshacer «Borrar todo» vuelve a ser editable
    _click(ov, *render.text_box(t).center().toTuple())
    assert ov.editing_text.uid == t.uid
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)


def test_partially_erased_text_opens_only_on_visible_part_and_keeps_erasure(ctrl):
    ov = _ov(ctrl)
    t = _write(ctrl, 150, 200, "MMMMMMMM", size=56)
    box = render.text_box(t)
    y = box.center().y()
    _erase(ctrl, box.left() - 60, box.left() + box.width() * 0.4, y, size=110)
    ctrl.set_tool(Tool.TEXT)
    _click(ov, box.left() + box.width() * 0.15, y)  # parte borrada: texto nuevo
    assert ov.editing_text.uid != t.uid
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    _click(ov, box.left() + box.width() * 0.8, y)  # parte visible: se abre
    assert ov.editing_text.uid == t.uid
    # mientras se edita, lo borrado sigue borrado en la vista previa
    d = ov.layer.devicePixelRatio()
    erased = [ov.layer.pixelColor(int(x * d), int(y * d)).alpha()
              for x in range(int(box.left() + 4), int(box.left() + box.width() * 0.3), 3)]
    visible = [ov.layer.pixelColor(int(x * d), int(yy * d)).alpha()
               for x in range(int(box.left() + box.width() * 0.6), int(box.right()), 2)
               for yy in range(int(box.top()), int(box.bottom()), 3)]
    assert max(erased) == 0 and max(visible) > 0
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)


# ====================================================================== figuras nuevas

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402

from pizarra_virtual import session, templates  # noqa: E402
from pizarra_virtual.items import GroupItem, ShapeItem, StampItem, TextEditItem, flatten  # noqa: E402
from pizarra_virtual.tools import EXTRA_SHAPES, FILLABLE_SHAPES, STAMPS, TOOL_SPECS  # noqa: E402


def _ink_count(img, rect=None, outside=False):
    n = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            if img.pixelColor(x, y).alpha() > 0:
                inside = rect is None or rect.contains(QPointF(x, y))
                n += (not inside) if outside else inside
    return n


def test_every_new_shape_draws_inside_its_rect():
    for tool in EXTRA_SHAPES:
        for (x1, y1, x2, y2) in ((60, 50, 260, 210), (260, 210, 60, 50), (60, 210, 260, 50)):
            for filled in (False, True):
                item = ShapeItem(tool, (20, 40, 200, 255), 6, 1.0, x1, y1, x2, y2, filled=filled)
                img = QImage(320, 260, QImage.Format.Format_ARGB32_Premultiplied)
                img.fill(0)
                p = QPainter(img)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                render.draw_shape(p, item)
                p.end()
                assert _ink_count(img) > 20, tool
                # nada fuera del rectángulo que se repinta (si no, quedarían restos en pantalla)
                assert _ink_count(img, render.shape_rect(item), outside=True) == 0, (tool, x1, y1)


def test_fill_only_for_closed_shapes():
    def ink(tool, filled):
        img = QImage(200, 200, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        render.draw_shape(p, ShapeItem(tool, (0, 0, 0, 255), 3, 1.0, 20, 20, 180, 180, filled=filled))
        p.end()
        return _ink_count(img)
    for tool in EXTRA_SHAPES:
        if tool in FILLABLE_SHAPES:
            assert ink(tool, True) > ink(tool, False) * 2, tool
        else:
            assert ink(tool, True) == ink(tool, False), tool


def test_draw_new_shapes_with_mouse_and_shift(ctrl):
    ov = _ov(ctrl)
    for tool in EXTRA_SHAPES:
        ctrl.set_tool(tool)
        n = len(ctrl.history)
        _drag(ov, [(100, 100), (200, 150), (300, 260)])
        assert len(ctrl.history) == n + 1 and ctrl.history[-1][1].tool == tool
    ctrl.set_tool(Tool.HEXAGON)
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 100))
    QTest.mouseMove(ov, QPoint(300, 160), 5)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, QPoint(300, 160))
    sh = ctrl.history[-1][1]
    assert abs(abs(sh.x2 - sh.x1) - abs(sh.y2 - sh.y1)) < 1e-6  # con Mayús: proporcionado


def test_shape_shortcuts_menu_and_toolbar_state(ctrl, qapp):
    tb = ctrl.toolbar
    for key, tool in ((Qt.Key.Key_D, Tool.DIAMOND), (Qt.Key.Key_E, Tool.STAR), (Qt.Key.Key_Q, Tool.ROUNDED_RECT),
                      (Qt.Key.Key_J, Tool.AXES), (Qt.Key.Key_W, Tool.DOUBLE_ARROW), (Qt.Key.Key_U, Tool.CURVED_ARROW),
                      (Qt.Key.Key_K, Tool.BRACE)):
        QTest.keyClick(tb, key)
        assert ctrl.tool == tool, key
        assert tb.more_shapes_btn.isChecked()
        assert not any(b.isChecked() for b in tb.tool_buttons.values())
    QTest.keyClick(tb, Qt.Key.Key_P)
    assert ctrl.tool == Tool.HEXAGON or ctrl.tool in (Tool.PENTAGON, Tool.OCTAGON)
    seen = {ctrl.tool}
    for _ in range(3):
        QTest.keyClick(tb, Qt.Key.Key_P)
        seen.add(ctrl.tool)
    assert seen == {Tool.PENTAGON, Tool.HEXAGON, Tool.OCTAGON}
    menu = tb.build_shapes_menu()
    acts = [a for a in menu.actions() if not a.isSeparator()]
    assert len(acts) == len(EXTRA_SHAPES)
    acts[-1].trigger()
    assert ctrl.tool == Tool.BRACE and tb.more_shapes_btn.isChecked()
    QTest.keyClick(tb, Qt.Key.Key_1)
    assert ctrl.tool == Tool.BRUSH and tb.tool_buttons[Tool.BRUSH].isChecked() and not tb.more_shapes_btn.isChecked()
    assert tb.fill_btn.isHidden()
    ctrl.set_tool(Tool.STAR)
    assert not tb.fill_btn.isHidden()


# ====================================================================== sellos


def test_stamp_tool_cycles_and_places_stamps(ctrl):
    ov, tb = _ov(ctrl), ctrl.toolbar
    QTest.keyClick(tb, Qt.Key.Key_S)
    assert ctrl.tool == Tool.STAMP and tb.stamp_btn.isChecked()
    kinds = [ctrl.stamp_kind]
    for _ in range(len(STAMPS) - 1):
        QTest.keyClick(tb, Qt.Key.Key_S)
        kinds.append(ctrl.stamp_kind)
    assert sorted(kinds) == sorted(STAMPS)
    for i, kind in enumerate(STAMPS):
        ctrl.set_stamp_kind(kind)
        x, y = 80 + i * 90, 200
        _click(ov, x, y)
        item = ctrl.history[-1][1]
        assert isinstance(item, StampItem) and item.kind == kind and (item.x, item.y) == (x, y)
        d = ov.canvas.devicePixelRatio()
        assert ov.canvas.pixelColor(round(x * d), round(y * d)).alpha() > 0 or kind in ("check", "cross"), kind
        rect = render.item_rect(item)
        ink = sum(ov.canvas.pixelColor(round(px * d), round(py * d)).alpha() > 0
                  for px in range(int(rect.left()), int(rect.right()), 3)
                  for py in range(int(rect.top()), int(rect.bottom()), 3))
        assert ink > 10, kind


def test_number_stamps_count_up_and_follow_undo(ctrl):
    ov = _ov(ctrl)
    ctrl.set_stamp_kind("number")
    for i in range(3):
        _click(ov, 100 + i * 80, 300)
    labels = [i.label for _, i in ctrl.history if isinstance(i, StampItem)]
    assert labels == ["1", "2", "3"]
    ctrl.undo()
    _click(ov, 400, 300)
    assert ctrl.history[-1][1].label == "3"  # tras deshacer, sigue la cuenta
    ctrl.new_page()
    assert ctrl.next_stamp_number() == 1  # cada página empieza en 1


def test_stamp_cursor_shows_preview(ctrl):
    ov = _ov(ctrl)
    ctrl.set_stamp_kind("smiley")
    assert ov.cursor().shape() == Qt.CursorShape.BitmapCursor
    assert not ov.cursor().pixmap().isNull()


def test_stamps_erase_and_session_roundtrip(ctrl, tmp_path):
    ov = _ov(ctrl)
    ctrl.set_stamp_kind("number")
    _click(ov, 200, 200)
    ctrl.set_stamp_kind("star")
    _click(ov, 320, 200)
    path = str(tmp_path / "sellos.pizarra")
    assert ctrl.save_session(path)
    ctrl.dirty = False
    ctrl.open_session(path)
    stamps = [i for i in ctrl.items_for(_ov(ctrl).key) if isinstance(i, StampItem)]
    assert [(s.kind, s.label) for s in stamps] == [("number", "1"), ("star", "")]
    ov = _ov(ctrl)
    d = ov.canvas.devicePixelRatio()
    assert ov.canvas.pixelColor(round(320 * d), round(200 * d)).alpha() > 0
    _erase(ctrl, 260, 380, 200, size=150)
    assert ov.canvas.pixelColor(round(320 * d), round(200 * d)).alpha() == 0


# ====================================================================== plantillas


def _boxes_overlap(a, b):
    return a.intersected(b).width() > 1 and a.intersected(b).height() > 1


def test_every_template_fits_the_screen_without_overlapping_texts():
    for w, h in ((1280, 720), (1920, 1080), (800, 600), (1366, 768)):
        area = QRectF(w * 0.08, h * 0.1, w * 0.84, h * 0.8)
        screen = QRectF(0, 0, w, h)
        for key in templates.TEMPLATES:
            group = templates.build(key, area, (20, 20, 20, 255), 3)
            items = flatten([group])
            assert items, key
            texts = [i for i in items if isinstance(i, TextItem)]
            assert texts, key
            for it in items:
                assert screen.contains(render.item_rect(it).adjusted(4, 4, -4, -4)), (key, w, it)
            boxes = [render.text_box(t) for t in texts]
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    assert not _boxes_overlap(boxes[i], boxes[j]), (key, w, texts[i].text, texts[j].text)
            assert len({t.uid for t in texts}) == len(texts)  # cada texto se edita por separado


def test_insert_template_is_one_undo_step_and_texts_are_editable(ctrl):
    ov = _ov(ctrl)
    ctrl.set_color(QColor("#1b3f7a"))
    n = len(ctrl.history)
    ctrl.insert_template("concept_map")
    assert len(ctrl.history) == n + 1 and isinstance(ctrl.history[-1][1], GroupItem)
    assert ctrl.tool == Tool.TEXT  # lista para escribir
    texts = _texts(ctrl)
    central = next(t for t in texts if t.text == "Tema central")
    _click(ov, *render.text_box(central).center().toTuple())
    assert ov.editing_text.uid == central.uid
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_End)
    for _ in range(len("Tema central")):
        QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Backspace)
    _type(ctrl.toolbar, "Fotosíntesis")
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    assert isinstance(ctrl.history[-1][1], TextEditItem)
    assert "Fotosíntesis" in [t.text for t in _texts(ctrl)] and "Tema central" not in [t.text for t in _texts(ctrl)]
    ctrl.undo()  # deshace la edición
    ctrl.undo()  # deshace la plantilla completa
    assert len(ctrl.history) == n and _texts(ctrl) == []


def test_template_session_roundtrip_and_pdf(ctrl, tmp_path):
    ov = _ov(ctrl)
    ctrl.set_background("white")
    for key in templates.TEMPLATES:
        ctrl.insert_template(key)
        ctrl.new_page()
    path = str(tmp_path / "plantillas.pizarra")
    assert ctrl.save_session(path)
    before = [[session.item_to_dict(i) for _, i in pg.history] for pg in ctrl.pages]
    ctrl.dirty = False
    ctrl.open_session(path)
    after = [[session.item_to_dict(i) for _, i in pg.history] for pg in ctrl.pages]
    assert before == after
    out = ctrl.export_pdf(str(tmp_path / "plantillas.pdf"))
    assert out and len(ctrl.page_images()) == len(templates.TEMPLATES) + 1
    assert ov is not None


def test_templates_menu_lists_all(ctrl):
    menu = ctrl.toolbar.build_templates_menu()
    assert [a.text() for a in menu.actions()] == [label for label, _ in templates.TEMPLATES.values()]
    menu.actions()[2].trigger()  # Venn de 2
    group = ctrl.history[-1][1]
    assert isinstance(group, GroupItem)
    assert sum(isinstance(i, ShapeItem) and i.tool == Tool.ELLIPSE for i in group.items) == 2


def test_new_settings_are_remembered(ctrl, qapp):
    from pizarra_virtual.app import Controller

    ctrl.set_stamp_kind("smiley")
    ctrl.set_tool(Tool.BRACE)
    ctrl._save_settings()
    other = Controller(qapp, settings=ctrl.settings, enable_hotkeys=False, enable_tray=False)
    try:
        assert other.stamp_kind == "smiley" and other.extra_shape == Tool.BRACE
    finally:
        other.shutdown()
    assert TOOL_SPECS[Tool.STAMP].min_size >= 20
