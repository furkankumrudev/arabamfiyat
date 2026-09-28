import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import type { Filters, TrendPoint } from "../types";
import { compactMoney, money, number, shortDate } from "../utils/format";
import { EmptyState, ErrorState, LoadingSkeleton } from "./StatePanels";
import { ListingChartLegend } from "./ListingChartLegend";

type Range = "30" | "90" | "180" | "365" | "all" | "custom";
type Interval = "day" | "week";
const RANGE_LABELS: Record<Range, string> = { "30": "30 Gün", "90": "90 Gün", "180": "6 Ay", "365": "1 Yıl", all: "Tümü", custom: "Özel" };
const startFor = (range: Range) => {
  if (range === "all" || range === "custom") return undefined;
  const now = new Date();
  now.setDate(now.getDate() - Number(range));
  return now.toISOString().slice(0, 10);
};

function TrendTooltip({ active, payload, interval, stat }: {
  active?: boolean;
  payload?: Array<{ payload: TrendPoint }>;
  interval: Interval;
  stat: "median" | "average";
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  const all = stat === "median" ? point.median_price : point.average_price;
  const clean = stat === "median" ? point.clean_median_price : point.clean_average_price;
  return <div className="chart-tooltip">
    <strong>{interval === "week" ? `${shortDate(point.date)} haftası` : shortDate(point.date)}</strong>
    <span><i style={{ background: "#2563eb" }} />Tüm ilanlar <b>{money(all)}</b></span>
    <small>{number(point.listing_count)} ilan</small>
    {clean != null && <><span><i style={{ background: "#16875b" }} />Temiz araç ilanları <b>{money(clean)}</b></span><small>{number(point.clean_listing_count)} ilan</small></>}
  </div>;
}

export function PriceTrendChart({ filters }: { filters: Filters }) {
  const [range, setRange] = useState<Range>("all");
  const [interval, setTrendInterval] = useState<Interval>("week");
  const [stat, setStat] = useState<"median" | "average">("median");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const startDate = range === "custom" ? customStart : startFor(range);
  const endDate = range === "custom" ? customEnd : undefined;
  const { data, loading, error } = useAsync(() => api.trend(filters, startDate, endDate, interval), [JSON.stringify(filters), startDate, endDate, interval]);
  const priceKey = stat === "median" ? "median_price" : "average_price";
  const cleanPriceKey = stat === "median" ? "clean_median_price" : "clean_average_price";
  const statLabel = stat === "median" ? "medyan" : "ortalama";

  return <section className="chart-card section-block">
    <div className="section-heading">
      <div><span className="eyebrow">FİYAT TRENDİ</span><h2>İkinci el araç fiyat trendi</h2><p>İlan tarihine göre {interval === "week" ? "haftalık" : "günlük"} {statLabel} fiyat</p></div>
      <div className="heading-controls">
        <div className="segmented" role="group" aria-label="Zaman aralığı"><button className={interval === "week" ? "selected" : ""} onClick={() => setTrendInterval("week")}>Haftalık</button><button className={interval === "day" ? "selected" : ""} onClick={() => setTrendInterval("day")}>Günlük</button></div>
        <div className="segmented" role="group" aria-label="Fiyat ölçüsü"><button className={stat === "median" ? "selected" : ""} onClick={() => setStat("median")}>Medyan</button><button className={stat === "average" ? "selected" : ""} onClick={() => setStat("average")}>Ortalama</button></div>
      </div>
    </div>
    <div className="chart-toolbar"><div className="range-buttons">{(Object.keys(RANGE_LABELS) as Range[]).map((item) => <button key={item} className={range === item ? "selected" : ""} onClick={() => setRange(item)}>{RANGE_LABELS[item]}</button>)}</div>{range === "custom" && <div className="date-controls"><label>Başlangıç<input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} /></label><label>Bitiş<input type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} /></label></div>}</div>
    {loading ? <LoadingSkeleton rows={5} /> : error ? <ErrorState detail={error} /> : !data?.available ? <EmptyState title="Geçmiş trend oluşmadı" detail={data?.message} /> : <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%">
      <LineChart data={data.points} margin={{ top: 12, right: 12, left: 4, bottom: 6 }}>
        <CartesianGrid stroke="#e7edf5" strokeDasharray="3 4" vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} tickLine={false} axisLine={false} minTickGap={28} />
        {/* A price trend reads its movement, so the axis hugs the data instead of starting at zero. */}
        <YAxis tickFormatter={compactMoney} tickLine={false} axisLine={false} width={78} domain={[(min: number) => Math.floor(min * 0.94 / 50_000) * 50_000, (max: number) => Math.ceil(max * 1.04 / 50_000) * 50_000]} />
        <Tooltip content={<TrendTooltip interval={interval} stat={stat} />} cursor={{ stroke: "#98a2b3", strokeDasharray: "3 3" }} />
        <Legend content={<ListingChartLegend showClean={data.clean_available} />} />
        <Line type="monotone" dataKey={priceKey} name="Tüm ilanlar" stroke="#2563eb" strokeWidth={2} dot={interval === "week" ? { r: 3, strokeWidth: 2, fill: "#fff" } : false} activeDot={{ r: 5, stroke: "#fff", strokeWidth: 2 }} />
        {data.clean_available && <Line type="monotone" dataKey={cleanPriceKey} name="Temiz araç ilanları" stroke="#16875b" strokeWidth={2} dot={interval === "week" ? { r: 3, strokeWidth: 2, fill: "#fff" } : false} activeDot={{ r: 5, stroke: "#fff", strokeWidth: 2 }} connectNulls />}
      </LineChart>
    </ResponsiveContainer></div>}
  </section>;
}
