import { ArrowLeftRight, BarChart3, CarFront, Info, Menu, Moon, Sun, X } from "lucide-react";
import type { Theme } from "../theme";
import { useState } from "react";

type Props = { page: "market" | "valuation" | "compare"; onNavigate: (path: string) => void; theme: Theme; onToggleTheme: () => void };

export function AppHeader({ page, onNavigate, theme, onToggleTheme }: Props) {
  const [open, setOpen] = useState(false);
  const navigate = (path: string) => { onNavigate(path); setOpen(false); };
  const navigateToMethodology = () => navigate("/piyasa-trendleri#metodoloji");
  return <header className="app-header">
    <div className="shell nav-shell">
      <button className="brand" onClick={() => navigate("/piyasa-trendleri")} aria-label="ArabamFiyat.com ana sayfa">
        <span className="brand-mark"><CarFront size={20} aria-hidden="true" /></span>
        <span><strong>ArabamFiyat<span>.com</span></strong><small>Türkiye ikinci el araç piyasa analizi</small></span>
      </button>
      <nav className={open ? "main-nav open" : "main-nav"} aria-label="Ana menü">
        <button className={page === "market" ? "active" : ""} onClick={() => navigate("/piyasa-trendleri")}><BarChart3 size={17} />Piyasa Trendleri</button>
        <button className={page === "valuation" ? "active" : ""} onClick={() => navigate("/arac-degerleme")}><CarFront size={17} />Araç Değerleme</button>
        <button className={page === "compare" ? "active" : ""} onClick={() => navigate("/arac-karsilastirma")}><ArrowLeftRight size={17} />Karşılaştır</button>
        <a href="/piyasa-trendleri#metodoloji" onClick={(event) => { event.preventDefault(); navigateToMethodology(); }}><Info size={17} />Proje Hakkında</a>
      </nav>
      <div className="header-actions">
      <button className="theme-toggle" onClick={onToggleTheme} aria-label={theme === "dark" ? "Açık temaya geç" : "Koyu temaya geç"} title={theme === "dark" ? "Açık tema" : "Koyu tema"}>{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button>
      <button className="icon-button menu-toggle" onClick={() => setOpen(!open)} aria-label="Menüyü aç veya kapat" aria-expanded={open}>{open ? <X /> : <Menu />}</button>
      </div>
    </div>
  </header>;
}
