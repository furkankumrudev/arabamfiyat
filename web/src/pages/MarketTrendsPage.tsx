import { ArrowRight } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "../api/client";
import { MarketMovers } from "../components/MarketMovers";
import { MarketSummary } from "../components/MarketSummary";
import { MarketTable } from "../components/MarketTable";
import { MethodologySection } from "../components/MethodologySection";
import { PriceRelationships } from "../components/PriceRelationships";
import { PriceTrendChart } from "../components/PriceTrendChart";
import { VehicleFilters } from "../components/VehicleFilters";
import { useAsync } from "../hooks/useAsync";
import type { Filters } from "../types";

export function MarketTrendsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [filters, setFilters] = useState<Filters>({});
  const summaryRef = useRef<HTMLDivElement>(null);
  // Picking a brand in the table narrows the whole page to it.
  const selectBrand = (brand: string) => {
    setFilters({ brand });
    summaryRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const { data: overview, loading } = useAsync(() => api.overview(filters), [JSON.stringify(filters)]);

  return <main>
    <section className="hero"><div className="shell hero-layout">
      <div>
        <span className="eyebrow">GÜNCEL PİYASA GÖRÜNÜMÜ</span>
        <h1>İkinci el araç fiyatlarını verilerle takip et</h1>
        <p>İlanlardan oluşturulan piyasa fiyatlarını, marka bazında değişimleri ve yıl/kilometre etkisini inceleyin.</p>
      </div>
      <div className="hero-cta">
        <button className="primary-button hero-button" onClick={() => onNavigate("/arac-degerleme")}>Aracımı değerle<ArrowRight size={17} /></button>
        <a href="/piyasa-trendleri#metodoloji" onClick={(event) => { event.preventDefault(); onNavigate("/piyasa-trendleri#metodoloji"); }}>Nasıl hesaplıyoruz?</a>
      </div>
    </div></section>
    <div className="shell page-content">
      <div ref={summaryRef} className="scroll-anchor"><MarketSummary data={overview} loading={loading} /></div>
      <VehicleFilters key={JSON.stringify(filters)} value={filters} onApply={setFilters} />
      <MarketMovers />
      <PriceTrendChart filters={filters} />
      <PriceRelationships filters={filters} />
      <MarketTable filters={filters} onSelectBrand={selectBrand} />
      <MethodologySection />
    </div>
  </main>;
}
