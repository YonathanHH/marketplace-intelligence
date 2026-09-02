/** Display formatting. Money is IDR, which needs compact forms to stay legible. */

export function formatIDR(value: number | null | undefined, opts: { compact?: boolean } = {}): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const { compact = true } = opts;
  const abs = Math.abs(value);
  if (!compact || abs < 1_000) return `Rp${Math.round(value).toLocaleString("en-US")}`;
  if (abs < 1_000_000) return `Rp${(value / 1_000).toFixed(abs < 10_000 ? 1 : 0)}k`;
  if (abs < 1_000_000_000) return `Rp${(value / 1_000_000).toFixed(abs < 10_000_000 ? 1 : 0)}M`;
  return `Rp${(value / 1_000_000_000).toFixed(2)}B`;
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs < 1_000) return String(Math.round(value));
  if (abs < 1_000_000) return `${(value / 1_000).toFixed(abs < 10_000 ? 1 : 0)}k`;
  if (abs < 1_000_000_000) return `${(value / 1_000_000).toFixed(abs < 10_000_000 ? 1 : 0)}M`;
  return `${(value / 1_000_000_000).toFixed(1)}B`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatShortDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

export function formatMonth(value: string | null | undefined): string {
  if (!value) return "—";
  const [year, month] = value.split("-");
  const d = new Date(Number(year), Number(month) - 1, 1);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function daysAgo(days: number | null | undefined): string {
  if (days === null || days === undefined) return "Never";
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.round(days / 30)}mo ago`;
  return `${(days / 365).toFixed(1)}y ago`;
}

export const TIER_COLOR: Record<string, string> = {
  Hot: "var(--tier-hot)",
  Warm: "var(--tier-warm)",
  Cool: "var(--tier-cool)",
  Low: "var(--tier-low)",
};

export function tierClass(tier: string): string {
  return `badge badge-${tier.toLowerCase()}`;
}

/** Categorical series colours — used consistently across every chart. */
export const SERIES = [
  "#7c6bff", "#4c9aff", "#35c07f", "#f2a33c", "#ff6f4d",
  "#c07fe8", "#3fc5c9", "#e8688f", "#9aa63a",
];
