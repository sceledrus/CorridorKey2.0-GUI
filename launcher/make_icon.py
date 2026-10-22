"""Draw a simple 'CK' pixel monogram and write ck2.ico (for the exe) and ck2_gui/icon.png (for the window).
Usage: python make_icon.py <out_ico> <out_png>"""
import sys
from PIL import Image, ImageDraw

GLYPH = {
    "C": [".XXX.", "X...X", "X....", "X....", "X....", "X...X", ".XXX."],
    "K": ["X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"],
}
YELLOW, GREEN, BG, EDGE = (255, 242, 3), (43, 196, 79), (15, 13, 0), (58, 55, 18)


def render(size=256):
    s = size / 256.0
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(44 * s), fill=BG, outline=EDGE, width=max(1, int(4 * s)))
    cell = 17 * s
    total_w = (5 + 1 + 5) * cell
    x0 = (size - total_w) / 2
    y0 = (size - 7 * cell) / 2
    for i, (ch, col) in enumerate((("C", YELLOW), ("K", GREEN))):
        ox = x0 + i * 6 * cell
        for r, row in enumerate(GLYPH[ch]):
            for c, v in enumerate(row):
                if v == "X":
                    d.rectangle([ox + c * cell, y0 + r * cell, ox + (c + 1) * cell - 1, y0 + (r + 1) * cell - 1], fill=col)
    return im


if __name__ == "__main__":
    big = render(256)
    big.save(sys.argv[2])
    big.save(sys.argv[1], sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", sys.argv[1], sys.argv[2])
