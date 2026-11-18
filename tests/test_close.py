"""Cerrar con Alt+F4 (o cualquier cierre de ventana) cierra TODO el programa.

Antes, Alt+F4 cerraba solo la barra de herramientas y la pizarra (con una hoja blanca o
cuadriculada) quedaba encima del escritorio, sin forma de quitarla.
"""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QMessageBox

from pizarra_virtual.items import StrokeItem
from pizarra_virtual.tools import Tool


def _quit_spy(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr(qapp, "quit", lambda: calls.append(1))
    return calls


def _all_closed(ctrl):
    return not ctrl.toolbar.isVisible() and not ctrl.overlays and ctrl.shutting_down


def test_closing_toolbar_closes_whole_program(ctrl, qapp, monkeypatch):
    calls = _quit_spy(qapp, monkeypatch)
    ctrl.set_background("white")
    ctrl.set_pattern("grid")
    overlays = list(ctrl.overlays.values())
    ctrl.toolbar.close()  # lo mismo que hace Windows con Alt+F4
    qapp.processEvents()
    assert calls == [1]
    assert _all_closed(ctrl)
    assert all(not ov.isVisible() for ov in overlays)


def test_closing_an_overlay_closes_whole_program(ctrl, qapp, monkeypatch):
    calls = _quit_spy(qapp, monkeypatch)
    ctrl.set_pattern("cartesian")
    ov = next(iter(ctrl.overlays.values()))
    ov.close()
    ov.close()  # varias peticiones seguidas se agrupan en una sola salida
    qapp.processEvents()
    assert calls == [1]
    assert _all_closed(ctrl) and not ov.isVisible()


def test_close_cancelled_keeps_everything(ctrl, qapp, monkeypatch):
    calls = _quit_spy(qapp, monkeypatch)
    ctrl.history.append((None, StrokeItem(Tool.PEN, (0, 0, 0, 255), 3, 1.0, points=[(1, 1, 3), (9, 9, 3)])))
    ctrl.dirty = True
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)
    ctrl.toolbar.close()
    qapp.processEvents()
    assert calls == []
    assert ctrl.toolbar.isVisible() and ctrl.overlays and not ctrl.shutting_down
    assert all(ov.isVisible() for ov in ctrl.overlays.values())
    # y se puede volver a cerrar después
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Discard)
    ctrl.toolbar.close()
    qapp.processEvents()
    assert calls == [1] and _all_closed(ctrl)


def test_alt_f4_not_swallowed_while_typing_text(ctrl, qapp):
    ov = next(iter(ctrl.overlays.values()))
    ctrl.set_tool(Tool.TEXT)
    ctrl.text_editor = ov
    alt_f4 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F4, Qt.KeyboardModifier.AltModifier)
    assert ctrl.eventFilter(ctrl.toolbar, alt_f4) is False
    letter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
    assert ctrl.eventFilter(ctrl.toolbar, letter) is True
    ctrl.text_editor = None


def test_about_to_quit_releases_everything(ctrl, qapp):
    ctrl.set_pattern("grid")
    ctrl._on_about_to_quit()  # p. ej. al cerrar la sesión de Windows
    assert _all_closed(ctrl)
    ctrl._on_about_to_quit()  # idempotente
