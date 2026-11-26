"""Lala Anlatıyor altyazıları için WhisperX kelime hizalama (GitHub Actions'ta çalışır; bulutta HuggingFace kapalı).

  python3 araclar/hizala_lala.py <bolumler/NN-slug/ses/hizalama>

build_video.py `audio` komutu, ölçümü olmayan her ses parçası için <dizin>/istek/<anahtar>.ogg ve .json yazar
(kelimeler + align_words tahmini). Bu betik her isteği WhisperX ile ölçer ve <dizin>/whisperx/<anahtar>.json yazar:
{"kelimeler": [[kelime, bas, son], ...], "olculen": n, "toplam": n}. Ölçülemeyen cümle tahmini saatini korur.
Uzun parçalar cümle cümle hizalanır: her cümle, tahmini aralığının biraz genişletilmiş penceresinde aranır.
"""
import sys, os, re, json, glob, difflib
import numpy as np

def norm(w):
    w = w.replace('I', 'ı').replace('İ', 'i').lower()
    return re.sub(r"[^0-9a-zçğıöşüâîû]", '', w)

def main():
    D = sys.argv[1].rstrip('/'); Q = os.path.join(D, 'istek'); O = os.path.join(D, 'whisperx'); os.makedirs(O, exist_ok=True)
    reqs = [p for p in sorted(glob.glob(os.path.join(Q, '*.json'))) if not os.path.exists(os.path.join(O, os.path.basename(p)))]
    if not reqs: print('yeni istek yok'); return
    import whisperx, torch
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    model, meta = whisperx.load_align_model(language_code='tr', device='cpu')
    for rp in reqs:
        key = os.path.basename(rp)[:-5]; R = json.load(open(rp, encoding='utf-8'))
        words, est, dur = R['kelimeler'], R['tahmin'], R['sure']
        audio = whisperx.load_audio(os.path.join(Q, key + '.ogg'))
        # cümlelere böl (nokta, soru, ünlem; çok uzun cümleyi virgülde de böl)
        groups, cur = [], []
        for i, w in enumerate(words):
            cur.append(i)
            if re.search(r'[.!?]["”’]?$', w) or (len(cur) >= 22 and re.search(r'[,;:]$', w)): groups.append(cur); cur = []
        if cur: groups.append(cur)
        times = [None] * len(words); olc = 0
        for g in groups:
            a = max(0.0, est[g[0]][0] - .3); b = min(dur, est[g[-1]][1] + .3)
            text = ' '.join(words[i] for i in g)
            try:
                r = whisperx.align([{'text': text, 'start': a, 'end': b}], model, meta, audio, 'cpu', return_char_alignments=False)
                ws = r.get('word_segments') or [w for s in r['segments'] for w in s.get('words', [])]
            except Exception as e:
                print(key, 'cümle hizalanamadı:', str(e)[:80]); continue
            if len(ws) != len(g):
                sm = difflib.SequenceMatcher(None, [norm(words[i]) for i in g], [norm(w.get('word', '')) for w in ws], autojunk=False)
                got = [None] * len(g)
                for op, i1, i2, j1, j2 in sm.get_opcodes():
                    if op == 'equal':
                        for q in range(i2 - i1): got[i1 + q] = ws[j1 + q]
                ws = got
            ok = [w for w in ws if w and w.get('start') is not None]
            score = np.mean([w.get('score', 0) for w in ok] or [0])
            if len(ok) < .6 * len(g) or score < .2: continue          # güvenilmez: bu cümle tahminde kalır
            for i, w in zip(g, ws):
                if w and w.get('start') is not None and w.get('end') is not None: times[i] = [float(w['start']), float(w['end'])]; olc += 1
        # eksikler: önce tahmin (cümle ölçülemediyse), sonra komşular arası doğrusal
        for g in groups:
            if all(times[i] is None for i in g):
                for i in g: times[i] = list(est[i])
        n = len(words); i = 0
        while i < n:
            if times[i] is not None: i += 1; continue
            j = i
            while j < n and times[j] is None: j += 1
            lo = times[i - 1][1] if i > 0 else est[i][0]; hi = times[j][0] if j < n else est[j - 1][1]
            hi = max(hi, lo + .05 * (j - i)); st = (hi - lo) / (j - i)
            for k in range(i, j): times[k] = [lo + st * (k - i), lo + st * (k - i + 1)]
            i = j
        for k in range(1, n):
            if times[k][0] < times[k - 1][0]: times[k][0] = times[k - 1][0]
            times[k][1] = max(times[k][1], times[k][0] + .04)
        d = [abs(t[0] - e[0]) for t, e in zip(times, est)]
        json.dump({'kelimeler': [[w, round(t[0], 3), round(t[1], 3)] for w, t in zip(words, times)], 'olculen': olc, 'toplam': n},
                  open(os.path.join(O, key + '.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'{key}: {olc}/{n} kelime ölçüldü, tahminle ortalama fark {np.mean(d):.2f} sn, en büyük {max(d):.2f} sn')

if __name__ == '__main__':
    main()
