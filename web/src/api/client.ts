import type {
  CatalogResponse, Filters, HealthResponse, SaleReportRequest, MarketOverview, MarketTableResponse, MoversResponse, PriceRelationshipsResponse, TrendResponse,
  ValuationRequest, ValuationResponse,
} from "../types";

// Same origin by default: the dev server proxies /api, and production serves both together.
const API_URL = import.meta.env.VITE_API_URL ?? "";

// fetch only rejects when no HTTP response arrived at all.
const unreachable = () => new Error("API'ye ulaşılamadı. API sunucusunun çalıştığından emin olun (scripts\\run_api.bat).");

async function request(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch {
    throw unreachable();
  }
}

async function failure(response: Response, fallback: string): Promise<Error> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (typeof body?.detail === "string") return new Error(body.detail);
  return new Error(response.status >= 500 ? `${fallback} (sunucu hatası ${response.status}; ayrıntı API penceresinde)` : fallback);
}

const toQuery = (values: Record<string, string | number | undefined | null>) => {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const result = query.toString();
  return result ? `?${result}` : "";
};

async function get<T>(path: string, params: Record<string, string | number | undefined | null> = {}): Promise<T> {
  const response = await request(`${API_URL}${path}${toQuery(params)}`);
  if (!response.ok) throw await failure(response, "Veriler şu anda alınamadı.");
  return response.json() as Promise<T>;
}

export const api = {
  health: () => get<HealthResponse>("/api/health"),
  brands: () => get<CatalogResponse>("/api/catalog/brands"),
  series: (brand: string) => get<CatalogResponse>("/api/catalog/series", { brand }),
  models: (brand: string, series: string) => get<CatalogResponse>("/api/catalog/models", { brand, series }),
  overview: (filters: Filters) => get<MarketOverview>("/api/market/overview", filters),
  trend: (filters: Filters, start_date?: string, end_date?: string, interval: "day" | "week" = "week") => get<TrendResponse>("/api/market/trend", { ...filters, start_date, end_date, interval }),
  priceRelationships: (filters: Filters) => get<PriceRelationshipsResponse>("/api/market/price-relationships", filters),
  table: (filters: Filters, group_by: string) => get<MarketTableResponse>("/api/market/table", { ...filters, group_by }),
  movers: (direction: "up" | "down") => get<MoversResponse>("/api/market/movers", { direction }),
  saleReport: async (payload: SaleReportRequest) => {
    const response = await request(`${API_URL}/api/sale-reports`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) throw await failure(response, "Satış bilgisi kaydedilemedi.");
    return response.json() as Promise<{ status: string; message: string }>;
  },
  valuation: async (payload: ValuationRequest) => {
    const response = await request(`${API_URL}/api/valuation`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) throw await failure(response, "Değerleme oluşturulamadı.");
    return response.json() as Promise<ValuationResponse>;
  },
};
