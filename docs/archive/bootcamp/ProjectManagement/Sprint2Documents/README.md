# Sprint 2 - Veri Bağlantılı Arayüz

**Çalışma biçimi:** Bireysel proje. Bu rapor, geliştiricinin gerçek çalışma notlarından hazırlanmıştır.

## Sprint Hedefi

İlk kullanıcı arayüzü demosunu oluşturmak, toplanan ilan verisini uygulamaya API üzerinden bağlamak ve kullanıcıya sunulacak web deneyiminin yönünü belirlemekti.

## Sprint Review

### Tamamlanan İşler

- Araç fiyat analizi fikrini kullanıcıya gösterebilmek için ilk arayüz demosu oluşturuldu.
- Uygulamanın veri katmanı ile arayüzü arasında API tabanlı bağlantı kuruldu.
- Toplanan ve temizlenen ilan verisinin arayüzde kullanılabilmesi için gerekli entegrasyon tamamlandı.
- Ham ilanları koruyup analizde kullanılacak ayrı bir temiz tablo üreten cleaning hattı tamamlandı; marka/model, fiyat, kilometre ve konum alanları normalize edildi, tekrar eden veya eksik kayıtlar ayrıştırıldı.
- Kullanıcının seçtiği araçla daha yakın ilanları yıl, kilometre, model yakınlığı ve veri güncelliğine göre puanlayan piyasa analiz motoru geliştirildi.
- Yeterli kayıt olduğunda aykırı fiyatlar dışarıda bırakılarak piyasa aralığı oluşturuldu; ilan sayısı yetersizse uygulamanın bunu açıkça göstermesi sağlandı.
- Gerçek ilan tarihlerinden fiyat trendi, model yılı ve kilometre ilişkisi grafiklerinin ilk sürümü eklendi.
- Gelecekte günlük fiyat değişimlerinin gerçek veriye dayanarak gösterilebilmesi için günlük piyasa özeti (snapshot) altyapısı oluşturuldu.
- İlk demo arayüzü değerlendirildi; görsel kalite ve kullanım deneyiminin hedeflenen seviyede olmadığı görüldü.
- Streamlit prototipini geliştirmeye devam etmek yerine, daha profesyonel bir web arayüzü için HTML, CSS ve JavaScript tabanlı bir yapıya geçme kararı alındı. Nihai uygulamada bu yön React tabanlı arayüz olarak hayata geçirildi.

### Karşılaşılan Sorun ve Alınan Karar

İlk arayüz demosu, veri bağlantısını doğrulamak için yararlı oldu; ancak ürünün görünümü ve kullanıcı deneyimi hedeflenen profesyonel seviyeye ulaşmadı. Bu nedenle Streamlit, ilk prototip olarak korunurken ana ürün arayüzünün modern web teknolojileriyle yeniden tasarlanmasına karar verildi.

### Sprint Çıktısı

- Gerçek ilan verisine bağlı çalışan ilk kullanıcı arayüzü demosu
- API ile arayüz arasındaki veri akışının doğrulanması
- Normalizasyon ve tekrar temizliği uygulanmış analiz tablosu
- Benzer ilan puanlama, aykırı fiyat temizliği ve gerçek ilan tarihli ilk piyasa grafikleri
- Daha profesyonel web uygulaması için net teknik ve tasarımsal yön

## Sonraki Sprint Adımları

- Web arayüzünü geliştirip okunaklı ve kullanıcı odaklı bir deneyime dönüştürmek
- Araç fiyat analizi ve değerleme akışını uygulamaya eklemek
- Grafikler, filtreler ve piyasa karşılaştırması ile analiz ekranlarını güçlendirmek
- Günlük snapshot verisi biriktikçe gerçek dönemsel fiyat değişimlerini göstermek

## Retrospective

### Başla

- Ana kullanıcı arayüzünü modern web teknolojileriyle geliştirmeye başla.
- Kullanıcının araç özelliklerini girip piyasa analizi alacağı değerleme akışını tasarla.
- Düşük örneklem veya geçmiş veri eksikliği olduğunda uygulamanın kesin olmayan sonuç üretmemesini sürdür.

### Bırak

- Streamlit prototipini nihai kullanıcı arayüzü seviyesine taşımaya çalışmayı bırak.

### Devam Et

- Arayüzü gerçek veri ve API sonuçlarıyla test etmeye devam et.
- Erken demo oluşturarak kullanıcı deneyimi sorunlarını görünür kılmaya devam et.

## Kanıtlar

[Teknik çalışma günlüğü](evidence/work-log.md) gerçek Git commitlerini, [piyasa trendleri ekranı](evidence/market-trends.png) çalışan ürünün gerçek ekranını içerir. Bu bireysel projede geriye dönük temsilî toplantı kaydı oluşturulmamıştır.

İlgili teknik çıktılar: `src/maintenance/clean_vehicle_data.py`, `src/analysis/market_engine.py`, `src/api/` ve `src/api/services/trend_service.py`.
