"""Elementos dibujados (modelo vectorial usado para deshacer/rehacer y re-renderizar)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace

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
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    # Gomas que «viajan» con el elemento al moverlo (las calcula resolve_items; no se guardan)
    mask: list = field(default_factory=list, compare=False, repr=False)


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
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    # Gomas que «viajan» con el elemento al moverlo (las calcula resolve_items; no se guardan)
    mask: list = field(default_factory=list, compare=False, repr=False)


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
    # Identificador estable: las ediciones posteriores (TextEditItem, mover…) se refieren a él.
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    # Gomas que «viajan» con el elemento al moverlo (las calcula resolve_items; no se guardan)
    mask: list = field(default_factory=list, compare=False, repr=False)


@dataclass
class TextEditItem:
    """Edición de un texto ya escrito: sustituye (en su mismo lugar) al texto con ese ``uid``.

    Se guarda en el historial como un paso más, así deshacer recupera la versión anterior.
    Si el texto nuevo queda vacío, el texto desaparece.
    """

    uid: str
    text: TextItem


@dataclass
class StampItem:
    """Sello (✔, ✘, estrella, carita, número, interrogación) centrado en (x, y)."""

    kind: str
    rgba: tuple[int, int, int, int]  # se usa en el sello de número
    size: float  # diámetro en píxeles lógicos
    opacity: float
    x: float
    y: float
    label: str = ""  # número del sello «number»
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    # Gomas que «viajan» con el elemento al moverlo (las calcula resolve_items; no se guardan)
    mask: list = field(default_factory=list, compare=False, repr=False)


@dataclass
class ImageItem:
    """Imagen pegada (PNG) que ocupa el rectángulo (x, y, w, h) en píxeles lógicos."""

    data: bytes  # PNG
    x: float
    y: float
    w: float
    h: float
    opacity: float = 1.0
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    # Gomas que «viajan» con el elemento al moverlo (las calcula resolve_items; no se guardan)
    mask: list = field(default_factory=list, compare=False, repr=False)


@dataclass
class TransformItem:
    """Mover y/o escalar elementos ya dibujados (herramienta Seleccionar).

    Escala ``scale`` respecto al punto (ox, oy) y después desplaza (dx, dy). El elemento movido
    pasa a estar delante de todo y se lleva consigo las partes que tenía borradas con la goma.
    """

    uids: list
    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    ox: float = 0.0
    oy: float = 0.0


@dataclass
class DeleteItem:
    """Eliminar elementos seleccionados (se puede deshacer)."""

    uids: list


@dataclass
class DuplicateItem:
    """Copias de elementos (``new_uids[i]`` es la copia de ``uids[i]``), desplazadas (dx, dy)."""

    uids: list
    new_uids: list
    dx: float = 24.0
    dy: float = 24.0


@dataclass
class GroupItem:
    """Varios elementos que se añaden y se deshacen juntos (p. ej. una plantilla).

    Sus textos se pueden editar después uno a uno (TextEditItem).
    """

    items: list = field(default_factory=list)


@dataclass
class ClearItem:
    """Borrado completo del lienzo (se puede deshacer)."""


Item = (StrokeItem | ShapeItem | TextItem | TextEditItem | StampItem | ImageItem | GroupItem | ClearItem
        | TransformItem | DeleteItem | DuplicateItem)
DRAWABLE = (StrokeItem, ShapeItem, TextItem, StampItem, ImageItem)


def is_eraser_item(item) -> bool:
    return isinstance(item, StrokeItem) and item.tool == Tool.ERASER


def transformed(item, dx: float = 0.0, dy: float = 0.0, scale: float = 1.0, ox: float = 0.0, oy: float = 0.0):
    """Copia del elemento escalada respecto a (ox, oy) y desplazada (dx, dy). Conserva el uid."""
    def f(x, y):
        return ox + (x - ox) * scale + dx, oy + (y - oy) * scale + dy

    mask = [transformed(m, dx, dy, scale, ox, oy) for m in getattr(item, "mask", [])]
    if isinstance(item, StrokeItem):
        pts = [(*f(x, y), w * scale) for x, y, w in item.points]
        return replace(item, points=pts, size=item.size * scale, mask=mask)
    if isinstance(item, ShapeItem):
        x1, y1 = f(item.x1, item.y1)
        x2, y2 = f(item.x2, item.y2)
        return replace(item, x1=x1, y1=y1, x2=x2, y2=y2, size=item.size * scale, mask=mask)
    if isinstance(item, (TextItem, StampItem)):
        x, y = f(item.x, item.y)
        return replace(item, x=x, y=y, size=item.size * scale, mask=mask)
    if isinstance(item, ImageItem):
        x, y = f(item.x, item.y)
        return replace(item, x=x, y=y, w=item.w * scale, h=item.h * scale, mask=mask)
    return item


def flatten(items) -> list:
    """Despliega los grupos (plantillas) en sus elementos, en orden."""
    out = []
    for item in items:
        if isinstance(item, GroupItem):
            out.extend(flatten(item.items))
        else:
            out.append(item)
    return out


def resolve_items(items, exclude_uid=None) -> list:
    """Elementos que hay que dibujar, en orden, con las ediciones ya aplicadas.

    - TextEditItem sustituye a su texto en el mismo lugar (respeta el orden con la goma).
    - TransformItem lleva los elementos al final (delante de todo), movidos/escalados, y cada
      uno se lleva en ``mask`` las gomas que lo afectaban: lo borrado sigue borrado.
    - DuplicateItem añade copias (con las mismas partes borradas) al final.
    - DeleteItem los quita.
    ``exclude_uid`` (un uid o un conjunto) oculta elementos que se dibujan aparte (en edición).
    No modifica los elementos del historial: los cambios se hacen sobre copias.
    """
    out: list = []

    def find(uid):
        for i in range(len(out) - 1, -1, -1):
            if getattr(out[i], "uid", None) == uid:
                return i
        return -1

    def carried(idx):
        """Gomas que afectan al elemento out[idx] (las suyas y las posteriores), o None si
        después hubo un «Borrar todo» (el elemento ya no se ve)."""
        later = out[idx + 1:]
        if any(isinstance(i, ClearItem) for i in later):
            return None
        return list(getattr(out[idx], "mask", [])) + [i for i in later if is_eraser_item(i)]

    for item in flatten(items):
        if isinstance(item, TextEditItem):
            i = find(item.uid)
            if i >= 0:
                out[i] = replace(item.text, mask=list(getattr(out[i], "mask", [])))
        elif isinstance(item, (TransformItem, DuplicateItem)):
            idxs = sorted(i for i in (find(u) for u in item.uids) if i >= 0)
            moved = []
            for i in idxs:
                mask = carried(i)
                if mask is None:
                    continue
                src = replace(out[i], mask=mask)
                if isinstance(item, TransformItem):
                    moved.append((i, transformed(src, item.dx, item.dy, item.scale, item.ox, item.oy)))
                else:
                    k = item.uids.index(out[i].uid)
                    copy = transformed(src, item.dx, item.dy)
                    copy.uid = item.new_uids[k] if k < len(item.new_uids) else uuid.uuid4().hex
                    moved.append((None, copy))
            for i, _ in sorted((m for m in moved if m[0] is not None), key=lambda m: -m[0]):
                del out[i]
            out.extend(new for _, new in moved)
        elif isinstance(item, DeleteItem):
            gone = set(item.uids)
            out = [o for o in out if getattr(o, "uid", None) not in gone]
        else:
            out.append(item)
    hidden = {exclude_uid} if isinstance(exclude_uid, str) else set(exclude_uid or ())
    return [o for o in out if not ((isinstance(o, TextItem) and not o.text.strip())
                                   or getattr(o, "uid", None) in hidden)]
