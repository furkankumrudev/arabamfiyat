import { AlertTriangle, BadgePercent, CalendarRange, Gauge, ShieldCheck, Sparkles } from "lucide-react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { ReferenceMileagePoint, ReferencePricePoint, TrendPoint, ValuationResponse } from "../types";
import { money, number, percent } from "../utils/format";
import { EmptyState } from "./StatePanels";

function ConditionAdjustmentCard({ data }: { data: ValuationResponse }) {
  // Entered damage that could not be applied must be visible, not silently dropped.
  if (data.condition_adjustment_percent == null) {
    if (!data.condition_adjustment_note) return null;
    return <div className="condition-adjustment-card"><div><span className="eyebrow"><BadgePercent size={14} />DURUM ETKİSİ</span><strong>Hesaba katılmadı</strong></div><p>{data.condition_adjustment_note} Gösterilen değer boya ve değişen durumunu içermez.</p></div>;
  }
  const unchanged = data.condition_adjustment_percent === 0;
  return <div className="condition-adjustment-card"><div><span className="eyebrow"><BadgePercent size={14} />DURUM ETKİSİ</span><strong>{unchanged ? "Referans durum" : percent(data.condition_adjustment_percent)}</strong></div><p>{data.condition_adjustment_note}</p></div>;
}

const MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
const formatPeriod = (period: string) => {
  const [year, month] = period.split("-").map(Number);
  return month ? `${MONTHS[month - 1]} ${year}` : period;
};

function ReferenceValueCard({ data }: { data: ValuationResponse }) {
  const reference = data.reference_value;
  if (!reference) return null;
  const demo = reference.source === "demo";
  const ratio = reference.market_to_reference_percent;
  const matchText = reference.match === "model"
    ? `Paket eşleşmesi: ${reference.matched_name}`
    : `Serinin ${reference.model_year} model ${number(reference.candidate_count)} paketinin medyanı (paket bazında eşleşme yok)`;
  return <div className="reference-value-card">
    <div>
      <span className="eyebrow"><ShieldCheck size={14} />{demo ? "DEMO KASKO DEĞERİ" : "TSB KASKO DEĞERİ"} · {formatPeriod(reference.period)}</span>
      <strong>{money(reference.value)}</strong>
    </div>
    <p>{matchText}.{ratio != null && <> İlan piyasası bu değerin <b>%{Math.round(ratio)}</b> seviyesinde.</>}</p>
    <small>{demo ? "Sentetik demo listesinden üretildi. " : ""}Sigorta referans değeridir; ilan veya satış fiyatı değildir.</small>
  </div>;
}

function ComparisonSummary({ data }: { data: ValuationResponse }) {
  const summary = data.comparison_summary;
  if (!summary) return null;
  const usesAllMatches = summary.selection_mode === "all_matching";
  const selectionDescription = summary.clean_only
    ? usesAllMatches ? "Seçilen modeldeki temiz beyanlı ilanların tamamı kullanıldı" : `Temiz beyanlı ilanlar · ${summary.selection_note}`
    : usesAllMatches ? "Tüm eşleşen ilanlar fiyat aykırıları ayıklandıktan sonra kullanıldı" : summary.selection_note;
  return <section className="comparison-summary">
    <div className="comparison-heading"><div><span className="eyebrow">PİYASA KARŞILAŞTIRMASI</span><h3>Referans ilan grubu</h3></div><p>{selectionDescription}</p></div>
    <div className="comparison-grid">
      <div><span>Toplam eşleşen</span><strong>{number(summary.matched_listing_count)}</strong><small>seçilen modeldeki ilanlar</small></div>
      <div><span>Analize giren</span><strong>{number(summary.used_listing_count)}</strong><small>{summary.outlier_count ? `${number(summary.selected_listing_count)} yakındaki ilanın ${number(summary.outlier_count)} aykırı fiyatı çıkarıldı` : usesAllMatches ? "tüm eşleşmeler kullanıldı" : "yakınlık aralığındaki tüm ilanlar kullanıldı"}</small></div>
      <div><span><CalendarRange size={14} />Referans yıl</span><strong>{summary.median_year ?? "—"}</strong><small>medyan model yılı</small></div>
      <div><span><Gauge size={14} />Referans kilometre</span><strong>{number(summary.median_mileage_km)} km</strong><small>medyan kilometre</small></div>
    </div>
  </section>;
}

function MarketRangeCard({ data }: { data: ValuationResponse }) {
  return <div className={`range-card${data.status === "low_sample" ? " leading" : ""}`}>
    <p>Önerilen piyasa aralığı</p>
    <strong>{money(data.recommended_low_price)} — {money(data.recommended_high_price)}</strong>
    <div className="range-card-details">
      <span>Medyan fiyat <b>{money(data.median_price)}</b></span>
      {data.asking_price != null && <span className={`price-assessment ${data.price_assessment === "Piyasa içinde" ? "within" : ""}`}>{data.price_assessment ?? "Fiyat karşılaştırması"}<b>{money(data.asking_price)}</b></span>}
    </div>
  </div>;
}

function compactPrice(value: number) {
  if (value >= 1_000_000) return `₺${(value / 1_000_000).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} Mn`;
  return `₺${Math.round(value / 1_000).toLocaleString("tr-TR")} bin`;
}

type PriceScatterPoint = ReferencePricePoint & { lane: number; is_recommended: boolean };

function PriceScatterTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: PriceScatterPoint }> }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <div className="price-density-tooltip">
    <strong>{money(point.price)}</strong>
    <span>{point.year ?? "Yıl bilgisi yok"} · {point.mileage_km == null ? "Kilometre bilgisi yok" : `${number(point.mileage_km)} km`}</span>
    <small>{point.is_recommended ? "Önerilen piyasa aralığında" : "Önerilen piyasa aralığı dışında"}</small>
  </div>;
}

function PriceDistribution({ data }: { data: ValuationResponse }) {
  const points = data.reference_price_points ?? [];
  const low = data.recommended_low_price;
  const median = data.median_price;
  const high = data.recommended_high_price;
  if (!points.length || low == null || median == null || high == null) return null;

  const laneCount = Math.min(8, Math.max(3, Math.ceil(Math.sqrt(points.length))));
  const chartData: PriceScatterPoint[] = [...points].sort((left, right) => left.price - right.price).map((point, index) => ({
    ...point,
    lane: (index % laneCount) + 1,
    is_recommended: point.price >= low && point.price <= high,
  }));
  const domainValues = [...points.map((point) => point.price), low, high];
  if (data.asking_price != null) domainValues.push(data.asking_price);
  const minimum = Math.min(...domainValues);
  const maximum = Math.max(...domainValues);
  const padding = Math.max((maximum - minimum) * 0.06, 10_000);
  const insideRange = chartData.filter((point) => point.is_recommended);
  const outsideRange = chartData.filter((point) => !point.is_recommended);
  const lowestPrice = chartData[0].price;
  const highestPrice = chartData[chartData.length - 1].price;

  return <section className="price-distribution-card">
    <div className="price-distribution-heading"><div><span className="eyebrow">FİYAT DAĞILIMI</span><h3>Benzer ilanların piyasa görünümü</h3><p>Her nokta analize giren tek bir ilanı, yeşil alan önerilen piyasa aralığını gösterir.</p></div><small>{number(data.listing_count)} analiz kaydı</small></div>
    <div className="price-density-summary">
      <div><span>En düşük ilan</span><strong>{money(lowestPrice)}</strong><small>Referans gruptaki en düşük fiyat</small></div>
      <div><span>Medyan fiyat</span><strong>{money(median)}</strong><small>Referans grubun orta noktası</small></div>
      <div><span>En yüksek ilan</span><strong>{money(highestPrice)}</strong><small>Referans gruptaki en yüksek fiyat</small></div>
      {data.asking_price != null && <div><span>Girdiğiniz fiyat</span><strong>{money(data.asking_price)}</strong><small className={data.price_assessment === "Piyasa içinde" ? "within" : ""}>{data.price_assessment ?? "Fiyat karşılaştırması"}</small></div>}
    </div>
    <div className="price-strip-chart" aria-label="Benzer ilanların etkileşimli nokta dağılımı grafiği">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 24, right: 20, left: 4, bottom: 8 }}>
          <CartesianGrid vertical={false} stroke="#e7edf5" strokeDasharray="3 4" />
          <XAxis type="number" dataKey="price" domain={[Math.max(0, minimum - padding), maximum + padding]} tickFormatter={compactPrice} tickLine={false} axisLine={false} minTickGap={34} />
          <YAxis type="number" dataKey="lane" domain={[0, laneCount + 1]} hide />
          <Tooltip cursor={{ stroke: "#b9c9df", strokeDasharray: "3 3" }} content={<PriceScatterTooltip />} />
          <ReferenceArea x1={low} x2={high} y1={0} y2={laneCount + 1} fill="#dff2e9" fillOpacity={0.72} />
          <ReferenceLine x={median} stroke="#123154" strokeWidth={2} />
          {data.asking_price != null && <ReferenceLine x={data.asking_price} stroke="#e8692e" strokeWidth={2} strokeDasharray="5 4" />}
          <Scatter data={outsideRange} fill="#78a7f5" />
          <Scatter data={insideRange} fill="#16875b" />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
    <div className="price-strip-legend"><span><i className="dot" />Her nokta bir ilan</span><span><i className="range" />Önerilen piyasa aralığı</span><span><i className="median" />Medyan fiyat</span>{data.asking_price != null && <span><i className="asking" />Girdiğiniz fiyat</span>}</div>
  </section>;
}

type ReferenceMileageChartPoint = ReferenceMileagePoint & { label: string };

function ReferenceMileageTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: ReferenceMileageChartPoint }> }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <div className="price-density-tooltip">
    <strong>{number(point.lower_mileage_km)} - {number(point.upper_mileage_km)} km</strong>
    <span>Medyan fiyat {money(point.median_price)}</span>
    <small>{number(point.listing_count)} referans ilan</small>
  </div>;
}

type ReferenceTrendChartPoint = TrendPoint & { label: string };

function ReferenceTrendTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: ReferenceTrendChartPoint }> }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <div className="price-density-tooltip">
    <strong>{point.label}</strong>
    <span>Medyan fiyat {money(point.median_price)}</span>
    <small>{number(point.listing_count)} ilan bu tarihte eklendi</small>
  </div>;
}

function shortDate(value: string) {
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short" }).format(date);
}

function ReferenceInsights({ data }: { data: ValuationResponse }) {
  const mileageData: ReferenceMileageChartPoint[] = (data.reference_mileage_points ?? []).map((point) => ({
    ...point,
    label: `${Math.round(point.lower_mileage_km / 1_000)}-${Math.round(point.upper_mileage_km / 1_000)} bin km`,
  }));
  const trendData: ReferenceTrendChartPoint[] = (data.reference_listing_trend ?? []).map((point) => ({ ...point, label: shortDate(point.date) }));
  if (!mileageData.length && !trendData.length) return null;

  return <section className="reference-insights">
    {mileageData.length > 0 && <article className="reference-chart-card">
      <div className="reference-chart-heading"><div><span className="eyebrow">KİLOMETRE ETKİSİ</span><h3>Yakın kilometre aralığında fiyat</h3><p>Yalnızca bu değerlemede kullanılan ilanların kilometre ve medyan fiyat ilişkisi.</p></div><small>{number(data.listing_count)} analiz kaydı</small></div>
      <div className="reference-chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={mileageData} margin={{ top: 22, right: 18, left: 4, bottom: 8 }}>
            <CartesianGrid vertical={false} stroke="#e7edf5" strokeDasharray="3 4" />
            <XAxis dataKey="label" tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={28} />
            <YAxis tickFormatter={compactPrice} tickLine={false} axisLine={false} width={52} />
            <Tooltip cursor={{ stroke: "#b9c9df", strokeDasharray: "3 3" }} content={<ReferenceMileageTooltip />} />
            <Line type="monotone" dataKey="median_price" name="Medyan fiyat" stroke="#16875b" strokeWidth={3} dot={{ r: 4, fill: "#fff", strokeWidth: 3 }} activeDot={{ r: 6 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </article>}
    {trendData.length > 0 && <article className="reference-chart-card">
      <div className="reference-chart-heading"><div><span className="eyebrow">İLAN TARİHİ</span><h3>İlan tarihine göre fiyat akışı</h3><p>Her tarihte eklenen karşılaştırılabilir ilanların medyan fiyatı gösterilir.</p></div><small>İlan fiyatı geçmişi değildir</small></div>
      <div className="reference-chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={trendData} margin={{ top: 22, right: 18, left: 4, bottom: 8 }}>
            <CartesianGrid vertical={false} stroke="#e7edf5" strokeDasharray="3 4" />
            <XAxis dataKey="label" tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={28} />
            <YAxis tickFormatter={compactPrice} tickLine={false} axisLine={false} width={52} />
            <Tooltip cursor={{ stroke: "#b9c9df", strokeDasharray: "3 3" }} content={<ReferenceTrendTooltip />} />
            <Line type="monotone" dataKey="median_price" name="Günlük medyan fiyat" stroke="#2563eb" strokeWidth={3} dot={{ r: 4, fill: "#fff", strokeWidth: 3 }} activeDot={{ r: 6 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </article>}
  </section>;
}

export function ValuationResult({ data }: { data: ValuationResponse | null }) {
  if (!data) return <div className="valuation-placeholder"><Sparkles size={26} /><strong>Aracınızın piyasa değerini hesaplayın</strong><p>Seçtiğiniz kriterlerle eşleşen gerçek ilanlardan bir tahmin oluşturacağız.</p></div>;
  // Without comparable listings the kasko value is still a useful anchor.
  if (data.status === "empty") return <><EmptyState title="Güncel piyasa karşılaştırması oluşmadı" detail={data.explanation} />{data.reference_value && <div className="valuation-result"><ReferenceValueCard data={data} /></div>}</>;
  // The engine reports "low_sample" when the reference group is below its own
  // minimum. Showing that estimate at full visual weight would contradict the
  // warning printed underneath it, so the range leads instead.
  const lowSample = data.status === "low_sample";
  return <section className="valuation-result">
    <div className={`result-hero${lowSample ? " low-confidence" : ""}`}>
      <span className="eyebrow">TAHMİNİ PİYASA DEĞERİ</span>
      <strong>{money(data.estimated_market_value)}</strong>
      <p>Güncel ilan verisi · {data.confidence} güven</p>
      {lowSample && <p className="result-hero-warning">
        <AlertTriangle size={15} />
        <span>Bu tahmin yalnızca {number(data.listing_count)} ilana dayanıyor. Tek bir sayı yerine yanındaki önerilen aralığı dikkate alın.</span>
      </p>}
    </div>
    <MarketRangeCard data={data} />
    <ConditionAdjustmentCard data={data} />
    <ReferenceValueCard data={data} />
    <ComparisonSummary data={data} />
    <PriceDistribution data={data} />
    <ReferenceInsights data={data} />
  </section>;
}
