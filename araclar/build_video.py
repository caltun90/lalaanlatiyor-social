#!/usr/bin/env python3
"""Lala Anlatiyor video builder.

Usage:
  build_video.py <episode.json> audio            -> builds narration.wav + timeline.json
  build_video.py <episode.json> frames t1 t2 ... -> writes preview frames (seconds)
  build_video.py <episode.json> section <idx>    -> renders one section to mp4
  build_video.py <episode.json> join             -> concat sections + mux audio
  build_video.py <episode.json> derinlik [--yeniden] -> depth maps into images_dir/derinlik/
  build_video.py <episode.json> klip t0 t1 out.mp4 -> render a time range with audio (test)

episode.json keys: workdir, images_dir, audio_dir, title, brand, sections[
  {label, pieces:[{audio:"p01.wav", shots:[[image, weight], ...]}]} ]
Optional (2.5D animation, needs derinlik maps; without them the old 2D motion is used):
  "hareketler": {image: {"hareket": derin|sakin|takip|sarsinti|yaklas|duz,
                         "efekt": [toz, kivilcim, duman, mum], "yon": sag|sol}}
  "hareket_varsayilan": "derin", "vinyet": true
  A single shot can override with a third element: [image, weight, {"hareket": ...}]
Optional (animated campaign map, 27 Nov 2026): a shot named "harita:<ad>" plays a Remotion map clip instead of a
  picture; "haritalar": {"<ad>": {baslik, altBaslik, duraklar, hedefYazi, cerceve, baslikYeri}} and
  araclar/harita/cek.py <episode.json> must run after `audio` (see araclar/harita/src/seferler.ts).
Optional (Veo/Gemini video clips, Cem 27 Nov 2026): a shot named "klip:<ad>" plays bolumler/NN-slug/klipler/<ad>.mp4
  (Gemini'de Veo ile uretilen 8 sn'lik klip, sesi kullanilmaz) instead of a picture. If the shot is longer than the
  clip, the clip is slowed down to at most 0.65x and then holds its last frame; keep klip shots around 8-11 s.
Optional (first 2 seconds hook, rule of 19 Nov 2026):
  "kanca": {"yazi": "SARAY NEDEN SUSTU?", "gorsel": image, "y": 0.7, "duraklama": 1}
  The first sentence of the first piece is the spoken hook: audio starts at ~0.15 s, the sentence is fitted to
  end before 1.9 s (gently sped up if needed), the first frame shows the hook picture with the big hook text and
  a fast push-in, then a hard cut; brand, title and label only come after the cut.
"""
import json, os, re, subprocess, sys, wave
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
LAYOUT = 'yatay'      # 'dikey': 1080x1920, blurred background + centered picture
FG_H, FG_Y = 720, 560
CAP_MAXC = 76
CAP_W_DIKEY = 690   # caption text width in vertical videos: keeps clear of the Shorts/TikTok buttons on the right
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
    kd = cfg.get('klipler_dir', 'klipler')
    cfg['klipler_dir'] = kd if os.path.isabs(kd) else os.path.join(base, kd)
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


VOWELS = set('aeıioöuüâîûAEIİOÖUÜÂÎÛ')


def detect_pauses(a, sr, min_d=0.13, thr=0.012):
    """(speech start, speech end, [(pause start, pause end)]) in seconds"""
    win = int(sr * 0.01)
    n = len(a) // win
    voiced = np.abs(a[:n * win]).reshape(n, win).max(axis=1) >= thr
    idx = np.where(voiced)[0]
    if len(idx) == 0:
        return 0.0, len(a) / sr, []
    first, last = int(idx[0]), int(idx[-1]) + 1
    pauses, c = [], 0
    for i in range(first, last):
        if not voiced[i]:
            c += 1
        else:
            if c * 0.01 >= min_d:
                pauses.append(((i - c) * 0.01, i * 0.01))
            c = 0
    return first * 0.01, last * 0.01, pauses


WHISPER_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-small.tar.bz2'
_REC = []


def norm_tr(x):
    x = x.replace('İ', 'i').replace('I', 'ı').lower()
    for a_, b_ in (('â', 'a'), ('î', 'i'), ('û', 'u')):
        x = x.replace(a_, b_)
    return ' '.join(re.sub(r'[^a-zçğıöşü0-9 ]', ' ', x).split())


def recognizer():
    """optional helper (pip install sherpa-onnx; model ~640 MB from GitHub). None when unavailable."""
    if _REC:
        return _REC[0]
    rec = None
    try:
        import sherpa_onnx
        d = os.path.expanduser('~/.cache/lala/sherpa-onnx-whisper-small')
        if not os.path.exists(d + '/small-encoder.int8.onnx'):
            os.makedirs(os.path.dirname(d), exist_ok=True)
            print('konusma tanima modeli indiriliyor (~640 MB)...')
            tb = d + '.tar.bz2'
            subprocess.run(['curl', '-sSLf', '-o', tb, WHISPER_URL], check=True)
            subprocess.run(['tar', 'xjf', tb, '-C', os.path.dirname(d)], check=True)
            os.remove(tb)
        rec = sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=d + '/small-encoder.int8.onnx', decoder=d + '/small-decoder.int8.onnx',
            tokens=d + '/small-tokens.txt', language='tr', task='transcribe', num_threads=2)
    except Exception as e:
        print(f'uyari: konusma tanima yok ({type(e).__name__}), altyazi yalnizca duraklama ve heceyle hizalanacak', file=sys.stderr)
    _REC.append(rec)
    return rec


def heard_spans(a, sr, spans, cache_dir):
    """what is said in each breath group (speech recognizer), cached next to the audio. None if unavailable."""
    import hashlib
    key = hashlib.md5(np.round(a * 32767).astype('<i2').tobytes() + repr([(round(x, 2), round(y, 2)) for x, y in spans]).encode()).hexdigest()[:16]
    cp = os.path.join(cache_dir, key + '.json') if cache_dir else None
    if cp and os.path.exists(cp):
        with open(cp, encoding='utf-8') as f:
            return json.load(f)
    rec = recognizer()
    if rec is None:
        return None
    out = []
    for b, e in spans:
        seg = a[int(max(0, b - 0.08) * sr):int((e + 0.08) * sr)]
        st = rec.create_stream()
        st.accept_waveform(sr, seg)
        rec.decode_stream(st)
        out.append(norm_tr(st.result.text))
    if cp:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cp, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False)
    return out


def heard_prior(words, heard):
    """for the end of each breath group: (word boundary index, confidence 0..1) from matching the recognized
    text against the script; numbers and misheard words simply lower the confidence around them."""
    import difflib
    nw = [norm_tr(w) for w in words]
    S, wend = '', []
    for w in nw:
        S += w + ' '
        wend.append(len(S))                 # script char position where word ends (after the space)
    Hc, hend = '', []
    for h in heard:
        Hc += h + ' '
        hend.append(len(Hc))
    blocks = [b for b in difflib.SequenceMatcher(None, Hc, S, autojunk=False).get_matching_blocks() if b.size >= 4]
    wend_a = np.array(wend)
    pri = []
    for p in hend[:-1]:
        prev = [b for b in blocks if b.a + b.size <= p]
        nxt = [b for b in blocks if b.a >= p]
        ins = [b for b in blocks if b.a < p < b.a + b.size]
        if ins:
            sp, gap = ins[0].b + (p - ins[0].a), 0
        elif prev and nxt:
            pa, pb = prev[-1].a + prev[-1].size, prev[-1].b + prev[-1].size
            na, nb = nxt[0].a, nxt[0].b
            gap = (na - pa) + max(0, nb - pb)
            sp = pb + (nb - pb) * ((p - pa) / max(1, na - pa))
        else:
            pri.append((None, 0.0)); continue
        i = int(np.argmin(np.abs(wend_a - sp))) + 1          # boundary index = words before it
        pri.append((i, 1.0 / (1.0 + gap / 10.0)))
    return pri


def align_words(words, a, sr, cache_dir=None):
    """Forced alignment: every pause in the audio is matched to a word boundary (dynamic programming) using
    (1) syllable counts vs. spoken durations, (2) punctuation, and (3) when the recognizer is available, what
    is actually said in each breath group. Inside a breath group words are spread by syllables.
    Returns (start[], end[]) per word in seconds."""
    N = len(words)
    syl = np.array([max(1, sum(ch in VOWELS for ch in w)) for w in words], dtype=float)
    cs = np.concatenate([[0.0], np.cumsum(syl)])
    s0, s1, pauses = detect_pauses(a, sr)
    if len(pauses) > N - 1:
        pauses = sorted(sorted(pauses, key=lambda p: p[0] - p[1])[:max(0, N - 1)])
    M = len(pauses)
    edges = [s0] + [x for p in pauses for x in p] + [s1]
    spans = [(edges[2 * k], edges[2 * k + 1]) for k in range(M + 1)]
    durs = np.array([e - b for b, e in spans])
    rate = durs.sum() / cs[-1]

    def last_char(i):
        return words[i - 1].rstrip('"”’\')')[-1:]
    bpen = np.zeros(N + 1)      # cost of putting a pause after word i-1 (boundary i)
    skip = np.zeros(N + 1)      # cost of passing boundary i without a pause
    for i in range(1, N):
        ch = last_char(i)
        if ch and ch in '.?!:':
            bpen[i], skip[i] = 0.0, 0.8
        elif ch and ch in ',;':
            bpen[i], skip[i] = 0.15, 0.05
        else:
            bpen[i], skip[i] = 1.2, 0.0
    cskip = np.cumsum(skip)
    prior = None
    if M:
        heard = heard_spans(a, sr, spans, cache_dir)
        if heard is not None:
            prior = heard_prior(words, heard)
            bpen = bpen * 0.5           # with real evidence, pauses inside a sentence are less surprising
    INF = 1e18
    dp = np.full((M + 2, N + 1), INF)
    bk = np.zeros((M + 2, N + 1), dtype=int)
    dp[0][0] = 0.0
    for j in range(1, M + 2):
        d = durs[j - 1]
        lo_i, hi_i = (N, N) if j == M + 1 else (j, N - (M + 1 - j))
        for i in range(lo_i, hi_i + 1):
            i0 = np.arange(max(j - 1, i - 70), i)
            prev = dp[j - 1][i0]
            ok = prev < INF
            if not ok.any():
                continue
            sy = cs[i] - cs[i0]
            z = (d - rate * sy) / (0.12 + 0.18 * rate * sy)
            cost = prev + z * z + (cskip[i - 1] - cskip[i0]) + bpen[i]
            if prior is not None and j <= M and prior[j - 1][0] is not None:
                cost = cost + prior[j - 1][1] * min(6.0, 0.9 * abs(cs[i] - cs[prior[j - 1][0]]))
            cost[~ok] = INF
            k = int(np.argmin(cost))
            dp[j][i], bk[j][i] = cost[k], i0[k]
    assert dp[M + 1][N] < INF, 'hizalama bulunamadi'
    b = [N]
    for j in range(M + 1, 0, -1):
        b.append(int(bk[j][b[-1]]))
    b = b[::-1]
    start, end = np.zeros(N), np.zeros(N)
    for k in range(M + 1):
        w0, w1 = b[k], b[k + 1]
        t_a, t_b = spans[k]
        tot = cs[w1] - cs[w0]
        for w in range(w0, w1):
            start[w] = t_a + (t_b - t_a) * (cs[w] - cs[w0]) / tot
            end[w] = t_a + (t_b - t_a) * (cs[w + 1] - cs[w0]) / tot
    return start, end


def caption_chunks(text):
    sents = [x.strip() for x in re.findall(r'[^.!?]+[.!?]+["”]?|[^.!?]+$', text) if x.strip()]
    merged = []
    for x in sents:
        if merged and (len(merged[-1]) < 20 or len(x) < 12) and len(merged[-1]) + len(x) < CAP_MAXC:
            merged[-1] += ' ' + x
        else:
            merged.append(x)
    out = []
    for x in merged:
        out += split_chunks(x, CAP_MAXC)
    return out


def whisperx_times(words, a, sr, cache_dir, est):
    """WhisperX kelime saatleri (Cem, 27 Kasim 2026). Bulut oturumu HuggingFace'e ulasamadigi icin olcum GitHub
    Actions'ta yapilir (araclar/hizala_lala.py, .github/workflows/hizala.yml). Bu parcanin olcumu onbellekte
    (<cache_dir>/whisperx/<anahtar>.json) varsa (bas[], son[]) doner; yoksa <cache_dir>/istek/ altina ses (ogg) ve
    kelimeler + tahmini saatler yazar ve None doner (altyazi align_words tahminiyle kurulur). WHISPERX=0 kapatir."""
    if not cache_dir or os.environ.get('WHISPERX') == '0':
        return None
    import hashlib
    key = 'wx' + hashlib.md5(np.round(a * 32767).astype('<i2').tobytes() + ' '.join(words).encode()).hexdigest()[:14]
    p = os.path.join(cache_dir, 'whisperx', key + '.json')
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        k = d.get('kelimeler', [])
        if len(k) == len(words):
            return np.array([float(x[1]) for x in k]), np.array([float(x[2]) for x in k])
        return None
    q = os.path.join(cache_dir, 'istek')
    os.makedirs(q, exist_ok=True)
    ogg = os.path.join(q, key + '.ogg')
    if not os.path.exists(ogg):
        tmp = os.path.join(q, key + '.tmp.wav')
        with wave.open(tmp, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((np.clip(a, -1, 1) * 32767).astype('<i2').tobytes())
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp, '-ac', '1', '-ar', '16000', '-c:a', 'libopus', '-b:a', '48k', ogg], check=True)
        os.remove(tmp)
        with open(os.path.join(q, key + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'kelimeler': words, 'tahmin': [[round(float(x), 3), round(float(y), 3)] for x, y in zip(*est)],
                       'sure': round(len(a) / sr, 3)}, f, ensure_ascii=False)
    print(f'whisperx: {key} olcumu yok, istek yazildi', file=sys.stderr)
    return None


def captions_for_piece(text, a, sr, t0, cache_dir=None):
    """Captions timed to the speech: each line appears when its first word is spoken (WhisperX if measured,
    otherwise align_words)."""
    if not text:
        return []
    chunks = caption_chunks(text)
    words = [w for c in chunks for w in c.split()]
    try:
        ws, we = align_words(words, a, sr, cache_dir)
    except Exception as e:      # fall back to the old estimate
        print(f'uyari: altyazi hizalanamadi ({e}), tahmini zamanlama kullaniliyor', file=sys.stderr)
        return captions_estimate(text, a, sr, t0)
    try:
        wx = whisperx_times(words, a, sr, cache_dir, (ws, we))
        if wx is not None:
            ws, we = wx
    except Exception as e:
        print(f'uyari: whisperx okunamadi ({e})', file=sys.stderr)
    caps, k = [], 0
    for n, c in enumerate(chunks):
        nw = len(c.split())
        b = max(0.0, ws[k] - 0.06)
        last_end = we[k + nw - 1]
        if n + 1 < len(chunks):
            nxt = ws[k + nw] - 0.06
            e = nxt if nxt - last_end < 1.0 else last_end + 0.5
        else:
            e = min(len(a) / sr, last_end + 0.35)
        caps.append({'t0': float(t0 + b), 't1': float(t0 + max(e, b + 0.3)), 'text': c,
                     'kelimeler': [[w, round(float(t0 + ws[k + q]), 2)] for q, w in enumerate(c.split())]})
        k += nw
    return caps


def captions_estimate(text, a, sr, t0):
    """Old method: sentence times predicted by character share, snapped to detected pauses."""
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
        ch = split_chunks(x, CAP_MAXC)
        cw = np.array([len(c_) for c_ in ch], dtype=float)
        cum = np.concatenate([[0], np.cumsum(cw) / cw.sum()])
        for k, c_ in enumerate(ch):
            caps.append({'t0': float(t0 + s0 + (s1 - s0) * cum[k]), 't1': float(t0 + s0 + (s1 - s0) * cum[k + 1]), 'text': c_})
    return caps


KANCA_LEAD, KANCA_MAX = 0.10, 1.88


def hook_fit(a, sr, lead, wd, nth=1):
    """first sentence of the first piece = spoken hook. Returns (audio, hook end, caption cut) in piece seconds.
    nth: which pause ends the sentence (2 when the sentence has one comma pause inside; inner pauses are
    shortened to 0.10 s). If the sentence would end after KANCA_MAX it is sped up (pitch kept) just enough."""
    def pauses(a):
        win = int(sr * 0.01)
        n = len(a) // win
        quiet = np.abs(a[:n * win]).reshape(n, win).max(axis=1) < 0.012
        out, c = [], 0
        for i, q in enumerate(quiet):
            if q:
                c += 1
            else:
                if c * 0.01 >= 0.12 and (i - c) * 0.01 > 0.3:
                    out.append(((i - c) * 0.01, i * 0.01))
                    if len(out) >= nth:
                        break
                c = 0
        return out
    ps = pauses(a)
    assert len(ps) >= nth, 'kanca: ilk cumlenin sonu bulunamadi'
    cut = 0.0
    for q0, q1 in reversed(ps[:nth - 1]):          # tighten comma pauses inside the hook sentence
        if q1 - q0 > 0.10:
            a = np.concatenate([a[:int((q0 + 0.05) * sr)], a[int((q1 - 0.05) * sr):]])
            cut += (q1 - q0) - 0.10
    p0, p1 = ps[nth - 1][0] - cut, ps[nth - 1][1] - cut
    if lead + p0 > KANCA_MAX:
        f = min(1.4, p0 / (KANCA_MAX - lead - 0.02))
        src, dst = os.path.join(wd, 'kanca_src.wav'), os.path.join(wd, 'kanca_hizli.wav')
        with wave.open(src, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes((np.clip(a[:int(p0 * sr)], -1, 1) * 32767).astype('<i2').tobytes())
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src, '-af', f'atempo={f:.4f}', '-ar', str(sr), dst], check=True)
        _, h = read_wav(dst)
        print(f'kanca: ilk cumle {p0:.2f}s, {f:.2f}x hizlandirildi -> {len(h) / sr:.2f}s')
        a = np.concatenate([h, a[int(p0 * sr):]])
        p1 = len(h) / sr + (p1 - p0)
        p0 = len(h) / sr
    if p1 - p0 < 0.45:       # let the hook land before the story starts
        add = 0.45 - (p1 - p0)
        k = int((p0 + (p1 - p0) / 2) * sr)
        a = np.concatenate([a[:k], np.zeros(int(add * sr), np.float32), a[k:]])
        p1 += add
    return a, p0, p0 + min(0.5, (p1 - p0) * 0.75)


def build_audio(cfg):
    wd = cfg['workdir']
    kanca = cfg.get('kanca')
    hz = os.path.join(cfg['audio_dir'], 'hizalama')
    LEAD = KANCA_LEAD if kanca else globals()['LEAD']
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
            text = piece.get('text')
            if kanca and si == 0 and pi == 0:
                a, h_end, h_cut = hook_fit(a, sr, LEAD, wd, int(kanca.get('duraklama', 1)))
                timeline['kanca'] = {'bitis': t + h_end, 'kes': max(2.2, t + h_end + 0.3)}
                assert t + h_end < 2.0, f'kanca cumlesi 2 saniyeyi asiyor: {t + h_end:.2f}'
                m = re.match(r'\s*([^.!?]+[.!?]+)\s*(.*)$', text or '', re.S)
                if m:
                    subs.append({'t0': 0.0, 't1': float(t + h_cut), 'text': m.group(1).strip()})
                    subs.extend(captions_for_piece(m.group(2), a[int(h_cut * sr):], sr, t + h_cut, hz))
                    text = None
            d = len(a) / sr
            srec['pieces'].append({'audio': piece['audio'], 'start': t, 'dur': d, 'shots': piece['shots']})
            subs.extend(captions_for_piece(text, a, sr, t, hz))
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
                shots.append({'sec': si, 'image': s[0], 't0': float(a0), 't1': float(a1),
                              'fx': s[2] if len(s) > 2 else None})
    timeline['shots'] = shots
    with open(os.path.join(wd, 'timeline.json'), 'w', encoding='utf-8') as f:
        json.dump(timeline, f, ensure_ascii=False, indent=1)
    if 'kanca' in timeline:
        print(f"kanca: cumle {timeline['kanca']['bitis']:.2f}s'de bitiyor, kesme {timeline['kanca']['kes']:.2f}s")
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


def make_title_dikey(brand, title):
    fb = ImageFont.truetype(SANS_B, 34)
    ft = ImageFont.truetype(SERIF_B, 62)
    tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
    lines = wrap(tmp, title, ft, 960)
    h_ = 70 + len(lines) * 78 + 20
    img = Image.new('RGBA', (W, h_), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bw = int(spaced_width(tmp, brand, fb, 8))
    spaced_text(d, ((W - bw) // 2, 0), brand, fb, GOLD + (255,), 8)
    y = 64
    for l in lines:
        lw = int(tmp.textlength(l, font=ft))
        d.text(((W - lw) // 2, y), l, font=ft, fill=CREAM + (255,), stroke_width=3, stroke_fill=(10, 10, 20, 255)); y += 78
    return np.array(img)


def make_hook(text, maxw, size):
    """big hook text for the first two seconds: cream letters, thick dark outline, gold bar underneath"""
    font = ImageFont.truetype(SANS_B, size)
    tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
    lines = wrap(tmp, text, font, maxw)
    lh = int(size * 1.16)
    tw = max(int(tmp.textlength(l, font=font)) for l in lines)
    pad = int(size * 0.42)
    w_, h_ = tw + pad * 2, lh * len(lines) + pad * 2 + 10
    img = Image.new('RGBA', (w_, h_), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w_ - 1, h_ - 1], radius=26, fill=(12, 14, 26, 178))
    for i, l in enumerate(lines):
        lw = int(tmp.textlength(l, font=font))
        d.text(((w_ - lw) // 2, pad - int(size * 0.12) + i * lh), l, font=font, fill=CREAM + (255,),
               stroke_width=max(6, size // 14), stroke_fill=(8, 8, 16, 255))
    d.rectangle([pad, h_ - pad // 2 - 12, w_ - pad, h_ - pad // 2 - 2], fill=GOLD + (255,))
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


DEPTH_URL = 'https://github.com/fabio-sim/Depth-Anything-ONNX/releases/download/v2.0.0/depth_anything_v2_vits.onnx'
# par: parallax travel in px (1920 wide), kz: dolly strength, pan: camera drift scale, dref: focus depth
HAREKET = {
    'derin':    dict(par=34,  kz=0.045, pan=1.0, dref=0.45),
    'sakin':    dict(par=16,  kz=0.032, pan=0.6, dref=0.45),
    'takip':    dict(par=56,  kz=0.015, pan=0.25, dref=0.70),
    'sarsinti': dict(par=30,  kz=0.040, pan=1.0, dref=0.45),
    'yaklas':   dict(par=14,  kz=0.085, pan=0.4, dref=0.40),
    'duz':      dict(par=0,   kz=0.0,   pan=1.0, dref=0.45),
}
_GRID, _VIG = {}, {}


def grid_half(ow, oh):
    """half-res sampling grid expressed in full-res output pixel coordinates"""
    k = (ow, oh)
    if k not in _GRID:
        sw, sh = ow // 2, oh // 2
        gx = (np.arange(sw, dtype=np.float32) + 0.5) * (ow / sw) - 0.5
        gy = (np.arange(sh, dtype=np.float32) + 0.5) * (oh / sh) - 0.5
        _GRID[k] = np.meshgrid(gx, gy)
    return _GRID[k]


def vignette(ow, oh, strength=0.20):
    k = (ow, oh, strength)
    if k not in _VIG:
        y, x = np.mgrid[0:oh, 0:ow].astype(np.float32)
        r = np.sqrt(((x - ow / 2) / (ow / 2)) ** 2 + ((y - oh / 2) / (oh / 2)) ** 2) / np.sqrt(2)
        m = 1.0 - strength * np.clip((r - 0.45) / 0.55, 0, 1) ** 1.6
        _VIG[k] = cv2.merge([(m * 255).astype(np.uint8)] * 3)
    return _VIG[k]


def load_depth(images_dir, name, iw, ih):
    p = os.path.join(images_dir, 'derinlik', name + '.png')
    if not os.path.exists(p):
        return None
    d = cv2.imread(p, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
    d = cv2.resize(d, (iw, ih), interpolation=cv2.INTER_LINEAR)
    k = max(3, int(iw * 0.006) | 1)   # grow near objects a little so their edges move with them
    d = cv2.dilate(d, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    return cv2.GaussianBlur(d, (0, 0), iw * 0.004)


def fill_from(D, m, sigma):
    """extend values of D inside mask m smoothly outward (normalized blur)"""
    num = cv2.GaussianBlur(D * m, (0, 0), sigma)
    den = cv2.GaussianBlur(m, (0, 0), sigma)
    return np.where(den > 1e-3, num / np.maximum(den, 1e-3), float(D[m > 0.5].mean()) if (m > 0.5).any() else 0.5).astype(np.float32)


def make_layers(im, D):
    """split into near (fg) and far (bg) layers: fg alpha, fg depth, bg plate (fg removed), bg depth.
    Returns None when the picture has no clear foreground."""
    ih, iw = D.shape
    hw_, hh_ = iw // 2, ih // 2
    d8 = (cv2.resize(D, (hw_, hh_), interpolation=cv2.INTER_AREA) * 255).astype(np.uint8)
    thr, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = max(thr / 255.0, 0.42)
    m = (d8.astype(np.float32) / 255.0 > thr).astype(np.float32)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    frac = m.mean()
    if frac < 0.03 or frac > 0.85:
        return None
    Dh = d8.astype(np.float32) / 255.0
    fgD = np.where(m > 0.5, Dh, fill_from(Dh, m, 40))
    bgD = np.where(m > 0.5, fill_from(Dh, 1 - m, 40), Dh)
    grow = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    small = cv2.resize(im, (hw_, hh_), interpolation=cv2.INTER_AREA)
    plate = cv2.inpaint(small, (grow * 255).astype(np.uint8), 6, cv2.INPAINT_TELEA)
    plate = cv2.resize(plate, (iw, ih), interpolation=cv2.INTER_CUBIC)
    g_full = cv2.resize(cv2.GaussianBlur(grow, (0, 0), 2), (iw, ih))[..., None]
    plate = (im * (1 - g_full) + plate * g_full).astype(np.uint8)
    up = lambda a: cv2.resize(a, (iw, ih), interpolation=cv2.INTER_LINEAR)
    alpha = cv2.GaussianBlur(m, (0, 0), 1.0)
    return dict(alpha=up(alpha), fgD=up(fgD), bgD=up(bgD), plate=plate)


class Particles:
    """dust motes / embers; position is a closed-form function of time so any frame renders alone"""
    def __init__(self, kind, seed, ow):
        r = np.random.default_rng(seed)
        self.kind, sc = kind, ow / 1920
        if kind == 'kivilcim':
            n = 60
            self.vx, self.vy = r.normal(0.008, 0.02, n), r.uniform(-0.12, -0.05, n)
            self.size, self.bri = r.uniform(1.4, 3.2, n) * sc, r.uniform(0.55, 1.0, n)
            self.col, self.amp = np.array([70, 160, 255], np.float32), 0.012
        else:   # toz
            n = 70
            self.vx, self.vy = r.normal(0.004, 0.006, n), r.normal(-0.004, 0.004, n)
            self.size, self.bri = r.uniform(1.2, 3.8, n) * sc, r.uniform(0.22, 0.6, n)
            self.col, self.amp = np.array([175, 220, 245], np.float32), 0.010
        self.x0, self.y0 = r.random(n), r.random(n)
        self.ph, self.w = r.uniform(0, 2 * np.pi, n), r.uniform(0.4, 1.4, n)
        self.pk = r.uniform(0.6, 1.4, n)   # parallax factor (particles float in front)

    def draw(self, layer, tl, parx, ow):
        hh, hw = layer.shape[:2]
        x = (self.x0 + self.vx * tl + self.amp * np.sin(self.w * tl + self.ph) + parx * self.pk / ow) % 1.0
        y = (self.y0 + self.vy * tl + self.amp * np.cos(0.7 * self.w * tl + self.ph)) % 1.0
        b = self.bri.copy()
        if self.kind == 'kivilcim':
            b *= (0.5 + 0.5 * np.sin(7 * self.w * tl + self.ph) ** 2) * np.clip(y * 1.6, 0, 1)
        else:
            b *= 0.6 + 0.4 * np.sin(0.9 * self.w * tl + self.ph) ** 2
        for i in range(len(x)):
            c = tuple(float(v) for v in self.col * b[i])
            cv2.circle(layer, (int(x[i] * hw * 16), int(y[i] * hh * 16)), max(16, int(self.size[i] * 8)), c, -1, cv2.LINE_AA, 4)


class Haze:
    """drifting smoke, stronger on far (low depth) areas"""
    def __init__(self, seed, ow, oh):
        r = np.random.default_rng(seed)
        self.w4, self.h4 = ow // 4, oh // 4
        tw = int(self.w4 * 1.9)
        def octave(gw, gh):
            return cv2.resize(r.random((gh, gw)).astype(np.float32), (tw, self.h4), interpolation=cv2.INTER_CUBIC)
        n = 0.6 * octave(10, 4) + 0.4 * octave(24, 9)
        self.tex = (n - n.min()) / (n.max() - n.min() + 1e-6)
        self.speed = r.uniform(0.012, 0.02) * self.w4
        self.dir = 1 if r.random() < 0.5 else -1
        self.x0 = (tw - self.w4) / 2

    def mask(self, tl, Dq):
        off = self.x0 + self.dir * self.speed * tl
        M = np.float32([[1, 0, off], [0, 1, 0]])
        n = cv2.warpAffine(self.tex, M, (self.w4, self.h4), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                           borderMode=cv2.BORDER_REFLECT)
        m = np.clip((n - 0.35) / 0.5, 0, 1) ** 1.5
        far = (1 - Dq) ** 1.4 if Dq is not None else 0.7
        return m * far * 0.32


class Shot:
    def __init__(self, rec, idx, cfg, cache):
        images_dir = cfg['images_dir']
        self.t0, self.t1, self.sec = rec['t0'], rec['t1'], rec['sec']
        self.name = rec['image']
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
        self.ow, self.oh = (W, H) if LAYOUT == 'yatay' else (W, FG_H)
        self.sc = self.ow / 1920
        self.base = max(self.ow / self.iw, self.oh / self.ih)
        self.bg = None
        if LAYOUT == 'dikey':
            key = rec['image'] + '#bg'
            if key not in cache:
                sc = max(W / self.iw, H / self.ih)
                big = cv2.resize(self.im, (int(self.iw * sc) + 1, int(self.ih * sc) + 1), interpolation=cv2.INTER_AREA)
                x0 = (big.shape[1] - W) // 2; y0 = (big.shape[0] - H) // 2
                bg = cv2.GaussianBlur(big[y0:y0 + H, x0:x0 + W], (0, 0), 28)
                cache[key] = (bg.astype(np.float32) * 0.42).astype(np.uint8)
            self.bg = cache[key]
        # animation spec
        spec = dict(cfg.get('hareketler', {}).get(self.name, {}))
        if rec.get('fx'):
            spec.update(rec['fx'])
        dkey = self.name + '#d'
        if dkey not in cache:
            cache[dkey] = load_depth(images_dir, self.name, self.iw, self.ih)
        self.dep = cache[dkey]
        lkey = self.name + '#L'
        if lkey not in cache:
            cache[lkey] = make_layers(self.im, self.dep) if self.dep is not None else None
        self.layers = cache[lkey]
        self.mot = spec.get('hareket', cfg.get('hareket_varsayilan', 'derin'))
        if self.mot not in HAREKET:
            self.mot = 'derin'
        hp = HAREKET[self.mot if self.dep is not None else 'duz']
        self.fx = [e for e in spec.get('efekt', []) if e in ('toz', 'kivilcim', 'duman', 'mum')]
        self.vig = cfg.get('vinyet', True)
        seed = (sum(ord(c) * (i + 1) for i, c in enumerate(self.name)) * 7919 + idx * 104729) % (2 ** 31)
        rng = np.random.default_rng(seed)
        m0, m1, sign = MOTIONS[idx % len(MOTIONS)]
        pan = hp['pan']
        c0 = (.5 + (m0[1] - .5) * pan, .5 + (m0[2] - .5) * pan)
        c1 = (.5 + (m1[1] - .5) * pan, .5 + (m1[2] - .5) * pan)
        if self.mot == 'takip':
            sign = +1
        self.zsign = sign
        dur = self.t1 - self.t0 + XF
        self.dref = hp['dref']
        self.par = hp['par'] * self.sc * min(1.0, max(0.55, dur / 10))
        self.kz = hp['kz']
        if self.mot == 'takip':
            self.pdir = -1 if spec.get('yon', 'sag') == 'sol' else 1
        else:
            dx = c1[0] - c0[0]
            self.pdir = (-1 if dx > 0 else 1) if abs(dx) > 1e-3 else (1 if idx % 2 else -1)
        self.impacts = []
        if self.mot == 'sarsinti' and self.dep is not None:
            t_ = rng.uniform(0.4, 1.2)
            while t_ < dur + 1:
                self.impacts.append((t_, rng.uniform(0, 2 * np.pi), rng.uniform(6, 11) * self.sc))
                t_ += rng.uniform(1.6, 3.0)
        # margin needed for parallax/dolly/shake so the frame edge never shows
        dd_max = max(self.dref, 1 - self.dref)
        margin = self.par * dd_max + self.kz * dd_max * self.ow / 2 + (14 * self.sc if self.impacts else 0)
        zmin = 1.03 + 2 * margin / self.ow
        dz = min(0.13, max(0.05, 0.008 * dur))
        if sign > 0:
            self.a = (zmin, c0[0], c0[1]); self.b = (zmin + dz, c1[0], c1[1])
        else:
            self.a = (zmin + dz, c0[0], c0[1]); self.b = (zmin, c1[0], c1[1])
        self.parts = [Particles(e, seed + k, self.ow) for k, e in enumerate(self.fx) if e in ('toz', 'kivilcim')]
        self.haze = Haze(seed + 7, self.ow, self.oh) if 'duman' in self.fx else None
        self.ph = rng.uniform(0, 6.28, 3)

    def shake(self, tl):
        ox = 0.8 * self.sc * np.sin(tl * 13.1); oy = 0.8 * self.sc * np.sin(tl * 11.7 + 1)
        fl = 0.0
        for ti, ang, a in self.impacts:
            u = tl - ti
            if 0 <= u < 1.2:
                e = a * np.exp(-u * 7)
                ox += e * np.cos(ang) * np.cos(u * 38)
                oy += e * np.sin(ang) * np.cos(u * 38 + 0.7)
                fl += 0.06 * np.exp(-u * 10)
        return ox, oy, fl

    def frame(self, t, lo, hi):
        p = (t - lo) / max(1e-6, hi - lo)
        p = min(1.0, max(0.0, p))
        tl = t - lo
        z = self.a[0] + (self.b[0] - self.a[0]) * p
        cx = self.a[1] + (self.b[1] - self.a[1]) * p
        cy = self.a[2] + (self.b[2] - self.a[2]) * p
        s = self.base * z
        hw, hh = (self.ow / 2) / s, (self.oh / 2) / s
        x = min(max(cx * self.iw, hw), self.iw - hw)
        y = min(max(cy * self.ih, hh), self.ih - hh)
        ox = oy = flash = 0.0
        if self.impacts:
            ox, oy, flash = self.shake(tl)
        elif self.mot == 'takip' and self.dep is not None:
            oy = 2.5 * self.sc * np.sin(2 * np.pi * 1.6 * tl)
        x += ox / s; y += oy / s
        par = self.par * (2 * p - 1) * self.pdir
        Dh = None
        if self.dep is None or (self.par == 0 and self.kz == 0):
            M = np.array([[1 / s, 0, x - hw], [0, 1 / s, y - hh]], dtype=np.float64)
            fg = cv2.warpAffine(self.im, M, (self.ow, self.oh), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                borderMode=cv2.BORDER_REPLICATE)
        else:
            kz = self.kz * (p if self.zsign > 0 else 1 - p)
            gx, gy = grid_half(self.ow, self.oh)
            bx = gx * np.float32(1 / s) + np.float32(x - hw)
            by = gy * np.float32(1 / s) + np.float32(y - hh)
            ux = (par + (gx - self.ow / 2) * kz) / s
            uy = ((gy - self.oh / 2) * kz) / s
            dref = np.float32(self.dref)

            def warp(depth, n_it=2):
                mx, my = bx, by
                for _ in range(n_it):   # fixed-point: depth at the source point
                    Dw = cv2.remap(depth, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                    dd = Dw - dref
                    mx = bx - dd * ux
                    my = by - dd * uy
                return mx, my, Dw

            def full(a):
                return cv2.resize(a, (self.ow, self.oh), interpolation=cv2.INTER_LINEAR)

            L = self.layers
            if L is None:
                mx, my, Dh = warp(self.dep, 3)
                fg = cv2.remap(self.im, full(mx), full(my), cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            else:
                bmx, bmy, Db = warp(L['bgD'])
                fmx, fmy, Df = warp(L['fgD'])
                back = cv2.remap(L['plate'], full(bmx), full(bmy), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                fmx, fmy = full(fmx), full(fmy)
                front = cv2.remap(self.im, fmx, fmy, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                al = cv2.remap(L['alpha'], fmx, fmy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)[..., None]
                fg = (back + (front.astype(np.float32) - back) * al).astype(np.uint8)
                ah = cv2.resize(al[..., 0], (Db.shape[1], Db.shape[0]), interpolation=cv2.INTER_AREA)
                Dh = Db + (Df - Db) * ah
        if self.haze is not None:
            Dq = cv2.resize(Dh, (self.haze.w4, self.haze.h4), interpolation=cv2.INTER_AREA) if Dh is not None else None
            hm = cv2.resize(self.haze.mask(tl, Dq), (self.ow, self.oh), interpolation=cv2.INTER_LINEAR)[..., None]
            f = fg.astype(np.float32)
            fg = (f + (np.float32([200, 205, 210]) - f) * hm).astype(np.uint8)
        gain = 1.0 + flash
        if 'mum' in self.fx:
            q = self.ph
            gain += 0.028 * (np.sin(2 * np.pi * 1.3 * tl + q[0]) + 0.6 * np.sin(2 * np.pi * 3.1 * tl + q[1])
                             + 0.4 * np.sin(2 * np.pi * 7.3 * tl + q[2])) / 2.0
        if abs(gain - 1.0) > 1e-3:
            fg = cv2.convertScaleAbs(fg, alpha=gain)
        if self.parts:
            layer = np.zeros((self.oh // 2, self.ow // 2, 3), np.uint8)
            for pa in self.parts:
                pa.draw(layer, tl, par * 0.9, self.ow)
            layer = cv2.GaussianBlur(layer, (0, 0), 1.1)
            fg = cv2.add(fg, cv2.resize(layer, (self.ow, self.oh), interpolation=cv2.INTER_LINEAR))
        if self.vig:
            fg = cv2.multiply(fg, vignette(self.ow, self.oh), scale=1 / 255)
        if self.bg is None:
            return fg
        comp = self.bg.copy()
        comp[FG_Y:FG_Y + FG_H] = fg
        return comp


class VideoShot:
    """Remotion ile cizilmis harita klibi (araclar/harita/cek.py, Cem 27 Kasim 2026). Gorsel adi 'harita:<ad>' olan
    cekim gorsel yerine <workdir>/harita_<ad>.mp4 klibini oynatir; klip cekimin gorundugu andan baslar.
    'klip:<ad>' ise Gemini/Veo ile uretilmis <klipler_dir>/<ad>.mp4 klibini oynatir (gerekirse yavaslatir)."""
    def __init__(self, rec, cfg):
        self.t0, self.t1, self.sec, self.name = rec['t0'], rec['t1'], rec['sec'], rec['image']
        self.dep = 'video'
        kind, ad = self.name.split(':', 1)
        self.veo = kind == 'klip'
        if self.veo:
            self.path = os.path.join(cfg['klipler_dir'], ad + '.mp4')
            assert os.path.exists(self.path), f'Veo klibi yok: {self.path}'
        else:
            self.path = os.path.join(cfg['workdir'], 'harita_' + ad + '.mp4')
            assert os.path.exists(self.path), f'harita klibi yok: {self.path} (once: python3 araclar/harita/cek.py <episode.json>)'
        self.cap = cv2.VideoCapture(self.path)
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)); self.fps = self.cap.get(cv2.CAP_PROP_FPS) or FPS
        self.pos, self.cur = -1, None
        self.ow, self.oh = (W, H) if LAYOUT == 'yatay' else (W, FG_H)

    def _read(self, i):
        i = max(0, min(self.n - 1, i))
        if i == self.pos:
            return self.cur
        if i != self.pos + 1:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, fr = self.cap.read()
        if ok:
            self.pos, self.cur = i, fr
        return self.cur

    def frame(self, t, lo, hi):
        rate = 1.0
        if self.veo and hi - lo > 0:
            rate = max(0.65, min(1.0, (self.n / self.fps) / (hi - lo)))
        fr = self._read(int(round((t - lo) * self.fps * rate)))
        if fr.shape[1] != self.ow or fr.shape[0] != self.oh:
            fr = cv2.resize(fr, (self.ow, self.oh), interpolation=cv2.INTER_AREA)
        if LAYOUT == 'yatay':
            return fr.copy()
        sc = max(W / self.ow, H / self.oh)
        big = cv2.resize(fr, (int(self.ow * sc) + 1, int(self.oh * sc) + 1), interpolation=cv2.INTER_AREA)
        x0 = (big.shape[1] - W) // 2; y0 = (big.shape[0] - H) // 2
        comp = (cv2.GaussianBlur(big[y0:y0 + H, x0:x0 + W], (0, 0), 28).astype(np.float32) * 0.42).astype(np.uint8)
        comp[FG_Y:FG_Y + FG_H] = fr
        return comp


class Renderer:
    def __init__(self, cfg):
        self.cfg = cfg
        with open(os.path.join(cfg['workdir'], 'timeline.json'), encoding='utf-8') as f:
            self.tl = json.load(f)
        cache = {}
        self.shots = [VideoShot(r, cfg) if r['image'].startswith(('harita:', 'klip:')) else Shot(r, i, cfg, cache) for i, r in enumerate(self.tl['shots'])]
        miss = sorted({s.name for s in self.shots if s.dep is None})
        if miss:
            print(f'uyari: derinlik haritasi yok, 2D hareket kullaniliyor: {", ".join(miss)}', file=sys.stderr)
        self.labels = [make_label(s['label']) for s in self.tl['sections']]
        self.title = make_title(cfg['brand'], cfg['title'], cfg['subtitle']) if LAYOUT == 'yatay' else make_title_dikey(cfg['brand'], cfg['title'])
        self.total = self.tl['total']
        self.subs = self.tl.get('subs', [])
        self.subcache = {}
        self.subfont = ImageFont.truetype(SANS_B, 46 if LAYOUT == 'yatay' else 52)
        self.kanca = None
        k = cfg.get('kanca')
        if k and 'kanca' in self.tl:
            kes = self.tl['kanca']['kes']
            rec = {'image': k.get('gorsel', self.tl['shots'][0]['image']), 't0': 0.0, 't1': kes, 'sec': 0,
                   'fx': {'hareket': k.get('hareket', 'yaklas'), 'efekt': k.get('efekt', [])}}
            yat = LAYOUT == 'yatay'
            self.kanca = {'kes': kes, 'shot': Shot(rec, 0, cfg, cache),
                          'img': make_hook(k['yazi'], 1640 if yat else 860, k.get('punto', 132 if yat else 118)),
                          'y': k.get('y', 0.30 if yat else 0.195), 'zoom': k.get('zoom', 0.15)}

    def caption(self, text):
        if text in self.subcache:
            return self.subcache[text]
        tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
        lines = wrap(tmp, text, self.subfont, 1500 if LAYOUT == 'yatay' else CAP_W_DIKEY)
        if len(lines) > 2 and LAYOUT == 'dikey':
            lines = lines[:3]
        elif len(lines) > 2:
            lines = [' '.join(lines[:-1]), lines[-1]] if len(lines) == 3 and tmp.textlength(' '.join(lines[:-1]), font=self.subfont) < 1700 else lines[:2]
        tw = max(int(tmp.textlength(l, font=self.subfont)) for l in lines)
        lh = 60 if LAYOUT == 'yatay' else 70
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

    def render_kanca(self, t):
        """0 .. kes: hook picture with a fast push-in, big hook text popping in, subtitle. No brand, no label."""
        K = self.kanca
        kes = K['kes']
        fr = K['shot'].frame(t, 0.0, kes)
        u = min(1.0, max(0.0, t / kes))
        z = 1.0 + K['zoom'] * (1 - (1 - u) ** 3)          # fast at the very start, easing out
        M = cv2.getRotationMatrix2D((W / 2, H * (0.5 if LAYOUT == 'yatay' else (FG_Y + FG_H / 2) / H)), 0, z)
        fr = cv2.warpAffine(fr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        img = K['img']
        s = 1.0 + 0.10 * max(0.0, 1 - t / 0.22) ** 2      # readable on frame 0, settles in 0.2 s
        s = min(s, (W - 24) / img.shape[1])
        if s > 1.002:
            img = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_LINEAR)
        x = max(0, (W - img.shape[1]) // 2)
        y = max(0, int(H * K['y'] - img.shape[0] / 2))
        blend(fr, img[:, :W - x], x, y)
        cap = next((c for c in self.subs if c['t0'] <= t < c['t1']), None)
        if cap:
            ci = self.caption(cap['text'])
            blend(fr, ci, (W - ci.shape[1]) // 2, (H - ci.shape[0] - 54) if LAYOUT == 'yatay' else (FG_Y + FG_H + 80))
        return fr

    def render(self, t):
        kes = 0.0
        if self.kanca:
            kes = self.kanca['kes']
            if t < kes:
                return self.render_kanca(t)
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
        la = min(1.0, max(0.0, (t - sec['t0'] - 0.5 - (kes if s.sec == 0 else 0)) / 0.5))
        if LAYOUT == 'yatay':
            blend(fr, self.labels[s.sec], 56, 48, la)
        else:
            blend(fr, self.title, 0, 190, min(1.0, (t - kes) / 0.4) if kes else 1.0)
        # opening title
        if s.sec == 0 and LAYOUT == 'yatay':
            a = min(1.0, max(0.0, (t - 1.6 - kes) / 0.6)) * min(1.0, max(0.0, (9.2 + kes - t) / 0.6))
            if a > 0:
                th = self.title.shape[0]
                blend(fr, self.title, 56, H - th - (230 if self.subs else 70), a)
        cap = next((c for c in self.subs if c['t0'] <= t < c['t1']), None)
        if cap:
            ci = self.caption(cap['text'])
            blend(fr, ci, (W - ci.shape[1]) // 2, (H - ci.shape[0] - 54) if LAYOUT == 'yatay' else (FG_Y + FG_H + 80))
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


def depth_model_path():
    p = os.environ.get('LALA_DEPTH_MODEL') or os.path.expanduser('~/.cache/lala/depth_anything_v2_vits.onnx')
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        print('derinlik modeli indiriliyor (~100 MB)...')
        subprocess.run(['curl', '-sSLf', '-o', p + '.part', DEPTH_URL], check=True)
        os.replace(p + '.part', p)
    return p


def build_depth(cfg, force=False):
    """Depth Anything V2 (small, ONNX, CPU): one 8-bit PNG per image, near = bright."""
    import onnxruntime as ort
    idir = cfg['images_dir']
    ddir = os.path.join(idir, 'derinlik')
    os.makedirs(ddir, exist_ok=True)
    names = sorted({os.path.splitext(f)[0] for f in os.listdir(idir) if f.lower().endswith(('.jpg', '.png'))})
    sess = None
    for n in names:
        out = os.path.join(ddir, n + '.png')
        if os.path.exists(out) and not force:
            continue
        if sess is None:
            sess = ort.InferenceSession(depth_model_path(), providers=['CPUExecutionProvider'])
            iname = sess.get_inputs()[0].name
        pth = next(os.path.join(idir, n + e) for e in ('.jpg', '.png') if os.path.exists(os.path.join(idir, n + e)))
        im = cv2.imread(pth, cv2.IMREAD_COLOR)
        h, w = im.shape[:2]
        x = cv2.resize(im[:, :, ::-1], (518, 518), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        x = ((x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]).transpose(2, 0, 1)[None].astype(np.float32)
        d = sess.run(None, {iname: x})[0].squeeze()
        lo, hi = np.percentile(d, [1, 99])
        d = np.clip((d - lo) / (hi - lo + 1e-6), 0, 1)
        d = cv2.resize(d, (w // 2, h // 2), interpolation=cv2.INTER_CUBIC)
        cv2.imwrite(out, (np.clip(d, 0, 1) * 255).astype(np.uint8))
        print('derinlik', n)


def main():
    global W, H, LAYOUT, CAP_MAXC
    cfg = load_cfg(sys.argv[1])
    cmd = sys.argv[2]
    if cfg.get('layout') == 'dikey':
        W, H = cfg.get('size', [1080, 1920])
        LAYOUT, CAP_MAXC = 'dikey', 40
    wd = cfg['workdir']
    if cmd == 'audio':
        build_audio(cfg)
    elif cmd == 'derinlik':
        build_depth(cfg, force='--yeniden' in sys.argv[3:])
    elif cmd == 'klip':
        t0, t1, out = float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
        r = Renderer(cfg)
        tmp = os.path.join(wd, 'klip_silent.mp4')
        p = subprocess.Popen(['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}',
                              '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'fast', '-crf', '21',
                              '-pix_fmt', 'yuv420p', tmp], stdin=subprocess.PIPE)
        for f in range(int(round(t0 * FPS)), int(round(t1 * FPS))):
            p.stdin.write(r.render(f / FPS).tobytes())
        p.stdin.close()
        assert p.wait() == 0
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp, '-ss', str(t0), '-t', str(t1 - t0),
                        '-i', os.path.join(wd, 'narration.wav'), '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                        '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', '-shortest', out], check=True)
        print('wrote', out)
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
