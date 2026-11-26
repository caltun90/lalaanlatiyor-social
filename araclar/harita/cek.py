#!/usr/bin/env python3
"""Bölümün harita kliplerini Remotion ile çizer (Cem, 27 Kasım 2026).

  python3 araclar/harita/cek.py <episode.json>        (build_video.py ... audio'dan SONRA, section'dan ÖNCE)

episode.json'da "haritalar": {"<ad>": {Sefer alanları, bkz. src/seferler.ts}} olur ve bir çekim görsel yerine
"harita:<ad>" adını taşır (ör. ["harita:zigetvar", 2]). Betik timeline.json'dan o çekimin süresini okur ve
<workdir>/harita_<ad>.mp4 dosyasını çekimin boyuna ve videonun düzenine (yatay 1920x1080, dikey 1080x720) göre çizer.
build_video.py section/frames bu klibi görsel yerine oynatır. İlk çalıştırmada araclar/harita içinde npm ci yapılır.
"""
import json, os, subprocess, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    ep = os.path.abspath(sys.argv[1]); base = os.path.dirname(ep)
    cfg = json.load(open(ep, encoding='utf-8'))
    wd = cfg['workdir'] if os.path.isabs(cfg['workdir']) else os.path.join(base, cfg['workdir'])
    tl = json.load(open(os.path.join(wd, 'timeline.json'), encoding='utf-8'))
    dikey = cfg.get('layout') == 'dikey'
    gw, gh = (1080, 720) if dikey else (1920, 1080)
    need = {}
    for s in tl['shots']:
        if s['image'].startswith('harita:'):
            ad = s['image'].split(':', 1)[1]
            need[ad] = max(need.get(ad, 0), s['t1'] - s['t0'] + 1.0)      # çapraz geçiş payı
    if not need:
        print('bu bölümde harita çekimi yok'); return
    if not os.path.isdir(os.path.join(HERE, 'node_modules')):
        subprocess.run(['npm', 'ci', '--no-audit', '--no-fund', '--loglevel=error'], cwd=HERE, check=True)
    chrome = os.environ.get('CHROME_PATH') or shutil.which('google-chrome') or shutil.which('chromium')
    for ad, sure in need.items():
        props = dict(cfg.get('haritalar', {}).get(ad) or {})
        assert props, f'episode.json "haritalar" içinde "{ad}" yok'
        props.update({'sure': round(sure, 2), 'genislik': gw, 'yukseklik': gh})
        pf = os.path.join(wd, f'harita_{ad}.props.json'); json.dump(props, open(pf, 'w', encoding='utf-8'), ensure_ascii=False)
        out = os.path.join(wd, f'harita_{ad}.mp4')
        cmd = ['npx', 'remotion', 'render', 'src/index.ts', 'Harita', out, f'--props={pf}', '--concurrency=2', '--crf=18', '--log=error']
        if chrome: cmd.append(f'--browser-executable={chrome}')
        print('harita çiziliyor:', ad, f'{sure:.1f} sn', f'{gw}x{gh}', flush=True)
        subprocess.run(cmd, cwd=HERE, check=True)
        print('->', out)

if __name__ == '__main__':
    main()
