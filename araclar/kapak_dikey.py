"""Lala Anlatıyor dikey (Shorts) kapak üretici, 1080x1920.
Kullanım: python3 kapak_dikey.py <görsel> <çıktı.jpg> "<satır1>" "<satır2>" "<satır3 (kırmızı bant)>" [--odak 0.5]
Arka plan: aynı görselin bulanık ve koyulaştırılmış hali. Üstte görsel genişliğe sığdırılmış, altında büyük üç satır yazı.
"""
import argparse
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

W, H = 1080, 1920
FONT = "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf"

def fit(d, t, maxw, start):
    s = start
    while s > 40:
        f = ImageFont.truetype(FONT, s)
        if d.textlength(t, font=f) <= maxw: return f
        s -= 4
    return ImageFont.truetype(FONT, s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gorsel"); ap.add_argument("cikti")
    ap.add_argument("satir1"); ap.add_argument("satir2"); ap.add_argument("satir3")
    ap.add_argument("--odak", type=float, default=0.5, help="üstteki görselde yatay kırpma merkezi")
    ap.add_argument("--zoom", type=float, default=1.0, help="üstteki görselin yakınlaştırması")
    ap.add_argument("--ust", type=int, default=300, help="görselin üst kenarı (piksel)")
    ap.add_argument("--yukseklik", type=int, default=1000, help="görsel alanının yüksekliği")
    a = ap.parse_args()
    src = Image.open(a.gorsel).convert("RGB")
    # arka plan
    sc = max(W / src.width, H / src.height)
    bg = src.resize((round(src.width*sc), round(src.height*sc)), Image.LANCZOS)
    x0 = (bg.width - W)//2; bg = bg.crop((x0, 0, x0+W, H)).filter(ImageFilter.GaussianBlur(30))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    # üst görsel: 1080x1000 alan, yakınlaştırılmış
    PH = a.yukseklik; TOP = a.ust
    sc2 = max(W / src.width, PH / src.height) * a.zoom
    fg = src.resize((round(src.width*sc2), round(src.height*sc2)), Image.LANCZOS)
    fx = int((fg.width - W) * a.odak); fy = int((fg.height - PH) * 0.15)
    fg = fg.crop((fx, fy, fx+W, fy+PH))
    fg = ImageEnhance.Contrast(ImageEnhance.Color(fg).enhance(1.15)).enhance(1.1)
    im = bg.copy(); im.paste(fg, (0, TOP))
    ov = Image.new("RGBA", (W, H), (0,0,0,0)); d = ImageDraw.Draw(ov)
    for y in range(TOP+PH-420, TOP+PH):
        t = (y-(TOP+PH-420))/420
        d.line([(0,y),(W,y)], fill=(10,4,6,int(235*t)))
    im = Image.alpha_composite(im.convert("RGBA"), ov)
    d = ImageDraw.Draw(im)
    lines = [(a.satir1,(255,205,40),190),(a.satir2,(255,244,225),160),(a.satir3,(255,255,255),170)]
    y = TOP+PH-240  # Instagram ızgarası 9:16 kapağı ortadan 3:4 kırpar (y 240-1680); yazı bu alanda kalmalı
    for i,(t,col,s) in enumerate(lines):
        if not t: continue
        f = fit(d, t, W-80, s); bb = d.textbbox((0,0), t, font=f); h = bb[3]-bb[1]; tw = d.textlength(t, font=f); x = (W-tw)/2
        if i == 2:
            pad = 26; d.rectangle([x-36, y, x+tw+36, y+h+2*pad], fill=(190,18,28), outline=(255,215,90), width=6)
            d.text((x, y+pad-bb[1]), t, font=f, fill=col, stroke_width=5, stroke_fill=(60,0,0)); y += h+2*pad+20
        else:
            d.text((x, y-bb[1]), t, font=f, fill=col, stroke_width=10, stroke_fill=(20,8,4)); y += h+26
    im.convert("RGB").save(a.cikti, quality=90)

if __name__ == "__main__":
    main()
