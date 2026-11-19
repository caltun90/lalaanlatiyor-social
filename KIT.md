# Lala Anlatıyor: üretim kiti (bulut sürümü)

Günlük zamanlanmış görev tamamen bulutta çalışır. Cem'in bilgisayarına, Chrome'a ya da C:\dev klasörüne ihtiyaç duymaz ve onlara dokunmaz. Tek kaynak bu depodur: `caltun90/lalaanlatiyor-social` (herkese açık). Depoya anahtar, belirteç ya da kişisel bilgi yazılmaz.

## 1. Sabitler

- Kanal: Lala Anlatıyor, YouTube @LalaAnlatiyor, kanal kimliği UC-PHvR1Mom6FRRiReVg2USQ.
- Buffer (lalaanlatiyor hesabı, ücretsiz plan, kanal başına en fazla 10 planlı gönderi): YouTube "Lala Anlatıyor", TikTok "osmanl.tarihi73", X "lalaanlatiyor".
- Senaryolar: https://claude.ai/artifact/UbeYc7E79sCQTxwsKeLZfX (1. hafta, 5 senaryo, Claude Docs bağlayıcısıyla okunur; kimlik df7d2b7d-21ba-449c-96e9-b63d8bcc0542). Konu takvimi: https://claude.ai/artifact/EfQSU1KxKFxXnTmAzvXb3F
- Anlatım kalıbı (Cem, 17 Kasım 2026 gecesi, 2. bölümden itibaren): düz hikâye anlatımı. Anlatıcı bir hikâye anlatır gibi anlatır. "Şehzadem" hitabı YOK, izleyiciye rol verme YOK ("sen kâtipsin" gibi ikinci tekil anlatım yok), araya giren dersler ve öğütler yok, "Hadi şimdi yat" kapanışı yok. Olay baştan sona üçüncü kişiyle, sahne sahne, merak uyandırarak anlatılır; uydurma kişi ve konuşma eklenmez, bu yüzden "neyi uydurdum" kapanışına da gerek kalmaz. Açılış tek cümlelik kanca, kapanış olayın sonucunu ve bir sonraki bölümün konusunu söyleyen 1-2 cümle. Senaryo belgesindeki 2-5. bölüm metinleri eski kalıpla (şehzadem, sen anlatımı) yazılıdır: seslendirmeden önce aynı olayları ve aynı kaynakları koruyarak bu yeni kalıba göre yeniden yaz ve `bolumler/NN-slug/senaryo.md` olarak kaydet. 1. bölüm (Zigetvar) eski kalıpla yayınlandı, ona dokunma. Görsel tariflerinde de izleyici karakteri (genç kâtip, çırak vb.) yerine olayın gerçek kişileri ve mekânları çizilir; Lala yalnızca açılış ve kapanış görselinde anlatıcı olarak görünebilir.
- Üslup: Cem'e yazılan her şey Türkçe, kısa, sade. Uzun tire (em dash) hiçbir yerde kullanılmaz.
- Anlatım dili (Cem, 17 Kasım 2026): herkesin bildiği günlük Türkçe. Az bilinen ya da eski kelime kullanma (nikris, cülus, huruç, tebdil, müdebbir gibi). Böyle bir kelime gerekiyorsa yerine bilineni söyle (nikris yerine "ayağındaki ağrılı hastalık" ya da "gut hastalığı", cülus bahşişi yerine "tahta çıkış bahşişi") ya da ilk geçtiği yerde tek cümleyle açıkla. Senaryo belgesindeki metinleri seslendirmeden önce bu kurala göre sadeleştir. Kısa özetlerde de aynı kural geçerli.

## 2. Depo düzeni

- `log.json`: kayıt listesi. Her kayıt: {no, slug, baslik, durum, tarih, uzun_youtube, kisa_yt_post, kisa_tiktok_post, x_post, notlar}. Durumlar: senaryo (görsel yok), hazir (görseller depoda), yuklendi.
- `bolumler/NN-slug/`: `episode.json`, `gorseller/*.jpg`, `ses/pNN.wav`, `seslendirme_metni.txt`, varsa `senaryo.md`.
- `araclar/build_video.py`: kurgu betiği. `stil/karakter_sayfasi.jpg`: karakter referansı. `videos/`: Buffer'ın alacağı kısa videolar.
- `work/` ve `cikti/` klasörleri depoya girmez (.gitignore). Uzun video depoya konmaz (100 MB sınırı), doğrudan YouTube'a yüklenir.

## 3. Görsel stoğu (görevin tek dış bağımlılığı)

- Görseller ChatGPT ile üretilir ve bu yalnızca Cem'in bilgisayarında, Cem'in başlattığı ayrı bir oturumda yapılır. Günlük görev görsel ÜRETMEZ. Gemini API'nin ücretsiz katmanında görsel üretimi yok (17 Kasım 2026'da denendi, 429).
- Görev yalnızca `gorseller/` klasörü dolu olan (log'da durum "hazir") bölümleri işler. Hazır bölüm kalmadıysa hiçbir şey üretmez ve Cem'e tek cümleyle "Görsel stoğu bitti, sıradaki bölüm: <ad>" diye bildirir.
- Stok oturumunda kullanılan stil cümlesi: clean flat 2D cartoon illustration, thick dark-brown outlines, simple shapes, flat colors with minimal shading, slightly large heads, small dot eyes, friendly and readable. Palette: deep teal, burgundy, warm gold, cream, muted navy. 16:9 landscape, no text or letters.

## 4. Günlük akış

1. Depoyu `add_repo` ile push yetkisiyle ekle, klonla, `git push --dry-run origin HEAD:main` ile yetkiyi sına. Bu kiti ve `log.json` dosyasını oku.
2. Sıradaki "hazir" bölümü seç (en küçük numara). Yoksa bölüm 3'teki kurala göre bildir ve dur.
3. Ses: bölüm 5. Eksik `pNN.wav` dosyalarını üret, depoya koy.
4. Uzun video: bölüm 6.
5. Kısa özetler: bölüm 7.
6. Yayın: bölüm 8.
7. Kayıt: `log.json` güncelle, yeni ses dosyalarını, kısa videoları, episode dosyalarını commit et, `git push origin HEAD:main`. Cem'e rapor ver.

Bölüm 01-zigetvar (17 Kasım 2026): 35 görsel, p01-p14 ses ve `episode.json` hazır. Yapılacak: uzun video kurgusu, kısa özetler, yayın.

## 5. Ses (Gemini API)

- Model `gemini-3.8-flash-tts`, ses `Algieba`. İstek: POST `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-tts:generateContent`, başlık `x-goog-api-key`, gövde `{"contents":[{"parts":[{"text":"<metin>"}]}],"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Algieba"}}}}}`.
- Yanıt `inlineData`: mimeType `audio/wav` ise veri hazır WAV dosyasıdır, olduğu gibi yaz. `audio/L16` ise ham PCM'dir, 24 kHz mono 16 bit WAV başlığı ekle.
- Anahtar Cem'in diğer kanallarıyla ortaktır. Bir çalışmada en fazla 8 istek. Bir uzun videonun anlatımını 5-6 parçaya böl (parça başına en fazla 1.800 karakter), iki kısa özet 2 istek. 429 gelirse başka modele geçme (diğer kanalların kotasını yeme): o güne kadar üretileni depoya koy, kalanı ertesi çalışmaya bırak.
- Rakamla yazılan tarihleri yazıyla ver. Her parçayı ürettikten sonra süresine bak (yaklaşık 13-15 karakter/saniye); çok kısa ya da çok uzun çıkan parçayı bir kez yeniden üret.

## 6. Uzun video

- `pip install --break-system-packages opencv-python-headless pillow numpy onnxruntime` ve ffmpeg gerekir.
- Hareket (19 Kasım 2026, Cem'in kararı): görseller 2.5D canlandırılır. Önce `python3 araclar/build_video.py bolumler/NN-slug/episode.json derinlik` çalıştır: Depth Anything V2 modelini (GitHub, ~100 MB, `~/.cache/lala/`) indirir ve her görsel için `gorseller/derinlik/<ad>.png` üretir (35 görsel yaklaşık 40 saniye). Bu klasörü commit et. Harita yoksa betik eski düz yakınlaşmaya döner ve uyarı yazar.
- `episode.json` ve kısa özet dosyalarına `"hareketler": {"<görsel adı>": {"hareket": "...", "efekt": [...]}}` yaz. Hareketler: `derin` (varsayılan, katmanlı kaydırma ve yavaş yaklaşma), `sakin` (iç mekân, konuşma), `yaklas` (yakın plan yüz, mektup), `takip` (at, yürüyüş, araba; `"yon": "sag"` ya da `"sol"` ile hareket yönü), `sarsinti` (top, gedik, çatışma), `duz` (eski 2D). Efektler: `mum` (kandil, mum, ateş ışığı titremesi), `toz` (havada uçuşan toz), `kivilcim` (ateş, top, yangın), `duman` (kuşatma dumanı, uzak planlarda yoğun). Görseli gözle görerek seç, her sahneye en fazla iki efekt. Örnek: `bolumler/01-zigetvar/episode.json`.
- Deneme için `klip <başlangıç sn> <bitiş sn> <çıktı.mp4>` komutu sesli kısa parça üretir.
- `python3 araclar/build_video.py bolumler/NN-slug/episode.json audio`, sonra `frames <4 farklı saniye>` ile kare kontrolü (Read ile aç), sonra her bölüm için `section <n>` (ikişer paralel), sonra `join`. Hareketli sürümde kare başına yaklaşık 65 ms; 8 dakikalık video iki çekirdekte yaklaşık 10-15 dakikada işlenir.
- Altyazı (Cem, 17 Kasım 2026): bütün videolar gömülü altyazıyla yayınlanır. `episode.json` içinde her parçaya `"text": "<o parçada seslendirilen metin, aynen>"` yaz; betik cümleleri duraklamalara oturtup altyazıyı kendisi üretir. Kare kontrolünde altyazının taşmadığına ve doğru cümleyi gösterdiğine bak. Kısa özetlerde de altyazı olur.
- `episode.json`: yollar bu dosyaya göre görelidir. sections[{label, pieces[{audio, shots[[görsel adı, ağırlık]]}]}]. Etiket ekranın sol üstünde durur, seslendirilmez. Tek görsel 20 saniyeden uzun kalmasın.
- Yeni bölüm için senaryoyu 5-6 ses parçasına böl, her parçaya o metnin anlattığı 4-7 görseli karakter sayısıyla orantılı ağırlıkla ver.
- Senaryo belgesinde "emin olmadığım" diye işaretli noktaları seslendirmeden önce ikinci güvenilir kaynaktan doğrula ya da cümleyi yumuşat.
- Müzik ve ses efekti yok.

## 7. Kısa özet videolar

- İki dikey özet (1080x1920, 30 fps): A (YouTube Short ve TikTok, 2:40-2:55), B (X, en fazla 2:15).
- Özet uzun videodan kesme değil, kendi kısa anlatımıdır: Lala'nın ağzından, olayın en çarpıcı üç anı, sonu "Devamı kanalda şehzadem." A yaklaşık 330-360 kelime, B yaklaşık 250-270 kelime, ayrı seslendirilir.
- Görseller o bölümün görselleridir. Dikey yerleşim: arka planda aynı görselin bulanık ve koyulaştırılmış hali, ortada görselin kendisi (genişliğe sığdırılmış, hafif yakınlaşma hareketi), üstte "LALA ANLATIYOR" ve video başlığı. `build_video.py` yalnızca yatay üretir; dikey kipi ilk çalışmada ekle (episode.json'a "size": [1080, 1920] ve "layout": "dikey"), kare kontrolü yap, betiği commit et ve "Öğrenilenler"e not düş.
- Dosyalar `videos/<tarih>-<slug>-kisa-a.mp4` ve `-kisa-b.mp4`, her biri 90 MB altında.

## 8. Yayın

Uzun video (YouTube API):
- `git clone --depth 1 https://github.com/caltun90/demekoyuzden-social` ile `yt_upload.py` al (yalnızca okuma).
- Önce belirtecin kanalını doğrula (`channels?mine=true`, kimlik UC-PHvR1Mom6FRRiReVg2USQ). Başka kanal çıkarsa yükleme.
- `YT_CLIENT_ID=... YT_CLIENT_SECRET=... YT_REFRESH_TOKEN=... python3 yt_upload.py <video.mp4> --title "<en fazla 90 karakter>" --desc "<açıklama>" --tags "lalaanlatiyor,osmanlı tarihi,<konu>" --publish-at <bugün>T19:00:00+03:00 --thumb <kapak.jpg>`. Saat 18:50'yi geçtiyse şimdi + 30 dakika.
- Açıklama: 2-3 cümlelik kanca, bölüm dakikaları, "Bu videoda olaylar gerçektir, izleyicinin rolü kurgudur.", kaynaklar, en fazla 8 etiket. Kapak 1280x720, en güçlü görsel üzerine en fazla 5 kelimelik başlık.

Kısa videolar (Buffer API):
- Kısa videoları push et, `https://raw.githubusercontent.com/caltun90/lalaanlatiyor-social/main/videos/<dosya>` adresinin 200 döndüğünü doğrula.
- POST https://api.buffer.com , Authorization: Bearer <BUFFER_API_KEY>, GraphQL. Şemayı ezbere yazma: https://developers.buffer.com/llms.txt içindeki örnekleri oku, alanları introspection ile doğrula. Kanal kimliklerini her çalışmada API'den oku.
- A: YouTube Short (başlık en fazla 90 karakter, categoryId "27", public, madeForKids false) ve TikTok, bugün 20:00 (+03:00). B: X, bugün 20:00. Saat geçtiyse şimdi + 30 dakika.
- Metin: 1-2 cümlelik kanca, "Devamı YouTube'da: Lala Anlatıyor", en fazla 5 etiket (#lalaanlatiyor dahil). X metni en fazla 280 karakter, bağlantı yok.
- Planladıktan sonra üç gönderiyi API'den geri okuyup doğrula. Aynı videoyu iki kez planlama.

## 9. Öğrenilenler

- (17 Kasım 2026) Gemini TTS API `audio/wav` döndürüyor; veriyi PCM sanıp yeniden başlık eklemek sesi bozar.
- (17 Kasım 2026) Proje oturumundan `add_repo` ile push yetkisi alınabiliyor.
- (18 Kasım 2026) YouTube yenileme belirteci üretildikten yaklaşık 3,5 saat sonra invalid_grant verdi; sebebi bilinmiyor. Belirteç reddedilirse uzun videoyu `cikti/` altında bırakma, yüklemeyi atla, kısa özetlere devam et ve Cem'e bildir.
- (18 Kasım 2026) Altyazı betiğe eklendi: episode.json parçalarındaki `text` alanından üretilir.
- (18 Kasım 2026) Dikey kip betiğe eklendi: episode json'da "size": [1080, 1920], "layout": "dikey". Örnek: bolumler/01-zigetvar/kisa-a.json.
- (18 Kasım 2026) YouTube Short'u Buffer ile DEĞİL, uzun video gibi YouTube API ile doğrudan yükle (başlığın sonuna #shorts). Buffer'daki YouTube kanalı kopuk; Buffer yalnızca TikTok ve X için kullanılır. Buffer kanal listesinde isDisconnected true olan kanala gönderi oluşturma.
- (18 Kasım 2026) Kanal 17 Kasım gecesi YouTube tarafından kapatıldı, itirazla ertesi gün açıldı. Yeni kanalda aynı gün içinde yoğun otomasyon riskli: günde en fazla bir uzun video ve bir Short yükle, aynı videonun ikinci kopyasını yükleme.
- (18 Kasım 2026) Kısa özet metinleri saniyede yaklaşık 16 karakter hızla okunuyor: 2:50 için yaklaşık 2.700, 2:10 için yaklaşık 2.050 karakter yaz.
- (19 Kasım 2026) 2.5D hareket betiğe eklendi (`derinlik` komutu, `hareketler` alanı, bölüm 6). Tek katmanlı derinlik kaydırması karakter kenarında hayalet kopya bırakıyordu; betik artık ön planı ayrı katmana alıp arkasını dolduruyor. Takip hareketinde kaydırmayı büyütme, hayalet geri gelir.
- (19 Kasım 2026) Görsellerde ay yıldızlı kırmızı bayrak var (ör. courier, siege_wide); 16. yüzyıl için anakronizm. Yeni stok oturumlarında istemde "no crescent-and-star flags" yaz.
- (19 Kasım 2026) ChatGPT aynı sohbette 12-13 görselden sonra düz çizgi film stilinden gerçekçi, boyama görünüme kaydı ve ay yıldızlı bayrak ekledi; 21 görsel yeniden üretildi. Stok oturumunda stil cümlesini ve "no flags" notunu her istemin başına yaz, her 10 görselde bir toplu kontrol yap.
- (19 Kasım 2026) İlk 2 saniye kancası betiğe eklendi: episode json'da `"kanca": {"yazi": "<en fazla 5 kelime>", "gorsel": "<ad>", "punto": .., "y": ..}`; kanca cümlesi ilk ses parçasının ilk cümlesidir (18-23 karakter olursa 2 saniyeden önce biter, uzarsa betik hafifçe hızlandırır), marka ve başlık kesmeden sonra gelir. `demekoyuzden-social` bu oturumdan klonlanamıyor (depo kapsamı dışı), yerine `araclar/yt_yukle.py` kullan (aynı ortam değişkenleri). Buffer'da YouTube kanalı yeniden bağlı görünüyor (isDisconnected false) ama Short yine API ile yüklendi.
- (19 Kasım 2026) Cem soru biçimindeki belirsiz kancayı beğenmedi ("Şehir o sabah ne gördü?"): kanca olayın en çarpıcı somut gerçeğini doğrudan söylemeli ("On dokuz şehzade, tek gece."), merak sorusu hemen ardından gelmeli ("Peki nasıl?"). Kanca cümlesinde virgül varsa episode json'da `"duraklama": 2` yaz. YouTube belirteci yalnızca yükleyebilir, silemez ve değiştiremez: yüklemeden önce kancayı ve başlığı kesinleştir, değişiklik gerekirse eski videoyu Cem Studio'dan siler.
- (19 Kasım 2026) Altyazı eski yöntemde yer yer 2 saniye erken ya da geç kalıyordu (Cem fark etti). Betik artık sesteki her duraklamayı metindeki noktalama yerine eşleyip kelimeleri heceye göre dağıtıyor (`align_words`); ek model gerekmez. Dikey videoda altyazı genişliği 690 pikselle sınırlı (`CAP_W_DIKEY`), çünkü Short ve TikTok'ta sağdaki düğmeler x=930 pikselden sonrasını kapatıyor; sağ kenara yazı koyma. Cümle içi dramatik duraklamalarda şaşmaması için `pip install --break-system-packages sherpa-onnx` kur: betik GitHub'daki whisper-small modelini (~640 MB, huggingface bu ortamdan erişilemiyor) kendisi indirir, her nefes grubunda söyleneni metinle eşler ve sonucu `ses/hizalama/` altına yazar (commit et). Kurulu değilse yalnızca duraklama ve heceyle hizalar. Arka plandaki kurgu, kullanıcı yanıtı beklenirken durduruluyor: uzun işleri soru sormadan önce bitir.
