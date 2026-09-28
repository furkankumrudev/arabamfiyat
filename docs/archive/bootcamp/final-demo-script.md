# Final Demo Akışı

Bu akış, üç dakikalık proje videosunda ana kullanıcı yolculuğunu açık ve kısa biçimde göstermek içindir.

## 0:00 - 0:20 | Problem ve ürün

ArabamFiyat.com'un ikinci el araç ilanlarındaki güncel piyasa fiyatını analiz ettiğini söyleyin. Kullanıcının araç değeri hakkında daha bilinçli karar vermesini hedeflediğini belirtin.

## 0:20 - 0:45 | Veri yaklaşımı

Güncel piyasa aralığının yerel temiz ilan verisinden hesaplandığını gösterin. Kaggle verisinin eski olduğu için mutlak güncel fiyat kaynağı olarak kullanılmadığını; yalnızca boya ve değişen parçanın göreli etkisini öğrenmekte kullanıldığını açıklayın.

## 0:45 - 1:20 | Piyasa trendleri

`Piyasa Trendleri` ekranını açın. Marka, seri ve model filtrelerini seçin; ilan sayısı, medyan/ortalama, fiyat trendi ile yıl ve kilometre grafiklerini gösterin.

## 1:20 - 2:25 | Araç değerleme

`Araç Değerleme` ekranında marka, seri, model, yıl, kilometre, istenen fiyat, değişen ve boyalı parça bilgilerini girin. `Araç değerini hesapla` düğmesine basın. Tahmini piyasa değeri, önerilen aralık, kullanıcının fiyat konumu, kondisyon etkisi ve referans ilan özetini açıklayın.

## 2:25 - 2:50 | Teknik mimari ve doğrulama

FastAPI, React, SQLite ve CatBoost rollerini kısaca anlatın. Docker ile `http://localhost:8080` üzerinde çalıştığını, backend testleri ve React production build'in başarılı olduğunu gösterin.

## 2:50 - 3:00 | Sınır ve kapanış

Sonuçların ilan verisinin kapsamına bağlı olduğunu; düşük örneklemde uygulamanın bunu belirttiğini söyleyin. Projenin güncel veri ve açıklanabilir kondisyon etkisini birlikte kullanma yaklaşımını özetleyin.
