# Data Strategy

## Amaç

ArabamFiyat.com'un veri stratejisi, kullanıcının seçtiği araç özelliklerine göre güncel ve benzer ilanları analiz ederek piyasa fiyat aralığı üretmektir.

## Ana Karar

Ürün tek bir veri kaynağına bağlı değildir. Her kaynak aynı ilan şemasını üretir ve aynı hattan geçer:

```text
Kaynak (demo | CSV | ileride partner API)
  -> SQLite ham ilan tablosu
  -> cleaning hattı
  -> benzer ilan filtreleme
  -> fiyat dağılımı ve piyasa aralığı
```

Kaynaklar `src/ingestion/sources/` altında, `ListingSource` arayüzünü uygular. Yeni bir kaynak eklemek analiz, API veya arayüzde değişiklik gerektirmez.

| Kaynak | Durum | Not |
| --- | --- | --- |
| Demo | Hazır | Sentetik, deterministik; herkesin projeyi veri olmadan çalıştırabilmesi için |
| CSV | Hazır | Kullanım izni olan her veri: partner dışa aktarımı, lisanslı veri seti, elle toplanan ilanlar |
| TSB kasko listesi | Hazır (aktarım) | Resmi, aylık, otomatikleştirilebilir sigorta referans değeri; ilan fiyatıyla karıştırılmaz |
| Partner / resmi API | Planlı | Aynı arayüzle eklenecek |

## Katalog Verisi

Arayüzde marka, seri ve model/paket seçimlerinin hazır gelmesi için `data/reference/vehicle_catalog.json` kullanılır.

Bu dosya statik bir eğitim datası değildir; yalnızca kullanıcı deneyimini iyileştiren referans katalogdur.

## Güncel İlan Verisi

Kullanıcı arayüzü veri toplamaz; yalnızca veritabanındaki temizlenmiş ilanları analiz eder. Varsayılan lokal veritabanı:

```text
data/runtime/vehicle_listings.sqlite3
```

## Sorumlu Kullanım

İlk prototipte ilanlar sahibinden.com'dan tarayıcıyla toplanıyordu. Bu yöntem kaynağın kullanım koşullarıyla çelişir, elle erişim doğrulaması gerektirdiği için otomatikleştirilemez ve site değiştikçe bozulur. Bu nedenle ürünün parçası olmaktan çıkarıldı; kod `src/experimental/sahibinden/` altında yalnızca araştırma prototipi olarak duruyor.

Sentetik demo verisi `source = demo` olarak saklanır, gerçek veriyle aynı veritabanına yüklenemez ve arayüzde her zaman etiketlenir.

## MVP Değeri

İlk MVP için model eğitimi şart değildir. Kullanıcıya değer üreten ilk çıktı:

- benzer ilan sayısı
- fiyat dağılımı
- medyan fiyat
- önerilen alt/üst piyasa aralığı
- benzer ilan listesi

Bu yaklaşım ürünün doğrudan kullanıcı problemine cevap vermesini sağlar.
