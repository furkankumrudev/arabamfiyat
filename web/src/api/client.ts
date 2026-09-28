import type {
  CatalogResponse, Filters, HealthResponse, MarketOverview, MarketTableResponse, MoversResponse, PriceRelationshipsResponse, TrendResponse,
  ValuationRequest, ValuationResponse,
} from "../types";

const API_URL = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

const toQuery = (values: Record<string, string | number | undefined | null>) => {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const result = query.toString();
  return result ? `?${result}` : "";
};

async function get<T>(path: string, params: Record<string, string | number | undefined | null> = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}${toQuery(params)}`);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? "Veriler şu anda alınamadı.");
  }
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
  valuation: async (payload: ValuationRequest) => {
    const response = await fetch(`${API_URL}/api/valuation`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Değerleme oluşturulamadı.");
    return response.json() as Promise<ValuationResponse>;
  },
};
