#!/usr/bin/env python3
"""Lala Anlatiyor video builder.

Usage:
  build_video.py <episode.json> audio            -> builds narration.wav + timeline.json
  build_video.py <episode.json> frames t1 t2 ... -> writes preview frames (seconds)
  build_video.py <episode.json> section <idx>    -> renders one section to mp4
  build_video.py <episode.json> join             -> concat sections + mux audio

episode.json keys: workdir, images_dir, audio_dir, title, brand, sections[
  {label, pieces:[{audio:"p01.wav", shots:[[image, weight], ...]}]} ]
"""
import json, os, re, subprocess, sys, wave
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
LEAD, GAP_IN, GAP_SEC, TAIL = 0.7, 0.45, 1.4, 2.4
XF = 0.5          # crossfade between shots inside a section (seconds)
FADE = 0.55       # fade from/to black at section edges
SERIF_B = '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf'
SANS_B = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
NAVY = (22, 30, 52)
GOLD = (214, 170, 84)
CREAM = (250, 240, 214)


def load_cfg(path):
    with open(path, encoding='utf-8') as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    for k in ('workdir', 'images_dir', 'audio_dir', 'output'):
        if not os.path.isabs(cfg[k]):
            cfg[k] = os.path.join(base, cfg[k])
    os.makedirs(cfg['workdir'], exist_ok=True)
    os.makedirs(os.path.dirname(cfg['output']), exist_ok=True)
    return cfg


# ---------------------------------------------------------------- audio
def read_wav(path):
    with wave.open(path, 'rb') as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    assert sw == 2, f'{path}: expected 16-bit PCM, got {sw*8}-bit'
    a = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return sr, a


def trim_silence(a, sr, thr=0.008, pad=0.06):
    win = int(sr * 0.02)
    n = len(a) // win
    env = np.abs(a[:n * win]).reshape(n, win).max(axis=1)
    idx = np.where(env > thr)[0]
    if len(idx) == 0:
        return a
    s = max(0, idx[0] * win - int(pad * sr))
    e = min(len(a), (idx[-1] + 1) * win + int(pad * sr))
    return a[s:e]


def split_chunks(sentence, maxc=76):
    words, out, cur = sentence.split(), [], ''
    for w_ in words:
        t = (cur + ' ' + w_).strip()
        if len(t) <= maxc:
            cur = t
        else:
            out.append(cur); cur = w_
    if cur:
        out.append(cur)
    if len(out) > 1 and len(out[-1]) < 14:      # avoid a tiny last chunk
        out[-2:] = [out[-2] + ' ' + out[-1]] if len(out[-2]) + len(out[-1]) < maxc + 14 else out[-2:]
    return out


def captions_for_piece(text, a, sr, t0):
    """Sentence-level captions: predicted by character share, snapped to detected pauses."""
    if not text:
        return []
    sents = [x.strip() for x in re.findall(r'[^.!?]+[.!?]+["”]?|[^.!?]+$', text) if x.strip()]
    merged = []
    for x in sents:
        if merged and (len(merged[-1]) < 20 or len(x) < 12) and len(merged[-1]) + len(x) < 76:
            merged[-1] += ' ' + x
        else:
            merged.append(x)
    sents = merged
    d = len(a) / sr
    win = int(sr * 0.01)
    n = len(a) // win
    env = np.abs(a[:n * win]).reshape(n, win).max(axis=1) < 0.012
    pauses, c = [], 0
    for i, q in enumerate(env):
        if q:
            c += 1
        else:
            if c * 0.01 >= 0.18 and i - c > 5:
                pauses.append(((i - c) * 0.01, i * 0.01))
            c = 0
    wts = np.array([len(x) + 6 for x in sents], dtype=float)
    pred = d * np.cumsum(wts) / wts.sum()
    bounds, last = [], 0.0
    for i in range(len(sents) - 1):
        cand = [(abs((p0 + p1) / 2 - pred[i]), p0, p1) for p0, p1 in pauses if abs((p0 + p1) / 2 - pred[i]) <= 1.6 and p0 > last + 0.5]
        if cand:
            _, p0, p1 = min(cand)
            b = (p0 + p1) / 2
        else:
            b = max(pred[i], last + 0.5)
        bounds.append(b); last = b
    edges = [0.0] + bounds + [d]
    caps = []
    for i, x in enumerate(sents):
        s0, s1 = edges[i], edges[i + 1]
        ch = split_chunks(x)
        cw = np.array([len(c_) for c_ in ch], dtype=float)
        cum = np.concatenate([[0], np.cumsum(cw) / cw.sum()])
        for k, c_ in enumerate(ch):
            caps.append({'t0': float(t0 + s0 + (s1 - s0) * cum[k]), 't1': float(t0 + s0 + (s1 - s0) * cum[k + 1]), 'text': c_})
    return caps


def build_audio(cfg):
    wd = cfg['workdir']
    sr0 = None
    chunks, t = [], LEAD
    timeline = {'sections': []}
    subs = []
    chunks.append(('sil', LEAD))
    nsec = len(cfg['sections'])
    for si, sec in enumerate(cfg['sections']):
        srec = {'label': sec['label'], 'pieces': []}
        for pi, piece in enumerate(sec['pieces']):
            sr, a = read_wav(os.path.join(cfg['audio_dir'], piece['audio']))
            if sr0 is None:
                sr0 = sr
            assert sr == sr0
            a = trim_silence(a, sr)
            d = len(a) / sr
            srec['pieces'].append({'audio': piece['audio'], 'start': t, 'dur': d, 'shots': piece['shots']})
            subs.extend(captions_for_piece(piece.get('text'), a, sr, t))
            chunks.append(('aud', a))
            t += d
            last_piece = pi == len(sec['pieces']) - 1
            last_sec = si == nsec - 1
            gap = TAIL if (last_piece and last_sec) else (GAP_SEC if last_piece else GAP_IN)
            chunks.append(('sil', gap))
            t += gap
        timeline['sections'].append(srec)
    out = []
    for kind, v in chunks:
        out.append(np.zeros(int(round(v * sr0)), dtype=np.float32) if kind == 'sil' else v)
    full = np.concatenate(out)
    total = len(full) / sr0
    timeline['total'] = total
    timeline['subs'] = subs
    pcm = (np.clip(full, -1, 1) * 32767).astype('<i2')
    raw = os.path.join(wd, 'narration_raw.wav')
    with wave.open(raw, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr0); w.writeframes(pcm.tobytes())
    final = os.path.join(wd, 'narration.wav')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', raw, '-af',
                    'highpass=f=60,loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', '48000', '-ac', '2', final], check=True)
    # shot schedule
    shots = []   # global list: dict(sec, image, t0, t1)
    secs = timeline['sections']
    for si, sec in enumerate(secs):
        ps = sec['pieces']
        sec_t0 = 0.0 if si == 0 else (secs[si - 1]['pieces'][-1]['start'] + secs[si - 1]['pieces'][-1]['dur'] + GAP_SEC / 2)
        sec_t1 = total if si == len(secs) - 1 else (ps[-1]['start'] + ps[-1]['dur'] + GAP_SEC / 2)
        sec['t0'], sec['t1'] = sec_t0, sec_t1
        for pi, p in enumerate(ps):
            p_t0 = sec_t0 if pi == 0 else (p['start'] - GAP_IN / 2)
            p_t1 = sec_t1 if pi == len(ps) - 1 else (p['start'] + p['dur'] + GAP_IN / 2)
            ws = np.array([float(s[1]) for s in p['shots']])
            cum = np.concatenate([[0], np.cumsum(ws) / ws.sum()])
            for k, s in enumerate(p['shots']):
                a0 = p_t0 if k == 0 else p['start'] + p['dur'] * cum[k]
                a1 = p_t1 if k == len(p['shots']) - 1 else p['start'] + p['dur'] * cum[k + 1]
                shots.append({'sec': si, 'image': s[0], 't0': float(a0), 't1': float(a1)})
    timeline['shots'] = shots
    with open(os.path.join(wd, 'timeline.json'), 'w', encoding='utf-8') as f:
        json.dump(timeline, f, ensure_ascii=False, indent=1)
    print(f'total {total:.2f}s  shots {len(shots)}')
    for s in shots:
        print(f"  sec{s['sec']} {s['t0']:7.2f}-{s['t1']:7.2f} ({s['t1']-s['t0']:5.2f}s) {s['image']}")


# ---------------------------------------------------------------- drawing
def spaced_text(draw, xy, text, font, fill, spacing):
    x, y = xy
    for chx in text:
        draw.text((x, y), chx, font=font, fill=fill)
        x += draw.textlength(chx, font=font) + spacing
    return x


def spaced_width(draw, text, font, spacing):
    return sum(draw.textlength(c, font=font) + spacing for c in text) - spacing


def make_label(text):
    font = ImageFont.truetype(SERIF_B, 34)
    tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
    sp = 3
    tw = int(spaced_width(tmp, text, font, sp))
    padx, pady, hh = 30, 16, 44
    img = Image.new('RGBA', (tw + padx * 2 + 14, hh + pady * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=14, fill=NAVY + (215,), outline=GOLD + (255,), width=3)
    d.rectangle([14, pady + 2, 19, img.height - pady - 3], fill=GOLD + (255,))
    spaced_text(d, (padx + 8, pady + 1), text, font, CREAM + (255,), sp)
    return np.array(img)


def wrap(draw, text, font, maxw):
    words, lines, cur = text.split(), [], ''
    for w_ in words:
        t = (cur + ' ' + w_).strip()
        if draw.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w_
    lines.append(cur)
    return lines


def make_title(brand, title, sub):
    fb = ImageFont.truetype(SANS_B, 30)
    ft = ImageFont.truetype(SERIF_B, 52)
    fs = ImageFont.truetype(SANS_B, 30)
    tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
    lines = wrap(tmp, title, ft, 1000)
    tw = max(int(tmp.textlength(l, font=ft)) for l in lines)
    w_ = max(tw, int(spaced_width(tmp, brand, fb, 6))) + 110
    h_ = 60 + 40 + len(lines) * 66 + 52 + 30
    img = Image.new('RGBA', (w_, h_), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w_ - 1, h_ - 1], radius=20, fill=NAVY + (228,), outline=GOLD + (255,), width=3)
    d.rectangle([24, 34, 31, h_ - 35], fill=GOLD + (255,))
    spaced_text(d, (56, 30), brand, fb, GOLD + (255,), 6)
    y = 30 + 50
    for l in lines:
        d.text((56, y), l, font=ft, fill=CREAM + (255,)); y += 66
    d.text((56, y + 8), sub, font=fs, fill=(205, 200, 185, 255))
    return np.array(img)


def blend(frame, rgba, x, y, alpha=1.0):
    if alpha <= 0:
        return
    h_, w_ = rgba.shape[:2]
    roi = frame[y:y + h_, x:x + w_].astype(np.float32)
    a = (rgba[..., 3:4].astype(np.float32) / 255.0) * alpha
    rgb = rgba[..., :3][..., ::-1].astype(np.float32)   # RGB -> BGR
    frame[y:y + h_, x:x + w_] = (roi * (1 - a) + rgb * a).astype(np.uint8)


# ---------------------------------------------------------------- motion
MOTIONS = [  # (zoom0, cx0, cy0) -> (zoom1, cx1, cy1); zoom deltas get scaled by duration
    ((1.00, .50, .50), (1.00, .50, .46), +1),   # push in, slight up
    ((1.00, .46, .50), (1.00, .54, .50), -1),   # pull out, drift right
    ((1.00, .54, .52), (1.00, .47, .48), +1),   # push in, drift left
    ((1.00, .50, .47), (1.00, .50, .52), -1),   # pull out, slight down
    ((1.00, .45, .50), (1.00, .55, .50), +1),   # push in, drift right
    ((1.00, .55, .48), (1.00, .46, .52), -1),   # pull out, drift left
]


class Shot:
    def __init__(self, rec, idx, images_dir, cache):
        self.t0, self.t1, self.sec = rec['t0'], rec['t1'], rec['sec']
        if rec['image'] not in cache:
            im = None
            for ext in ('.jpg', '.png'):
                pth = os.path.join(images_dir, rec['image'] + ext)
                if os.path.exists(pth):
                    im = cv2.imread(pth, cv2.IMREAD_COLOR)
                    break
            assert im is not None, rec['image']
            cache[rec['image']] = im
        self.im = cache[rec['image']]
        self.ih, self.iw = self.im.shape[:2]
        self.base = max(W / self.iw, H / self.ih)
        m0, m1, sign = MOTIONS[idx % len(MOTIONS)]
        dur = self.t1 - self.t0 + XF
        dz = min(0.13, max(0.05, 0.008 * dur))
        zmin = 1.03
        if sign > 0:
            self.a = (zmin, m0[1], m0[2]); self.b = (zmin + dz, m1[1], m1[2])
        else:
            self.a = (zmin + dz, m0[1], m0[2]); self.b = (zmin, m1[1], m1[2])

    def frame(self, t, lo, hi):
        p = (t - lo) / max(1e-6, hi - lo)
        p = min(1.0, max(0.0, p))
        z = self.a[0] + (self.b[0] - self.a[0]) * p
        cx = self.a[1] + (self.b[1] - self.a[1]) * p
        cy = self.a[2] + (self.b[2] - self.a[2]) * p
        s = self.base * z
        hw, hh = (W / 2) / s, (H / 2) / s
        x = min(max(cx * self.iw, hw), self.iw - hw)
        y = min(max(cy * self.ih, hh), self.ih - hh)
        M = np.array([[1 / s, 0, x - hw], [0, 1 / s, y - hh]], dtype=np.float64)
        return cv2.warpAffine(self.im, M, (W, H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_REPLICATE)


class Renderer:
    def __init__(self, cfg):
        self.cfg = cfg
        with open(os.path.join(cfg['workdir'], 'timeline.json'), encoding='utf-8') as f:
            self.tl = json.load(f)
        cache = {}
        self.shots = [Shot(r, i, cfg['images_dir'], cache) for i, r in enumerate(self.tl['shots'])]
        self.labels = [make_label(s['label']) for s in self.tl['sections']]
        self.title = make_title(cfg['brand'], cfg['title'], cfg['subtitle'])
        self.total = self.tl['total']
        self.subs = self.tl.get('subs', [])
        self.subcache = {}
        self.subfont = ImageFont.truetype(SANS_B, 46)

    def caption(self, text):
        if text in self.subcache:
            return self.subcache[text]
        tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
        lines = wrap(tmp, text, self.subfont, 1500)
        if len(lines) > 2:
            lines = [' '.join(lines[:-1]), lines[-1]] if len(lines) == 3 and tmp.textlength(' '.join(lines[:-1]), font=self.subfont) < 1700 else lines[:2]
        tw = max(int(tmp.textlength(l, font=self.subfont)) for l in lines)
        lh = 60
        img = Image.new('RGBA', (tw + 72, lh * len(lines) + 30), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=16, fill=(10, 12, 22, 150))
        for i, l in enumerate(lines):
            lw = int(tmp.textlength(l, font=self.subfont))
            d.text(((img.width - lw) // 2, 12 + i * lh), l, font=self.subfont, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))
        arr = np.array(img)
        self.subcache[text] = arr
        return arr

    def bounds(self, i):
        """active window of shot i including crossfade overlap with same-section neighbours"""
        s = self.shots[i]
        lo = s.t0 - (XF / 2 if i > 0 and self.shots[i - 1].sec == s.sec else 0)
        hi = s.t1 + (XF / 2 if i < len(self.shots) - 1 and self.shots[i + 1].sec == s.sec else 0)
        return lo, hi

    def render(self, t):
        idx = next((i for i, s in enumerate(self.shots) if s.t0 <= t < s.t1), len(self.shots) - 1)
        s = self.shots[idx]
        lo, hi = self.bounds(idx)
        fr = s.frame(t, lo, hi)
        # crossfade with neighbour in same section
        if idx > 0 and self.shots[idx - 1].sec == s.sec and t < s.t0 + XF / 2:
            plo, phi = self.bounds(idx - 1)
            k = (t - (s.t0 - XF / 2)) / XF
            fr = cv2.addWeighted(self.shots[idx - 1].frame(t, plo, phi), 1 - k, fr, k, 0)
        elif idx < len(self.shots) - 1 and self.shots[idx + 1].sec == s.sec and t >= s.t1 - XF / 2:
            nlo, nhi = self.bounds(idx + 1)
            k = (t - (s.t1 - XF / 2)) / XF
            fr = cv2.addWeighted(fr, 1 - k, self.shots[idx + 1].frame(t, nlo, nhi), k, 0)
        sec = self.tl['sections'][s.sec]
        # label
        la = min(1.0, max(0.0, (t - sec['t0'] - 0.5) / 0.5))
        blend(fr, self.labels[s.sec], 56, 48, la)
        # opening title
        if s.sec == 0:
            a = min(1.0, max(0.0, (t - 1.6) / 0.6)) * min(1.0, max(0.0, (9.2 - t) / 0.6))
            if a > 0:
                th = self.title.shape[0]
                blend(fr, self.title, 56, H - th - (230 if self.subs else 70), a)
        cap = next((c for c in self.subs if c['t0'] <= t < c['t1']), None)
        if cap:
            ci = self.caption(cap['text'])
            blend(fr, ci, (W - ci.shape[1]) // 2, H - ci.shape[0] - 54)
        # section edge fades
        f = min(1.0, max(0.0, (t - sec['t0']) / FADE), max(0.0, (sec['t1'] - t) / FADE))
        if s.sec == len(self.tl['sections']) - 1:
            f = min(1.0, max(0.0, (t - sec['t0']) / FADE), max(0.0, (sec['t1'] - t) / 1.6))
        if f < 1.0:
            fr = (fr.astype(np.float32) * f).astype(np.uint8)
        return fr

    def section_frames(self, si):
        sec = self.tl['sections'][si]
        return int(round(sec['t0'] * FPS)), int(round(sec['t1'] * FPS))


def main():
    cfg = load_cfg(sys.argv[1])
    cmd = sys.argv[2]
    wd = cfg['workdir']
    if cmd == 'audio':
        build_audio(cfg)
    elif cmd == 'frames':
        r = Renderer(cfg)
        for ts in sys.argv[3:]:
            t = float(ts)
            cv2.imwrite(os.path.join(wd, f'preview_{t:07.2f}.jpg'), r.render(t), [cv2.IMWRITE_JPEG_QUALITY, 88])
    elif cmd == 'section':
        si = int(sys.argv[3])
        r = Renderer(cfg)
        f0, f1 = r.section_frames(si)
        tmp = os.path.join(wd, f'sec{si:02d}.part.mp4')
        out = os.path.join(wd, f'sec{si:02d}.mp4')
        p = subprocess.Popen(['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}',
                              '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'fast', '-crf', '21',
                              '-pix_fmt', 'yuv420p', '-g', '60', '-threads', '1', tmp], stdin=subprocess.PIPE)
        for f in range(f0, f1):
            p.stdin.write(r.render(f / FPS).tobytes())
        p.stdin.close()
        assert p.wait() == 0
        os.replace(tmp, out)
        print(f'section {si}: frames {f0}-{f1} ok')
    elif cmd == 'join':
        n = len(cfg['sections'])
        lst = os.path.join(wd, 'concat.txt')
        with open(lst, 'w') as f:
            for i in range(n):
                f.write(f"file 'sec{i:02d}.mp4'\n")
        silent = os.path.join(wd, 'video_silent.mp4')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', silent], check=True)
        out = cfg['output']
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', silent, '-i', os.path.join(wd, 'narration.wav'),
                        '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                        '-movflags', '+faststart', '-shortest', out], check=True)
        print('wrote', out)


if __name__ == '__main__':
    main()
