import { ArrowLeftRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { ResultActions } from "../components/ResultActions";
import { ErrorState, LoadingSkeleton } from "../components/StatePanels";
import { VehicleFilters } from "../components/VehicleFilters";
import type { Filters, ValuationRequest, ValuationResponse } from "../types";
import { money, number, percent } from "../utils/format";
import { requestFromQuery, valuationQuery } from "../utils/valuationLink";

type Side = "a" | "b";
const SIDES: Side[] = ["a", "b"];
const LABELS: Record<Side, string> = { a: "1. araç", b: "2. araç" };
const MAX_MODEL_YEAR = new Date().getFullYear() + 1;
const digits = (value: string) => value.replace(/\D/g, "");
const formatDigits = (value: string) => value ? new Intl.NumberFormat("tr-TR").format(Number(value)) : "";

type Draft = { filters: Filters; year: string; mileage: string };
const draftFrom = (request: ValuationRequest | null): Draft => ({
  filters: { brand: request?.brand, series: request?.series, model: request?.model },
  year: request?.year != null ? String(request.year) : "",
  mileage: request?.mileage_km != null ? String(request.mileage_km) : "",
});
const requestFrom = (draft: Draft): ValuationRequest => ({
  ...draft.filters,
  year: draft.year ? Number(draft.year) : undefined,
  mileage_km: draft.mileage ? Number(draft.mileage) : undefined,
});
const vehicleName = (request: ValuationRequest) =>
  [request.brand, request.series, request.model, request.year, request.mileage_km != null ? `${number(request.mileage_km)} km` : null].filter(Boolean).join(" · ");

function VehicleColumn({ side, draft, onChange }: { side: Side; draft: Draft; onChange: (draft: Draft) => void }) {
  return <div className="compare-column">
    <span className="compare-badge">{LABELS[side]}</span>
    <VehicleFilters value={draft.filters} onApply={(filters) => onChange({ ...draft, filters })} autoApply showRangeFilters={false} />
    <div className="compare-extras">
      <label className="field"><span>Model yılı</span><input type="number" min="1980" max={MAX_MODEL_YEAR} value={draft.year} onChange={(event) => onChange({ ...draft, year: event.target.value })} placeholder="Örn. 2020" /></label>
      <label className="field"><span>Kilometre</span><input inputMode="numeric" value={formatDigits(draft.mileage)} onChange={(event) => onChange({ ...draft, mileage: digits(event.target.value) })} placeholder="Örn. 90.000" /></label>
    </div>
  </div>;
}

type Row = { label: string; value: (result: ValuationResponse) => number | null | undefined; format: (value: number | null | undefined) => string; compare?: boolean };
const ROWS: Row[] = [
  { label: "Tahmini piyasa değeri", value: (r) => r.estimated_market_value, format: money, compare: true },
  { label: "Önerilen aralık (alt)", value: (r) => r.recommended_low_price, format: money },
  { label: "Önerilen aralık (üst)", value: (r) => r.recommended_high_price, format: money },
  { label: "Medyan ilan fiyatı", value: (r) => r.median_price, format: money, compare: true },
  { label: "Kasko değeri", value: (r) => r.reference_value?.value, format: money, compare: true },
  { label: "Kullanıcı satış medyanı", value: (r) => r.sale_reports?.median_price, format: money, compare: true },
  { label: "Analize giren ilan", value: (r) => r.listing_count, format: number },
];

function CompareTable({ requests, results }: { requests: Record<Side, ValuationRequest>; results: Record<Side, ValuationResponse> }) {
  return <div className="table-scroll compare-table">
    <p className="compare-vehicles"><span><b>{LABELS.a}:</b> {vehicleName(requests.a)}</span><span><b>{LABELS.b}:</b> {vehicleName(requests.b)}</span></p>
    <table>
    <thead><tr><th /><th>{vehicleName(requests.a)}</th><th>{vehicleName(requests.b)}</th><th>Fark (2. araç)</th></tr></thead>
    <tbody>
      {ROWS.map((row) => {
        const a = row.value(results.a);
        const b = row.value(results.b);
        const delta = row.compare && a && b ? (b - a) / a * 100 : null;
        return <tr key={row.label}><td><strong>{row.label}</strong></td><td data-label={LABELS.a}>{row.format(a)}</td><td data-label={LABELS.b}>{row.format(b)}</td>
          {/* A higher price is neither good nor bad here, so the difference stays neutral. */}
          <td className="compare-delta" data-label="Fark">{delta == null ? "—" : `${percent(delta)} · ${money(Math.abs((b ?? 0) - (a ?? 0)))}`}</td></tr>;
      })}
      <tr><td><strong>Güven</strong></td><td data-label={LABELS.a}>{results.a.confidence ?? "—"}</td><td data-label={LABELS.b}>{results.b.confidence ?? "—"}</td><td className="compare-empty" /></tr>
    </tbody>
  </table></div>;
}

export function ComparePage() {
  const [shared] = useState(() => ({ a: requestFromQuery(window.location.search, "a_"), b: requestFromQuery(window.location.search, "b_") }));
  const [drafts, setDrafts] = useState<Record<Side, Draft>>(() => ({ a: draftFrom(shared.a), b: draftFrom(shared.b) }));
  const [requests, setRequests] = useState<Record<Side, ValuationRequest> | null>(null);
  const [results, setResults] = useState<Record<Side, ValuationResponse> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const ready = SIDES.every((side) => drafts[side].filters.brand && drafts[side].filters.series);

  const run = (current: Record<Side, Draft>) => {
    const next = { a: requestFrom(current.a), b: requestFrom(current.b) };
    const query = new URLSearchParams();
    valuationQuery(next.a, "a_", query);
    valuationQuery(next.b, "b_", query);
    window.history.replaceState({}, "", `/arac-karsilastirma?${query.toString()}`);
    setLoading(true);
    setError(null);
    setRequests(next);
    Promise.all([api.valuation(next.a), api.valuation(next.b)])
      .then(([a, b]) => setResults({ a, b }))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  };
  useEffect(() => { if (shared.a && shared.b) run(drafts); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!loading && (results || error)) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [loading, results, error]);

  const empty = results && SIDES.filter((side) => results[side].status === "empty");
  return <main>
    <section className="hero valuation-hero compact-hero"><div className="shell">
      <span className="eyebrow">KARŞILAŞTIRMA</span>
      <h1>İki aracı yan yana karşılaştırın</h1>
      <p>Aynı bütçedeki iki seçeneği ya da aynı aracın iki farklı yılını seçin; piyasa değeri, fiyat aralığı ve kasko değeri tek tabloda görünsün.</p>
    </div></section>
    <div className="shell page-content">
      <div className="compare-grid">{SIDES.map((side) => <VehicleColumn key={side} side={side} draft={drafts[side]} onChange={(draft) => setDrafts({ ...drafts, [side]: draft })} />)}</div>
      <div className="compare-submit">
        <button className="primary-button" onClick={() => run(drafts)} disabled={!ready || loading}><ArrowLeftRight size={17} />{loading ? "Karşılaştırılıyor…" : "Karşılaştır"}</button>
        {!ready && <small>Her iki araç için de marka ve seri seçin.</small>}
      </div>
      <div ref={resultRef} className="result-anchor">
        {loading ? <LoadingSkeleton rows={5} /> : error ? <ErrorState detail={error} /> : results && requests && <section className="compare-result">
          <ResultActions />
          <CompareTable requests={requests} results={results} />
          {empty && empty.length > 0 && <p className="compare-note">{empty.map((side) => LABELS[side]).join(" ve ")} için yeterli benzer ilan bulunamadı; yıl veya kilometreyi boş bırakmayı deneyin.</p>}
          <p className="compare-note">Değerler ayrı ayrı yapılan iki değerlemenin sonucudur; kondisyon bilgisi olmadan, benzer ilanların fiyatına göre hesaplanır.</p>
        </section>}
      </div>
    </div>
  </main>;
}
