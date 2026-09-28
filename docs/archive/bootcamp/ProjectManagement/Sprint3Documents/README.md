# Sprint 3 - Yapay Zeka Destekli Değerleme ve Teslim Hazırlığı

**Çalışma biçimi:** Bireysel proje. Bu rapor, geliştiricinin gerçek çalışma notlarından hazırlanmıştır.

## Sprint Hedefi

Profesyonel web arayüzünü tamamlamak ve araç özelliklerine göre değerleme yapan yapay zeka destekli analiz akışını güvenilir biçimde uygulamaya eklemekti.

## Sprint Review

### Tamamlanan İşler

- ArabamFiyat.com için daha düzenli, okunaklı ve kullanıcı odaklı React web arayüzü geliştirildi.
- Kullanıcının araç özelliklerini girerek piyasa analizi ve fiyat değerlendirmesi alacağı akış tamamlandı.
- Araç özellikleri, kilometre, model yılı, boya ve değişen bilgilerini değerlendirebilen CatBoost tabanlı model geliştirildi.
- Eğitim verisi için zorunlu alan, mantıksal sınır ve grup içi uç fiyat temizliği uygulandı; eğitim/test ayrımı ile model metrikleri kaydedildi.
- Model eğitimi için kullanılan Kaggle veri setinin güncel fiyatları temsil etmediği tespit edildi.
- Eski veri setindeki fiyatı doğrudan güncel tahmin olarak kullanmak yerine, modelden yalnızca fiyatı etkileyen parametrelerin göreli etkisi alındı.
- Güncel fiyat ve piyasa aralığı, yerel temiz ilan verisinden üretildi; yapay zeka modeli ise boya ve değişen bilgisinin bu güncel değere etkisini oran olarak uyguladı.
- Kondisyon katsayısı aşırı sonuç üretmemesi için güvenli bir aralıkta sınırlandı; model, fiyatı yükselten bir etki üretmeyecek şekilde kullanıldı.
- Sonuç ekranına fiyat aralığı, kullanıcının girdiği fiyatın piyasa içindeki konumu, referans ilan özeti ile temiz araç ve tüm ilan karşılaştırma grafikleri eklendi.
- Model kartı, mimari dokümanı ve Docker ile tek komutlu yerel çalışma yapısı eklendi.
- API servisleri, veri bulunmayan ve düşük örneklemli durumlar için test edildi; React production build'i ve Docker sağlık kontrolü doğrulandı.

### Karşılaşılan Sorun ve Alınan Karar

Kaggle veri seti yaklaşık iki yıl öncesine ait olduğu için, modelin doğrudan ürettiği fiyatlar güncel piyasa koşullarından farklılaşabiliyordu. Bu nedenle eski veri setini güncel fiyatın kaynağı olarak kullanmak doğru bulunmadı. Çözüm olarak güncel ilanlardan benzer araçların piyasa değeri hesaplandı; Kaggle ile eğitilen model yalnızca boya ve değişen gibi kondisyon bilgilerinin fiyat üzerindeki göreli etkisini hesaplamak için kullanıldı.

### Sprint Çıktısı

- Güncel ilan verisine dayalı araç piyasa analizi ve fiyat aralığı
- Boya ve değişen etkisini güncel piyasa değerine uygulayan yapay zeka destekli değerleme
- Profesyonel React arayüzü, grafikler ve kullanıcı değerleme akışı
- Birim testleri, production build ve Docker ile API/web uygulamasını tek komutla çalıştırabilen yerel teslim yapısı

## Sonraki Adımlar

- Gerçek kullanıcı akışı ekran görüntülerini ve proje demo videosunu hazırlamak
- Proje belgelerini son kez gözden geçirip GitHub'a göndermek
- Uygulamayı çevrimiçi bir ortama yayınlamak veya deploy hazırlığını belgelemek

## Retrospective

### Başla

- Model sonuçlarını güncel piyasa verisiyle birlikte değerlendirmeye devam et.
- Teslim için ekran görüntüsü, demo videosu ve deploy kanıtlarını hazırlamaya başla.
- Canlı ortamda yalnızca izinli ve güncel veri kaynağı kullanılmasını planla.

### Bırak

- Eski bir veri setinden öğrenilen mutlak fiyatı, güncel fiyat tahmini olarak doğrudan kullanmayı bırak.

### Devam Et

- Güncel ilan verisini piyasa değeri için temel kaynak olarak kullanmaya devam et.
- Yapay zeka modelini açıklanabilir ve sınırlılıkları belgelenmiş bir destek katmanı olarak kullanmaya devam et.

## Kanıtlar

[Değerleme sonucu](evidence/valuation-result.png) gerçek kullanıcı akışını; [teknik doğrulama](evidence/verification.md) test, production build ve Docker sonuçlarını içerir. Model metrikleri [model kartında](../../../../model-card.md) ayrıntılı biçimde belgelenmiştir.

İlgili teknik çıktılar: `src/ml/`, `tests/test_ml_training.py`, `tests/test_api_services.py`, `web/`, `docker-compose.yml`, `docs/model-card.md` ve `docs/architecture.md`.
