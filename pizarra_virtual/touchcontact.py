"""Tamaño real del contacto de cada toque en Windows (para borrar con la palma).

Qt no transmite el tamaño del contacto de los toques en Windows (lo deja en 1×1), así que
se lee directamente: al llegar WM_POINTERDOWN o WM_POINTERUPDATE de un toque se consulta
GetPointerTouchInfo y se guarda el ancho de la zona de contacto (rcContact) en píxeles físicos. La pizarra lo
consulta al empezar el trazo.
"""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

from .winutil import IS_WINDOWS

log = logging.getLogger(__name__)

WM_POINTERUPDATE = 0x0245
WM_POINTERDOWN = 0x0246
WM_POINTERUP = 0x0247
PT_TOUCH = 2
TOUCH_MASK_CONTACTAREA = 0x1
RECENT_S = 0.5  # el dato vale para el toque que empieza ahora (no para uno antiguo)

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _POINTER_INFO(ctypes.Structure):  # noqa: N801
        _fields_ = [("pointerType", ctypes.c_uint32), ("pointerId", ctypes.c_uint32),
                    ("frameId", ctypes.c_uint32), ("pointerFlags", ctypes.c_uint32),
                    ("sourceDevice", wintypes.HANDLE), ("hwndTarget", wintypes.HWND),
                    ("ptPixelLocation", wintypes.POINT), ("ptHimetricLocation", wintypes.POINT),
                    ("ptPixelLocationRaw", wintypes.POINT), ("ptHimetricLocationRaw", wintypes.POINT),
                    ("dwTime", wintypes.DWORD), ("historyCount", ctypes.c_uint32),
                    ("InputData", ctypes.c_int32), ("dwKeyStates", wintypes.DWORD),
                    ("PerformanceCount", ctypes.c_uint64), ("ButtonChangeType", ctypes.c_int)]

    class _POINTER_TOUCH_INFO(ctypes.Structure):  # noqa: N801
        _fields_ = [("pointerInfo", _POINTER_INFO), ("touchFlags", ctypes.c_uint32),
                    ("touchMask", ctypes.c_uint32), ("rcContact", wintypes.RECT),
                    ("rcContactRaw", wintypes.RECT), ("orientation", ctypes.c_uint32),
                    ("pressure", ctypes.c_uint32)]

    _user32 = ctypes.windll.user32
    _user32.GetPointerType.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]  # (_prune)
    _user32.GetPointerTouchInfo.argtypes = [ctypes.c_uint32, ctypes.POINTER(_POINTER_TOUCH_INFO)]


class TouchContacts(QAbstractNativeEventFilter):
    """Guarda el tamaño de cada toque activo (por identificador de puntero de Windows)."""

    def __init__(self):
        super().__init__()
        self.sizes: dict[int, float] = {}  # pid -> ancho del contacto (píxeles físicos)
        self.when = 0.0  # cuándo cambió por última vez

    def set(self, pid: int, size: float) -> None:
        self.sizes[pid] = size
        self.when = time.monotonic()

    def up(self, pid: int) -> None:
        self.sizes.pop(pid, None)

    def recent_size(self) -> float:
        """Tamaño del toque, solo si hay UN único contacto: con varios no se sabe cuál es cuál
        (p. ej. un dedo que escribe y la mano que se apoya después) y no se adivina."""
        if len(self.sizes) != 1 or time.monotonic() - self.when > RECENT_S:
            return 0.0
        return next(iter(self.sizes.values()))

    def _prune(self) -> None:
        """Olvida punteros que ya no existen (por si se perdió su WM_POINTERUP)."""
        kind = ctypes.c_uint32()
        for pid in list(self.sizes):
            if not _user32.GetPointerType(pid, ctypes.byref(kind)):
                self.sizes.pop(pid, None)

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (API de Qt)
        try:
            et = bytes(event_type.data()) if hasattr(event_type, "data") else bytes(event_type)
            if et != b"windows_generic_MSG":
                return False, 0
            msg = wintypes.MSG.from_address(int(message))
            m = msg.message
            if m not in (WM_POINTERDOWN, WM_POINTERUPDATE, WM_POINTERUP):
                return False, 0
            pid = int(msg.wParam) & 0xFFFF
            if m == WM_POINTERUP:
                self.up(pid)
            elif m == WM_POINTERDOWN or pid in self.sizes:  # (ratón y lápiz: no se siguen)
                info = _POINTER_TOUCH_INFO()  # solo lo rellena si el puntero es un toque
                if _user32.GetPointerTouchInfo(pid, ctypes.byref(info)) \
                        and info.pointerInfo.pointerType == PT_TOUCH:
                    r = info.rcContact
                    size = float(max(r.right - r.left, r.bottom - r.top)) \
                        if info.touchMask & TOUCH_MASK_CONTACTAREA else 0.0
                    if m == WM_POINTERDOWN and self.sizes:
                        self._prune()
                    self.set(pid, size)
        except Exception:  # pragma: no cover
            log.exception("Error leyendo el contacto táctil")
        return False, 0


def install() -> TouchContacts | None:
    if not IS_WINDOWS:
        return None
    f = TouchContacts()
    QCoreApplication.instance().installNativeEventFilter(f)
    return f


def uninstall(f: TouchContacts | None) -> None:
    if f is not None and QCoreApplication.instance() is not None:
        QCoreApplication.instance().removeNativeEventFilter(f)
