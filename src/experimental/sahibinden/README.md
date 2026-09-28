# Deneysel: sahibinden.com scraper'ı

Bu klasör, projenin ilk sürümünde ilan verisini sahibinden.com arama sayfalarından toplayan araştırma prototipini içerir. **Ürün bu koda bağlı değildir**; hiçbir ürün modülü onu içe aktarmaz ve varsayılan kurulumla gelmez.

## Neden ürünün dışında

- **Kullanım koşulları:** Kaynak site otomatik veri toplamayı yasaklar. Toplanan veriyi herkese açık bir üründe kullanmak hukuki risk taşır.
- **Otomatikleştirilemez:** Site otomatik erişimi engeller; scraper görünür bir tarayıcı açar ve erişim doğrulamasının elle geçilmesini bekler. Sunucuda veya zamanlanmış görevde çalışamaz.
- **Kırılgan:** Sayfa yapısı değiştiğinde ayrıştırma sessizce bozulur.

Ürün bunun yerine kaynak bağımsız bir veri katmanı kullanır (`src/ingestion/sources/`): demo verisi, CSV aktarımı ve TSB kasko listesi. Ayrıntı için ana [README](../../../README.md#veri-kaynakları).

## İçerik

| Dosya | Görev |
| --- | --- |
| `scraper.py` | Ortak tarayıcı, ayrıştırma ve kayıt yardımcıları |
| `category_page_scraper.py` | Kategori sayfalarını sırayla gezer |
| `city_segment_scraper.py` | İl bazında böler |
| `recent_listing_scraper.py` | Belirli bir tarihten yeni ilanları çeker |
| `check_removed_listings.py` | Kayıtlı ilanların hâlâ yayında olup olmadığını kontrol eder |

## Günlük güncelleme

```powershell
.\scripts\experimental\run_daily_update.bat
```

Son 24 saatin ilanlarını çeker, ardından bakım hattını çalıştırır: ilanları temizler ve günün piyasa özetini kaydeder. Fiyat trendi ve değişim yüzdeleri bu günlük özetlerden oluştuğu için komutu her gün çalıştırmak gerekir; atlanan bir günün özeti sonradan oluşturulamaz. Tarayıcı açılır ve erişim doğrulaması istenirse elle geçmeniz beklenir (en fazla 180 saniye). Temiz beyanlı ilanlar için ayrıca `run_daily_clean_update.bat` vardır.

Betikler: `scripts/experimental/`. Bağımlılıklar: `pip install -r requirements-experimental.txt`.

Yalnızca kullanım izniniz olan kaynaklarda ve kaynağın kurallarına, `robots.txt` kontrollerine ve hız sınırlarına uyarak araştırma amacıyla kullanın.
