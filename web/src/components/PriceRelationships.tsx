import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import type { Filters, PriceRelationshipPoint } from "../types";
import { compactMoney, money, number } from "../utils/format";
import { EmptyState, ErrorState, LoadingSkeleton } from "./StatePanels";
import { ListingChartLegend } from "./ListingChartLegend";

type ComparisonPoint = PriceRelationshipPoint & { clean_median_price?: number; clean_listing_count?: number };

function mergePoints(points: PriceRelationshipPoint[], cleanPoints: PriceRelationshipPoint[]): ComparisonPoint[] {
  const cleanByLabel = new Map(cleanPoints.map((point) => [point.label, point]));
  return points.map((point) => {
    const clean = cleanByLabel.get(point.label);
    return { ...point, clean_median_price: clean?.median_price, clean_listing_count: clean?.listing_count };
  });
}

function PriceTooltip({ points }: { points: ComparisonPoint[] }) {
  return <Tooltip formatter={(value, name) => [money(Number(value)), name]} labelFormatter={(value) => `${value} · ${number(points.find((point) => point.label === value)?.listing_count)} ilan`} />;
}

function RelationshipLineChart({ points, showClean }: { points: ComparisonPoint[]; showClean: boolean }) {
  return <div className="relationship-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={points} margin={{ top: 12, right: 8, left: 8, bottom: 6 }}><CartesianGrid stroke="#e7edf5" strokeDasharray="3 4" /><XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={12} /><YAxis tickFormatter={compactMoney} tickLine={false} axisLine={false} width={84} /><PriceTooltip points={points} /><Legend content={<ListingChartLegend showClean={showClean} />} /><Line type="monotone" dataKey="median_price" name="Tüm ilanlar" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />{showClean && <Line type="monotone" dataKey="clean_median_price" name="Temiz araç ilanları" stroke="#16875b" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} connectNulls />}</LineChart></ResponsiveContainer></div>;
}

export function PriceRelationships({ filters }: { filters: Filters }) {
  const { data, loading, error } = useAsync(() => api.priceRelationships(filters), [JSON.stringify(filters)]);
  const yearPoints = mergePoints(data?.year_points ?? [], data?.clean_year_points ?? []);
  const mileagePoints = mergePoints(data?.mileage_points ?? [], data?.clean_mileage_points ?? []);
  return <section className="relationship-section section-block"><div className="section-heading"><div><span className="eyebrow">FİYAT İLİŞKİSİ</span><h2>Yıl ve kilometre fiyatı nasıl etkiliyor?</h2><p>Seçili ilan grubundaki medyan fiyat dağılımı.</p></div></div>
    {loading ? <LoadingSkeleton rows={6} /> : error ? <ErrorState detail={error} /> : <div className="relationship-grid">
      <div className="relationship-panel"><h3>Model yılına göre fiyat</h3><p>Yeni model yıllarının piyasa fiyatı</p>{data?.year_available ? <RelationshipLineChart points={yearPoints} showClean={Boolean(data.clean_year_available)} /> : <EmptyState title="Yıl karşılaştırması oluşmadı" detail={data?.message} />}</div>
      <div className="relationship-panel"><h3>Kilometreye göre fiyat</h3><p>Artan kilometrenin piyasa fiyatındaki karşılığı</p>{data?.mileage_available ? <RelationshipLineChart points={mileagePoints} showClean={Boolean(data.clean_mileage_available)} /> : <EmptyState title="Kilometre karşılaştırması oluşmadı" detail={data?.message} />}</div>
    </div>}
  </section>;
}
