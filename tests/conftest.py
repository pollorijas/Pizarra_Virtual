import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32" and os.environ["QT_QPA_PLATFORM"].startswith("offscreen"):
    # Sin esto, Qt «offscreen» en Windows no encuentra ninguna fuente y el texto no se dibuja
    # (igual que en tools/build_manual.py): las pruebas usan las fuentes reales de Windows.
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    yield app


@pytest.fixture
def ctrl(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    from pizarra_virtual.app import Controller

    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    c = Controller(qapp, settings=settings, enable_hotkeys=False, enable_tray=False)
    c.start()
    qapp.processEvents()
    yield c
    c.shutdown()
    qapp.processEvents()
