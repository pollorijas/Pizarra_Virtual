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
    _user32.GetPointerType.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    _user32.GetPointerTouchInfo.argtypes = [ctypes.c_uint32, ctypes.POINTER(_POINTER_TOUCH_INFO)]


class TouchContacts(QAbstractNativeEventFilter):
    def __init__(self):
        super().__init__()
        self.size = 0.0  # ancho del último contacto (píxeles físicos)
        self.when = 0.0
        self.downs = 0  # toques vistos (diagnóstico)
        self.error = ""

    def recent_size(self) -> float:
        return self.size if time.monotonic() - self.when <= RECENT_S else 0.0

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (API de Qt)
        try:
            et = bytes(event_type.data()) if hasattr(event_type, "data") else bytes(event_type)
            if et == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message in (WM_POINTERDOWN, WM_POINTERUPDATE):
                    self.downs += msg.message == WM_POINTERDOWN
                    pid = int(msg.wParam) & 0xFFFF
                    kind = ctypes.c_uint32()
                    if _user32.GetPointerType(pid, ctypes.byref(kind)) and kind.value == PT_TOUCH:
                        info = _POINTER_TOUCH_INFO()
                        if _user32.GetPointerTouchInfo(pid, ctypes.byref(info)) \
                                and info.touchMask & TOUCH_MASK_CONTACTAREA:
                            r = info.rcContact
                            self.size = float(max(r.right - r.left, r.bottom - r.top))
                            self.when = time.monotonic()
                        else:
                            self.error = f"GetPointerTouchInfo: {ctypes.GetLastError()} mask={info.touchMask}"
                    else:
                        self.error = f"tipo {kind.value}"
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
