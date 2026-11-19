"""Páginas de la pizarra, guardado/apertura de sesiones (.pizarra) y exportación a PDF."""
from __future__ import annotations

import base64
import gzip
import json
import math
import os
from dataclasses import dataclass, field

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter

from . import __version__, render
from .items import (
    ClearItem, DeleteItem, DuplicateItem, GroupItem, ImageItem, ShapeItem, StampItem, StrokeItem, TextEditItem,
    TextItem, TransformItem, resolve_items,
)
from .tools import BACKGROUNDS, PATTERNS, BrushType, Tool

FILE_EXTENSION = ".pizarra"
FORMAT_VERSION = 1


@dataclass
class Page:
    """Una página: su historial (con la pantalla de cada elemento), rehacer, fondo y pauta."""

    history: list = field(default_factory=list)
    redo: list = field(default_factory=list)
    background: str = "transparent"
    pattern: str = "none"

    def has_content(self) -> bool:
        return any(not isinstance(item, ClearItem) for _, item in self.history)

    def items_for(self, key: str, exclude_uid: str | None = None) -> list:
        """Lo que se dibuja en la pantalla ``key`` (con las ediciones de texto aplicadas)."""
        return resolve_items([item for k, item in self.history if k is None or k == key], exclude_uid)


# ---------------------------------------------------------------------- serialización


def item_to_dict(item) -> dict:
    d = _item_to_dict(item)
    uid = getattr(item, "uid", None)
    if uid and d.get("type") not in ("text_edit",):
        d["uid"] = uid  # lo usan las ediciones posteriores (mover, eliminar, editar texto…)
    return d


def _item_to_dict(item) -> dict:
    if isinstance(item, StrokeItem):
        return {"type": "stroke", "tool": item.tool.value, "rgba": list(item.rgba), "size": item.size,
                "opacity": item.opacity, "brush": item.brush.value, "seed": item.seed,
                "points": [[x, y, w] for x, y, w in item.points]}  # exactos: se re-dibuja idéntico
    if isinstance(item, ShapeItem):
        return {"type": "shape", "tool": item.tool.value, "rgba": list(item.rgba), "size": item.size,
                "opacity": item.opacity, "x1": item.x1, "y1": item.y1, "x2": item.x2, "y2": item.y2,
                "filled": item.filled}
    if isinstance(item, TextItem):
        return {"type": "text", "rgba": list(item.rgba), "size": item.size, "opacity": item.opacity,
                "x": item.x, "y": item.y, "text": item.text, "bold": item.bold}
    if isinstance(item, StampItem):
        return {"type": "stamp", "kind": item.kind, "rgba": list(item.rgba), "size": item.size,
                "opacity": item.opacity, "x": item.x, "y": item.y, "label": item.label}
    if isinstance(item, ImageItem):
        return {"type": "image", "png": base64.b64encode(item.data).decode("ascii"), "x": item.x, "y": item.y,
                "w": item.w, "h": item.h, "opacity": item.opacity}
    if isinstance(item, GroupItem):
        return {"type": "group", "items": [item_to_dict(i) for i in item.items]}
    if isinstance(item, TextEditItem):
        return {"type": "text_edit", "uid": item.uid, "text": item_to_dict(item.text)}
    if isinstance(item, TransformItem):
        return {"type": "transform", "uids": list(item.uids), "dx": item.dx, "dy": item.dy,
                "scale": item.scale, "ox": item.ox, "oy": item.oy}
    if isinstance(item, DeleteItem):
        return {"type": "delete", "uids": list(item.uids)}
    if isinstance(item, DuplicateItem):
        return {"type": "duplicate", "uids": list(item.uids), "new_uids": list(item.new_uids),
                "dx": item.dx, "dy": item.dy}
    if isinstance(item, ClearItem):
        return {"type": "clear"}
    raise TypeError(f"Elemento desconocido: {item!r}")


def item_from_dict(d: dict):
    item = _item_from_dict(d)
    # Las sesiones anteriores a la 1.4 no guardan uid en trazos, figuras ni sellos: se genera uno.
    if d.get("uid") and hasattr(item, "uid") and d.get("type") != "text_edit":
        item.uid = str(d["uid"])
    return item


def _item_from_dict(d: dict):
    t = d.get("type")
    if t == "stroke":
        return StrokeItem(Tool(d["tool"]), tuple(d["rgba"]), float(d["size"]), float(d["opacity"]),
                          BrushType(d.get("brush", "hard")), int(d.get("seed", 0)),
                          [tuple(map(float, pt)) for pt in d["points"]])
    if t == "shape":
        return ShapeItem(Tool(d["tool"]), tuple(d["rgba"]), float(d["size"]), float(d["opacity"]),
                         float(d["x1"]), float(d["y1"]), float(d["x2"]), float(d["y2"]), bool(d.get("filled")))
    if t == "text":
        return TextItem(tuple(d["rgba"]), float(d["size"]), float(d["opacity"]), float(d["x"]), float(d["y"]),
                        str(d.get("text", "")), bool(d.get("bold")))
    if t == "stamp":
        return StampItem(str(d["kind"]), tuple(d["rgba"]), float(d["size"]), float(d["opacity"]),
                         float(d["x"]), float(d["y"]), str(d.get("label", "")))
    if t == "image":
        return ImageItem(base64.b64decode(d["png"]), float(d["x"]), float(d["y"]), float(d["w"]), float(d["h"]),
                         float(d.get("opacity", 1.0)))
    if t == "group":
        return GroupItem([item_from_dict(i) for i in d.get("items", [])])
    if t == "text_edit":
        text = item_from_dict(d["text"])
        text.uid = str(d["uid"])
        return TextEditItem(str(d["uid"]), text)
    if t == "transform":
        return TransformItem([str(u) for u in d["uids"]], float(d.get("dx", 0)), float(d.get("dy", 0)),
                             float(d.get("scale", 1)), float(d.get("ox", 0)), float(d.get("oy", 0)))
    if t == "delete":
        return DeleteItem([str(u) for u in d["uids"]])
    if t == "duplicate":
        return DuplicateItem([str(u) for u in d["uids"]], [str(u) for u in d["new_uids"]],
                             float(d.get("dx", 24)), float(d.get("dy", 24)))
    if t == "clear":
        return ClearItem()
    raise ValueError(f"Tipo de elemento desconocido: {t!r}")


def session_to_dict(pages: list[Page], screens: list[str]) -> dict:
    return {
        "app": "PizarraVirtual",
        "format": FORMAT_VERSION,
        "version": __version__,
        "screens": screens,
        "pages": [{"background": pg.background, "pattern": pg.pattern,
                   "items": [{"screen": key, "item": item_to_dict(item)} for key, item in pg.history]}
                  for pg in pages],
    }


def session_from_dict(data: dict, current_screens: list[str]) -> list[Page]:
    """Reconstruye las páginas. Las pantallas guardadas que no existen en este equipo se
    asignan por orden a las actuales (y si sobran, a la principal)."""
    if data.get("app") != "PizarraVirtual" or not isinstance(data.get("pages"), list):
        raise ValueError("El archivo no es una sesión de Pizarra Virtual.")
    if int(data.get("format", 0)) > FORMAT_VERSION:
        raise ValueError("La sesión se creó con una versión más nueva de Pizarra Virtual.")
    saved = list(data.get("screens") or [])
    mapping: dict[str, str] = {}
    if current_screens:
        for i, key in enumerate(saved):
            if key in current_screens:
                mapping[key] = key
            else:
                mapping[key] = current_screens[i] if i < len(current_screens) else current_screens[0]
    pages = []
    for pd in data["pages"]:
        bg = pd.get("background", "transparent")
        pat = pd.get("pattern", "none")
        page = Page(background=bg if bg in BACKGROUNDS else "transparent",
                    pattern=pat if pat in PATTERNS else "none")
        for entry in pd.get("items", []):
            key = entry.get("screen")
            if key is not None:
                key = mapping.get(key, current_screens[0] if current_screens else key)
            page.history.append((key, item_from_dict(entry["item"])))
        pages.append(page)
    return pages or [Page()]


def save_session(path: str, pages: list[Page], screens: list[str]) -> str:
    if not path.lower().endswith(FILE_EXTENSION):
        path += FILE_EXTENSION
    data = json.dumps(session_to_dict(pages, screens), ensure_ascii=False, separators=(",", ":"))
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)  # escritura atómica: nunca deja un archivo a medias
    return path


def load_session(path: str, current_screens: list[str]) -> list[Page]:
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return session_from_dict(json.loads(raw.decode("utf-8")), current_screens)


# ---------------------------------------------------------------------- imágenes y PDF


def render_page(page: Page, items, width: int, height: int, scale: float = 2.0,
                paper_for_transparent: QColor | None = QColor(255, 255, 255)) -> QImage:
    """Imagen de una página (fondo + pauta + dibujos) a ``scale`` píxeles por píxel lógico.

    Con fondo transparente u oscurecido se usa papel blanco (el escritorio no forma parte
    de la página), salvo que ``paper_for_transparent`` sea None.
    """
    size_w, size_h = max(1, math.ceil(width * scale)), max(1, math.ceil(height * scale))
    paper_bg = page.background if page.background in render.PAPER_COLORS else "white"
    paper = render.PAPER_COLORS.get(page.background, paper_for_transparent)
    out = QImage(size_w, size_h, QImage.Format.Format_ARGB32_Premultiplied)
    out.setDevicePixelRatio(scale)
    out.fill(paper if paper is not None else QColor(0, 0, 0, 0))
    canvas = QImage(size_w, size_h, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.setDevicePixelRatio(scale)
    canvas.fill(Qt.GlobalColor.transparent)
    layer = QImage(canvas)
    for item in items:
        render.apply_item_to_canvas(canvas, layer, item)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    render.draw_pattern(p, width, height, page.pattern, paper_bg)
    p.drawImage(QPointF(0, 0), canvas)
    p.end()
    return out


def export_pdf(path: str, images: list[QImage], title: str = "Pizarra Virtual") -> str:
    """Un PDF A4 apaisado con una imagen por página, centrada y con número de página."""
    if not path.lower().endswith(".pdf"):
        path += ".pdf"
    writer = QPdfWriter(path)
    writer.setTitle(title)
    writer.setCreator(f"Pizarra Virtual {__version__}")
    writer.setResolution(150)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Landscape,
                                     QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter))
    p = QPainter(writer)
    if not p.isActive():
        raise OSError(f"No se pudo crear el PDF en {path}")
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    area = QRectF(writer.pageLayout().paintRectPixels(writer.resolution()))
    area.moveTo(0, 0)
    footer_h = 40.0
    font = QFont()
    font.setPointSizeF(9)
    for i, img in enumerate(images):
        if i:
            writer.newPage()
        box = QRectF(0, 0, area.width(), area.height() - footer_h)
        iw, ih = img.width(), img.height()
        s = min(box.width() / iw, box.height() / ih)
        target = QRectF(0, 0, iw * s, ih * s)
        target.moveCenter(box.center())
        p.drawImage(target, img, QRectF(0, 0, iw, ih))
        p.setPen(QColor(150, 150, 150))
        p.drawRect(target)
        p.setFont(font)
        p.setPen(QColor(90, 90, 90))
        p.drawText(QRectF(0, area.height() - footer_h + 8, area.width(), footer_h - 8),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                   f"{title}  ·  Página {i + 1} de {len(images)}")
    p.end()
    return path


__all__ = ["Page", "FILE_EXTENSION", "save_session", "load_session", "render_page", "export_pdf",
           "item_to_dict", "item_from_dict"]
