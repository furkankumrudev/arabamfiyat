# Product Backlog

Durumlar proje ilerledikce gercek sprint kararlarina gore guncellenir.

| ID | User story | Oncelik | Durum | Kabul kriteri |
| --- | --- | --- | --- | --- |
| AF-01 | Kullanici olarak marka, seri ve model secebilmeliyim. | Must | Done | Secimler katalog ve veritabanindan gelir. |
| AF-02 | Kullanici olarak yil ve kilometre ile analizi daraltabilmeliyim. | Must | Done | Filtreler API sorgusuna yansir. |
| AF-03 | Kullanici olarak benzer ilanlardan fiyat araligi gorebilmeliyim. | Must | Done | Aykiri fiyatlar disarida birakilir, guven seviyesi gosterilir. |
| AF-04 | Kullanici olarak piyasa trendini gercek ilan tarihlerinden gorebilmeliyim. | Must | Done | Grafik sahte tarihsel veri uretmez. |
| AF-05 | Sistem olarak yeni ilanlari temizleyip analiz tablosuna aktarmaliyim. | Must | Done | Ham kayitlar cleaning hattindan gecerek analiz tablosuna aktarilir. |
| AF-06 | Kullanici olarak aracimin tahmini piyasa degerini gorebilmeliyim. | Must | Done | FastAPI mevcut piyasa motorunu kullanir. |
| AF-07 | Sistem olarak gunluk piyasa ozetlerini saklamaliyim. | Should | Done | Tekrarlayan gun kaydi olusmaz; gunluk snapshot betigi ve idempotent test bulunur. |
| AF-08 | Kullanici olarak yeterli gecmis veri yoksa bunu acikca gormeliyim. | Must | Done | 30/90/yillik alanlarda sahte yuzde gosterilmez. |
| AF-09 | Kullanici olarak boya ve degisen bilgisinin guncel piyasa degerine etkisini gorebilmeliyim. | Must | Done | Kaggle ile ogrenilen kondisyon katsayisi, guncel ilanlardan uretilen degerin uzerine uygulanir. |
| AF-10 | Gelistirici olarak kondisyon etkisi modelini tekrar egitip metriklerini kaydedebilmeliyim. | Should | Done | Train/test ayrimi, MAE, RMSE, SMAPE ve model artefakti egitim komutuyla uretilir. |
| AF-11 | Kullanici olarak urunu mobil ekranda kullanabilmeliyim. | Should | Done | 360px gorunumde yatay tasma olmaz. |
| AF-12 | Juri olarak urunu yerelde veya deploy edilmis ortamda calistirabilmeliyim. | Must | Done | Docker ile tek komutlu yerel kurulum ve calisan demo dogrulandi. |
| AF-13 | Juri olarak modelin veri kaynagini, metriklerini ve sinirlarini inceleyebilmeliyim. | Must | Done | [Model karti](../../../model-card.md) modelin kullanim amacini ve sinirlarini aciklar. |
