import { useEffect, useState } from "react";
import { AppHeader } from "./components/AppHeader";
import { DataSourceBanner } from "./components/DataSourceBanner";
import { MarketTrendsPage } from "./pages/MarketTrendsPage";
import { ValuationPage } from "./pages/ValuationPage";

type Page = "market" | "valuation";
const pageFor = (pathname: string): Page => pathname === "/arac-degerleme" ? "valuation" : "market";

export default function App() {
  const [page, setPage] = useState<Page>(() => pageFor(window.location.pathname));
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
  return <><AppHeader page={page} onNavigate={navigate} /><DataSourceBanner />{page === "valuation" ? <ValuationPage /> : <MarketTrendsPage />}<footer><div className="shell">ArabamFiyat.com <span>·</span> Veriye dayalı ikinci el araç piyasa analizi</div></footer></>;
}
