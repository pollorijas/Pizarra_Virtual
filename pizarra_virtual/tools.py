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
    TEXT = "text"
    LASER = "laser"
    RECT = "rect"
    ELLIPSE = "ellipse"
    TRIANGLE = "triangle"
    LINE = "line"
    ARROW = "arrow"
    # Figuras adicionales (botón «Más figuras»)
    PENTAGON = "pentagon"
    HEXAGON = "hexagon"
    OCTAGON = "octagon"
    DIAMOND = "diamond"
    STAR = "star"
    ROUNDED_RECT = "rounded_rect"
    AXES = "axes"
    DOUBLE_ARROW = "double_arrow"
    CURVED_ARROW = "curved_arrow"
    BRACE = "brace"
    # Sellos
    STAMP = "stamp"
    # Seleccionar y mover
    SELECT = "select"
    # Nota adhesiva y zona tapada (v1.5)
    NOTE = "note"
    COVER = "cover"


FREEHAND_TOOLS = (Tool.BRUSH, Tool.PENCIL, Tool.PEN, Tool.HIGHLIGHTER, Tool.ERASER)
EXTRA_SHAPES = (Tool.PENTAGON, Tool.HEXAGON, Tool.OCTAGON, Tool.DIAMOND, Tool.STAR, Tool.ROUNDED_RECT,
                Tool.AXES, Tool.DOUBLE_ARROW, Tool.CURVED_ARROW, Tool.BRACE)
SHAPE_TOOLS = (Tool.RECT, Tool.ELLIPSE, Tool.TRIANGLE, Tool.LINE, Tool.ARROW) + EXTRA_SHAPES
FILLABLE_SHAPES = (Tool.RECT, Tool.ELLIPSE, Tool.TRIANGLE, Tool.PENTAGON, Tool.HEXAGON, Tool.OCTAGON,
                   Tool.DIAMOND, Tool.STAR, Tool.ROUNDED_RECT)
# Figuras que se dibujan de un punto a otro (con Mayús: ángulos de 15°)
LINEAR_SHAPES = (Tool.LINE, Tool.ARROW, Tool.DOUBLE_ARROW, Tool.CURVED_ARROW)
# Herramientas con botón propio en la barra (el resto va en los menús «Más figuras» y «Sellos»)
MAIN_TOOLS = (Tool.BRUSH, Tool.PENCIL, Tool.PEN, Tool.HIGHLIGHTER, Tool.ERASER, Tool.TEXT, Tool.LASER,
              Tool.RECT, Tool.ELLIPSE, Tool.TRIANGLE, Tool.LINE, Tool.ARROW)
POLYGON_SIDES = {Tool.PENTAGON: 5, Tool.HEXAGON: 6, Tool.OCTAGON: 8}


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
    Tool.PEN: ToolSpec("Pluma", "3", "pen", 3, 1, 30, 100),
    Tool.HIGHLIGHTER: ToolSpec("Destacador", "4", "highlighter", 24, 6, 90, 40),
    Tool.ERASER: ToolSpec("Goma de borrar", "5", "eraser", 30, 4, 250, 100, has_opacity=False),
    Tool.TEXT: ToolSpec("Texto", "T", "text", 36, 10, 160, 100),
    Tool.LASER: ToolSpec("Puntero láser / tinta temporal", "L", "laser", 14, 6, 40, 100, has_opacity=False),
    Tool.RECT: ToolSpec("Rectángulo / cuadrado", "6", "rect", 4, 1, 40, 100),
    Tool.ELLIPSE: ToolSpec("Elipse / círculo", "7", "ellipse", 4, 1, 40, 100),
    Tool.TRIANGLE: ToolSpec("Triángulo", "8", "triangle", 4, 1, 40, 100),
    Tool.LINE: ToolSpec("Línea", "9", "line", 4, 1, 40, 100),
    Tool.ARROW: ToolSpec("Flecha", "0", "arrow", 4, 1, 40, 100),
    Tool.PENTAGON: ToolSpec("Pentágono", "P", "pentagon", 4, 1, 40, 100),
    Tool.HEXAGON: ToolSpec("Hexágono", "P", "hexagon", 4, 1, 40, 100),
    Tool.OCTAGON: ToolSpec("Octágono", "P", "octagon", 4, 1, 40, 100),
    Tool.DIAMOND: ToolSpec("Rombo", "D", "diamond", 4, 1, 40, 100),
    Tool.STAR: ToolSpec("Estrella", "E", "star", 4, 1, 40, 100),
    Tool.ROUNDED_RECT: ToolSpec("Rectángulo redondeado", "Q", "rounded_rect", 4, 1, 40, 100),
    Tool.AXES: ToolSpec("Ejes de coordenadas", "J", "axes", 3, 1, 20, 100),
    Tool.DOUBLE_ARROW: ToolSpec("Flecha doble", "W", "double_arrow", 4, 1, 40, 100),
    Tool.CURVED_ARROW: ToolSpec("Flecha curva", "U", "curved_arrow", 4, 1, 40, 100),
    Tool.BRACE: ToolSpec("Llave", "K", "brace", 4, 1, 40, 100),
    Tool.STAMP: ToolSpec("Sellos", "S", "stamp", 56, 20, 200, 100),
    Tool.SELECT: ToolSpec("Seleccionar y mover", "A", "select", 1, 1, 1, 100, has_opacity=False),
    Tool.NOTE: ToolSpec("Nota adhesiva", "O", "note", 28, 12, 96, 100, has_opacity=False),
    Tool.COVER: ToolSpec("Tapar zona", "H", "cover", 1, 1, 1, 100, has_opacity=False),
}
# Herramientas sin grosor ajustable
UNSIZED_TOOLS = (Tool.SELECT, Tool.COVER)

# Colores del papel de las notas adhesivas: clave -> (etiqueta, RGBA)
NOTE_COLORS = {
    "yellow": ("Amarilla", (255, 238, 128, 255)),
    "pink": ("Rosada", (255, 190, 214, 255)),
    "blue": ("Celeste", (176, 218, 255, 255)),
    "green": ("Verde", (196, 238, 170, 255)),
    "orange": ("Naranja", (255, 206, 140, 255)),
    "white": ("Blanca", (250, 250, 250, 255)),
}
NOTE_TEXT_RGBA = (38, 50, 56, 255)

# Lado desde el que se descubre la cortina: clave -> etiqueta
CURTAIN_SIDES = {
    "top": "Desde arriba",
    "bottom": "Desde abajo",
    "left": "Desde la izquierda",
    "right": "Desde la derecha",
}
# Trazos que la regla y el transportador guían (y con los que dibuja el compás)
GUIDED_TOOLS = (Tool.BRUSH, Tool.PENCIL, Tool.PEN, Tool.HIGHLIGHTER)
# Trazos a mano alzada que pueden convertirse en figuras perfectas («Reconocer formas»)
RECOGNIZABLE_TOOLS = (Tool.BRUSH, Tool.PENCIL, Tool.PEN)

# Sellos: clave -> etiqueta
STAMPS = {
    "check": "Correcto ✔",
    "cross": "Incorrecto ✘",
    "star": "Estrella",
    "smiley": "Carita feliz",
    "number": "Número (1, 2, 3…)",
    "question": "Pregunta ?",
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

# Pautas que se dibujan sobre el fondo: clave -> etiqueta
PATTERNS = {
    "none": "Sin pauta",
    "grid": "Cuadrícula",
    "mm": "Papel milimetrado",
    "ruled": "Hoja rayada",
    "calligraphy": "Pauta de caligrafía",
    "cartesian": "Plano cartesiano",
    "staff": "Pentagrama",
}
