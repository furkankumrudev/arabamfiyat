import { useEffect, useRef, useState } from "react";
import { ValuationForm } from "../components/ValuationForm";
import { ValuationResult } from "../components/ValuationResult";
import { api } from "../api/client";
import type { ValuationRequest, ValuationResponse } from "../types";
import { ErrorState, LoadingSkeleton } from "../components/StatePanels";

export function ValuationPage() {
  const [result, setResult] = useState<ValuationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const submit = (payload: ValuationRequest) => {
    setLoading(true);
    setError(null);
    api.valuation(payload).then(setResult).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
  };
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
      <ValuationForm onSubmit={submit} loading={loading} />
      <div ref={resultRef} className="result-anchor">{loading ? <LoadingSkeleton rows={5} /> : error ? <ErrorState detail={error} /> : <ValuationResult data={result} />}</div>
    </div>
  </main>;
}
