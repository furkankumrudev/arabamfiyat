# Sprint 1 - Proje ve Veri Temeli

**Çalışma biçimi:** Bireysel proje. Bu rapor, geliştiricinin gerçek çalışma notlarından hazırlanmıştır.

## Sprint Hedefi

Veri bilimi odağında uygulanabilir bir problem seçmek, ikinci el araç fiyat analizi ürününün veri ihtiyacını belirlemek ve güncel ilan verisini toplayabilecek ilk güvenilir yaklaşımı oluşturmaktı.

## Sprint Review

### Tamamlanan İşler

- İlgi alanı ve veri bilimi hedefleri doğrultusunda ikinci el araç fiyat analizi uygulaması fikri seçildi.
- Kullanıcının piyasa fiyatını grafiklerle inceleyebilmesi için güncel ilan verisine ihtiyaç olduğu belirlendi.
- Araç ilanı verisi sağlayabilecek kaynaklar araştırıldı ve kullanılacak veri kaynaklarına karar verildi.
- İlk scraper denemeleri yapıldı; ilan verisini daha güvenilir biçimde toplayabilen basit akışlar oluşturuldu.
- İlan kayıtlarını saklamak için SQLite tabanlı ilk veri şeması ve ham veri deposu oluşturuldu.
- Araç marka, seri ve model seçimi için katalog yapısının temeli oluşturuldu.
- Toplanan verilerin sonraki analiz ve arayüz çalışmalarında kullanılabilmesi için veri seti oluşturma yönü netleştirildi.

### Karşılaşılan Sorun ve Alınan Karar

İlk veri toplama denemelerinde scraper akışları kararsız çalıştı ve erişim sorunları yaşandı. Bu nedenle kapsamı çok geniş, karmaşık ve kırılgan yaklaşımlar yerine; daha yüzeysel, basit ve kontrol edilebilir veri toplama akışlarına odaklanma kararı alındı. Bu karar, çalışır scraper'lar ve kullanılabilir bir veri seti elde edilmesini sağladı.

### Sprint Çıktısı

- İkinci el araç fiyat analizi için net ürün yönü
- Güncel ilan verisini toplamak üzere belirlenmiş veri kaynakları
- Çalışan ilk scraper akışları ve analizde kullanılacak veri seti temeli
- Ham ilan verisini saklayabilecek SQLite altyapısı ve araç katalog temeli

## Sonraki Sprint Adımları

- Kullanıcının araç özelliklerini girebileceği uygulama arayüzünü geliştirmek
- Toplanan verileri kullanıcıya anlamlı grafik ve analiz olarak sunmak
- Ham veriyi analiz için güvenilir bir temiz veri tablosuna dönüştürmek
- Fiyat tahmini için kullanılabilecek yapay zeka modelinin araştırılması ve ilk prototipinin hazırlanması

## Retrospective

### Başla

- Arayüz prototipini ve kullanıcı akışını geliştirmeye başla.
- Veri temizleme kurallarını ve benzer araç karşılaştırma mantığını oluşturmaya başla.
- Fiyat tahmini için uygun model ve veri özelliklerini araştır.

### Bırak

- Erişim sorunu üreten, gereğinden karmaşık ve sürdürülebilir olmayan scraper denemelerine fazla zaman ayırmayı bırak.

### Devam Et

- Güncel veri ihtiyacını küçük ve kontrol edilebilir adımlarla doğrulamaya devam et.
- Veri kalitesini uygulama geliştirmeden önce kontrol etmeye devam et.

## Kanıtlar

[Teknik çalışma günlüğü](evidence/work-log.md), Sprint 1 ile ilişkili gerçek Git commitlerini listeler. Bu bireysel projede geriye dönük temsilî toplantı kaydı oluşturulmamıştır.

İlgili teknik çıktılar: ham ilan tablosu, veri temizleme hattı ve `data/reference/vehicle_catalog.json`.
