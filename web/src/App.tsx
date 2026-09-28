import { useEffect, useState } from "react";
import { AppHeader } from "./components/AppHeader";
import { DataSourceBanner } from "./components/DataSourceBanner";
import { ComparePage } from "./pages/ComparePage";
import { MarketTrendsPage } from "./pages/MarketTrendsPage";
import { ValuationPage } from "./pages/ValuationPage";
import { ThemeContext, useTheme } from "./theme";

type Page = "market" | "valuation" | "compare";
const pageFor = (pathname: string): Page => pathname === "/arac-degerleme" ? "valuation" : pathname === "/arac-karsilastirma" ? "compare" : "market";
const TITLES: Record<Page, string> = { market: "Piyasa Trendleri", valuation: "Araç Değerleme", compare: "Araç Karşılaştırma" };

export default function App() {
  const [page, setPage] = useState<Page>(() => pageFor(window.location.pathname));
  const { theme, toggle } = useTheme();
  useEffect(() => { const sync = () => setPage(pageFor(window.location.pathname)); window.addEventListener("popstate", sync); return () => window.removeEventListener("popstate", sync); }, []);
  useEffect(() => {
    const target = window.location.hash.slice(1);
    if (!target) return;
    const timer = window.setTimeout(() => document.getElementById(target)?.scrollIntoView({ behavior: "smooth" }), 0);
    return () => window.clearTimeout(timer);
  }, [page]);
  const navigate = (path: string) => {
    window.history.pushState({}, "", path);
    setPage(pageFor(path));
    const target = path.split("#")[1];
    if (!target) { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    window.setTimeout(() => document.getElementById(target)?.scrollIntoView({ behavior: "smooth" }), 0);
  };
  useEffect(() => { document.title = `${TITLES[page]} | ArabamFiyat.com`; }, [page]);
  const link = (path: string) => (event: React.MouseEvent) => { event.preventDefault(); navigate(path); };
  return <ThemeContext.Provider value={theme}><AppHeader page={page} onNavigate={navigate} theme={theme} onToggleTheme={toggle} /><DataSourceBanner />{page === "valuation" ? <ValuationPage /> : page === "compare" ? <ComparePage /> : <MarketTrendsPage onNavigate={navigate} />}
    <footer><div className="shell footer-grid">
      <div><strong>ArabamFiyat.com</strong><p>Veriye dayalı ikinci el araç piyasa analizi. Sonuçlar ilan verisinden üretilen karar destek tahminleridir; ekspertiz veya satış garantisi değildir.</p></div>
      <nav aria-label="Alt menü"><a href="/piyasa-trendleri" onClick={link("/piyasa-trendleri")}>Piyasa trendleri</a><a href="/arac-degerleme" onClick={link("/arac-degerleme")}>Araç değerleme</a><a href="/arac-karsilastirma" onClick={link("/arac-karsilastirma")}>Karşılaştır</a><a href="/piyasa-trendleri#metodoloji" onClick={link("/piyasa-trendleri#metodoloji")}>Nasıl hesaplıyoruz?</a><a href="https://github.com/furkankumrudev/arabamfiyat" target="_blank" rel="noreferrer">GitHub</a></nav>
    </div></footer></ThemeContext.Provider>;
}
