import { useEffect, useRef, useState } from "react";
import { ValuationForm } from "../components/ValuationForm";
import { ResultActions } from "../components/ResultActions";
import { SaleReportForm } from "../components/SaleReportForm";
import { ValuationResult } from "../components/ValuationResult";
import { api } from "../api/client";
import type { ValuationRequest, ValuationResponse } from "../types";
import { ErrorState, LoadingSkeleton } from "../components/StatePanels";
import { requestFromQuery, valuationQuery } from "../utils/valuationLink";

export function ValuationPage() {
  const [result, setResult] = useState<ValuationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [request, setRequest] = useState<ValuationRequest | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const [shared] = useState(() => requestFromQuery(window.location.search));
  const submit = (payload: ValuationRequest) => {
    setLoading(true);
    setError(null);
    setRequest(payload);
    // Keep the address shareable: opening it shows this same valuation.
    window.history.replaceState({}, "", `/arac-degerleme?${valuationQuery(payload)}`);
    api.valuation(payload).then(setResult).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
  };
  // A shared link runs its valuation straight away.
  useEffect(() => { if (shared) submit(shared); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Bring the answer into view; on a phone it would otherwise sit below the form.
  useEffect(() => {
    if (!loading && (result || error)) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [loading, result, error]);

  return <main>
    <section className="hero valuation-hero compact-hero"><div className="shell">
      <span className="eyebrow">ARAÇ DEĞERLEME</span>
      <h1>Aracınızın piyasa değerini görün</h1>
      <p>Marka ve seriyi seçin; yıl, kilometre ve kondisyon bilgisi ekledikçe karşılaştırma aracınıza daha çok benzer.</p>
    </div></section>
    <div className="shell page-content">
      <ValuationForm onSubmit={submit} loading={loading} initial={shared ?? undefined} />
      {result && request && <div className="print-only print-header"><strong>ArabamFiyat.com · Araç değerleme raporu</strong><span>{[request.brand, request.series, request.model, request.year, request.mileage_km != null ? `${new Intl.NumberFormat("tr-TR").format(request.mileage_km)} km` : null].filter(Boolean).join(" · ")}</span><small>{new Intl.DateTimeFormat("tr-TR", { dateStyle: "long" }).format(new Date())} · Karar desteğidir; ekspertiz veya satış garantisi değildir.</small></div>}
      <div ref={resultRef} className="result-anchor">{loading ? <LoadingSkeleton rows={5} /> : error ? <ErrorState detail={error} /> : <>{result && result.status !== "empty" && <ResultActions />}<ValuationResult data={result} />{result && request && <SaleReportForm key={JSON.stringify(request)} vehicle={request} />}</>}</div>
    </div>
  </main>;
}
