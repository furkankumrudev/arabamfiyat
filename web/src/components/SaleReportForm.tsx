import { CheckCircle2, HandCoins } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { ValuationRequest } from "../types";

const digits = (value: string) => value.replace(/\D/g, "");
const formatDigits = (value: string) => value ? new Intl.NumberFormat("tr-TR").format(Number(value)) : "";
const thisMonth = () => new Date().toISOString().slice(0, 7);

// Actual sale prices are what listings cannot tell; each report makes future valuations better.
export function SaleReportForm({ vehicle }: { vehicle: ValuationRequest }) {
  const [salePrice, setSalePrice] = useState("");
  const [year, setYear] = useState(vehicle.year ? String(vehicle.year) : "");
  const [mileage, setMileage] = useState(vehicle.mileage_km != null ? String(vehicle.mileage_km) : "");
  const [soldMonth, setSoldMonth] = useState(thisMonth());
  const [city, setCity] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);
  if (!vehicle.brand || !vehicle.series) return null;
  const ready = Number(salePrice) >= 10_000 && Number(year) >= 1950;

  const submit = () => {
    if (!ready) return;
    setState("sending");
    setError(null);
    api.saleReport({
      brand: vehicle.brand!, series: vehicle.series!, model: vehicle.model || undefined,
      year: Number(year), mileage_km: mileage ? Number(mileage) : undefined, sale_price: Number(salePrice),
      sold_month: soldMonth || undefined, city: city.trim() || undefined,
      changed_parts: vehicle.changed_parts ?? undefined, painted_parts: vehicle.painted_parts ?? undefined,
    }).then(() => setState("sent")).catch((reason: Error) => { setError(reason.message); setState("idle"); });
  };

  if (state === "sent") return <section className="sale-report sent" role="status"><CheckCircle2 size={22} /><div><strong>Teşekkürler!</strong><p>Satış bilginiz kaydedildi. Aynı araç için yeterli bildirim biriktiğinde değerlemelerde satış fiyatı medyanı olarak görünecek.</p></div></section>;

  return <section className="sale-report" aria-label="Satış fiyatı bildirimi">
    <div className="sale-report-heading"><span className="eyebrow"><HandCoins size={14} />SATIŞ BİLDİRİMİ</span><h3>Bu aracı sattınız mı?</h3><p>İlan fiyatı pazarlığın başlangıcıdır. Gerçekte kaça sattığınızı paylaşırsanız {vehicle.brand} {vehicle.series} değerlemeleri daha doğru olur.</p></div>
    <div className="sale-report-grid">
      <label className="field"><span>Satış fiyatı</span><input inputMode="numeric" value={formatDigits(salePrice)} onChange={(event) => setSalePrice(digits(event.target.value))} placeholder="Örn. 950.000" /></label>
      <label className="field"><span>Model yılı</span><input type="number" min="1950" max={new Date().getFullYear() + 1} value={year} onChange={(event) => setYear(event.target.value)} placeholder="Örn. 2020" /></label>
      <label className="field"><span>Kilometre</span><input inputMode="numeric" value={formatDigits(mileage)} onChange={(event) => setMileage(digits(event.target.value))} placeholder="Örn. 90.000" /></label>
      <label className="field"><span>Satış ayı</span><input type="month" value={soldMonth} max={thisMonth()} onChange={(event) => setSoldMonth(event.target.value)} /></label>
      <label className="field"><span>Şehir (isteğe bağlı)</span><input value={city} maxLength={60} onChange={(event) => setCity(event.target.value)} placeholder="Örn. Ankara" /></label>
      <button className="primary-button" onClick={submit} disabled={!ready || state === "sending"}>{state === "sending" ? "Gönderiliyor…" : "Satışı paylaş"}</button>
    </div>
    {error && <p className="sale-report-error">{error}</p>}
    <small>Kimlik bilgisi istenmez. Tek bir bildirim hiçbir yerde gösterilmez; en az 3 bildirim biriktiğinde yalnızca medyanı görünür.</small>
  </section>;
}
