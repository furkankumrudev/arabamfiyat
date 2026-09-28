import type { ValuationRequest } from "../types";

// Short, readable parameter names keep shared links tidy.
const TEXT = { brand: "marka", series: "seri", model: "paket" } as const;
const NUMBERS = { year: "yil", mileage_km: "km", asking_price: "fiyat", changed_parts: "degisen", painted_parts: "boyali" } as const;

export function valuationQuery(request: ValuationRequest): string {
  const query = new URLSearchParams();
  for (const [key, name] of Object.entries(TEXT)) {
    const value = request[key as keyof typeof TEXT];
    if (value) query.set(name, value);
  }
  for (const [key, name] of Object.entries(NUMBERS)) {
    const value = request[key as keyof typeof NUMBERS];
    if (value != null) query.set(name, String(value));
  }
  if (request.clean_only) query.set("temiz", "1");
  return query.toString();
}

/** A request read from a shared link, or null when the link does not name a vehicle. */
export function requestFromQuery(search: string): ValuationRequest | null {
  const query = new URLSearchParams(search);
  const request: ValuationRequest = {};
  for (const [key, name] of Object.entries(TEXT)) {
    const value = query.get(name)?.trim();
    if (value) request[key as keyof typeof TEXT] = value.slice(0, 140);
  }
  if (!request.brand || !request.series) return null;
  for (const [key, name] of Object.entries(NUMBERS)) {
    const value = Number(query.get(name));
    if (query.has(name) && Number.isFinite(value) && value >= 0) request[key as keyof typeof NUMBERS] = Math.round(value);
  }
  if (query.get("temiz") === "1") {
    request.clean_only = true;
    delete request.changed_parts;
    delete request.painted_parts;
  }
  return request;
}
