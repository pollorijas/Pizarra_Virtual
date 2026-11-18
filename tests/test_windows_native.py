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
        assert len(ids) == 7, "no se registraron todos los atajos globales"
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
        return list(_grab(name).crop(box).convert("RGB").getdata())

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
