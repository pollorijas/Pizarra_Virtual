"""Genera assets/pizarra.ico a partir del icono vectorial de la app (requiere Pillow).

Uso:  python tools/make_icon.py
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from pizarra_virtual.icons import app_icon_image  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    images = []
    for s in SIZES:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        app_icon_image(s).save(buf, "PNG")
        images.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "pizarra.ico")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    images[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    images[-1].save(out.replace(".ico", ".png"))
    print("Icono generado:", out)


if __name__ == "__main__":
    main()
