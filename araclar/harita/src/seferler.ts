// Bir harita = bir sefer ya da yolculuk. Bölümün episode.json'unda "haritalar": {"<ad>": Sefer} olarak yazılır.
// Durak: ad, [boylam, enlem], alt (isteğe bağlı küçük kırmızı yazı, ör. tarih). Tarih ve yer kaynakla doğrulanmadan yazılmaz.
export type Durak = { ad: string; lonlat: [number, number]; alt?: string };
export type Sefer = {
  baslik: string;                 // büyük yazı, ör. "1566"
  altBaslik: string;              // ör. "Kanuni'nin son seferi"
  duraklar: Durak[];              // rota sırasıyla, en az 2
  hedefYazi?: string;             // son durağın altında beliren büyük kırmızı yazı, ör. "KUŞATMA"
  cerceve: [[number, number], [number, number]];   // başta görünen bölge: [[batı, güney], [doğu, kuzey]]
  baslikYeri?: 'sol-ust' | 'sag-ust' | 'sol-alt' | 'sag-alt';   // varsayılan sag-ust (alt kısım altyazıya ayrılır)
  sure?: number; genislik?: number; yukseklik?: number;          // cek.py doldurur
};

export const ZIGETVAR: Sefer = {
  baslik: '1566',
  altBaslik: "Kanuni'nin son seferi",
  duraklar: [
    { ad: 'İstanbul', lonlat: [28.98, 41.01], alt: 'Mayıs 1566' },
    { ad: 'Edirne', lonlat: [26.56, 41.68] },
    { ad: 'Sofya', lonlat: [23.32, 42.70] },
    { ad: 'Niş', lonlat: [21.90, 43.32] },
    { ad: 'Belgrad', lonlat: [20.46, 44.82] },
    { ad: 'Zigetvar', lonlat: [17.79, 46.05], alt: 'Ağustos 1566' },
  ],
  hedefYazi: 'KUŞATMA',
  cerceve: [[15.5, 39.8], [30.5, 47.6]],
  baslikYeri: 'sag-ust',
};
