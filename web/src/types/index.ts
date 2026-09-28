export type Filters = {
  brand?: string;
  series?: string;
  model?: string;
  body_type?: string;
  fuel_type?: string;
  transmission?: string;
  year_min?: number;
  year_max?: number;
  mileage_max?: number;
};

export type CatalogOption = { name: string; listing_count?: number | null };
export type CatalogResponse = { items: CatalogOption[] };

export type MarketOverview = {
  median_price: number | null;
  average_price: number | null;
  listing_count: number;
  last_updated_at: string | null;
  source_status: string;
  change_30d: number | null;
  change_90d: number | null;
  change_yoy: number | null;
  message?: string | null;
};

export type TrendPoint = {
  date: string;
  median_price: number;
  average_price: number;
  listing_count: number;
  clean_median_price?: number | null;
  clean_average_price?: number | null;
  clean_listing_count?: number | null;
};
export type TrendResponse = { available: boolean; label: string; points: TrendPoint[]; clean_available: boolean; clean_listing_count: number; message?: string | null };

export type PriceRelationshipPoint = {
  label: string;
  median_price: number;
  average_price: number;
  listing_count: number;
};
export type PriceRelationshipsResponse = {
  listing_count: number;
  clean_listing_count: number;
  year_available: boolean;
  mileage_available: boolean;
  clean_year_available: boolean;
  clean_mileage_available: boolean;
  year_points: PriceRelationshipPoint[];
  mileage_points: PriceRelationshipPoint[];
  clean_year_points: PriceRelationshipPoint[];
  clean_mileage_points: PriceRelationshipPoint[];
  message?: string | null;
};

export type MarketTableRow = {
  label: string;
  average_price: number;
  median_price: number;
  listing_count: number;
  change_30d: number | null;
  change_90d: number | null;
  change_yoy: number | null;
};
export type MarketTableResponse = { group_by: string; rows: MarketTableRow[]; message?: string | null };

export type MoverItem = {
  label: string;
  change_percent: number;
  average_price: number;
  listing_count: number;
  direction: "up" | "down";
};
export type MoversResponse = { available: boolean; items: MoverItem[]; message?: string | null };

export type SimilarListing = {
  id: number | null;
  title: string;
  brand: string | null;
  series: string | null;
  model: string | null;
  year: number | null;
  mileage_km: number | null;
  price: number;
  city: string | null;
  listing_date: string | null;
  listing_url: string | null;
  similarity_score: number | null;
};

export type ComparisonSummary = {
  matched_listing_count: number;
  selected_listing_count: number;
  used_listing_count: number;
  outlier_count: number;
  selection_mode: "all_matching" | "context_window";
  selection_note: string;
  clean_only: boolean;
  median_year: number | null;
  median_mileage_km: number | null;
};

export type ReferencePricePoint = {
  price: number;
  year: number | null;
  mileage_km: number | null;
};

export type ReferenceMileagePoint = {
  lower_mileage_km: number;
  upper_mileage_km: number;
  median_price: number;
  average_price: number;
  listing_count: number;
};

export type ValuationRequest = Filters & {
  year?: number;
  mileage_km?: number;
  asking_price?: number;
  clean_only?: boolean;
  changed_parts?: number;
  painted_parts?: number;
};
export type ValuationResponse = {
  status: string;
  estimated_market_value: number | null;
  recommended_low_price: number | null;
  recommended_high_price: number | null;
  median_price: number | null;
  listing_count: number;
  confidence: string | null;
  price_assessment: string | null;
  asking_price_delta_percent: number | null;
  asking_price: number | null;
  explanation: string;
  comparison_summary: ComparisonSummary | null;
  reference_price_points: ReferencePricePoint[];
  reference_mileage_points: ReferenceMileagePoint[];
  reference_listing_trend: TrendPoint[];
  condition_adjustment_percent: number | null;
  condition_adjustment_note: string | null;
  reference_value: ReferenceValue | null;
};

export type ReferenceValue = {
  value: number;
  period: string;
  source: string;
  model_year: number;
  match: "model" | "series";
  matched_name: string | null;
  candidate_count: number;
  market_to_reference_percent: number | null;
};

export type HealthResponse = {
  status: string;
  database_available: boolean;
  listing_count: number | null;
  message: string | null;
  data_sources: string[];
  demo_data: boolean;
};
