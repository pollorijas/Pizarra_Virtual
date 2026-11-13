import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
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
    for ov in list(c.overlays.values()):
        ov.close()
    c.toolbar.close()
    qapp.processEvents()
