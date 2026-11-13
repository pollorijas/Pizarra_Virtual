"""Punto de entrada de la aplicación."""
from __future__ import annotations

import logging
import os
import sys
import traceback

from . import APP_NAME, __version__

log = logging.getLogger("pizarra_virtual")


def _log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "PizarraVirtual")
    os.makedirs(path, exist_ok=True)
    return path


def setup_logging() -> str | None:
    handlers: list[logging.Handler] = []
    path = None
    try:
        path = os.path.join(_log_dir(), "pizarra.log")
        handlers.append(logging.FileHandler(path, encoding="utf-8", mode="w"))
    except OSError:
        pass
    if sys.stderr is not None:  # en el .exe sin consola stderr es None
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return path


def _install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        log.critical("Error no controlado:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(None, APP_NAME, f"Se produjo un error inesperado:\n{exc}\n\n"
                                                     f"Detalles en {os.path.join(_log_dir(), 'pizarra.log')}")
        except Exception:
            pass

    sys.excepthook = hook


def _install_translations(app) -> None:
    """Traduce los diálogos estándar de Qt (selector de color, etc.) al español."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name in ("qtbase", "qt"):
        tr = QTranslator(app)
        if tr.load(QLocale("es"), name, "_", path):
            app.installTranslator(tr)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    setup_logging()
    _install_excepthook()
    log.info("%s %s iniciando (Python %s, %s)", APP_NAME, __version__, sys.version.split()[0], sys.platform)

    if "--selftest" in argv:
        from .selftest import run

        return run()

    from PySide6.QtCore import QDir, QLockFile, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QMessageBox

    from . import icons, winutil
    from .app import Controller

    # Qt 6 ya es "Per-Monitor DPI Aware v2" en Windows; además se evita redondear el
    # factor de escala (125 %, 150 %, 175 %) para que el lienzo coincida píxel a píxel.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    winutil.set_app_user_model_id("PizarraVirtual.Desktop.1")

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("PizarraVirtual")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(icons.app_icon())
    app.setStyle("Fusion")
    _install_translations(app)

    lock = QLockFile(os.path.join(QDir.tempPath(), "pizarra_virtual.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "Pizarra Virtual ya se está ejecutando.\n"
                                                "Búscala en el área de notificación (junto al reloj).")
        return 0

    ctrl = Controller(app)
    ctrl.start()
    rc = app.exec()
    lock.unlock()
    log.info("Saliendo (código %s)", rc)
    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
