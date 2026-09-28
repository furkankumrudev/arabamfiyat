import { FlaskConical } from "lucide-react";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";

// Synthetic demo listings must never be mistaken for the real market.
export function DataSourceBanner() {
  const { data } = useAsync(() => api.health(), []);
  if (!data?.demo_data) return null;
  return <div className="data-source-banner" role="status">
    <div className="shell"><FlaskConical size={16} aria-hidden="true" /><p><strong>Demo verisi.</strong> Gösterilen ilanlar ve fiyatlar sentetiktir; uygulamanın nasıl çalıştığını göstermek için üretilmiştir, gerçek piyasayı yansıtmaz.</p></div>
  </div>;
}
