"""Barra básica / avanzada y botón «Ocultar» arriba de todo."""
import pytest
from PySide6.QtCore import QRect, QSettings
from PySide6.QtTest import QTest

from pizarra_virtual.tools import BASIC_TOOLS, Tool


def _basic(ctrl):
    ctrl.set_basic_toolbar(True)
    QTest.qWait(30)  # la barra se reconstruye después del clic
    assert ctrl.toolbar.basic
    return ctrl.toolbar


def _shown(tb, w) -> bool:
    return w.isVisibleTo(tb)


def test_hide_button_is_on_top_and_toggles(ctrl, qapp):
    tb = ctrl.toolbar
    tb.set_two_columns(False)
    tb.refit()
    hide, mode = tb.hide_btn, tb.mode_btn
    y = lambda w: w.mapTo(tb, w.rect().topLeft()).y()  # noqa: E731
    assert y(hide) < y(mode) < y(tb.tool_buttons[Tool.BRUSH])
    assert hide.text() == "Ocultar" and not hide.isChecked()
    hide.click()
    assert not ctrl.visible and hide.text() == "Mostrar" and hide.isChecked()
    hide.click()
    assert ctrl.visible and hide.text() == "Ocultar" and not hide.isChecked()
    # En dos columnas, «Ocultar» y «Dibujando» van lado a lado, también arriba de todo
    tb.set_two_columns(True)
    tb.refit()
    assert y(hide) == y(mode) and hide.mapTo(tb, hide.rect().topLeft()).x() < mode.mapTo(tb, mode.rect().topLeft()).x()


def test_basic_toolbar_shows_only_common_tools(ctrl, qapp):
    ctrl.toolbar.set_two_columns(False)  # la avanzada en una columna, para comparar
    ctrl.toolbar.refit()
    advanced_height = ctrl.toolbar.height()
    tb = _basic(ctrl)
    for tool in BASIC_TOOLS:
        assert _shown(tb, tb.tool_buttons[tool]), tool
    for w in (tb.hide_btn, tb.mode_btn, tb.note_btn, tb.more_btn, tb.color_btn, tb.swatches, tb.size_slider,
              tb.undo_btn, tb.redo_btn, tb.clear_btn, tb.layout_btn):
        assert _shown(tb, w)
    for w in (tb.tool_buttons[Tool.LINE], tb.select_btn, tb.bg_combo, tb.pattern_combo, tb.spot_btn,
              tb.opacity_slider, tb.brush_combo, tb.prev_btn, tb.capture_btn):
        assert not _shown(tb, w)
    ctrl.set_tool(Tool.BRUSH)
    tb.set_two_columns(False)
    tb.refit()
    assert tb.height() < advanced_height * 0.65
    # Sigue sincronizada aunque sus controles ocultos no se vean
    ctrl.set_tool(Tool.LINE)
    assert tb.more_btn.isChecked() and not tb.tool_buttons[Tool.BRUSH].isChecked()
    ctrl.set_tool(Tool.PEN)
    assert tb.tool_buttons[Tool.PEN].isChecked() and not tb.more_btn.isChecked()


def test_basic_toolbar_fits_small_laptop(ctrl, qapp, monkeypatch):
    """1366×768 (unos 728 px útiles): la barra básica cabe en una sola columna."""
    tb = _basic(ctrl)
    screen = tb._current_screen()
    real = screen.availableGeometry()
    small = QRect(real.left(), real.top(), real.width(), min(real.height(), 728))
    monkeypatch.setattr(type(screen), "availableGeometry", lambda self: small)
    tb.update_orientation()
    assert not tb.horizontal
    assert tb.frameGeometry().height() <= 560


def test_basic_menu_has_the_rest(ctrl, qapp):
    tb = _basic(ctrl)
    menu = tb.build_basic_menu()
    texts = [a.text().split("\t")[0] for a in menu.actions()]
    for label in ("Fondo de la pizarra", "Pauta", "Línea", "Flecha", "Más figuras", "Sellos", "Plantillas",
                  "Regla, transportador y compás", "Seleccionar y mover", "Pegar imagen o texto", "Foco",
                  "Cortina", "Tapar zona", "Temporizador", "Zoom", "Página nueva",
                  "Captura de pantalla y recortar zona", "Sesión y PDF", "Ayuda",
                  "Barra avanzada (todas las opciones)"):
        assert label in texts, label
    # Fondo: submenú con las cuatro opciones, la actual marcada
    bg = next(a.menu() for a in menu.actions() if a.text() == "Fondo de la pizarra")
    bg.aboutToShow.emit()
    acts = bg.actions()
    assert [a.text() for a in acts] == ["Transparente", "Oscurecer escritorio", "Pizarra blanca", "Pizarra verde"]
    assert acts[0].isChecked()
    acts[2].trigger()
    assert ctrl.background == "white"
    # Las acciones del menú funcionan
    next(a for a in menu.actions() if a.text().startswith("Línea")).trigger()
    assert ctrl.tool == Tool.LINE
    next(a for a in menu.actions() if a.text().startswith("Página nueva")).trigger()
    assert len(ctrl.pages) == 2
    # Volver a la barra avanzada
    next(a for a in menu.actions() if a.text().startswith("Barra avanzada")).trigger()
    QTest.qWait(30)
    assert not ctrl.basic_toolbar and not ctrl.toolbar.basic


def test_switch_button_and_setting(ctrl, qapp):
    ctrl.toolbar.layout_btn.click()
    QTest.qWait(30)
    tb = ctrl.toolbar
    assert tb.basic and str(ctrl.settings.value("basic_toolbar")) == "true"
    assert tb.layout_btn.text() == "Más opciones"
    tb.layout_btn.click()
    QTest.qWait(30)
    assert not ctrl.toolbar.basic and str(ctrl.settings.value("basic_toolbar")) == "false"


def test_old_toolbar_is_disconnected_after_rebuild(ctrl, qapp):
    old = ctrl.toolbar
    _basic(ctrl)
    calls = []
    old.sync = lambda: calls.append(1)  # (ya no está conectada; no debe llamarse)
    ctrl.set_color(ctrl.color)
    assert calls == []


def test_shortcuts_work_in_basic_toolbar(ctrl, qapp):
    tb = _basic(ctrl)
    seqs = {sc.key().toString(): sc for sc in tb._shortcuts if sc.isEnabled()}
    seqs["9"].activated.emit()  # Línea: no tiene botón en la barra básica, pero su atajo funciona
    assert ctrl.tool == Tool.LINE


@pytest.mark.parametrize("short, expected", [(True, True), (False, False)])
def test_default_depends_on_screen_height(qapp, tmp_path, monkeypatch, short, expected):
    from pizarra_virtual.app import Controller

    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Controller, "_short_screen", staticmethod(lambda: short))
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)  # nunca se eligió
    c = Controller(qapp, settings=settings, enable_hotkeys=False, enable_tray=False)
    try:
        assert c.basic_toolbar is expected and c.toolbar.basic is expected
    finally:
        c.shutdown()
        qapp.processEvents()
    # Lo elegido se recuerda
    settings.setValue("basic_toolbar", "false" if expected else "true")
    c = Controller(qapp, settings=settings, enable_hotkeys=False, enable_tray=False)
    try:
        assert c.basic_toolbar is not expected
    finally:
        c.shutdown()
        qapp.processEvents()


def test_touch_mode_keeps_basic_toolbar(ctrl, qapp):
    _basic(ctrl)
    ctrl.set_touch_mode(True)
    QTest.qWait(30)
    tb = ctrl.toolbar
    assert tb.basic and tb.k > 1
    tb.set_two_columns(False)
    tb.refit()
    assert tb.height() <= 728  # sigue cabiendo en un notebook de 1366×768, con botones grandes
    ctrl.set_touch_mode(False)
    QTest.qWait(30)


def _darkest(widget) -> int:
    img = widget.grab().toImage()
    return min(img.pixelColor(x, y).lightness() for x in range(0, img.width(), 2) for y in range(0, img.height(), 2))


def test_dialogs_use_dark_readable_text(ctrl, qapp):
    """Los diálogos (p. ej. «¿Guardar los cambios?» al salir) no heredan la letra clara de la barra."""
    from PySide6.QtWidgets import QLabel, QMessageBox

    box = QMessageBox(QMessageBox.Icon.Question, "Pizarra Virtual", "Hay cambios sin guardar.",
                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard, ctrl.toolbar)
    box.button(QMessageBox.StandardButton.Discard).setText("No guardar")
    box.show()
    qapp.processEvents()
    label = next(w for w in box.findChildren(QLabel) if w.text() == "Hay cambios sin guardar.")
    assert _darkest(label) < 90  # letra oscura (antes, gris claro: ~200)
    assert _darkest(box.button(QMessageBox.StandardButton.Discard)) < 90
    box.done(0)  # (close() no cierra un QMessageBox sin botón de cancelar)
    box.deleteLater()
    # La barra sigue con su estilo oscuro y letra clara
    tb_img = ctrl.toolbar.panel.grab().toImage()
    assert tb_img.pixelColor(tb_img.width() // 2, 4).lightness() < 80
