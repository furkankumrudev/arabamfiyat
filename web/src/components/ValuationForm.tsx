import { useState } from "react";
import { VehicleFilters } from "./VehicleFilters";
import type { Filters, ValuationRequest } from "../types";

const formatNumberInput = (value: string) => value ? new Intl.NumberFormat("tr-TR").format(Number(value)) : "";
const MAX_MODEL_YEAR = new Date().getFullYear() + 1;

export function ValuationForm({ onSubmit, loading = false }: { onSubmit: (payload: ValuationRequest) => void; loading?: boolean }) {
  const [filters, setFilters] = useState<Filters>({});
  const [year, setYear] = useState("");
  const [mileage, setMileage] = useState("");
  const [askingPrice, setAskingPrice] = useState("");
  const [cleanOnly, setCleanOnly] = useState(false);
  // A blank counterpart used to disable the condition model entirely. Start at
  // zero so entering only one field still compares against an undamaged car.
  const [changedParts, setChangedParts] = useState("0");
  const [paintedParts, setPaintedParts] = useState("0");

  const ready = Boolean(filters.brand && filters.series);
  const submit = () => ready && onSubmit({
    ...filters,
    year: year ? Number(year) : undefined,
    mileage_km: mileage ? Number(mileage) : undefined,
    asking_price: askingPrice ? Number(askingPrice) : undefined,
    clean_only: cleanOnly,
    changed_parts: !cleanOnly ? Number(changedParts || 0) : undefined,
    painted_parts: !cleanOnly ? Number(paintedParts || 0) : undefined,
  });

  const updateAskingPrice = (value: string) => setAskingPrice(value.replace(/\D/g, ""));
  const updateMileage = (value: string) => setMileage(value.replace(/\D/g, ""));
  const updateCleanOnly = (value: boolean) => {
    setCleanOnly(value);
    if (value) {
      setChangedParts("");
      setPaintedParts("");
    } else {
      setChangedParts("0");
      setPaintedParts("0");
    }
  };

  return <div className="valuation-form">
    <VehicleFilters value={filters} onApply={setFilters} autoApply showRangeFilters={false} />
    <div className="valuation-extras">
      <label className="field"><span>Model yılı</span><input type="number" min="1980" max={MAX_MODEL_YEAR} value={year} onChange={(event) => setYear(event.target.value)} placeholder="Örn. 2021" /></label>
      <label className="field"><span>Kilometre</span><input type="text" inputMode="numeric" value={formatNumberInput(mileage)} onChange={(event) => updateMileage(event.target.value)} placeholder="Örn. 80.000" /></label>
      <label className="field"><span>İstenen fiyat</span><input type="text" inputMode="numeric" value={formatNumberInput(askingPrice)} onChange={(event) => updateAskingPrice(event.target.value)} placeholder="Örn. 1.500.000" /></label>
      <label className="clean-only-toggle"><input type="checkbox" checked={cleanOnly} onChange={(event) => updateCleanOnly(event.target.checked)} /><span><strong>Temiz araç</strong><small>Temiz beyanlı ilanlarla karşılaştır</small></span></label>
      {!cleanOnly && <><label className="field"><span>Değişen parça</span><input type="number" min="0" max="30" value={changedParts} onChange={(event) => setChangedParts(event.target.value)} placeholder="Örn. 0" /></label>
      <label className="field"><span>Boyalı parça</span><input type="number" min="0" max="30" value={paintedParts} onChange={(event) => setPaintedParts(event.target.value)} placeholder="Örn. 1" /></label></>}
      <div className={`valuation-submit-group ${cleanOnly ? "clean-only" : ""}`}>
        <button className="primary-button valuation-submit" onClick={submit} disabled={!ready || loading}>{loading ? "Hesaplanıyor…" : "Araç değerini hesapla"}</button>
        {!ready && <small>Hesaplamak için marka ve seri seçin.</small>}
      </div>
    </div>
  </div>;
}
