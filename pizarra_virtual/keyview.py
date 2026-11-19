"""Mostrar en pantalla las teclas pulsadas (atajos), para enseñar a usar el teclado.

Se consulta el estado del teclado (no se instala ningún gancho del sistema) unas 60 veces
por segundo mientras la opción está activa. Por privacidad solo se muestran los atajos
(combinaciones con Ctrl, Alt o Win) y las teclas especiales (Intro, Esc, Tab, flechas,
F1…F12, Supr…): nunca el texto que se escribe, que podría ser una contraseña.
"""
from __future__ import annotations

VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_RMENU = 0xA5  # Alt derecha (AltGr en teclados españoles: escribe @, #, €…)
VK_LWIN, VK_RWIN = 0x5B, 0x5C
MODIFIERS = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_RMENU, VK_LWIN, VK_RWIN)

SPECIAL = {
    0x08: "Retroceso", 0x09: "Tab", 0x0D: "Intro", 0x1B: "Esc", 0x21: "RePág", 0x22: "AvPág",
    0x23: "Fin", 0x24: "Inicio", 0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓", 0x2C: "Impr Pant",
    0x2D: "Insert", 0x2E: "Supr",
    **{0x70 + i: f"F{i + 1}" for i in range(12)},
}
# Teclas que escriben (solo se muestran dentro de un atajo)
TYPING = {
    0x20: "Espacio",
    **{0x30 + i: str(i) for i in range(10)},
    **{0x41 + i: chr(0x41 + i) for i in range(26)},
    **{0x60 + i: f"Num {i}" for i in range(10)},
    0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num -", 0x6E: "Num .", 0x6F: "Num /",
    0xBB: "+", 0xBC: ",", 0xBD: "-", 0xBE: ".",
}
KEYS = tuple(MODIFIERS) + tuple(SPECIAL) + tuple(TYPING)


class KeyWatcher:
    """Convierte el conjunto de teclas pulsadas en cada consulta en textos como «Ctrl + C»."""

    def __init__(self):
        self._prev: set[int] = set()
        self._win_alone = False

    def reset(self) -> None:
        self._prev = set()
        self._win_alone = False

    def update(self, pressed: set[int]) -> list[str]:
        new = pressed - self._prev
        released = self._prev - pressed
        self._prev = set(pressed)
        win = bool(pressed & {VK_LWIN, VK_RWIN})
        out: list[str] = []
        if new & {VK_LWIN, VK_RWIN} and not (pressed - set(MODIFIERS)):
            self._win_alone = True
        for vk in sorted(new):
            if vk in MODIFIERS:
                continue
            self._win_alone = False
            ctrl = VK_CONTROL in pressed
            alt = VK_MENU in pressed
            if VK_RMENU in pressed:  # AltGr (= Ctrl + Alt): se está escribiendo un carácter
                ctrl = alt = False
            shift = VK_SHIFT in pressed
            name = SPECIAL.get(vk) or TYPING.get(vk)
            if name is None:
                continue
            if not (ctrl or alt or win) and vk not in SPECIAL:
                continue  # texto que se escribe: no se muestra
            parts = [m for m, on in (("Win", win), ("Ctrl", ctrl), ("Alt", alt), ("Mayús", shift)) if on]
            out.append(" + ".join(parts + [name]))
        if released & {VK_LWIN, VK_RWIN} and not win:
            if self._win_alone:
                out.append("Win")
            self._win_alone = False
        return out


__all__ = ["KeyWatcher", "KEYS"]
