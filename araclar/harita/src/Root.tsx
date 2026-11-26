import React from 'react';
import { Composition } from 'remotion';
import { Harita } from './Harita';
import { ZIGETVAR, Sefer } from './seferler';

// Boyut ve süre props'tan gelir (cek.py): genislik, yukseklik, sure (sn). Varsayılan: Zigetvar örneği, 1920x1080, 12 sn.
export const Root: React.FC = () => (
  <Composition id="Harita" component={Harita} fps={30} width={1920} height={1080} durationInFrames={360}
    defaultProps={ZIGETVAR as Sefer}
    calculateMetadata={({ props }) => ({ durationInFrames: Math.max(90, Math.round((props.sure ?? 12) * 30)),
      width: props.genislik ?? 1920, height: props.yukseklik ?? 1080 })} />
);
