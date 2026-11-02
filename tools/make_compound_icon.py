"""Make the CompoundIME icons from the centaur archer drawing (tools/data/compound-icon.png).

  python tools/make_compound_icon.py <out-dir>
Writes
  compound_ime.ico          product icon (installer, Apps list, settings tool)
  compound_ime_langbar.ico  input-mode icon on the taskbar
  compound_ime-256.png      preview of the product icon
  compound_ime.svg          product icon as SVG (Linux; the 256 px picture inside)
  compound_ime_langbar-64.png  the input-mode icon as PNG (Linux)
Both icons are the black drawing on a light rounded square, so they read on dark and light
taskbars. The drawing's lines are thin for small icons, so each size thickens them first
(at 16 px a line is about 1.3 px wide instead of vanishing).
"""
import argparse
import base64
import io
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
LANGBAR_SIZES = (16, 20, 24, 32, 40, 48, 64)
INK = (17, 17, 17)
BADGE = (245, 245, 245, 255)
SOURCE = Path(__file__).with_name("data") / "compound-icon.png"
LINE = 11  # the drawing's line width in SOURCE pixels (1024 px picture)


def ink_mask():
    """The drawing as a mask (255 = ink), cropped to the drawing and made square."""
    gray = Image.open(SOURCE).convert("L")
    mask = gray.point(lambda v: 255 if v < 128 else 0)
    left, top, right, bottom = mask.getbbox()
    side = max(right - left, bottom - top)
    square = Image.new("L", (side, side), 0)
    square.paste(mask.crop((left, top, right, bottom)), ((side - (right - left)) // 2, (side - (bottom - top)) // 2))
    return square


def draw(size, mask, scale=8):
    """The icon at |size| px: a light rounded square with the drawing, lines thickened for small sizes."""
    s = size * scale
    inner = round(s * 0.80)
    drawing = mask.resize((inner, inner), Image.LANCZOS).point(lambda v: 255 if v >= 96 else 0)
    have = LINE * inner / mask.width
    want = (1.3 if size <= 24 else 1.1) * scale  # the thinnest line at |size|, in the 8x picture
    grow = int(round(want - have))
    if grow >= 2:
        drawing = drawing.filter(ImageFilter.MaxFilter(grow | 1))
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((scale // 2, scale // 2, s - scale // 2, s - scale // 2),
                                          radius=round(s * 0.19), fill=BADGE)
    ink = Image.new("RGBA", (inner, inner), INK + (255,))
    offset = (s - inner) // 2
    img.paste(ink, (offset, offset), drawing)
    return img.resize((size, size), Image.LANCZOS)


def svg(png):
    data = base64.b64encode(png).decode("ascii")
    return ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            'viewBox="0 0 256 256"><image width="256" height="256" '
            f'xlink:href="data:image/png;base64,{data}"/></svg>\n')


def save_ico(images, path):
    images[-1].save(path, sizes=[im.size for im in images], append_images=images[:-1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    mask = ink_mask()
    images = [draw(size, mask) for size in SIZES]
    images[-1].save(args.out / "compound_ime-256.png")
    save_ico(images, args.out / "compound_ime.ico")
    save_ico([draw(size, mask) for size in LANGBAR_SIZES], args.out / "compound_ime_langbar.ico")
    png = io.BytesIO()
    images[-1].save(png, format="PNG")
    (args.out / "compound_ime.svg").write_text(svg(png.getvalue()), encoding="utf-8")
    draw(64, mask).save(args.out / "compound_ime_langbar-64.png")
    print("icon", args.out / "compound_ime.ico")


if __name__ == "__main__":
    main()
