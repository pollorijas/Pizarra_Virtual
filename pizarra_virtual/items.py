"""Elementos dibujados (modelo vectorial usado para deshacer/rehacer y re-renderizar)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .tools import BrushType, Tool


@dataclass
class StrokeItem:
    """Trazo a mano alzada. Cada punto guarda (x, y, ancho) en coordenadas lógicas."""

    tool: Tool
    rgba: tuple[int, int, int, int]
    size: float
    opacity: float = 1.0
    brush: BrushType = BrushType.HARD
    seed: int = 0
    points: list[tuple[float, float, float]] = field(default_factory=list)


@dataclass
class ShapeItem:
    """Figura definida por el punto inicial y final del arrastre."""

    tool: Tool
    rgba: tuple[int, int, int, int]
    size: float
    opacity: float
    x1: float
    y1: float
    x2: float
    y2: float
    filled: bool = False


@dataclass
class TextItem:
    """Texto escrito con el teclado; (x, y) es la esquina superior izquierda."""

    rgba: tuple[int, int, int, int]
    size: float  # tamaño de letra en píxeles
    opacity: float
    x: float
    y: float
    text: str = ""
    bold: bool = False
    # Identificador estable: las ediciones posteriores (TextEditItem) se refieren a él.
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class TextEditItem:
    """Edición de un texto ya escrito: sustituye (en su mismo lugar) al texto con ese ``uid``.

    Se guarda en el historial como un paso más, así deshacer recupera la versión anterior.
    Si el texto nuevo queda vacío, el texto desaparece.
    """

    uid: str
    text: TextItem


@dataclass
class ClearItem:
    """Borrado completo del lienzo (se puede deshacer)."""


Item = StrokeItem | ShapeItem | TextItem | TextEditItem | ClearItem


def resolve_items(items, exclude_uid: str | None = None) -> list:
    """Elementos que hay que dibujar, en orden, con las ediciones de texto ya aplicadas.

    Cada TextEditItem sustituye a la versión vigente de su texto en la posición original
    (así se respeta el orden respecto a la goma y al resto de trazos). ``exclude_uid`` oculta
    un texto (el que se está editando, que se dibuja aparte).
    """
    out: list = []
    for item in items:
        if isinstance(item, TextEditItem):
            for i in range(len(out) - 1, -1, -1):
                o = out[i]
                if isinstance(o, TextItem) and o.uid == item.uid:
                    out[i] = item.text
                    break
        else:
            out.append(item)
    return [o for o in out if not (isinstance(o, TextItem) and (not o.text.strip() or o.uid == exclude_uid))]
