// Lala Anlatıyor sefer haritası (Remotion, Cem 27 Kasım 2026): parşömen zemin, mürekkep kıyılar, Tuna ve kolları,
// ilerleyen kırmızı rota, sırayla beliren şehir iğneleri, hedefte kuşatma halkaları.
// Kare kare çizilir (useCurrentFrame); harita verisi Natural Earth (kamu malı), public/ klasöründe.
// Alt %24 altyazıya ayrılır: rota ve yazılar oraya düşmez.
import React, { useEffect, useMemo, useState } from 'react';
import { AbsoluteFill, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig, delayRender, continueRender, spring } from 'remotion';
import { geoMercator, geoPath } from 'd3-geo';
import type { Sefer } from './seferler';

const INK = '#4a3524', LAND = '#ead8ad', SEA = '#a8c3bd', RIVER = '#5f93a8', RED = '#a3271f', PAPER = '#f3e4bf';
const FONT = "'DejaVu Serif', 'Lora', serif";
const NEHIR = ['Danube', 'Donau', 'Drava', 'Sava', 'Tisza', 'Morava', 'Maritsa', 'Dunav', 'Dnipro', 'Dniester', 'Euphrates', 'Tigris', 'Nile', 'Kizilirmak', 'Kızılırmak', 'Sakarya', 'Volga', 'Don', 'Prut', 'Bug', 'Rhine', 'Rhein', 'Po', 'Ebro', 'Firat', 'Dicle', 'Al Furat', 'Shatt al Arab', 'Dnepre', 'Tisa', 'Damietta Branch', 'Rosetta Branch'];

type FC = { type: 'FeatureCollection'; features: any[] };
function useGeo(name: string) {
  const [d, setD] = useState<FC | null>(null);
  const [h] = useState(() => delayRender('harita ' + name));
  useEffect(() => { fetch(staticFile(name)).then(r => r.json()).then(j => { setD(j); continueRender(h); }); }, [h, name]);
  return d;
}

export const Harita: React.FC<Sefer> = ({ baslik, altBaslik, duraklar, hedefYazi, cerceve, baslikYeri = 'sag-ust' }) => {
  const f = useCurrentFrame(); const { width: W, height: H, fps, durationInFrames: N } = useVideoConfig();
  const land = useGeo('ne_50m_land.geojson'), rivers = useGeo('ne_50m_rivers_lake_centerlines.geojson'), lakes = useGeo('ne_50m_lakes.geojson');
  const u = Math.min(W / 1920, H / 1080);              // yazı ve çizgi ölçeği
  const ALT = H * 0.76;                                 // bunun altı altyazının
  const t0 = 0.9 * fps, t1 = Math.max(t0 + fps, t0 + (N - t0) * 0.68);   // rota süresinin %68'inde biter, sonu kuşatma vurgusu
  const p = interpolate(f, [t0, t1], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const proj = useMemo(() => {
    const pr = geoMercator();
    const box = { type: 'Feature', geometry: { type: 'MultiPoint', coordinates: [cerceve[0], cerceve[1], [cerceve[0][0], cerceve[1][1]], [cerceve[1][0], cerceve[0][1]]] } } as any;
    pr.fitExtent([[W * 0.03, H * 0.03], [W * 0.97, H * 0.97]], box);
    return pr;
  }, [W, H, cerceve]);
  const path = geoPath(proj);
  const pts = duraklar.map(d => proj(d.lonlat) as [number, number]);
  const seg = pts.slice(1).map((q, i) => Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]));
  const total = Math.max(1, seg.reduce((a, b) => a + b, 0));
  const at = (v: number) => { let L = v * total; for (let i = 0; i < seg.length; i++) { if (L <= seg[i]) { const k = L / Math.max(1e-6, seg[i]); return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k]; } L -= seg[i]; } return pts[pts.length - 1]; };
  const reached = (i: number) => { let L = 0; for (let k = 0; k < i; k++) L += seg[k]; return L / total; };
  // kamera: baştaki bölgeden, bütün rotayı üst %76'ya sığdıran görünüme
  const xs = pts.map(q => q[0]), ys = pts.map(q => q[1]);
  const bw = Math.max(...xs) - Math.min(...xs), bh = Math.max(...ys) - Math.min(...ys);
  const zEnd = Math.max(1, Math.min(1.35, W * 0.72 / Math.max(bw, 1), ALT * 0.72 / Math.max(bh, 1)));
  const k = interpolate(f, [0.5 * fps, t1], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.quad) });
  const zoom = 1 + (zEnd - 1) * k;
  const tx = (Math.min(...xs) + Math.max(...xs)) / 2, ty = (Math.min(...ys) + Math.max(...ys)) / 2;
  const cx = W / 2 + (tx - W / 2) * k, cy = H / 2 + (ty - H / 2) * k;
  const sy = H / 2 + (ALT / 2 - H / 2) * k;              // rotanın ortası ekranda üst bölgenin ortasına iner
  const toScreen = (q: number[]) => [W / 2 + (q[0] - cx) * zoom, sy + (q[1] - cy) * zoom];
  const head = at(p);
  const routeD = 'M' + pts.map(q => q.join(',')).join('L');
  const drawn = p * total;
  const intro = spring({ frame: f, fps, config: { damping: 200 } });
  const end = interpolate(f, [t1, t1 + 0.5 * fps], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const pulse = 1 + 0.25 * Math.sin(f / fps * 2 * Math.PI * 1.4);
  const last = pts[pts.length - 1], lastS = toScreen(last);
  const sag = baslikYeri.startsWith('sag'), ust = baslikYeri.endsWith('ust');
  const bx = sag ? W * 0.96 : W * 0.04, by = ust ? H * 0.11 : ALT - 70 * u;
  return (
    <AbsoluteFill style={{ background: SEA }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <defs>
          <radialGradient id="vin" cx="50%" cy="45%" r="75%"><stop offset="60%" stopColor="#000" stopOpacity="0" /><stop offset="100%" stopColor="#3b2410" stopOpacity="0.45" /></radialGradient>
          <filter id="kag"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4" /><feColorMatrix values="0 0 0 0 0.35  0 0 0 0 0.25  0 0 0 0 0.12  0 0 0 0.10 0" /></filter>
        </defs>
        <g transform={`translate(${W / 2} ${sy}) scale(${zoom}) translate(${-cx} ${-cy})`}>
          {land && <path d={path(land as any) || ''} fill={LAND} stroke={INK} strokeWidth={2.2 * u / zoom} strokeLinejoin="round" />}
          {lakes && <path d={path(lakes as any) || ''} fill={SEA} stroke={INK} strokeWidth={1.4 * u / zoom} />}
          {rivers && rivers.features.filter(r => NEHIR.includes(r.properties.name)).map((r, i) =>
            <path key={i} d={path(r) || ''} fill="none" stroke={RIVER} strokeWidth={(r.properties.name === 'Danube' || r.properties.name === 'Donau' ? 4.2 : 2.4) * u / zoom} strokeLinecap="round" opacity={0.9} />)}
          <path d={routeD} fill="none" stroke="#fff6dc" strokeWidth={13 * u / zoom} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${drawn} ${total + 10}`} opacity={0.7} />
          <path d={routeD} fill="none" stroke={RED} strokeWidth={6.5 * u / zoom} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${drawn} ${total + 10}`} />
          {duraklar.map((d, i) => {
            const r = reached(i); const s = spring({ frame: f - (t0 + (t1 - t0) * r) + 2, fps, config: { damping: 12, stiffness: 160 } });
            const ilk = i === 0, son = i === duraklar.length - 1; const [x, y] = pts[i];
            const fs = (son || ilk ? 46 : 36) * u / zoom;
            const sol = toScreen([x, y])[0] > W * 0.7;
            return (
              <g key={d.ad} transform={`translate(${x} ${y}) scale(${Math.max(0, i === 0 ? intro : s)})`}>
                <circle r={(son ? 15 : 11) * u / zoom} fill={son ? RED : '#fff6dc'} stroke={INK} strokeWidth={3.5 * u / zoom} />
                <text x={(sol ? -22 : 22) * u / zoom} y={-14 * u / zoom} textAnchor={sol ? 'end' : 'start'} fontFamily={FONT} fontWeight={700} fontSize={fs} fill={INK} stroke={PAPER} strokeWidth={7 * u / zoom} paintOrder="stroke">{d.ad}</text>
                {d.alt && <text x={(sol ? -22 : 22) * u / zoom} y={fs * 0.95} textAnchor={sol ? 'end' : 'start'} fontFamily={FONT} fontSize={fs * 0.62} fill={RED} stroke={PAPER} strokeWidth={6 * u / zoom} paintOrder="stroke">{d.alt}</text>}
              </g>
            );
          })}
          {p > 0 && p < 1 && <g transform={`translate(${head[0]} ${head[1]})`}>
            <circle r={22 * pulse * u / zoom} fill={RED} opacity={0.22} /><circle r={10 * u / zoom} fill={RED} stroke="#fff6dc" strokeWidth={3 * u / zoom} /></g>}
          {end > 0 && <g transform={`translate(${last[0]} ${last[1]})`} opacity={end}>
            {[0, 1, 2].map(q0 => { const q = ((f - t1) / fps * 0.9 + q0 / 3) % 1; return <circle key={q0} r={(20 + q * 90) * u / zoom} fill="none" stroke={RED} strokeWidth={4 * u / zoom} opacity={1 - q} />; })}
          </g>}
        </g>
        <rect width={W} height={H} filter="url(#kag)" />
        <rect width={W} height={H} fill="url(#vin)" />
        <g transform={`translate(${bx} ${by}) scale(${intro})`} opacity={intro}>
          <text x={0} y={0} textAnchor={sag ? 'end' : 'start'} fontFamily={FONT} fontWeight={700} fontSize={100 * u} fill={INK} stroke={PAPER} strokeWidth={10 * u} paintOrder="stroke">{baslik}</text>
          <text x={0} y={62 * u} textAnchor={sag ? 'end' : 'start'} fontFamily={FONT} fontSize={46 * u} fill={RED} stroke={PAPER} strokeWidth={8 * u} paintOrder="stroke">{altBaslik}</text>
        </g>
        {hedefYazi && end > 0 && <text x={Math.min(W * 0.9, Math.max(W * 0.1, lastS[0]))} y={Math.min(ALT - 10 * u, lastS[1] + 130 * u)} textAnchor="middle" fontFamily={FONT} fontWeight={700} fontSize={64 * u} fill={RED} stroke={PAPER} strokeWidth={9 * u} paintOrder="stroke" opacity={end} letterSpacing={5 * u}>{hedefYazi}</text>}
      </svg>
    </AbsoluteFill>
  );
};
