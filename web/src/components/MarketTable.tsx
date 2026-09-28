import { ArrowDownUp, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import type { Filters, MarketTableRow } from "../types";
import { money, number, percent } from "../utils/format";
import { EmptyState, ErrorState, LoadingSkeleton } from "./StatePanels";

const tone = (value: number | null | undefined) => value == null || Math.abs(value) < 0.05 ? "" : value > 0 ? "positive" : "negative";

export function MarketTable({ filters, onSelectBrand }: { filters: Filters; onSelectBrand?: (brand: string) => void }) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<keyof MarketTableRow>("listing_count");
  const [descending, setDescending] = useState(true);
  const { data, loading, error } = useAsync(() => api.table(filters, "brand"), [JSON.stringify(filters)]);
  const rows = useMemo(() => (data?.rows ?? [])
    .filter((row) => row.label.toLocaleLowerCase("tr").includes(search.toLocaleLowerCase("tr")))
    .sort((a, b) => {
      const aValue = a[sortKey] ?? -Infinity;
      const bValue = b[sortKey] ?? -Infinity;
      return (aValue < bValue ? -1 : aValue > bValue ? 1 : 0) * (descending ? -1 : 1);
    }), [data, search, sortKey, descending]);
  const sort = (key: keyof MarketTableRow) => {
    if (sortKey === key) setDescending(!descending);
    else { setSortKey(key); setDescending(true); }
  };
  const columns: { key: keyof MarketTableRow; text: string }[] = [
    { key: "label", text: "Marka" },
    { key: "average_price", text: "Ortalama fiyat" },
    { key: "median_price", text: "Medyan fiyat" },
    { key: "listing_count", text: "İlan sayısı" },
  ];

  return <section className="section-block table-section"><div className="section-heading"><div><span className="eyebrow">KARŞILAŞTIRMA</span><h2>Marka karşılaştırma tablosu</h2><p>Bir markaya tıklayarak sayfanın tamamını o markaya daraltın. Değişimler günlük piyasa özetlerinden hesaplanır.</p></div><div className="table-controls"><label className="search-input"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Marka ara" /></label></div></div>
    {loading ? <LoadingSkeleton rows={6} /> : error ? <ErrorState detail={error} /> : !rows.length ? <EmptyState detail={data?.message} /> : <div className="table-scroll"><table><thead><tr>{columns.map((column) => <th key={column.key}><button onClick={() => sort(column.key)}>{column.text}<ArrowDownUp size={13} /></button></th>)}<th>Son 30 gün</th><th>Son 90 gün</th><th>Yıllık değişim</th></tr></thead><tbody>{rows.map((row) => <tr key={row.label}><td>{onSelectBrand ? <button className="row-link" onClick={() => onSelectBrand(row.label)} title={`${row.label} piyasasını göster`}>{row.label}</button> : <strong>{row.label}</strong>}</td><td>{money(row.average_price)}</td><td>{money(row.median_price)}</td><td>{number(row.listing_count)}</td><td className={tone(row.change_30d)}>{percent(row.change_30d)}</td><td className={tone(row.change_90d)}>{percent(row.change_90d)}</td><td className={tone(row.change_yoy)}>{percent(row.change_yoy)}</td></tr>)}</tbody></table></div>}
  </section>;
}
