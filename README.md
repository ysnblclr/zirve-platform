# Zirve Platformu

Finviz'de **tüm zamanların** ve **52 haftanın zirvesindeki** ABD hisselerini ve ETF'lerini tarar,
her birine **1 yıllık yükseliş potansiyeli puanı (0–100)** ve **risk seviyesi** verir. Taramalar,
izleme listesi, performans takibi ve model analizi tarayıcıda açılan bir panelden yönetilir.

## Başlatma

| Ne | Nasıl |
| --- | --- |
| Platformu aç (sadece bu bilgisayar) | `Baslat.bat` → tarayıcıda http://127.0.0.1:8790 açılır |
| Telefondan da erişilsin (aynı Wi-Fi) | `Baslat-Ag.bat` → adres Ayarlar sayfasında görünür |
| Kapat | Açılan siyah pencereyi kapatın |

İlk açılışta eksik paketler (`fastapi`, `uvicorn`, `requests`, `beautifulsoup4`, `lxml`) otomatik kurulur.

## Sayfalar

| Sayfa | İçerik |
| --- | --- |
| Panel | Piyasa özeti (SPY, QQQ, IWM, DIA), son taramanın en iyi 10 hissesi ve 5 ETF'i, endüstri dağılımı, uyarılar |
| Taramalar | Seçeneklerle yeni tarama (zirve / geniş mod, küçük şirketler, kaldıraçlı ETF'ler), canlı ilerleme, geçmiş taramalar |
| Tarama ayrıntısı | Sıralanabilir ve süzülebilir hisse/ETF tabloları; satıra tıklayınca nedenler, riskler, puan dağılımı ve haberler; CSV ve HTML dışa aktarma |
| Hisse sayfası | 3 yıllık haftalık fiyat grafiği (52 haftalık zirve çizgisiyle), puan geçmişi, nedenler/riskler, güncel haberler. Üstteki aramayla taramada olmayan bir sembol de "Şimdi puanla" ile anlık puanlanabilir |
| İzleme listesi | Takip ettiğiniz semboller: eklendiği fiyattan bugüne getiri ve son puan |
| Performans | Her taramanın ilk 5/10/20 adayının tarama gününden bugüne getirisi ve SPY'a göre farkı: modelin gerçekte işe yarayıp yaramadığını burada görürsünüz |
| Analiz | Geriye dönük test ve model; "Analizi yeniden çalıştır" ile ayda bir güncelleyin |
| Ayarlar | Varsayılan tarama, günlük otomatik tarama saati, uyarı eşiği, puan ağırlıkları |

## Otomatik tarama

- **Platform açıkken:** Ayarlar → "Her gün otomatik tara" (varsayılan saat 23:15; ABD borsası Türkiye
  saatiyle yazın 23:00'te, kışın 00:00'da kapanır).
- **Platform kapalıyken:** Windows Görev Zamanlayıcı'da her akşam şu komutu çalıştıran bir görev oluşturun
  (Başlangıç klasörü bu klasör olmalı): `py -3 tara.py`. Sonuçlar bir sonraki açılışta panelde görünür.

## Puan nasıl hesaplanıyor?

| Bileşen | Ağırlık | İçerik |
| --- | --- | --- |
| Teknik model | 40 | Geçmiş veriyle eğitilmiş modelin "12 ayda ≥ +%50" olasılığı (hacim artışı, oynaklık, dipten uzaklık, momentum) |
| Büyüme | 25 | Çeyreklik satış/kâr büyümesi, ivmelenme, gelecek yıl kâr beklentisi, bilanço sürprizi |
| Kurum/analist | 10 | Kurumsal alım, analist önerisi ve hedef fiyat, içeriden sahiplik |
| Değerleme | 8 | PEG, ileri F/K, fiyat/satış |
| Endüstri gücü | 7 | Endüstri grubunun 3/6/12 aylık performans sırası |
| Kalite | 5 | Özsermaye kârlılığı, faaliyet marjı |
| Trend | 5 | Fiyat > 50 > 200 günlük ortalama |

Ağırlıklar Ayarlar sayfasından değiştirilebilir. **Risk** sütunu ayrı bir modelden gelir: benzer profildeki
hisselerin 12 ayda %30+ düşme oranı (Düşük < %8, Orta %8–15, Yüksek > %15).

## Geriye dönük testin bulguları (12 Ekim 2026)

- Sadece zirvede olmak avantaj değil: yeni zirvedeki hisselerin 12 aylık medyan getirisi (%12) tabandan (%13) farksız.
- Büyük kazananları ayıranlar: son 4 haftada hacmin yıllık ortalamanın 2 katını aşması, 52 haftalık dipten
  %200+ uzaklık, yüksek oynaklık, güçlü 6 aylık momentum. Bunlar sert düşüş olasılığını da artırır.
- Endüstrinin yarısından fazlası aynı anda zirvedeyken sonraki yılın medyan getirisi %8'e düşüyor.
- Model, eğitimde kullanılmayan son dönemde test edildi: en yüksek tahmin diliminde +%50'yi geçen oran %35, en düşükte %14.

**Sınırlar:** Evren bugün işlem gören hisselerden oluştuğu için mutlak olasılıklar iyimserdir; sıralama
için kullanın. Temel veriler geçmişe dönük test edilemedi. Jeopolitik/emtia şokları (BWET gibi) önceden
bilinemez; platform bu hareketleri ancak başladıktan sonra hacim ve momentumdan yakalar.

## Arayüz ve erişilebilirlik

Arayüz, masaüstündeki "Arayüz kuralları" listesine göre tasarlandı:

| Kural kaynağı | Uygulama |
| --- | --- |
| 10 Arayüz Tasarım Kuralı (IHS) | Tutarlı menü ve düzen, asimetrik görsel hiyerarşi, serif başlık ve sade gövde yazısı, her işlem için anında geri bildirim, kısa formlar |
| WCAG 2.2 AA ve 9 yeni madde | Odak halkası yapışkan başlığın altında kalmaz, tüm tıklama hedefleri en az 24 px, Yardım bağlantısı her sayfada aynı yerde, tekrar veri girişi istenmez; sayfalar axe-core ile iki temada da hatasız |
| ARIA canlı bölgeler | Bildirim ve duyuru bölgeleri sayfa açılırken hazır; yalnızca önemli anlar duyurulur, kalıcı kayıt Uyarılar sayfasında |
| CSS Cascade Layers | `@layer reset, tokens, base, layout, components, utilities` |
| Baymard: form alanlarını azaltma | Tarama formunda tek soru; ek seçenekler ve not alanı açılır bölümde |
| W3C Design Tokens | `web/tokens.json` tek kaynak; `/tokens.css` ondan üretilir |
| HTML dialog | Silme onayı `<dialog>` ile; Esc kapatır, odak geri döner |
| Radix 12 adımlı renk ölçeği ve OKLCH | Gri, vurgu (petrol mavisi), olumlu, olumsuz ve uyarı tonları OKLCH'de; metin kontrastı otomatik doğrulanır |
| GOV.UK onay kutuları | Büyük kutular etiketin solunda, fieldset ve legend ile gruplu, ipucu metinli, ön seçimsiz |
| 6 ve daha az seçenek | Radyo düğmesi ya da bölümlü seçici; daha uzun listelerde açılır liste |
| Yapay zekâ izlenimi veren işaretler | Emoji, uzun tire, mor gradyan, Inter yazı tipi ve amaçsız animasyon yok |

Renkleri değiştirmek için `core/tokens.py` içindeki ton ve açıklık değerlerini düzenleyip
`py -3 -m core.tokens` çalıştırın; komut kontrastı denetler ve yetersizse hata verir.

## Klasör yapısı

```
Baslat.bat, Baslat-Ag.bat   başlatıcılar
sunucu.py                   web sunucusu (python sunucu.py --help)
tara.py                     komut satırından tarama
core/                       veri toplama, puanlama, analiz, veritabanı, zamanlayıcı
app/api.py                  web API
web/                        arayüz (HTML, CSS, JS)
veri/                       veritabanı (zirve.db), fiyat önbelleği, model (analiz_sonuc.json)
```

Yedek almak için `veri/zirve.db` dosyasını kopyalamanız yeterli.

## Notlar

- Veri kaynakları: Finviz ücretsiz screener (~15 dk gecikmeli, sorgu başına en fazla 1.000 satır) ve
  Yahoo Finance haftalık fiyatlar. Program istekler arasında bekler; çok sık tarama yapmayın.
- Ağ modunda şifre yoktur; yalnızca güvendiğiniz ev ağında kullanın.
- Bu platform bir tarama aracıdır, yatırım tavsiyesi değildir.
