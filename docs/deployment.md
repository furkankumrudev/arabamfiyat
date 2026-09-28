# Docker ile Çalıştırma

Bu yapı, React arayüzü ve FastAPI servisinin tek bir yerel adres altında çalışmasını sağlar. Web uygulaması `http://localhost:8080` adresinden açılır; `/api` istekleri Nginx üzerinden FastAPI konteynerine yönlendirilir.

## Gereksinimler

- Docker Desktop
- Opsiyonel izinli SQLite veritabanı: `data/runtime/vehicle_listings.sqlite3` (yoksa demo verisi kullanılır)
- Opsiyonel kondisyon etkisi modeli: `data/models/kaggle_price_effect/kaggle_price_effect_model.cbm`

Veritabanı konteynere salt okunur kaynak olarak bağlanır ve Git'e eklenmez. İlk açılışta `api-runtime` adlı kalıcı volume'e kopyalanır; bu, Windows bind mount'larında SQLite dosya kilitleme sorunlarını önler. Volume dolu olduğunda tohumlama tekrarlanmaz, böylece biriken günlük snapshot'lar ve temizlenmiş tablo yeniden başlatmalarda korunur. Tohumu bilerek tazelemek için `RESEED_DB=1` kullanılır. Veritabanı yoksa API ilk açılışta sentetik demo verisini üretir ve yükler. `/api/health` bunu `demo_data: true` olarak bildirir, arayüz de her sayfada "Demo verisi" uyarısı gösterir; sentetik fiyatlar gerçek piyasa gibi sunulmaz. Boş başlatmak için `DEMO_DATA=0 docker compose up` kullanılır.

## Servisler

| Servis | Görev |
| --- | --- |
| `api` | FastAPI; veritabanını yalnızca okur |
| `scheduler` | Günlük bakım hattını çalıştırır; veritabanına yazan tek servis |
| `web` | Nginx üzerinde React arayüzü |

`scheduler`, `api` ile aynı imajı ve aynı `api-runtime` volume'unu kullanır. Tek yazar / çok okuyan bu düzen SQLite için güvenlidir.

### Zamanlama ayarları

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `PIPELINE_HOUR` | `3` | Günlük çalıştırma saati (UTC) |
| `PIPELINE_MINUTE` | `0` | Günlük çalıştırma dakikası (UTC) |
| `PIPELINE_RUN_ON_START` | `false` | Konteyner açılışında bir kez hemen çalıştır |

İlan toplama adımı bu hatta bilinçli olarak dahil değildir: tarayıcı sürüyor ve manuel erişim doğrulaması isteyebiliyor, bu yüzden operatör komutu olarak kalır.

## Çalıştırma

```bat
docker compose up --build
```

Uygulama:

```text
http://localhost:8080
```

API dokümantasyonu:

```text
http://localhost:8080/docs
```

## Canlı Ortama Alma Notu

Canlı ortamda SQLite ve model artefaktı Docker imajına eklenmemelidir. Bunlar kalıcı ve erişimi kontrollü bir volume veya izinli bir veri deposundan bağlanmalıdır. Ortam değişkenleriyle `SQLITE_DB_PATH` ve `CORS_ORIGINS` ayarlanabilir.

## Doğrulama

Docker Desktop kurulu bir ortamda aşağıdaki kontroller yapılmalıdır:

```bat
docker compose config
docker compose up --build
```

Ardından web ekranından araç değerleme akışı ve `http://localhost:8080/api/health` endpointi doğrulanmalıdır.

Health yanıtı veri akışının durumunu da bildirir:

```json
{
  "status": "ok",
  "database_available": true,
  "listing_count": 12345,
  "last_pipeline_success_at": "2026-09-21T03:00:12+00:00",
  "pipeline_age_hours": 6.4,
  "pipeline_stale": false
}
```

`status` alanı, hat 36 saatten uzun süredir başarıyla tamamlanmadıysa `degraded` olur. Hat hiç çalışmadıysa üç alan da `null` döner; sistem tahminde bulunmaz. Bu, durmuş bir veri akışının "sağlıklı" görünmesini engeller.
