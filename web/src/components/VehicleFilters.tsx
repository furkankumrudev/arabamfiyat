import { RotateCcw, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CatalogOption, Filters } from "../types";

const EMPTY: Filters = {};
// Dealers list next year's model year before the calendar turns.
const MAX_MODEL_YEAR = new Date().getFullYear() + 1;
const formatNumberInput = (value: number | undefined) => value == null ? "" : new Intl.NumberFormat("tr-TR").format(value);
type Props = {
  value: Filters;
  onApply: (filters: Filters) => void;
  autoApply?: boolean;
  showRangeFilters?: boolean;
};

function Select({ label, value, options, disabled, onChange }: {
  label: string;
  value?: string;
  options: CatalogOption[];
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  // The shipped catalog covers far more vehicles than the database holds, so
  // hide the entries with nothing to analyse. If none has listings, keep them
  // all rather than rendering an empty dropdown.
  const withListings = options.filter((option) => (option.listing_count ?? 0) > 0);
  const visible = withListings.length ? withListings : options;
  return <label className="field"><span>{label}</span>
    <select value={value ?? ""} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
      <option value="">Tümü</option>
      {visible.map((option) => <option key={option.name} value={option.name}>{option.name}{option.listing_count ? ` (${option.listing_count})` : ""}</option>)}
    </select>
  </label>;
}

export function VehicleFilters({ value, onApply, autoApply = false, showRangeFilters = true }: Props) {
  const [draft, setDraft] = useState<Filters>(value);
  const [brands, setBrands] = useState<CatalogOption[]>([]);
  const [series, setSeries] = useState<CatalogOption[]>([]);
  const [models, setModels] = useState<CatalogOption[]>([]);

  useEffect(() => { api.brands().then((result) => setBrands(result.items)).catch(() => setBrands([])); }, []);
  useEffect(() => {
    setSeries([]);
    setModels([]);
    if (draft.brand) api.series(draft.brand).then((result) => setSeries(result.items)).catch(() => setSeries([]));
  }, [draft.brand]);
  useEffect(() => {
    setModels([]);
    if (draft.brand && draft.series) api.models(draft.brand, draft.series).then((result) => setModels(result.items)).catch(() => setModels([]));
  }, [draft.brand, draft.series]);

  // Notify the parent outside the state updater: updaters run during render,
  // where updating another component's state is not allowed.
  const updateDraft = (update: (current: Filters) => Filters) => {
    const updated = update(draft);
    setDraft(updated);
    if (autoApply) onApply(updated);
  };

  const change = (key: keyof Filters, next: string) => updateDraft((current) => {
    const updated = { ...current, [key]: next || undefined };
    if (key === "brand") { delete updated.series; delete updated.model; }
    if (key === "series") delete updated.model;
    return updated;
  });

  return <section className="filter-panel" aria-label="Araç filtreleri">
    <div className="section-heading compact"><div><span className="eyebrow"><SlidersHorizontal size={15} />ARAÇ FİLTRELERİ</span><h2>{showRangeFilters ? "Piyasayı daraltın" : "Aracınızı seçin"}</h2></div><button className="text-button" onClick={() => { setDraft(EMPTY); onApply(EMPTY); }}><RotateCcw size={15} />{showRangeFilters ? "Filtreleri temizle" : "Seçimi temizle"}</button></div>
    <div className={`filter-grid${showRangeFilters ? "" : " vehicle-selection-grid"}`}>
      <Select label="Marka" value={draft.brand} options={brands} onChange={(next) => change("brand", next)} />
      <Select label="Seri" value={draft.series} options={series} disabled={!draft.brand} onChange={(next) => change("series", next)} />
      <Select label="Model" value={draft.model} options={models} disabled={!draft.series} onChange={(next) => change("model", next)} />
      {showRangeFilters && <><label className="field"><span>Minimum model yılı</span><input type="number" min="1980" max={MAX_MODEL_YEAR} value={draft.year_min ?? ""} onChange={(event) => updateDraft((current) => ({ ...current, year_min: event.target.value ? Number(event.target.value) : undefined }))} placeholder="Örn. 2018" /></label>
      <label className="field"><span>Maksimum model yılı</span><input type="number" min="1980" max={MAX_MODEL_YEAR} value={draft.year_max ?? ""} onChange={(event) => updateDraft((current) => ({ ...current, year_max: event.target.value ? Number(event.target.value) : undefined }))} placeholder="Örn. 2024" /></label>
      <label className="field"><span>Maksimum kilometre</span><input type="text" inputMode="numeric" value={formatNumberInput(draft.mileage_max)} onChange={(event) => { const digits = event.target.value.replace(/\D/g, ""); updateDraft((current) => ({ ...current, mileage_max: digits ? Number(digits) : undefined })); }} placeholder="Örn. 100.000" /></label></>}
      {!autoApply && <button className="primary-button filter-submit" onClick={() => onApply(draft)}>Analizi güncelle</button>}
    </div>
  </section>;
}
