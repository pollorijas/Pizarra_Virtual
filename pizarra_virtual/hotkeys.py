"""Atajos de teclado globales para Windows mediante RegisterHotKey.

Los atajos funcionan aunque la pizarra no tenga el foco (por ejemplo en modo
"ratón libre", cuando se está usando otra aplicación). En otros sistemas el
registro devuelve False y la app usa solo los atajos locales.
"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Qt, QTimer
from PySide6.QtWidgets import QWidget

from .winutil import IS_WINDOWS

log = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _user32.RegisterHotKey.restype = wintypes.BOOL
    _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.UnregisterHotKey.restype = wintypes.BOOL


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: "GlobalHotkeys"):
        super().__init__()
        self._owner = owner
        self._last = None

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (API de Qt)
        try:
            et = bytes(event_type.data()) if hasattr(event_type, "data") else bytes(event_type)
            if et == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    key = (int(msg.wParam), int(msg.time))
                    if key != self._last:  # evita doble entrega del mismo mensaje
                        self._last = key
                        self._owner._dispatch(int(msg.wParam))
                    return True, 0
        except Exception:  # pragma: no cover
            log.exception("Error procesando WM_HOTKEY")
        return False, 0


class GlobalHotkeys(QObject):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 0xB000
        self._hwnd = 0
        self._filter = None
        self._window = None
        if IS_WINDOWS:
            # Ventana nativa oculta que recibe los WM_HOTKEY.
            self._window = QWidget(None, Qt.WindowType.Tool)
            self._window.setWindowTitle("Pizarra Virtual - atajos")
            self._hwnd = int(self._window.winId())
            self._filter = _HotkeyFilter(self)
            QCoreApplication.instance().installNativeEventFilter(self._filter)

    @property
    def available(self) -> bool:
        return bool(self._hwnd)

    def register(self, modifiers: int, vk: int, callback: Callable[[], None]) -> bool:
        if not self._hwnd:
            return False
        hid = self._next_id
        self._next_id += 1
        ok = bool(_user32.RegisterHotKey(self._hwnd, hid, modifiers | MOD_NOREPEAT, vk))
        if ok:
            self._callbacks[hid] = callback
        else:
            log.warning("No se pudo registrar el atajo global (mods=%s, vk=%s)", modifiers, vk)
        return ok

    def unregister_all(self) -> None:
        if self._hwnd:
            for hid in list(self._callbacks):
                _user32.UnregisterHotKey(self._hwnd, hid)
        self._callbacks.clear()

    def _dispatch(self, hid: int) -> None:
        cb = self._callbacks.get(hid)
        if cb is not None:
            # Se sale del filtro nativo antes de ejecutar la acción.
            QTimer.singleShot(0, cb)
