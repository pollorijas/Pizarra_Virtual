"""Pruebas de la versión 1.5: cortina desde cuatro lados, tapar zona, notas adhesivas, recortar zona,
mostrar teclas pulsadas y modo táctil."""
import math

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QKeyEvent, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pizarra_virtual import capture, keyview, render, session
from pizarra_virtual.items import CoverItem, DeleteItem, ImageItem, NoteItem, TransformItem
from pizarra_virtual.keyview import KeyWatcher
from pizarra_virtual.tools import NOTE_COLORS, Tool


def _ov(ctrl):
    return ctrl.overlay_for_screen(QGuiApplication.primaryScreen())


def _drag(ov, pts):
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*map(int, pts[0])))
    for x, y in pts[1:]:
        QTest.mouseMove(ov, QPoint(int(x), int(y)), 3)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*map(int, pts[-1])))


def _click(ov, x, y):
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(x), int(y)))


def _type(widget, text):
    for ch in text:
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.ShortcutOverride, 0, Qt.KeyboardModifier.NoModifier, ch))
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch))


def _grab(ov) -> QImage:
    QApplication.processEvents()
    img = ov.grab().toImage()
    img.setDevicePixelRatio(1.0)
    return img


def _px(ov, img, x, y) -> QColor:
    d = ov.devicePixelRatioF()
    return img.pixelColor(round(x * d), round(y * d))


def _canvas(ov, x, y) -> QColor:
    d = ov.canvas.devicePixelRatio()
    return ov.canvas.pixelColor(round(x * d), round(y * d))


def _cursor_to(ov, x, y):
    QCursor.setPos(ov.mapToGlobal(QPoint(int(x), int(y))))


def _dark(c: QColor) -> bool:
    return c.alpha() == 255 and c.red() < 70 and c.green() < 70 and c.blue() < 80


# ====================================================================== cortina desde cuatro lados


@pytest.mark.parametrize("side, covered, revealed", [
    ("top", (0.3, 0.9), (0.3, 0.05)),
    ("bottom", (0.3, 0.1), (0.3, 0.95)),
    ("left", (0.9, 0.3), (0.05, 0.3)),
    ("right", (0.1, 0.3), (0.95, 0.3)),
])
def test_curtain_reveals_from_each_side(ctrl, side, covered, revealed):
    ov = _ov(ctrl)
    _cursor_to(ov, 100, 100)
    ctrl.show_curtain(side)
    assert ctrl.curtain_active and ov.curtain == 0 and ov.curtain_side == side
    w, h = ov.width(), ov.height()
    img = _grab(ov)
    assert _dark(_px(ov, img, w * revealed[0], h * revealed[1]))  # al principio tapa todo
    # Descubrir un 20 % desde su lado (con las flechas en la dirección del lado)
    arrow = {"top": Qt.Key.Key_Down, "bottom": Qt.Key.Key_Up, "left": Qt.Key.Key_Right, "right": Qt.Key.Key_Left}[side]
    QTest.keyClick(ctrl.toolbar, arrow)
    QTest.keyClick(ctrl.toolbar, arrow)
    ext = h if side in ("top", "bottom") else w
    assert math.isclose(ov.curtain, ext * 0.2)
    img = _grab(ov)
    assert _px(ov, img, w * revealed[0], h * revealed[1]).alpha() < 255  # ya descubierto
    assert _dark(_px(ov, img, w * covered[0], h * covered[1]))  # el resto sigue tapado
    # La flecha contraria vuelve a tapar; las del otro eje no hacen nada
    back = {Qt.Key.Key_Down: Qt.Key.Key_Up, Qt.Key.Key_Up: Qt.Key.Key_Down,
            Qt.Key.Key_Right: Qt.Key.Key_Left, Qt.Key.Key_Left: Qt.Key.Key_Right}[arrow]
    QTest.keyClick(ctrl.toolbar, back)
    assert math.isclose(ov.curtain, ext * 0.1)
    other = Qt.Key.Key_Right if side in ("top", "bottom") else Qt.Key.Key_Down
    QTest.keyClick(ctrl.toolbar, other)
    assert math.isclose(ov.curtain, ext * 0.1)


def test_curtain_drag_from_left_and_right(ctrl):
    ov = _ov(ctrl)
    _cursor_to(ov, 100, 100)
    ctrl.set_tool(Tool.BRUSH)
    ctrl.show_curtain("left")
    _drag(ov, [(30, 200), (130, 200), (230, 200)])  # se arrastra el borde: no se dibuja
    assert math.isclose(ov.curtain, 200, abs_tol=1)
    assert not ctrl.history
    ctrl.show_curtain("right")  # empieza de nuevo, toda tapada, desde la derecha
    assert ov.curtain == 0 and ov.curtain_side == "right"
    w = ov.width()
    _drag(ov, [(w - 30, 200), (w - 130, 200), (w - 330, 200)])
    assert math.isclose(ov.curtain, 300, abs_tol=1)
    assert not ctrl.history
    # Lo descubierto se puede usar: se dibuja a la derecha, fuera de la cortina
    _drag(ov, [(w - 100, 300), (w - 50, 300)])
    assert len(ctrl.history) == 1


def test_curtain_shift_v_cycles_and_v_remembers_side(ctrl, tmp_path):
    ov = _ov(ctrl)
    _cursor_to(ov, 100, 100)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_V)
    assert ov.curtain_side == "top"
    for expected in ("bottom", "left", "right", "top", "bottom"):
        QTest.keyClick(ctrl.toolbar, Qt.Key.Key_V, Qt.KeyboardModifier.ShiftModifier)
        assert ov.curtain_side == expected and ov.curtain == 0
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_V)
    assert not ctrl.curtain_active
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_V)
    assert ov.curtain_side == "bottom"  # se recuerda el último lado
    ctrl._save_settings()
    assert ctrl.settings.value("curtain_side") == "bottom"


def test_curtain_menu_lists_four_sides_and_remove(ctrl):
    menu = ctrl.toolbar.build_curtain_menu()
    texts = [a.text() for a in menu.actions() if a.text()]
    assert texts == ["Cortina: desde arriba", "Cortina: desde abajo", "Cortina: desde la izquierda",
                     "Cortina: desde la derecha"]
    menu.actions()[2].trigger()
    assert ctrl.curtain_active and _ov(ctrl).curtain_side == "left"
    menu = ctrl.toolbar.build_curtain_menu()
    remove = [a for a in menu.actions() if a.text().startswith("Quitar")]
    assert remove and next(a for a in menu.actions() if a.text().endswith("izquierda")).isChecked()
    remove[0].trigger()
    assert not ctrl.curtain_active


# ====================================================================== tapar zona


def test_cover_hides_area_and_click_reveals_with_undo(ctrl):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    _drag(ov, [(120, 200), (260, 200)])  # «la respuesta»
    ctrl.set_tool(Tool.COVER)
    assert not ctrl.toolbar.size_slider.isVisible()
    _drag(ov, [(100, 170), (200, 210), (300, 240)])
    cover = ctrl.history[-1][1]
    assert isinstance(cover, CoverItem) and (cover.x, cover.y, cover.w, cover.h) == (100, 170, 200, 70)
    c = _canvas(ov, 190, 200)
    assert c.alpha() == 255 and c.red() < 90  # tapado con el gris oscuro (ya no se ve el trazo rojo)
    # Un clic sobre la zona la descubre
    _click(ov, 150, 230)
    assert isinstance(ctrl.history[-1][1], DeleteItem) and ctrl.history[-1][1].uids == [cover.uid]
    c = _canvas(ov, 190, 200)
    assert c.red() > 150 and c.green() < 100  # vuelve a verse el trazo rojo
    ctrl.undo()  # deshacer vuelve a tapar
    assert _canvas(ov, 190, 200).red() < 90
    # Un clic fuera de una zona tapada no hace nada
    n = len(ctrl.history)
    _click(ov, 600, 500)
    assert len(ctrl.history) == n


def test_cover_tiny_drag_is_ignored_and_cover_can_be_moved(ctrl):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.COVER)
    _drag(ov, [(100, 100), (104, 103)])
    assert not ctrl.history
    _drag(ov, [(100, 100), (180, 160)])
    cover = ctrl.history[-1][1]
    ctrl.set_tool(Tool.SELECT)
    _drag(ov, [(140, 130), (240, 130), (340, 130)])
    assert isinstance(ctrl.history[-1][1], TransformItem)
    moved = next(i for i in ctrl.items_for(ov.key) if getattr(i, "uid", None) == cover.uid)
    assert math.isclose(moved.x, 300) and math.isclose(moved.y, 100)


def test_cover_and_note_are_saved_in_sessions(ctrl, tmp_path):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.COVER)
    _drag(ov, [(100, 100), (200, 160)])
    ctrl.set_note_color("pink")
    _click(ov, 300, 300)
    _type(ctrl.toolbar, "Recordar")
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    path = str(tmp_path / "clase.pizarra")
    assert ctrl.save_session(path)
    ctrl.dirty = False
    assert ctrl.open_session(path)
    items = ctrl.items_for(ov.key)
    cover = next(i for i in items if isinstance(i, CoverItem))
    note = next(i for i in items if isinstance(i, NoteItem))
    assert (cover.w, cover.h) == (100, 60)
    assert note.text == "Recordar" and tuple(note.color) == NOTE_COLORS["pink"][1]
    # PDF / imágenes de página: la zona tapada y la nota salen como se ven
    img = session.render_page(ctrl.page, items, ov.width(), ov.height(), scale=1.0)
    assert _dark(img.pixelColor(110, 110))
    paper = img.pixelColor(round(note.x + 3), round(note.y + 40))
    assert paper.red() > 230 and 160 < paper.green() < 210  # papel rosado


# ====================================================================== notas adhesivas


def test_note_is_written_like_text_and_grows(ctrl):
    ov = _ov(ctrl)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_O)
    assert ctrl.tool == Tool.NOTE
    _click(ov, 200, 200)
    note = ov.editing_text
    assert isinstance(note, NoteItem) and note.color == NOTE_COLORS["yellow"][1]
    small = render.note_rect(note)
    assert small.topLeft() == QPointF(200, 200)  # la nota empieza donde se hizo clic
    _type(ctrl.toolbar, "Tarea para el lunes: leer el capítulo 3")
    assert render.note_rect(note).width() > small.width()  # crece con lo escrito
    for line in ("y resumir", "y repasar", "y practicar"):
        QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Return)
        _type(ctrl.toolbar, line)
    assert render.note_rect(note).height() > small.height()
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    item = ctrl.history[-1][1]
    assert isinstance(item, NoteItem) and item.text == "Tarea para el lunes: leer el capítulo 3\ny resumir\ny repasar\ny practicar"
    paper = _canvas(ov, 205, 260)
    assert paper.red() > 240 and paper.green() > 220 and paper.blue() < 160  # papel amarillo


def test_empty_note_is_discarded_and_click_reopens_note(ctrl):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.NOTE)
    _click(ov, 200, 200)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    assert not ctrl.history
    _click(ov, 200, 200)
    _type(ctrl.toolbar, "Hola")
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    note = ctrl.history[-1][1]
    # Un clic en cualquier parte del papel (no solo sobre las letras) la abre para editarla
    r = render.note_rect(note)
    _click(ov, r.right() - 10, r.bottom() - 25)
    assert ov.editing_text is not None and ov.editing_text.uid == note.uid
    _type(ctrl.toolbar, "!")
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    edited = next(i for i in ctrl.items_for(ov.key) if i.uid == note.uid)
    assert isinstance(edited, NoteItem) and edited.text == "Hola!"
    # También con la herramienta Texto
    ctrl.set_tool(Tool.TEXT)
    _click(ov, r.left() + 20, r.bottom() - 20)
    assert ov.editing_text is not None and ov.editing_text.uid == note.uid
    ov.finish_current()


def test_note_keeps_dark_text_and_paper_color_changes(ctrl):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.NOTE)
    _click(ov, 200, 200)
    _type(ctrl.toolbar, "Ojo")
    ctrl.set_color(QColor("#ffeb3b"))  # un color de la paleta no cambia la letra de la nota
    assert ov.editing_text.rgba == (38, 50, 56, 255)
    ctrl.set_note_color("blue")
    assert ov.editing_text.color == NOTE_COLORS["blue"][1]
    ctrl.set_size(48)
    assert ov.editing_text.size == 48
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    note = ctrl.history[-1][1]
    assert note.size == 48 and note.color == NOTE_COLORS["blue"][1]
    # El menú de notas muestra los colores y marca el elegido
    menu = ctrl.toolbar.build_notes_menu()
    checked = [a.text() for a in menu.actions() if a.isChecked()]
    assert checked == ["Nota celeste"]
    assert len(menu.actions()) == len(NOTE_COLORS)


def test_note_can_be_moved_and_duplicated(ctrl):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.NOTE)
    _click(ov, 100, 100)
    _type(ctrl.toolbar, "Mover")
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    note = ctrl.history[-1][1]
    ctrl.set_tool(Tool.SELECT)
    _drag(ov, [(130, 130), (230, 180), (330, 230)])
    moved = next(i for i in ctrl.items_for(ov.key) if i.uid == note.uid)
    assert isinstance(moved, NoteItem) and math.isclose(moved.x, note.x + 200)
    assert ctrl.duplicate_selection()
    notes = [i for i in ctrl.items_for(ov.key) if isinstance(i, NoteItem)]
    assert len(notes) == 2 and all(n.text == "Mover" for n in notes)


# ====================================================================== recortar zona


def _fake_screen(ov):
    """Captura falsa: un degradado con un cuadrado azul en (200, 150)-(300, 250) lógicos."""
    d = ov.devicePixelRatioF()
    img = QImage(round(ov.width() * d), round(ov.height() * d), QImage.Format.Format_RGB32)
    img.fill(QColor(240, 240, 240))
    p = QPainter(img)
    p.fillRect(QRectF(200 * d, 150 * d, 100 * d, 100 * d), QColor(0, 0, 255))
    p.end()
    return img


@pytest.fixture
def fake_capture(ctrl, monkeypatch):
    ov = _ov(ctrl)
    saved = {}
    monkeypatch.setattr(capture, "grab_screen", lambda s: _fake_screen(ov))

    def fake_save(img, *a):
        saved["img"] = img
        return "recorte.png"

    monkeypatch.setattr(capture, "save_capture", fake_save)
    _cursor_to(ov, 400, 300)
    return saved


def _start_crop(ctrl, **kw):
    ctrl.start_crop(**kw)
    QTest.qWait(400)
    assert ctrl.crop_active


def test_crop_saves_only_the_dragged_area(ctrl, fake_capture):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    _start_crop(ctrl)
    assert ov.crop_active and ctrl.toolbar.isVisible()
    img = _grab(ov)
    assert _px(ov, img, 250, 200).blue() > 100  # se ve la pantalla congelada (oscurecida)
    _drag(ov, [(190, 140), (250, 200), (310, 260)])
    assert not ctrl.crop_active
    out = fake_capture["img"]
    d = ov.devicePixelRatioF()
    assert abs(out.width() - 120 * d) <= 1 and abs(out.height() - 120 * d) <= 1
    assert out.pixelColor(out.width() // 2, out.height() // 2) == QColor(0, 0, 255)
    assert out.pixelColor(2, 2) == QColor(240, 240, 240)
    assert not ctrl.history  # recortar no dibuja nada
    assert QGuiApplication.clipboard().image().size() == out.size()
    assert ctrl.last_capture == "recorte.png"


def test_crop_includes_drawing_unless_asked(ctrl, fake_capture):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    ctrl.set_size(20)
    _drag(ov, [(400, 400), (500, 400)])
    _start_crop(ctrl)
    _drag(ov, [(380, 380), (520, 420)])
    with_ink = fake_capture["img"]
    d = ov.devicePixelRatioF()
    assert with_ink.pixelColor(round(70 * d), round(20 * d)).red() > 200  # el trazo rojo está
    _start_crop(ctrl, with_drawing=False)
    _drag(ov, [(380, 380), (520, 420)])
    plain = fake_capture["img"]
    assert plain.pixelColor(round(70 * d), round(20 * d)) == QColor(240, 240, 240)


def test_crop_to_board_pastes_image_in_place(ctrl, fake_capture):
    ov = _ov(ctrl)
    _start_crop(ctrl, with_drawing=False, to_board=True)
    _drag(ov, [(200, 150), (300, 250)])
    item = ctrl.history[-1][1]
    assert isinstance(item, ImageItem)
    assert (item.x, item.y, item.w, item.h) == (200, 150, 100, 100)
    assert ctrl.tool == Tool.SELECT and ov.selection == [item.uid]
    assert "img" not in fake_capture  # no se guarda archivo
    assert _canvas(ov, 250, 200).blue() > 200


def test_crop_cancel_with_esc_or_right_click_restores_mouse_mode(ctrl, fake_capture):
    ov = _ov(ctrl)
    ctrl.set_drawing(False)
    _start_crop(ctrl)
    assert ctrl.drawing  # mientras se recorta, la pizarra recibe el ratón
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)
    assert not ctrl.crop_active and not ctrl.drawing  # vuelve a «Ratón libre»
    _start_crop(ctrl)
    _click(ov, 300, 300)  # un clic sin arrastrar sigue esperando
    assert ctrl.crop_active
    QTest.mouseClick(ov, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 300))
    assert not ctrl.crop_active and "img" not in fake_capture
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_X)  # atajo X
    QTest.qWait(400)
    assert ctrl.crop_active
    ctrl.cancel_crop()


def test_crop_from_zoom_uses_the_magnified_view(ctrl, fake_capture):
    ov = _ov(ctrl)
    ov.start_zoom(_fake_screen(ov), QPointF(250, 200), 2.0)
    ctrl.start_crop(with_drawing=False)
    assert ctrl.crop_active and not ov.zoom_active
    _drag(ov, [(230, 180), (270, 220)])  # alrededor del punto ampliado (250, 200)
    out = fake_capture["img"]
    d = ov.devicePixelRatioF()
    assert abs(out.width() - 40 * d) <= 1
    assert out.pixelColor(out.width() // 2, out.height() // 2) == QColor(0, 0, 255)


def test_capture_menu_offers_crop(ctrl):
    menu = ctrl.build_capture_menu(None)
    texts = [a.text() for a in menu.actions()]
    assert texts[0].startswith("Recortar zona (con lo dibujado)")
    assert "Recortar zona y pegarla en la pizarra" in texts


# ====================================================================== teclas pulsadas

CTRL, SHIFT, ALT, ALTGR, WIN = 0x11, 0x10, 0x12, 0xA5, 0x5B


def _keys(watcher, *states):
    out = []
    for st in states:
        out += watcher.update(set(st))
    return out


def test_key_watcher_shows_shortcuts_but_not_typing():
    w = KeyWatcher()
    assert _keys(w, {CTRL}, {CTRL, 0x43}, {CTRL}, set()) == ["Ctrl + C"]
    assert _keys(w, {0x41}, set(), {SHIFT, 0x42}, set(), {0x20}, set()) == []  # texto: nunca se muestra
    assert _keys(w, {0x0D}, set(), {SHIFT, 0x09}, set()) == ["Intro", "Mayús + Tab"]
    assert _keys(w, {ALT}, {ALT, 0x09}, {ALT}, {ALT, 0x09}, set()) == ["Alt + Tab", "Alt + Tab"]
    assert _keys(w, {CTRL, SHIFT}, {CTRL, SHIFT, 0x53}, set()) == ["Ctrl + Mayús + S"]
    assert _keys(w, {0x74}, set(), {0x2E}, set(), {0x25}, set()) == ["F5", "Supr", "←"]
    # AltGr (Ctrl + Alt derecha) escribe @, #, €…: no es un atajo
    assert _keys(w, {CTRL, ALT, ALTGR}, {CTRL, ALT, ALTGR, 0x51}, set()) == []
    # Win solo (abre el menú Inicio) y Win + D
    assert _keys(w, {WIN}, set()) == ["Win"]
    assert _keys(w, {WIN}, {WIN, 0x44}, {WIN}, set()) == ["Win + D"]
    assert set(keyview.KEYS) >= {CTRL, SHIFT, ALT, ALTGR, WIN, 0x43, 0x0D, 0x70}


def test_show_keys_displays_on_screen_and_counts_repeats(ctrl):
    ov = _ov(ctrl)
    state = {"keys": set()}
    ctrl.key_state = lambda: set(state["keys"])
    _cursor_to(ov, 300, 300)
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    assert ctrl.show_keys and ctrl.toolbar.keys_btn.isChecked()

    def press(*keys):
        state["keys"] = set(keys)
        ctrl._tick()

    for _ in range(2):
        press(CTRL)
        press(CTRL, 0x56)  # Ctrl + V
        press()
    assert ov.keys_shown == ["Ctrl + V  ×2"]
    press(0x41)  # una letra: no se muestra
    press()
    press(0x0D)
    press()
    assert ov.keys_shown == ["Ctrl + V  ×2", "Intro"]
    img = _grab(ov)
    from PySide6.QtGui import QFontMetrics

    fm = QFontMetrics(ov._key_font())
    left = (ov.width() - fm.horizontalAdvance("Intro") - 36) / 2  # borde izquierdo del globo
    bubble = _px(ov, img, left + 8, ov.height() - 90 - (fm.height() + 18) / 2)
    assert bubble.alpha() > 200 and bubble.red() < 60  # globo oscuro abajo en el centro (sin letras)
    ctrl.toggle_show_keys()
    assert not ctrl.show_keys and ov.keys_shown == []


def test_shown_keys_fade_out(ctrl, monkeypatch):
    from pizarra_virtual import overlay

    ov = _ov(ctrl)
    ov.show_key("Ctrl + Z", 1000.0)
    assert ov.effects_tick(1000.0 + overlay.KEY_SHOW_MS, QCursor.pos(), [])
    assert not ov.effects_tick(1000.0 + overlay.KEY_SHOW_MS + overlay.KEY_FADE_MS + 1, QCursor.pos(), [])
    assert ov.keys_shown == []


# ====================================================================== pantalla táctil


def _seq(ov, touch):
    return QTest.touchEvent(ov, touch)


def test_one_finger_draws(ctrl, touch):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    _seq(ov, touch).press(0, QPoint(100, 100), ov).commit()
    for x in range(110, 260, 10):
        _seq(ov, touch).move(0, QPoint(x, 100), ov).commit()
    _seq(ov, touch).release(0, QPoint(260, 100), ov).commit()
    assert len(ctrl.history) == 1 and len(ctrl.history[0][1].points) > 5
    assert _canvas(ov, 200, 100).alpha() > 0


def test_two_finger_tap_undoes_and_three_finger_tap_redoes(ctrl, touch):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    _drag(ov, [(100, 100), (200, 100)])
    _drag(ov, [(100, 200), (200, 200)])
    assert len(ctrl.history) == 2
    _seq(ov, touch).press(0, QPoint(300, 300), ov).press(1, QPoint(360, 300), ov).commit()
    _seq(ov, touch).release(0, QPoint(300, 300), ov).release(1, QPoint(360, 300), ov).commit()
    assert len(ctrl.history) == 1 and len(ctrl.redo_stack) == 1
    _seq(ov, touch).press(0, QPoint(300, 300), ov).press(1, QPoint(340, 300), ov) \
        .press(2, QPoint(380, 300), ov).commit()
    _seq(ov, touch).release(0, QPoint(300, 300), ov).release(1, QPoint(340, 300), ov) \
        .release(2, QPoint(380, 300), ov).commit()
    assert len(ctrl.history) == 2 and not ctrl.redo_stack


def test_second_finger_soon_after_cancels_the_stroke(ctrl, touch):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    _drag(ov, [(100, 100), (200, 100)])
    _seq(ov, touch).press(0, QPoint(300, 300), ov).commit()
    _seq(ov, touch).stationary(0).press(1, QPoint(360, 300), ov).commit()
    _seq(ov, touch).release(0, QPoint(300, 300), ov).release(1, QPoint(360, 300), ov).commit()
    # El primer dedo no dejó un punto: era un toque con dos dedos (deshacer)
    assert not ctrl.history
    assert _canvas(ov, 300, 300).alpha() == 0


def test_two_finger_tap_with_eraser_does_not_erase(ctrl, touch):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    ctrl.set_size(30)
    _drag(ov, [(250, 300), (450, 300)])
    _drag(ov, [(100, 100), (150, 100)])
    ctrl.set_tool(Tool.ERASER)
    _seq(ov, touch).press(0, QPoint(300, 300), ov).commit()
    _seq(ov, touch).stationary(0).press(1, QPoint(400, 300), ov).commit()
    _seq(ov, touch).release(0, QPoint(300, 300), ov).release(1, QPoint(400, 300), ov).commit()
    assert _canvas(ov, 300, 300).alpha() > 0  # la goma del primer dedo no borró
    assert len(ctrl.history) == 1  # y se deshizo el último trazo


def test_pinch_zooms_while_zoom_is_active(ctrl, touch):
    ov = _ov(ctrl)
    img = QImage(ov.canvas.size(), QImage.Format.Format_RGB32)
    img.fill(QColor(200, 200, 200))
    ov.start_zoom(img, QPointF(ov.width() / 2, ov.height() / 2), 2.0)
    z0 = ov.zoom_factor
    cx, cy = ov.width() // 2, ov.height() // 2
    _seq(ov, touch).press(0, QPoint(cx - 50, cy), ov).press(1, QPoint(cx + 50, cy), ov).commit()
    for d in range(60, 160, 20):
        _seq(ov, touch).move(0, QPoint(cx - d, cy), ov).move(1, QPoint(cx + d, cy), ov).commit()
    _seq(ov, touch).release(0, QPoint(cx - 150, cy), ov).release(1, QPoint(cx + 150, cy), ov).commit()
    assert ov.zoom_factor > z0 * 2.5
    assert not ctrl.history  # el gesto no deshizo ni dibujó nada


# ====================================================================== modo táctil (botones grandes)


def test_touch_mode_enlarges_toolbar_and_is_remembered(ctrl, qapp):
    from pizarra_virtual.toolbar import BTN

    assert not ctrl.touch_mode
    small = ctrl.toolbar.select_btn.width()
    assert small == BTN
    ctrl.toolbar.touch_btn.click()
    QTest.qWait(50)
    tb = ctrl.toolbar
    assert ctrl.touch_mode and tb.touch_btn.isChecked()
    assert tb.select_btn.width() > small * 1.3
    assert tb.isVisible()
    # Los atajos siguen funcionando una sola vez (la barra anterior ya no existe)
    ctrl.set_tool(Tool.BRUSH)
    QTest.keyClick(tb, Qt.Key.Key_V)
    assert ctrl.curtain_active
    QTest.keyClick(tb, Qt.Key.Key_V)
    assert not ctrl.curtain_active
    ctrl._save_settings()
    assert ctrl.settings.value("touch_mode") == "true"
    # Zonas de agarre más grandes: el asa de la selección
    ov = _ov(ctrl)
    assert ov._handle_rect(QRectF(0, 0, 100, 100)).width() > 20
    ctrl.set_touch_mode(False)
    QTest.qWait(50)
    assert ctrl.toolbar.select_btn.width() == BTN


def test_touch_mode_setting_is_loaded(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    from pizarra_virtual.app import Controller

    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.setValue("touch_mode", "true")
    settings.setValue("note_color", "green")
    c = Controller(qapp, settings=settings, enable_hotkeys=False, enable_tray=False)
    try:
        assert c.touch_mode and c.toolbar.btn > 40 and c.note_color == "green"
    finally:
        c.shutdown()


@pytest.mark.parametrize("late", [False, True])
def test_palm_erases_even_if_contact_size_arrives_late(ctrl, touch, late):
    ov = _ov(ctrl)
    ctrl.set_tool(Tool.BRUSH)
    ctrl.set_size(20)
    _drag(ov, [(200, 300), (400, 300)])
    eraser_size = ctrl.sizes[Tool.ERASER]
    contact = {"px": 0.0 if late else 120.0}
    ctrl.touch_contact_size = lambda: contact["px"] * ov.devicePixelRatioF()
    _seq(ov, touch).press(0, QPoint(300, 280), ov).commit()
    contact["px"] = 120.0  # (si llega tarde, Windows lo informa en el primer movimiento)
    for y in range(285, 325, 5):
        _seq(ov, touch).move(0, QPoint(300, y), ov).commit()
    _seq(ov, touch).release(0, QPoint(300, 320), ov).commit()
    assert [item.tool for _k, item in ctrl.history] == [Tool.BRUSH, Tool.ERASER]
    assert ctrl.history[-1][1].size >= 100  # goma del tamaño de la palma
    assert ctrl.sizes[Tool.ERASER] == eraser_size and ctrl.tool == Tool.BRUSH
    assert _canvas(ov, 300, 300).alpha() == 0
