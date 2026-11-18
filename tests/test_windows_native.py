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
        assert (cx, cy, cw) == (x, y, w)
        tb.sizeHint()
        tb.toggle_collapsed()
        _settle(qapp, 200)
        assert _rect(hwnd)[3] == h
    _grab("barra_desplegada.png")


def test_native_click_through_styles(ctrl, qapp):
    ov = _overlay(ctrl)
    _settle(qapp)
    hwnd = int(ov.winId())
    WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_TOPMOST, WS_EX_NOACTIVATE = 0x20, 0x80000, 0x8, 0x08000000
    st = _exstyle(hwnd)
    assert st & WS_EX_LAYERED and st & WS_EX_TOPMOST and st & WS_EX_NOACTIVATE
    assert not st & WS_EX_TRANSPARENT  # modo dibujo: recibe los clics
    ctrl.set_drawing(False)
    _settle(qapp, 200)
    assert _exstyle(hwnd) & WS_EX_TRANSPARENT  # «Ratón libre»: los clics atraviesan
    ctrl.set_drawing(True)
    _settle(qapp, 200)
    assert not _exstyle(hwnd) & WS_EX_TRANSPARENT


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
        assert len(ids) == 5, "no se registraron todos los atajos globales"
        _, _, user32 = _win32()
        assert c.drawing
        user32.PostMessageW(c.hotkeys._hwnd, WM_HOTKEY, ids[0], 0)  # Ctrl+Alt+D
        _settle(qapp, 200)
        assert not c.drawing
        user32.PostMessageW(c.hotkeys._hwnd, WM_HOTKEY, ids[0], 0)
        _settle(qapp, 200)
        assert c.drawing
    finally:
        c.hotkeys.unregister_all()
        for ov in list(c.overlays.values()):
            ov.close()
        c.toolbar.close()
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
