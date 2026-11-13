"""Definición de herramientas, tipos de pincel y sus valores por defecto."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tool(str, Enum):
    BRUSH = "brush"
    PENCIL = "pencil"
    PEN = "pen"
    HIGHLIGHTER = "highlighter"
    ERASER = "eraser"
    RECT = "rect"
    ELLIPSE = "ellipse"
    TRIANGLE = "triangle"
    LINE = "line"
    ARROW = "arrow"


FREEHAND_TOOLS = (Tool.BRUSH, Tool.PENCIL, Tool.PEN, Tool.HIGHLIGHTER, Tool.ERASER)
SHAPE_TOOLS = (Tool.RECT, Tool.ELLIPSE, Tool.TRIANGLE, Tool.LINE, Tool.ARROW)
FILLABLE_SHAPES = (Tool.RECT, Tool.ELLIPSE, Tool.TRIANGLE)


class BrushType(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    AIRBRUSH = "airbrush"
    CALLIGRAPHY = "calligraphy"


BRUSH_LABELS = {
    BrushType.HARD: "Duro",
    BrushType.SOFT: "Suave",
    BrushType.AIRBRUSH: "Aerógrafo",
    BrushType.CALLIGRAPHY: "Caligráfico",
}


@dataclass(frozen=True)
class ToolSpec:
    label: str
    key: str            # atajo de teclado local
    icon: str
    default_size: int
    min_size: int
    max_size: int
    default_opacity: int  # porcentaje
    has_opacity: bool = True


TOOL_SPECS: dict[Tool, ToolSpec] = {
    Tool.BRUSH: ToolSpec("Pincel", "1", "brush", 10, 1, 150, 100),
    Tool.PENCIL: ToolSpec("Lápiz", "2", "pencil", 2, 1, 8, 100),
    Tool.PEN: ToolSpec("Pluma", "3", "pen", 6, 1, 40, 100),
    Tool.HIGHLIGHTER: ToolSpec("Destacador", "4", "highlighter", 24, 6, 90, 40),
    Tool.ERASER: ToolSpec("Goma de borrar", "5", "eraser", 30, 4, 250, 100, has_opacity=False),
    Tool.RECT: ToolSpec("Rectángulo / cuadrado", "6", "rect", 4, 1, 40, 100),
    Tool.ELLIPSE: ToolSpec("Elipse / círculo", "7", "ellipse", 4, 1, 40, 100),
    Tool.TRIANGLE: ToolSpec("Triángulo", "8", "triangle", 4, 1, 40, 100),
    Tool.LINE: ToolSpec("Línea", "9", "line", 4, 1, 40, 100),
    Tool.ARROW: ToolSpec("Flecha", "0", "arrow", 4, 1, 40, 100),
}

PALETTE = [
    "#000000", "#ffffff", "#9e9e9e", "#6d4c41",
    "#e53935", "#fb8c00", "#ffeb3b", "#43a047",
    "#00acc1", "#1e88e5", "#8e24aa", "#d81b60",
]
DEFAULT_COLOR = "#e53935"

# Fondos disponibles: clave -> etiqueta
BACKGROUNDS = {
    "transparent": "Transparente",
    "dim": "Oscurecer escritorio",
    "white": "Pizarra blanca",
    "chalk": "Pizarra verde",
}
