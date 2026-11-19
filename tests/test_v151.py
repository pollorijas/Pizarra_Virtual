"""Pruebas de la versión 1.5.1: correcciones de la revisión de código."""
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QGuiApplication, QInputDevice, QTouchEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pizarra_virtual import capture, touchcontact, winutil
from pizarra_virtual.tools import Tool
from tests.test_v15 import _fake_screen, _start_crop

CTRL, ALT, K = 0x11, 0x12, 0x4B


def _ov(ctrl):
    return ctrl.overlay_for_screen(QGuiApplication.primaryScreen())


def _seq(ov, dev):
    return QTest.touchEvent(ov, dev)


def test_touch_screen_detection_ignores_pen_only_digitizers():
    assert not winutil.digitizer_has_touch(0x88)  # lápiz externo (Wacom) + listo
    assert not winutil.digitizer_has_touch(0xC4)  # lápiz integrado
    assert winutil.digitizer_has_touch(0x81)  # pantalla táctil integrada
    assert winutil.digitizer_has_touch(0x02)  # pantalla táctil externa
    assert winutil.digitizer_has_touch(0xC7)


def test_palm_eraser_size_is_restored_when_palm_becomes_a_gesture(ctrl):
    ov = _ov(ctrl)
    dev = QTest.createTouchDevice(QInputDevice.DeviceType.TouchScreen)
    ctrl.set_tool(Tool.BRUSH)
    base = ctrl.sizes[Tool.ERASER]
    ctrl.touch_contact_size = lambda: 120.0 * ov.devicePixelRatioF()
    _seq(ov, dev).press(0, QPoint(300, 300), ov).commit()
    assert ctrl.sizes[Tool.ERASER] >= 100  # la palma usa una goma grande…
    _seq(ov, dev).stationary(0).press(1, QPoint(380, 300), ov).commit()  # …pero era un gesto
    _seq(ov, dev).release(0, QPoint(300, 300), ov).release(1, QPoint(380, 300), ov).commit()
    assert ctrl.sizes[Tool.ERASER] == base
    # También si Windows cancela el toque
    _seq(ov, dev).press(0, QPoint(300, 300), ov).commit()
    assert ctrl.sizes[Tool.ERASER] >= 100
    QApplication.sendEvent(ov, QTouchEvent(QEvent.Type.TouchCancel, dev))
    assert ctrl.sizes[Tool.ERASER] == base and not ov._touch_active


def test_contact_size_is_only_trusted_with_a_single_contact():
    tc = touchcontact.TouchContacts()
    tc.down(1, 10.0)
    assert tc.recent_size() == 10.0
    tc.down(2, 120.0)  # la mano se apoya mientras el dedo escribe
    assert tc.recent_size() == 0.0  # no se sabe de quién es: no se convierte en goma
    tc.up(1)
    assert tc.recent_size() == 120.0
    tc.update(2, 130.0)
    assert tc.recent_size() == 130.0 and tc.size == 130.0
    tc.up(2)
    assert tc.recent_size() == 0.0


def test_mouse_mode_or_hiding_ends_the_crop(ctrl, monkeypatch):
    ov = _ov(ctrl)
    monkeypatch.setattr(capture, "grab_screen", lambda s: _fake_screen(ov))
    monkeypatch.setattr(capture, "save_capture", lambda img, *a: "x.png")
    _start_crop(ctrl)
    ctrl.set_drawing(False)  # Ctrl+Alt+D en medio del recorte
    assert not ctrl.crop_active and not ov.crop_active and not ctrl.drawing
    assert ctrl._crop is None
    ctrl.set_drawing(True)
    _start_crop(ctrl)
    ctrl.toggle_visible()  # Ctrl+Alt+H
    assert not ctrl.crop_active and not ctrl.visible
    ctrl.toggle_visible()
    assert not ov.crop_active


def test_enabling_key_display_does_not_show_its_own_shortcut(ctrl):
    ov = _ov(ctrl)
    state = {"keys": {CTRL, ALT, K}}
    ctrl.key_state = lambda: set(state["keys"])
    ctrl.toggle_show_keys()
    ctrl._tick()
    state["keys"] = set()
    ctrl._tick()
    assert ov.keys_shown == []
    state["keys"] = {CTRL, 0x43}
    ctrl._tick()
    assert ov.keys_shown == ["Ctrl + C"]


def test_old_toolbar_shortcuts_are_disabled_at_once(ctrl):
    old = ctrl.toolbar
    ctrl.set_touch_mode(True)
    QApplication.processEvents()  # se reconstruye la barra
    assert ctrl.toolbar is not old
    assert all(not sc.isEnabled() for sc in old._shortcuts)
    assert all(sc.isEnabled() for sc in ctrl.toolbar._shortcuts)
    ctrl.set_touch_mode(False)
    QTest.qWait(50)
