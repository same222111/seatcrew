"""Regenerate the app icon (seat grid with one blocked seat): python packaging/make_icon.py"""
from pathlib import Path
from PIL import Image, ImageDraw
R = Path(__file__).resolve().parent.parent
def icon(n=1024):
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0)); d = ImageDraw.Draw(im); s = n / 1024
    d.rounded_rectangle([40*s, 40*s, 984*s, 984*s], 200*s, fill=(11, 18, 14, 255), outline=(57, 255, 136, 255), width=int(24*s))
    cols = [(57, 255, 136), (57, 255, 136), (57, 255, 136), (57, 255, 136), (255, 176, 59), (40, 70, 52), (57, 255, 136), (255, 90, 90), (40, 70, 52)]
    for i, c in enumerate(cols):
        x, y = 190 + (i % 3) * 230, 190 + (i // 3) * 230
        d.rounded_rectangle([x*s, y*s, (x+184)*s, (y+184)*s], 36*s, fill=c + (255,))
    return im
im = icon()
im.save(R / "seatcrew/assets/icon.png"); im.resize((256, 256), Image.LANCZOS).save(R / "packaging/icon.png")
im.save(R / "packaging/icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
im.save(R / "packaging/icon.icns")
print("icons written")
