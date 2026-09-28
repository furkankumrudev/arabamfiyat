# Data

Bu klasör ArabamFiyat.com'un referans ve yerel çalışma verilerini tutar.

## Klasörler

```text
data/
  examples/
    listings_example.csv      # CSV aktarımı için örnek dosya
  reference/
    vehicle_catalog.json
    kasko/                    # aylık TSB kasko listeleri
  runtime/
    vehicle_listings.sqlite3  # yerel veritabanı (Git'e dahil değil)
```

## Reference Data

`data/reference/vehicle_catalog.json`, arayüzdeki marka, seri ve model/paket seçimlerini besleyen katalog dosyasıdır.

Bu dosya Git'e dahildir; çünkü uygulamanın dropdown seçenekleri için sabit referans veri gibi kullanılır.

## Runtime Data

`data/runtime/vehicle_listings.sqlite3`, analizde kullanılan ilan kayıtlarını tutan yerel SQLite veritabanıdır. İçine iki yolla veri girer:

- `scripts/load_demo_data`: sentetik demo verisi (arayüzde "Demo verisi" olarak etiketlenir)
- `scripts/import_listings <dosya.csv>`: kullanım izni olan gerçek veri

İkisi aynı veritabanında karıştırılmaz. Demodan gerçek veriye geçmek için veritabanı dosyasını silip gerçek veriyi yükle.

Bu klasör Git'e dahil edilmez. İçindeki veritabanı makineye özel çalışma verisidir.

## Veri Akışı

```text
Demo verisi veya CSV aktarımı
  -> vehicle_listings ham tablosunu günceller
  -> cleaning hattı vehicle_listings_clean tablosunu üretir
  -> FastAPI ve React arayüzü temiz tablodan piyasa analizini gösterir
```

## Not

Projenin ana yaklaşımı hazır statik fiyat dataset'i yerine güncel ilan verisiyle piyasa aralığı üretmektir.
