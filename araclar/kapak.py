"""Lala Anlatıyor kapak üretici.
Kullanım: python3 kapak.py <görsel> <çıktı.jpg> "<satır1>" "<satır2>" "<satır3 (kırmızı bant)>" [--zoom 1.1] [--ust 1.0] [--odak 0.5] [--olcek 0.85]
Satır 1 altın sarısı, satır 2 krem, satır 3 kırmızı bant üzerinde beyaz. Boş satır "" verilebilir.
"""
import sys, argparse
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

W, H = 1280, 720
FONT = "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf"

def fit_font(draw, text, max_w, start):
    s = start
    while s > 40:
        f = ImageFont.truetype(FONT, s)
        if draw.textlength(text, font=f) <= max_w:
            return f
        s -= 4
    return ImageFont.truetype(FONT, s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gorsel"); ap.add_argument("cikti")
    ap.add_argument("satir1"); ap.add_argument("satir2"); ap.add_argument("satir3")
    ap.add_argument("--odak", type=float, default=0.5, help="yatay kırpma merkezi 0-1")
    ap.add_argument("--ust", type=float, default=0.0, help="dikey kırpma başlangıcı 0-1")
    ap.add_argument("--zoom", type=float, default=1.0, help="yakınlaştırma (1.0 = tam görsel)")
    ap.add_argument("--olcek", type=float, default=1.0, help="yazı boyutu çarpanı (yüzler kapanıyorsa 0.8-0.9)")
    a = ap.parse_args()

    im = Image.open(a.gorsel).convert("RGB")
    sc = max(W / im.width, H / im.height) * a.zoom
    im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
    x0 = int((im.width - W) * a.odak); y0 = int((im.height - H) * a.ust)
    im = im.crop((x0, y0, x0 + W, y0 + H))
    # karanlık, gerilimli ton
    im = ImageEnhance.Color(im).enhance(1.15)
    im = ImageEnhance.Contrast(im).enhance(1.12)
    im = ImageEnhance.Brightness(im).enhance(0.82)
    # alt kısma koyu geçiş + kenarlara kırmızımsı karartma
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for y in range(H):
        t = max(0, (y - H * 0.30) / (H * 0.70))
        d.line([(0, y), (W, y)], fill=(10, 4, 6, int(215 * t ** 1.1)))
    vig = Image.new("L", (W, H), 0); dv = ImageDraw.Draw(vig)
    dv.ellipse([-W * 0.15, -H * 0.25, W * 1.15, H * 1.25], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(120))
    red = Image.new("RGBA", (W, H), (90, 0, 10, 255))
    red.putalpha(Image.eval(vig, lambda v: int((255 - v) * 0.85)))
    im = Image.alpha_composite(im.convert("RGBA"), ov)
    im = Image.alpha_composite(im, red)

    d = ImageDraw.Draw(im)
    lines = [(a.satir1, (255, 205, 40), 136), (a.satir2, (255, 244, 225), 104), (a.satir3, (255, 255, 255), 112)]
    fonts = [fit_font(d, t, W - 90, int(s * a.olcek)) if t else None for t, _, s in lines]
    hs = []
    for (t, _, _), f in zip(lines, fonts):
        if t:
            bb = d.textbbox((0, 0), t, font=f); hs.append(bb[3] - bb[1])
        else:
            hs.append(0)
    gap = 14; band_pad = 18
    total = sum(hs) + gap * (sum(1 for h in hs if h) - 1) + (2 * band_pad if a.satir3 else 0)
    y = H - 28 - total
    for i, ((t, col, _), f, h) in enumerate(zip(lines, fonts, hs)):
        if not t:
            continue
        tw = d.textlength(t, font=f); x = (W - tw) / 2
        bb = d.textbbox((0, 0), t, font=f)
        if i == 2:
            bx0, bx1 = x - 34, x + tw + 34
            by0, by1 = y, y + h + 2 * band_pad
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
            ds.rectangle([bx0 + 8, by0 + 10, bx1 + 8, by1 + 10], fill=(0, 0, 0, 160))
            im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(6))); d = ImageDraw.Draw(im)
            d.rectangle([bx0, by0, bx1, by1], fill=(190, 18, 28), outline=(255, 215, 90), width=5)
            d.text((x, y + band_pad - bb[1]), t, font=f, fill=col, stroke_width=4, stroke_fill=(60, 0, 0))
            y = by1 + gap
        else:
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
            ds.text((x + 6, y - bb[1] + 8), t, font=f, fill=(0, 0, 0, 200), stroke_width=10, stroke_fill=(0, 0, 0, 200))
            im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(5))); d = ImageDraw.Draw(im)
            d.text((x, y - bb[1]), t, font=f, fill=col, stroke_width=8, stroke_fill=(20, 8, 4))
            y += h + gap
    im.convert("RGB").save(a.cikti, quality=92)

if __name__ == "__main__":
    main()
