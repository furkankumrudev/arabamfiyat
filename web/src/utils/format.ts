export const money = (value: number | null | undefined) =>
  value == null
    ? "Yeterli veri yok"
    : new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 }).format(value);

export const number = (value: number | null | undefined) =>
  value == null ? "—" : new Intl.NumberFormat("tr-TR").format(value);

export const percent = (value: number | null | undefined) => {
  if (value == null) return "—";
  // Anything that rounds to zero is shown as 0, never as "-0%".
  const rounded = Math.round(value * 10) / 10;
  if (rounded === 0) return "0%";
  return `${rounded > 0 ? "+" : ""}${new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 }).format(rounded)}%`;
};

export const dateTime = (value: string | null | undefined) => {
  if (!value) return "Yeterli veri yok";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
};

export const shortDate = (value: string) => new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short" }).format(new Date(value));

// Axis and tooltip labels: short enough to stay on one line ("₺1,2 Mn", "₺850 bin").
export const compactMoney = (value: number) => {
  if (Math.abs(value) >= 1_000_000) return `₺${new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 }).format(value / 1_000_000)} Mn`;
  return `₺${new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 }).format(value / 1_000)} bin`;
};
