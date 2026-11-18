"""Elementos dibujados (modelo vectorial usado para deshacer/rehacer y re-renderizar)."""
from __future__ import annotations

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


@dataclass
class ClearItem:
    """Borrado completo del lienzo (se puede deshacer)."""


Item = StrokeItem | ShapeItem | TextItem | ClearItem
