# ArabamFiyat.com

ArabamFiyat.com, ikinci el araç alıcı ve satıcılarının benzer araçlardaki fiyat belirsizliğini azaltmak için geliştirilmiş veri destekli bir karar destek uygulamasıdır.

Kullanıcı marka, seri, model, yıl ve kilometre bilgisini girer. Uygulama yerel SQLite veritabanındaki temizlenmiş güncel ilanları karşılaştırır; piyasa değeri, önerilen fiyat aralığı, fiyat trendi ve yıl/kilometre ilişkisini gösterir. Boya ve değişen bilgisi varsa, ML modeli bu durumun göreli etkisini güncel piyasa değerine uygular.

> Bu ürün bir ekspertiz ya da kesin satış fiyatı hizmeti değildir. Sonuçlar, mevcut ilan verisinden üretilen karar destek tahminleridir.

## Demo

[2 dakikalık ürün demosunu YouTube'da izle](https://youtu.be/CIdeayz5XvY)

## Takım

| Takım adı | Üye | Roller |
| --- | --- | --- |
| ArabamFiyat.com | [Furkan Kumru](https://github.com/furkankumrudev) | Product Owner, Scrum Master, Developer |

Bu proje bireysel olarak geliştirildi; ürün planlama, veri/ML geliştirme, backend, frontend ve test sorumlulukları aynı geliştirici tarafından yürütüldü.

## Ana Teknolojiler

```text
React + TypeScript + Vite  ->  FastAPI  ->  SQLite
                                      ->  Piyasa analiz motoru
                                      ->  CatBoost kondisyon etkisi modeli
```

- Ana kullanıcı arayüzü: `web/`
- API: `src/api/`
- Piyasa motoru: `src/analysis/market_engine.py`
- Veri temizleme: `src/maintenance/clean_vehicle_data.py`
- Model eğitimi ve çıkarımı: `src/ml/`

Final ürün arayüzü React uygulamasıdır; demo ve geliştirme akışı `web/` klasöründen yürütülür.

## Hızlı Başlangıç

### Gereksinimler

- Python 3.11 veya üstü
- Node.js 20 veya üstü
- npm

Başka bir şey gerekmez: ilan veritabanı yoksa uygulama sentetik demo verisiyle açılır.

### Kurulum

Windows:

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
cd web
npm ci
cd ..
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
(cd web && npm ci)
```

Bağımlılık dosyaları:

| Dosya | İçerik |
| --- | --- |
| `requirements-api.txt` | API, analiz ve ML çalışma zamanı (ürünün ihtiyacı olan her şey) |
| `requirements.txt` | `requirements-api.txt` ile aynı; bu adı arayan barındırma servisleri için |
| `requirements-dev.txt` | Çalışma zamanı + lint ve test araçları |
| `requirements-experimental.txt` | Çalışma zamanı + deneysel sahibinden.com scraper'ı |

Surumler sabitlenmistir; yerel kurulum, CI ve container imajlari ayni paketleri kullanir.

`.env` dosyasında `SQLITE_DB_PATH` ile analiz veritabanının yolunu tanımlayabilirsin. Varsayılan yol:

```text
data/runtime/vehicle_listings.sqlite3
```

Veritabanı ve model artefaktları Git'e dahil edilmez. Veri yüklemenin yolları [Veri Kaynakları](#veri-kaynakları) bölümünde.

### Demo verisi

İlan verin yoksa sentetik demo verisini yükle:

```bat
scripts\load_demo_data.bat
```

```bash
./scripts/load_demo_data.sh
```

Komut 6.000 sentetik ilan üretir, temizleme hattından geçirir ve 14 haftalık piyasa özeti oluşturur. Arayüz bu durumda üstte **"Demo verisi"** uyarısı gösterir; sentetik fiyatlar hiçbir yerde gerçek piyasa gibi sunulmaz. `scripts\start_local.bat` ve Docker akışı, veritabanı yoksa bunu kendiliğinden yapar.

### Docker ile demo (önerilen)

Docker Desktop açıksa uygulamanın tamamını tek komutla başlat:

```bat
docker compose up --build
```

Ardından uygulamayı `http://localhost:8080` adresinden aç. Bu akışta React arayüzü ve FastAPI aynı adres üzerinden birlikte çalışır.

`data/runtime/vehicle_listings.sqlite3` varsa o kullanılır; yoksa API ilk açılışta demo verisini yükler. Boş başlatmak için `DEMO_DATA=0` ver.

Calisma veritabani `api-runtime` adli kalici bir volume uzerinde tutulur:
`data/runtime/` altindaki veritabani yalnizca volume bos oldugunda tohum olarak
kopyalanir, sonraki her yeniden baslatmada birikmis gunluk snapshot'lar korunur.
Tohumu bilerek tazelemek icin `RESEED_DB=1` ile baslat.

### Geliştirme ortamı

Windows'ta `scripts\start_local.bat` dosyasına çift tıkla: veritabanı yoksa demo verisini yükler, API ve web'i ayrı pencerelerde açar, siteyi tarayıcıda kendiliğinden açar.

Elle başlatmak için iki ayrı terminal aç. Windows:

```bat
scripts\run_api.bat
scripts\run_web_app.bat
```

Linux / macOS:

```bash
./scripts/run_api.sh
./scripts/run_web_app.sh
```

Her bakim komutunun iki platformda da karsiligi vardir (`scripts/*.bat` ve `scripts/*.sh`); POSIX scriptleri ortak ayarlari `scripts/lib.sh` uzerinden paylasir.

Adresler:

```text
Web:      http://127.0.0.1:5173
API:      http://127.0.0.1:8000
API docs: http://127.0.0.1:8000/docs
```

## Doğrulama

Lint, backend testlerini ve React production build'ini tek komutla çalıştır:

```bat
scripts\verify_project.bat
```

```bash
./scripts/verify_project.sh
```

Manuel olarak:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m unittest discover -s tests -v
(cd web && npm run build)
```

Ayni uc adim her push ve pull request'te GitHub Actions uzerinde calisir
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): backend Python 3.11 ve
3.12 uzerinde, frontend Node 22 uzerinde, ayrica her iki container imaji da
derlenir.

## ML Modeli

Model, güncel TL fiyatını doğrudan tahmin etmek için kullanılmaz. Eski eğitim verisinden boya ve değişen durumunun göreli etkisini öğrenir; bu katsayı güncel ilanlardan hesaplanan piyasa değerine uygulanır.

Eğitim ve metrikler için [model kartına](docs/model-card.md), sistemin bileşenleri için [mimari dokümanına](docs/architecture.md) bak.

Yerel Kaggle CSV dosyası proje kökünde `car_price_prediction.csv` adıyla varsa modeli yeniden eğitmek için:

```bat
scripts\train_price_model.bat
```

## Veri Kaynakları

Analiz katmanı ilanların nereden geldiğini bilmez. Her kaynak aynı ilan şemasını (`src/ingestion/schema.py`) üretir, aynı ham tabloya yazılır ve aynı temizleme hattından geçer:

```text
kaynak (demo | CSV | ileride partner API)  ->  vehicle_listings  ->  temizleme  ->  analiz + API
```

| Kaynak | Komut | Ne zaman |
| --- | --- | --- |
| Demo verisi | `scripts/load_demo_data` | Denemek, sunmak, geliştirmek |
| CSV dosyası | `scripts/import_listings <dosya.csv>` | Kullanım izni olan her veri: partner dışa aktarımı, lisanslı veri seti, elle toplanan ilanlar |
| TSB kasko değer listesi | `data/reference/kasko/` klasörü | Aylık resmi **sigorta referans değeri**; ilan fiyatıyla karıştırılmaz, ayrı tabloda tutulur |

Yeni bir kaynak eklemek, `ListingSource` arayüzünü (`src/ingestion/sources/base.py`) uygulayan küçük bir sınıf yazmaktır.

### CSV ile kendi verini yüklemek

Başlıklar şemanın sütun adlarıdır. Zorunlu olanlar: `title, brand, series, model, year, mileage_km, price`. İsteğe bağlı olanlar arasında `city, fuel_type, transmission, body_type, listing_date, source_listing_id` bulunur. Virgül veya noktalı virgül ile ayrılmış dosyalar ve `1.250.000 TL`, `85.000 km` gibi Türkçe yazımlar okunur. Örnek dosya: [data/examples/listings_example.csv](data/examples/listings_example.csv).

```bash
./scripts/import_listings.sh data/examples/listings_example.csv --source-name ornek
```

Zorunlu bir sütun eksikse aktarım hiçbir şey yazmadan durur ve dosyada gördüğü başlıkları listeler. Aynı dosyayı tekrar yüklemek kayıtları çoğaltmaz. Demo verisi ile gerçek veri aynı veritabanında karıştırılmaz; komut bunu reddeder.

Referans listelerinin nasıl bırakılacağı [data/reference/kasko/README.md](data/reference/kasko/README.md) dosyasında anlatılır.

### Deneysel: sahibinden.com scraper'ı

Projenin ilk sürümünde ilanlar sahibinden.com'dan tarayıcıyla toplanıyordu. Bu kod [src/experimental/sahibinden/](src/experimental/sahibinden/README.md) altında araştırma prototipi olarak duruyor. Ürün ona bağlı değildir ve varsayılan kurulumla gelmez; neden bırakıldığı klasörün README'sinde anlatılır.

## Günlük Veri Akışı

Referans aktarımı, analiz tablosunun tazelenmesi ve günlük piyasa özeti tek bir bakım hattında toplanmıştır:

```text
kasko liste kutusu -> import_reference_values (yeni donem yoksa atlanir)
ham ilan tablosu   -> clean_vehicle_data -> save_market_snapshot -> pipeline_runs kaydi
```

Tek seferlik çalıştırma:

```bash
./scripts/run_pipeline.sh
```

```bat
scripts\run_pipeline.bat
```

Sürekli çalıştırma (her gün 03:00 UTC, `PIPELINE_HOUR` / `PIPELINE_MINUTE` ile değiştirilir):

```bash
./scripts/run_scheduler.sh
```

Docker akışında bunu `scheduler` servisi üstlenir; `docker compose up` ile birlikte açılır.

Aylık liste günde bir kez kontrol edilir; yeni dönem yoksa adım `skipped` olarak kaydedilir — bu bir hata değildir ve hattı bayat göstermez.

Hattın her adımı, başarılı da olsa başarısız da olsa `pipeline_runs` tablosuna yazılır. Bir adım hata alırsa hat durmaz: sonraki adım yine çalışır ve hata kaydedilir. `/api/health` bu kayıtlara bakarak son başarılı çalışmayı, üzerinden geçen saati ve hattın bayatlayıp bayatlamadığını bildirir; 36 saati aşan sessizlikte `status` alanı `degraded` olur. Böylece durmuş bir veri akışı sessizce sağlıklı görünmez.

İlan verisini yüklemek bu hattın parçası değildir: kaynağa göre değişen, bilinçli yapılan bir işlemdir (`scripts/import_listings`, `scripts/load_demo_data`). Hat, veritabanında ne varsa onu tazeler.

## Veri İlkeleri

- Uygulama analizde temizlenmiş ilan tablosunu tercih eder; temiz tablo yoksa ham tabloya güvenli biçimde geri döner.
- Tarihsel trendler yalnızca gerçekten kaydedilmiş tarih veya snapshot verisinden üretilir.
- Geçmiş veri yetersizse uygulama sahte değişim yüzdesi ya da düz çizgi göstermez.
- Veri alma katmanı kaynaktan bağımsızdır; izinli veri kaynakları, resmi API'ler veya partner akışları aynı arayüzle eklenir.
- Sentetik demo verisi `source = demo` olarak saklanır, gerçek veriyle aynı veritabanına yüklenemez ve arayüzde her zaman etiketlenir.

## Dokümantasyon

- [Ürün vizyonu](docs/product-vision.md)
- [Hedef kitle](docs/target-audience.md)
- [Pazar araştırması](docs/market-research.md)
- [Veri sözlüğü](docs/data-dictionary.md)
- [Model kartı](docs/model-card.md)
- [Mimari](docs/architecture.md)
- [Docker ile çalıştırma](docs/deployment.md)
- [Bootcamp teslim kontrol listesi](docs/bootcamp-delivery.md)
- [Sprint ve backlog belgeleri](ProjectManagement/README.md)

## Lisans

Bu repo [MIT License](LICENSE) altında lisanslanmıştır.
