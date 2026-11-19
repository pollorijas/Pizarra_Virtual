"""Pruebas con ventanas REALES de Windows (plataforma Qt «windows», no «offscreen»).

Se ejecutan en GitHub Actions (windows-latest) con QT_QPA_PLATFORM=windows y comprueban
lo que solo puede verificarse en Windows: tamaño nativo de las ventanas, estilos
WS_EX_LAYERED / WS_EX_TRANSPARENT, atajos globales (WM_HOTKEY) y lo que realmente se
ve en el escritorio (capturas con PIL.ImageGrab). Guarda capturas en ``test-screens/``.
"""
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") != "windows",
    reason="solo en Windows con la plataforma nativa (QT_QPA_PLATFORM=windows)",
)

SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test-screens")


def _win32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    return ctypes, wintypes, user32


def _rect(hwnd):
    ctypes, wintypes, user32 = _win32()
    r = wintypes.RECT()
    assert user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def _exstyle(hwnd):
    _, _, user32 = _win32()
    return user32.GetWindowLongPtrW(hwnd, -20)


def _settle(qapp, ms=400):
    from PySide6.QtTest import QTest

    qapp.processEvents()
    QTest.qWait(ms)
    qapp.processEvents()


def _grab(name):
    from PIL import ImageGrab

    img = ImageGrab.grab(include_layered_windows=True)
    os.makedirs(SHOTS, exist_ok=True)
    img.save(os.path.join(SHOTS, name))
    return img


def _overlay(ctrl):
    from PySide6.QtGui import QGuiApplication

    return ctrl.overlay_for_screen(QGuiApplication.primaryScreen())


def test_native_toolbar_collapse_resizes_the_real_window(ctrl, qapp):
    tb = ctrl.toolbar
    _settle(qapp)
    hwnd = int(tb.winId())
    x, y, w, h = _rect(hwnd)
    assert h > 300
    for _ in range(2):  # dos ciclos, consultando tamaños en caché como hace Windows
        tb.sizeHint()
        tb.toggle_collapsed()
        _settle(qapp, 200)
        cx, cy, cw, ch = _rect(hwnd)
        assert ch < h / 4, (h, ch)  # la ventana nativa se encoge de verdad
        assert (cx, cy) == (x, y)
        assert cw == w or tb.horizontal
        tb.sizeHint()
        tb.toggle_collapsed()
        _settle(qapp, 200)
        assert _rect(hwnd)[3] == h
    _grab("barra_desplegada.png")


def test_native_click_through_styles(ctrl, qapp):
    ov = _overlay(ctrl)
    _settle(qapp)
    hwnd = int(ov.winId())
    WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_TOPMOST = 0x20, 0x80000, 0x8
    st = _exstyle(hwnd)
    assert st & WS_EX_LAYERED and st & WS_EX_TOPMOST
    assert not st & WS_EX_TRANSPARENT  # modo dibujo: recibe los clics
    ctrl.set_drawing(False)
    _settle(qapp, 200)
    assert _exstyle(hwnd) & WS_EX_TRANSPARENT  # «Ratón libre»: los clics atraviesan
    ctrl.set_drawing(True)
    _settle(qapp, 200)
    assert not _exstyle(hwnd) & WS_EX_TRANSPARENT


def _real_mouse(qapp, points, dpr):
    """Arrastre con el ratón REAL del sistema (SetCursorPos + mouse_event)."""
    _, _, user32 = _win32()
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
    phys = [(round(x * dpr), round(y * dpr)) for x, y in points]
    user32.SetCursorPos(*phys[0])
    _settle(qapp, 80)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    _settle(qapp, 60)
    for x, y in phys[1:]:
        user32.SetCursorPos(x, y)
        _settle(qapp, 15)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    _settle(qapp, 200)


def test_native_real_mouse_draws_and_passes_through(ctrl, qapp):
    """Con el ratón real: en modo dibujo se dibuja (y la barra sigue encima y con el foco);
    en «Ratón libre» el clic llega a la ventana que hay debajo."""
    from PySide6.QtWidgets import QWidget

    from pizarra_virtual.tools import Tool

    _, wintypes, user32 = _win32()
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND

    class Target(QWidget):
        clicks = 0

        def mousePressEvent(self, e):  # noqa: N802
            Target.clicks += 1

    target = Target()
    target.setWindowTitle("ventana de debajo")
    target.setGeometry(300, 450, 300, 150)
    target.show()
    _settle(qapp)
    ov = _overlay(ctrl)
    ctrl.set_drawing(True)
    ctrl.set_tool(Tool.PEN)
    _settle(qapp)
    dpr = ov.devicePixelRatioF()
    try:
        n0 = len(ctrl.history)
        _real_mouse(qapp, [(320 + i * 10, 520 + (i % 3)) for i in range(25)], dpr)
        assert len(ctrl.history) == n0 + 1, "el arrastre real no dibujó"
        stroke = ctrl.history[-1][1]
        assert stroke.tool == Tool.PEN and len(stroke.points) > 5
        assert Target.clicks == 0  # la superposición se quedó el clic

        # La barra sigue por encima de la superposición y conserva el foco del teclado.
        tb = ctrl.toolbar
        c = tb.frameGeometry().center()
        hit = user32.WindowFromPoint(wintypes.POINT(round(c.x() * dpr), round(c.y() * dpr)))
        assert int(user32.GetAncestor(hit, 2) or 0) == int(tb.winId())
        assert int(user32.GetForegroundWindow() or 0) != int(ov.winId())

        # «Ratón libre»: el clic atraviesa la pizarra y llega a la ventana de debajo.
        ctrl.set_drawing(False)
        _settle(qapp, 300)
        _real_mouse(qapp, [(450, 520), (452, 521)], dpr)
        assert Target.clicks >= 1, "el clic no atravesó la pizarra"
        assert len(ctrl.history) == n0 + 1
    finally:
        ctrl.set_drawing(True)
        target.close()
        _settle(qapp, 100)


def test_native_global_hotkey_messages(qapp, tmp_path, monkeypatch):
    """Se registran los atajos reales y un WM_HOTKEY llega a la acción correspondiente."""
    from PySide6.QtCore import QSettings

    from pizarra_virtual.app import Controller
    from pizarra_virtual.hotkeys import WM_HOTKEY

    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    c = Controller(qapp, settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
                   enable_hotkeys=True, enable_tray=False)
    try:
        c.start()
        _settle(qapp)
        ids = sorted(c.hotkeys._callbacks)
        assert len(ids) == 9, "no se registraron todos los atajos globales"
        _, _, user32 = _win32()
        assert c.drawing
        user32.PostMessageW(c.hotkeys._hwnd, WM_HOTKEY, ids[0], 0)  # Ctrl+Alt+D
        _settle(qapp, 200)
        assert not c.drawing
        user32.PostMessageW(c.hotkeys._hwnd, WM_HOTKEY, ids[0], 0)
        _settle(qapp, 200)
        assert c.drawing
    finally:
        c.shutdown()
        _settle(qapp, 100)


def _draw_red_line(ctrl, ov, y=300, x0=200, x1=600, size=20):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QColor
    from PySide6.QtTest import QTest

    from pizarra_virtual.tools import Tool

    ctrl.set_tool(Tool.BRUSH)
    ctrl.set_size(size)
    ctrl.set_color(QColor(255, 0, 0))
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x0, y))
    for x in range(x0, x1 + 1, 20):
        QTest.mouseMove(ov, QPoint(x, y), 5)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x1, y))


def _is_red(px):
    r, g, b = px[:3]
    return r > 200 and g < 60 and b < 60


def _red_thickness(img, x, y_from, y_to):
    return sum(1 for y in range(y_from, y_to) if _is_red(img.getpixel((x, y))))


def test_native_drawing_is_visible_on_the_desktop_and_in_zoom(ctrl, qapp):
    ov = _overlay(ctrl)
    _settle(qapp)
    dpr = ov.devicePixelRatioF()
    _draw_red_line(ctrl, ov)
    _settle(qapp)
    shot = _grab("escritorio_con_trazo.png")
    px = lambda lx, ly: shot.getpixel((round(lx * dpr), round(ly * dpr)))  # noqa: E731
    assert _is_red(px(400, 300)), px(400, 300)          # el trazo se ve sobre el escritorio
    assert not _is_red(px(400, 360))                    # fuera del trazo se ve el escritorio
    normal = _red_thickness(shot, round(400 * dpr), round(260 * dpr), round(340 * dpr))
    assert normal >= 15 * dpr

    # Zoom 2x centrado en el trazo: el trazo debe verse el doble de grueso.
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QCursor

    QCursor.setPos(ov.mapToGlobal(QPoint(400, 300)))
    ctrl.start_zoom()
    _settle(qapp, 800)
    assert ov.zoom_active
    zshot = _grab("zoom_2x.png")
    zoomed = _red_thickness(zshot, round(400 * dpr), round(220 * dpr), round(380 * dpr))
    assert 1.6 * normal <= zoomed <= 2.4 * normal, (normal, zoomed)
    ctrl.exit_zoom()
    _settle(qapp)
    after = _grab("despues_del_zoom.png")
    assert _is_red(after.getpixel((round(400 * dpr), round(300 * dpr))))


def test_native_capture_file_contains_drawing(ctrl, qapp, tmp_path):
    from PIL import Image

    ov = _overlay(ctrl)
    _settle(qapp)
    _draw_red_line(ctrl, ov, y=200)
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QCursor

    QCursor.setPos(ov.mapToGlobal(QPoint(50, 50)))
    ctrl.capture(with_drawing=True)
    _settle(qapp, 1200)
    files = list((tmp_path / "Pictures" / "Capturas Pizarra").glob("*.png"))
    assert len(files) == 1
    img = Image.open(files[0]).convert("RGB")
    dpr = ov.devicePixelRatioF()
    assert img.size == (round(ov.width() * dpr), round(ov.height() * dpr))
    assert _is_red(img.getpixel((round(400 * dpr), round(200 * dpr))))
    assert ov.isVisible() and ctrl.toolbar.isVisible()  # la pizarra vuelve a mostrarse


def _real_keys(qapp, text):
    """Pulsa teclas REALES del sistema (keybd_event) para letras, dígitos y espacio."""
    _, _, user32 = _win32()
    for ch in text.upper():
        vk = 0x20 if ch == " " else ord(ch)
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
        _settle(qapp, 30)


def test_native_text_tool_with_real_keyboard(ctrl, qapp):
    """Clic real con la herramienta Texto y teclas reales: el texto se escribe (sin disparar
    atajos como 1, F o Z) aunque la pizarra nunca toma el foco."""
    from pizarra_virtual.tools import Tool

    ov = _overlay(ctrl)
    ctrl.set_tool(Tool.TEXT)
    _settle(qapp)
    dpr = ov.devicePixelRatioF()
    _real_mouse(qapp, [(300, 250), (300, 250)], dpr)
    assert ctrl.text_editor is ov
    _real_keys(qapp, "hola 1 fz")
    _, _, user32 = _win32()
    user32.keybd_event(0x1B, 0, 0, 0)  # Esc
    user32.keybd_event(0x1B, 0, 2, 0)
    _settle(qapp, 300)
    assert ctrl.tool == Tool.TEXT and not ctrl.spotlight and not ctrl.zoom_active
    assert ctrl.history and ctrl.history[-1][1].text == "hola 1 fz"
    shot = _grab("texto_teclado_real.png")
    assert shot is not None


def test_native_click_ripple_on_other_programs(ctrl, qapp):
    """En «Ratón libre», un clic real sobre otra ventana también muestra la onda del clic."""
    ov = _overlay(ctrl)
    ctrl.set_drawing(False)
    ctrl.toggle_highlight()
    _settle(qapp, 200)
    dpr = ov.devicePixelRatioF()
    try:
        _, _, user32 = _win32()
        user32.SetCursorPos(round(500 * dpr), round(400 * dpr))
        _settle(qapp, 100)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        _settle(qapp, 60)
        assert ov._ripples, "no se detectó el clic real"
        shot = _grab("onda_clic.png")
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        ripple_px = [shot.getpixel((round((500 + dx) * dpr), round(400 * dpr))) for dx in range(8, 40)]
        assert any(_is_red(px) or (px[0] > 180 and px[1] < 120) for px in ripple_px)
    finally:
        ctrl.toggle_highlight()
        ctrl.set_drawing(True)
        _settle(qapp, 100)


def test_native_spotlight_on_real_desktop(ctrl, qapp):
    ov = _overlay(ctrl)
    dpr = ov.devicePixelRatioF()
    _, _, user32 = _win32()
    _settle(qapp)
    before = _grab("sin_foco.png")
    user32.SetCursorPos(round(400 * dpr), round(300 * dpr))
    ctrl.toggle_spotlight()
    _settle(qapp, 300)
    shot = _grab("foco.png")
    ctrl.toggle_spotlight()
    # a la derecha (la barra de herramientas está a la izquierda y queda por encima del foco)
    far = (round(min(ov.width() - 5, 400 + ctrl.spotlight_radius + 50) * dpr), round(300 * dpr))
    near = (round(400 * dpr), round(300 * dpr))
    lum = lambda px: sum(px[:3]) / 3  # noqa: E731
    assert lum(shot.getpixel(far)) < lum(before.getpixel(far)) * 0.5 + 1  # fuera del foco: oscuro
    assert abs(lum(shot.getpixel(near)) - lum(before.getpixel(near))) < 25  # dentro: igual que antes


def test_native_real_alt_f4_removes_the_sheet_from_the_desktop(ctrl, qapp, monkeypatch):
    """Alt+F4 real con la hoja cuadriculada: deben desaparecer la barra y la hoja."""
    _, _, user32 = _win32()
    calls = []
    monkeypatch.setattr(qapp, "quit", lambda: calls.append(1))
    ov = _overlay(ctrl)
    dpr = ov.devicePixelRatioF()
    ctrl.set_background("white")
    ctrl.set_pattern("grid")
    ctrl._raise_toolbar(activate=True)
    _settle(qapp, 500)
    ov_hwnd, tb_hwnd = int(ov.winId()), int(ctrl.toolbar.winId())
    point = (round(min(ov.width() - 20, 900) * dpr), round(min(ov.height() - 20, 500) * dpr))
    before = _grab("hoja_antes_alt_f4.png").getpixel(point)
    assert min(before[:3]) > 200  # la hoja blanca tapa el escritorio
    assert user32.GetForegroundWindow() == tb_hwnd
    user32.keybd_event(0x12, 0, 0, 0)  # Alt
    user32.keybd_event(0x73, 0, 0, 0)  # F4
    user32.keybd_event(0x73, 0, 2, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    _settle(qapp, 600)
    assert calls == [1]
    assert not user32.IsWindowVisible(ov_hwnd) and not user32.IsWindowVisible(tb_hwnd)
    after = _grab("hoja_despues_alt_f4.png").getpixel(point)
    assert after != before, (before, after)  # vuelve a verse el escritorio


def test_native_mouse_mode_with_cartesian_sheet_can_return(ctrl, qapp):
    """Hoja blanca + plano cartesiano → «Ratón libre» con un clic real: debe verse el
    escritorio, la barra debe quedar encima (según Windows) y se debe poder volver."""
    import ctypes
    from ctypes import wintypes

    _, _, user32 = _win32()
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetAncestor.restype = wintypes.HWND
    ov = _overlay(ctrl)
    tb = ctrl.toolbar
    dpr = ov.devicePixelRatioF()
    ctrl.set_background("white")
    ctrl.set_pattern("cartesian")
    ctrl.set_drawing(True)
    _settle(qapp, 500)
    x0, y0 = round(min(ov.width() - 80, 880) * dpr), round(min(ov.height() - 80, 480) * dpr)
    box = (x0, y0, x0 + 60, y0 + 60)  # zona sin barra ni trazos (incluye líneas de la cuadrícula)

    def region(name):
        img = _grab(name).crop(box).convert("RGB")
        raw = img.tobytes()  # (getdata() desaparece en Pillow 14)
        return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]

    sheet = region("cartesiano_dibujando.png")
    assert sum(min(px) > 180 for px in sheet) > 0.95 * len(sheet)  # hoja clara (blanco y cuadrícula)

    def top_window_at(widget):
        c = widget.mapToGlobal(widget.rect().center())
        hwnd = user32.WindowFromPoint(wintypes.POINT(round(c.x() * dpr), round(c.y() * dpr)))
        return int(user32.GetAncestor(hwnd, 2) or 0)  # GA_ROOT

    def click(widget):
        c = widget.mapToGlobal(widget.rect().center())
        _real_mouse(qapp, [(c.x(), c.y()), (c.x(), c.y())], dpr)

    for cycle in range(2):
        click(tb.mode_btn)  # → «Ratón libre»
        _settle(qapp, 400)
        assert not ctrl.drawing, cycle
        free = region(f"cartesiano_raton_libre_{cycle}.png")
        changed = sum(a != b for a, b in zip(free, sheet))
        assert changed > 0.5 * len(sheet), (cycle, changed, free[:3])  # se ve el escritorio, no la hoja
        assert top_window_at(tb.mode_btn) == int(tb.winId()), cycle  # la barra está encima de la hoja
        click(tb.mode_btn)  # → «Dibujando»: se puede volver
        _settle(qapp, 400)
        assert ctrl.drawing, cycle
        assert region(f"cartesiano_vuelta_{cycle}.png") == sheet, cycle  # la hoja vuelve igual


def test_native_edit_written_text_with_real_mouse_and_keyboard(ctrl, qapp):
    """Clic real sobre un texto ya escrito: se abre, Fin + teclas reales lo amplían y
    arrastrarlo con el ratón real lo mueve."""
    from pizarra_virtual import render
    from pizarra_virtual.items import TextEditItem, TextItem
    from pizarra_virtual.tools import Tool

    _, _, user32 = _win32()
    ov = _overlay(ctrl)
    dpr = ov.devicePixelRatioF()
    ctrl.set_tool(Tool.TEXT)
    _settle(qapp)
    _real_mouse(qapp, [(400, 300), (400, 300)], dpr)
    _real_keys(qapp, "hola")
    user32.keybd_event(0x1B, 0, 0, 0)  # Esc
    user32.keybd_event(0x1B, 0, 2, 0)
    _settle(qapp, 200)
    (t,) = [i for i in ctrl.items_for(ov.key) if isinstance(i, TextItem)]
    c = render.text_box(t).center()
    _real_mouse(qapp, [(c.x(), c.y()), (c.x(), c.y())], dpr)  # abrir para editar
    assert ctrl.text_editor is ov and ov.editing_text.uid == t.uid
    user32.keybd_event(0x23, 0, 0, 0)  # Fin
    user32.keybd_event(0x23, 0, 2, 0)
    _real_keys(qapp, " mundo")
    _real_mouse(qapp, [(c.x(), c.y())] + [(c.x() + 10 * k, c.y() + 6 * k) for k in range(1, 13)], dpr)
    user32.keybd_event(0x1B, 0, 0, 0)
    user32.keybd_event(0x1B, 0, 2, 0)
    _settle(qapp, 300)
    (e,) = [i for i in ctrl.items_for(ov.key) if isinstance(i, TextItem)]
    assert e.text.lower() == "hola mundo" and isinstance(ctrl.history[-1][1], TextEditItem)
    assert abs(e.x - (t.x + 120)) <= 2 and abs(e.y - (t.y + 72)) <= 2
    assert ctrl.tool == Tool.TEXT and not ctrl.spotlight
    _grab("texto_editado.png")


def test_native_erased_text_stamps_and_templates_with_real_input(ctrl, qapp):
    """Ratón y teclado reales: un texto borrado con la goma ya no se reabre (el clic crea uno nuevo),
    un clic con Sellos pone el sello, y un rótulo de plantilla se edita con un clic."""
    from pizarra_virtual import render
    from pizarra_virtual.items import GroupItem, StampItem, TextEditItem, TextItem
    from pizarra_virtual.tools import Tool

    _, _, user32 = _win32()
    ov = _overlay(ctrl)
    dpr = ov.devicePixelRatioF()

    def esc():
        user32.keybd_event(0x1B, 0, 0, 0)
        user32.keybd_event(0x1B, 0, 2, 0)
        _settle(qapp, 200)

    # 1) texto borrado con la goma
    ctrl.set_tool(Tool.TEXT)
    ctrl.set_size(48)
    _settle(qapp)
    # lejos de la barra (en pantallas pequeñas ocupa dos columnas, unos 270 px)
    x0 = max(500, ctrl.toolbar.geometry().right() + 120)
    _real_mouse(qapp, [(x0, 250), (x0, 250)], dpr)
    _real_keys(qapp, "borrar")
    esc()
    (t,) = [i for i in ctrl.items_for(ov.key) if isinstance(i, TextItem)]
    box = render.text_box(t)
    ctrl.set_tool(Tool.ERASER)
    ctrl.set_size(120)
    cy = box.center().y()
    _real_mouse(qapp, [(x, cy) for x in range(int(box.left()) - 50, int(box.right()) + 60, 12)], dpr)
    d = ov.canvas.devicePixelRatio()
    left_ink = sum(ov.canvas.pixelColor(round(x * d), round(y * d)).alpha() > 0
                   for x in range(int(box.left()), int(box.right()), 2)
                   for y in range(int(box.top()), int(box.bottom()), 2))
    kinds = [type(i).__name__ + ":" + getattr(getattr(i, "tool", None), "value", "") for _, i in ctrl.history]
    assert left_ink == 0, (left_ink, kinds, box)  # la goma real borró todo el texto
    ctrl.set_tool(Tool.TEXT)
    _real_mouse(qapp, [(box.center().x(), cy), (box.center().x(), cy)], dpr)
    assert ov.editing_text is not None and ov.editing_text.uid != t.uid, (kinds, box)  # texto nuevo
    esc()

    # 2) sello con un clic real
    ctrl.set_stamp_kind("check")
    _settle(qapp)
    _real_mouse(qapp, [(x0, 420), (x0, 420)], dpr)
    assert isinstance(ctrl.history[-1][1], StampItem)

    # 3) plantilla y edición de un rótulo
    ctrl.clear_all()
    ctrl.insert_template("essay")
    _settle(qapp, 300)
    assert isinstance(ctrl.history[-1][1], GroupItem) and ctrl.tool == Tool.TEXT
    intro = next(i for i in ctrl.items_for(ov.key) if isinstance(i, TextItem) and i.text == "Introducción")
    c = render.text_box(intro).center()
    _real_mouse(qapp, [(c.x(), c.y()), (c.x(), c.y())], dpr)
    assert ov.editing_text is not None and ov.editing_text.uid == intro.uid
    user32.keybd_event(0x23, 0, 0, 0)  # Fin
    user32.keybd_event(0x23, 0, 2, 0)
    _real_keys(qapp, " uno")
    esc()
    assert isinstance(ctrl.history[-1][1], TextEditItem)
    texts = [i.text.lower() for i in ctrl.items_for(ov.key) if isinstance(i, TextItem)]
    assert "introducción uno" in texts
    _grab("plantilla_editada.png")


def test_native_v14_recognition_select_paste_and_timer(ctrl, qapp):
    """Ratón y teclado reales: formas perfectas, seleccionar-mover-eliminar, Ctrl+V de una imagen
    y temporizador (encima de la pizarra y con su botón de pausa)."""
    import ctypes
    import math
    from ctypes import wintypes

    from PySide6.QtGui import QColor, QGuiApplication, QImage

    from pizarra_virtual.items import DeleteItem, ImageItem, ShapeItem, TransformItem
    from pizarra_virtual.tools import Tool

    _, _, user32 = _win32()
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetAncestor.restype = wintypes.HWND
    ov = _overlay(ctrl)
    dpr = ov.devicePixelRatioF()
    # Todo dentro de la pantalla también al 150 % (unos 683 x 512 px lógicos) y lejos de la barra
    cx = min(ov.width() - 100, max(ctrl.toolbar.geometry().right() + 100, 420))

    def key(vk, ctrl_down=False):
        if ctrl_down:
            user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        if ctrl_down:
            user32.keybd_event(0x11, 0, 2, 0)
        _settle(qapp, 250)

    # 1) Formas perfectas: un círculo a mano alzada se vuelve un círculo exacto
    ctrl.set_tool(Tool.PEN)
    ctrl.set_recognize_shapes(True)
    _settle(qapp)
    pts = [(cx + 70 * math.cos(a / 16), 260 + 70 * math.sin(a / 16)) for a in range(0, 106)]
    _real_mouse(qapp, pts, dpr)
    circle = ctrl.history[-1][1]
    assert isinstance(circle, ShapeItem) and circle.tool == Tool.ELLIPSE

    # 2) Seleccionar con un clic sobre el borde y bajarlo 100 px; Supr lo elimina
    ctrl.set_tool(Tool.SELECT)
    _settle(qapp)
    edge = (circle.x2, (circle.y1 + circle.y2) / 2)
    _real_mouse(qapp, [edge] + [(edge[0], edge[1] + k * 10) for k in range(1, 11)], dpr)
    assert isinstance(ctrl.history[-1][1], TransformItem) and ov.selection == [circle.uid]
    (moved,) = [i for i in ctrl.items_for(ov.key) if getattr(i, "uid", None) == circle.uid]
    assert abs(moved.y1 - (circle.y1 + 100)) <= 2 and abs(moved.x1 - circle.x1) <= 2
    key(0x2E)  # Supr
    assert isinstance(ctrl.history[-1][1], DeleteItem) and not ctrl.items_for(ov.key)

    # 3) Ctrl+V con una imagen en el portapapeles de Windows
    img = QImage(160, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(30, 136, 229))
    QGuiApplication.clipboard().setImage(img)
    _settle(qapp, 200)
    user32.SetCursorPos(round(cx * dpr), round(260 * dpr))
    ctrl._raise_toolbar(activate=True)
    _settle(qapp, 300)
    key(0x56, ctrl_down=True)  # Ctrl+V
    assert isinstance(ctrl.history[-1][1], ImageItem) and ctrl.tool == Tool.SELECT
    _grab("imagen_pegada.png")

    # 4) Temporizador: encima de la pizarra y el botón de pausa responde a un clic real
    ctrl.start_timer(120)
    _settle(qapp, 400)
    w = ctrl.timer_window
    b = w.pause_btn
    c = b.mapToGlobal(b.rect().center())
    hwnd = user32.WindowFromPoint(wintypes.POINT(round(c.x() * dpr), round(c.y() * dpr)))
    assert int(user32.GetAncestor(hwnd, 2) or 0) == int(w.winId())
    assert w.running
    _real_mouse(qapp, [(c.x(), c.y()), (c.x(), c.y())], dpr)
    assert not w.running  # en pausa
    _grab("temporizador.png")


def test_native_v15_crop_keys_curtain_and_cover(ctrl, qapp, tmp_path):
    """Recortar zona con la pantalla real y el ratón real; teclas reales mostradas en pantalla;
    cortina desde la izquierda y zona tapada que se descubre con un clic real."""
    from PIL import Image
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QCursor

    from pizarra_virtual.items import CoverItem, DeleteItem, ImageItem
    from pizarra_virtual.tools import Tool

    _, _, user32 = _win32()
    ov = _overlay(ctrl)
    dpr = ov.devicePixelRatioF()
    _settle(qapp)
    x0 = max(ctrl.toolbar.geometry().right() + 60, 300)
    x1 = min(ov.width() - 40, x0 + 200)
    _draw_red_line(ctrl, ov, y=260, x0=x0, x1=x1)

    # 1) Recortar zona (con lo dibujado): el PNG guardado contiene solo esa parte, con la línea
    QCursor.setPos(ov.mapToGlobal(QPoint(x0, 200)))
    ctrl.start_crop()
    _settle(qapp, 1000)
    assert ctrl.crop_active
    _grab("recortar_zona.png")
    _real_mouse(qapp, [(x0 - 20, 230), (x0 + 60, 260), (x1 + 20, 290)], dpr)
    assert not ctrl.crop_active
    files = list((tmp_path / "Pictures" / "Capturas Pizarra").glob("*.png"))
    assert len(files) == 1
    img = Image.open(files[0]).convert("RGB")
    w_expected = (x1 + 20 - (x0 - 20)) * dpr
    assert abs(img.size[0] - w_expected) <= 2 and abs(img.size[1] - 60 * dpr) <= 2
    assert _is_red(img.getpixel((img.size[0] // 2, img.size[1] // 2)))

    # 2) Recortar y pegar en la pizarra: queda una imagen en el mismo lugar
    ctrl.start_crop(with_drawing=False, to_board=True)
    _settle(qapp, 1000)
    _real_mouse(qapp, [(x0, 320), (x0 + 50, 350), (x0 + 100, 380)], dpr)
    item = ctrl.history[-1][1]
    assert isinstance(item, ImageItem) and abs(item.x - x0) <= 1 and abs(item.w - 100) <= 1

    # 3) Teclas reales: Ctrl + Mayús + K se muestra; una letra sola, no
    ctrl.set_tool(Tool.BRUSH)
    ctrl.toggle_show_keys()
    QCursor.setPos(ov.mapToGlobal(QPoint(x0, 200)))
    _settle(qapp, 200)
    for vk in (0x11, 0x10, 0x4B):
        user32.keybd_event(vk, 0, 0, 0)
        _settle(qapp, 60)
    for vk in (0x4B, 0x10, 0x11):
        user32.keybd_event(vk, 0, 2, 0)
    _settle(qapp, 150)
    user32.keybd_event(0x51, 0, 0, 0)  # Q (rectángulo redondeado): se pulsa, pero no se muestra
    _settle(qapp, 60)
    user32.keybd_event(0x51, 0, 2, 0)
    _settle(qapp, 150)
    assert ov.keys_shown == ["Ctrl + Mayús + K"], ov.keys_shown
    _grab("teclas_en_pantalla.png")
    ctrl.toggle_show_keys()

    # 4) Cortina desde la izquierda, arrastrada con el ratón real
    ctrl.set_tool(Tool.BRUSH)
    ctrl.show_curtain("left")
    _settle(qapp, 200)
    grab_x = ov.width() // 2
    _real_mouse(qapp, [(grab_x, 300), (grab_x + 20, 300), (grab_x + 40, 300)], dpr)
    assert abs(ov.curtain - 40) <= 2 and ov.curtain_side == "left"
    _grab("cortina_izquierda.png")
    ctrl.toggle_curtain()

    # 5) Tapar zona con el ratón real y descubrirla con un clic real
    ctrl.set_tool(Tool.COVER)
    _settle(qapp, 200)
    _real_mouse(qapp, [(x0 - 10, 240), (x0 + 50, 260), (x1, 285)], dpr)
    cover = ctrl.history[-1][1]
    assert isinstance(cover, CoverItem)
    shot = _grab("zona_tapada.png")
    assert not _is_red(shot.getpixel((round((x0 + 100) * dpr), round(260 * dpr))))  # la línea no se ve
    _real_mouse(qapp, [(x0 + 30, 250), (x0 + 30, 250)], dpr)
    assert isinstance(ctrl.history[-1][1], DeleteItem)
    shot = _grab("zona_descubierta.png")
    assert _is_red(shot.getpixel((round((x0 + 100) * dpr), round(260 * dpr))))


def _touch_injection():
    """Inyección de toques REALES de Windows (InjectTouchInput), como una pantalla táctil."""
    import ctypes
    from ctypes import wintypes

    class POINTER_INFO(ctypes.Structure):  # noqa: N801
        _fields_ = [("pointerType", ctypes.c_uint32), ("pointerId", ctypes.c_uint32),
                    ("frameId", ctypes.c_uint32), ("pointerFlags", ctypes.c_uint32),
                    ("sourceDevice", wintypes.HANDLE), ("hwndTarget", wintypes.HWND),
                    ("ptPixelLocation", wintypes.POINT), ("ptHimetricLocation", wintypes.POINT),
                    ("ptPixelLocationRaw", wintypes.POINT), ("ptHimetricLocationRaw", wintypes.POINT),
                    ("dwTime", wintypes.DWORD), ("historyCount", ctypes.c_uint32),
                    ("InputData", ctypes.c_int32), ("dwKeyStates", wintypes.DWORD),
                    ("PerformanceCount", ctypes.c_uint64), ("ButtonChangeType", ctypes.c_int)]

    class POINTER_TOUCH_INFO(ctypes.Structure):  # noqa: N801
        _fields_ = [("pointerInfo", POINTER_INFO), ("touchFlags", ctypes.c_uint32),
                    ("touchMask", ctypes.c_uint32), ("rcContact", wintypes.RECT),
                    ("rcContactRaw", wintypes.RECT), ("orientation", ctypes.c_uint32),
                    ("pressure", ctypes.c_uint32)]

    user32 = ctypes.windll.user32
    user32.InitializeTouchInjection.argtypes = [ctypes.c_uint32, wintypes.DWORD]
    user32.InjectTouchInput.argtypes = [ctypes.c_uint32, ctypes.POINTER(POINTER_TOUCH_INFO)]
    if not user32.InitializeTouchInjection(10, 0x3):  # TOUCH_FEEDBACK_NONE
        return None
    DOWN, UPDATE, UP, INRANGE, INCONTACT = 0x10000, 0x20000, 0x40000, 0x2, 0x4

    def frame(contacts):
        """contacts: lista de (id, x, y, estado «down»/«move»/«up», ancho del contacto)."""
        arr = (POINTER_TOUCH_INFO * len(contacts))()
        for k, (pid, x, y, state, size) in enumerate(contacts):
            t = arr[k]
            t.pointerInfo.pointerType = 2  # PT_TOUCH
            t.pointerInfo.pointerId = pid
            t.pointerInfo.ptPixelLocation = wintypes.POINT(int(x), int(y))
            t.pointerInfo.pointerFlags = {"down": DOWN | INRANGE | INCONTACT,
                                          "move": UPDATE | INRANGE | INCONTACT, "up": UP}[state]
            t.touchMask = 0x1 | 0x2 | 0x4  # área de contacto, orientación y presión
            h = size // 2
            t.rcContact = wintypes.RECT(int(x) - h, int(y) - h, int(x) + h, int(y) + h)
            t.orientation = 90
            t.pressure = 32000
        return bool(user32.InjectTouchInput(len(contacts), arr))

    return frame


def test_native_v15_real_touch_draws_undoes_and_palm_erases(ctrl, qapp):
    """Toques reales de Windows: un dedo dibuja, dos dedos a la vez deshacen, la palma borra."""
    if os.environ.get("PIZARRA_TOUCH") != "1":
        pytest.skip("se ejecuta en su propio paso, con la pantalla táctil virtual (PIZARRA_TOUCH=1)")
    frame = _touch_injection()
    if frame is None:
        pytest.skip("este Windows no permite inyectar toques (InitializeTouchInjection)")
    from pizarra_virtual.tools import Tool

    ov = _overlay(ctrl)
    dpr = ov.devicePixelRatioF()
    ctrl.set_tool(Tool.BRUSH)
    ctrl.set_size(16)
    _settle(qapp)
    x0 = max(ctrl.toolbar.geometry().right() + 60, 300)

    def phys(x, y):
        return round(x * dpr), round(y * dpr)

    # 1) Un dedo dibuja una línea
    assert frame([(0, *phys(x0, 250), "down", 10)])
    _settle(qapp, 30)
    for k in range(1, 21):
        frame([(0, *phys(x0 + k * 10, 250), "move", 10)])
        _settle(qapp, 15)
    frame([(0, *phys(x0 + 200, 250), "up", 10)])
    _settle(qapp, 300)
    assert len(ctrl.history) == 1 and ctrl.history[0][1].tool == Tool.BRUSH
    assert ov.touch_events > 0, "Qt no entregó eventos táctiles (los trató como ratón)"
    _grab("toque_dibuja.png")

    # 2) La palma (contacto ancho) borra aunque la herramienta sea el pincel
    frame([(0, *phys(x0 + 100, 250), "down", round(120 * dpr))])
    _settle(qapp, 30)
    for k in range(1, 6):
        frame([(0, *phys(x0 + 100, 250 + k), "move", round(120 * dpr))])
        _settle(qapp, 15)
    frame([(0, *phys(x0 + 100, 255), "up", round(120 * dpr))])
    _settle(qapp, 300)
    last = ctrl.history[-1][1]
    tc = ctrl._touch_contacts
    assert last.tool == Tool.ERASER, (last.tool, tc.downs, tc.size, tc.error, ov.touch_events, str(ov.touch_sizes[-10:]))
    assert ctrl.tool == Tool.BRUSH and ctrl.sizes[Tool.ERASER] < 120 * 2  # el tamaño de la goma se restaura

    # 3) Toque con dos dedos a la vez: deshacer (la goma de la palma)
    n = len(ctrl.history)
    frame([(0, *phys(x0, 400), "down", 10), (1, *phys(x0 + 80, 400), "down", 10)])
    _settle(qapp, 60)
    frame([(0, *phys(x0, 400), "up", 10), (1, *phys(x0 + 80, 400), "up", 10)])
    _settle(qapp, 300)
    assert len(ctrl.history) == n - 1
    assert all(item.tool == Tool.BRUSH for _k, item in ctrl.history)
