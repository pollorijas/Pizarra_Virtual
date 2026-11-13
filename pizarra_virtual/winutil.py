"""Utilidades específicas de Windows (via ctypes). En otros sistemas son no-ops."""
from __future__ import annotations

import logging
import os
import subprocess
import sys

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        _GetWindowLong = _user32.GetWindowLongPtrW
        _SetWindowLong = _user32.SetWindowLongPtrW
        _GetWindowLong.restype = ctypes.c_ssize_t
        _SetWindowLong.restype = ctypes.c_ssize_t
        _SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    else:  # pragma: no cover - Windows de 32 bits
        _GetWindowLong = _user32.GetWindowLongW
        _SetWindowLong = _user32.SetWindowLongW
        _GetWindowLong.restype = ctypes.c_long
        _SetWindowLong.restype = ctypes.c_long
        _SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]


def set_click_through(hwnd: int, enabled: bool) -> None:
    """Refuerza WS_EX_TRANSPARENT en una ventana *layered* (Qt ya lo hace normalmente).

    Solo se toca el bit si la ventana ya es layered: añadir WS_EX_LAYERED a una
    ventana que Qt no pinta como layered la volvería invisible.
    """
    if not IS_WINDOWS or not hwnd:
        return
    try:
        style = _GetWindowLong(hwnd, GWL_EXSTYLE)
        if not style & WS_EX_LAYERED:
            return
        new = (style | WS_EX_TRANSPARENT) if enabled else (style & ~WS_EX_TRANSPARENT)
        if new != style:
            _SetWindowLong(hwnd, GWL_EXSTYLE, new)
    except Exception:  # pragma: no cover
        log.exception("No se pudo cambiar WS_EX_TRANSPARENT")


def set_app_user_model_id(app_id: str) -> None:
    """Agrupa la app correctamente en la barra de tareas / área de notificación."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:  # pragma: no cover
        log.debug("SetCurrentProcessExplicitAppUserModelID no disponible")


def open_folder(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
        return
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):  # pragma: no cover
        subprocess.Popen(["xdg-open", path])  # noqa: S603,S607
