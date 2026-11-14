/** Shared UI primitives, all styled from the design tokens. */

import { useId, type ReactNode } from "react";
import { formatCompact, TIER_COLOR } from "../lib/format";
import { IconAlert, IconInfo } from "./icons";

/* ------------------------------------------------------------------ Card -- */
export function Card({
  title, subtitle, actions, children, flush, className = "",
}: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode;
  children: ReactNode; flush?: boolean; className?: string;
}) {
  const titleId = useId();
  return (
    <section className={`card ${className}`} aria-labelledby={title ? titleId : undefined}>
      {(title || actions) && (
        <header className="card-header">
          {title && (
            <div className="card-heading">
              <h2 className="card-title" id={titleId}>{title}</h2>
              {subtitle && <p className="card-subtitle">{subtitle}</p>}
            </div>
          )}
          {actions && <div className="card-header-actions">{actions}</div>}
        </header>
      )}
      <div className={`card-body ${flush ? "flush" : ""}`}>{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------- KPI -- */
/**
 * A headline figure. `hint` is rendered as real, always-visible text rather
 * than a `title` attribute: native tooltips never appear for keyboard or touch
 * users, so anything worth explaining has to be on the page.
 */
export function Kpi({
  label, value, meta, accent, hint,
}: {
  label: string; value: ReactNode; meta?: ReactNode; accent?: boolean; hint?: string;
}) {
  return (
    <div className={`kpi ${accent ? "kpi-lead" : ""}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {meta && <div className="kpi-meta">{meta}</div>}
      {hint && (
        <p className="kpi-hint">
          <IconInfo size={11} />
          {hint}
        </p>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- Badge -- */
export function TierBadge({ tier }: { tier: string }) {
  return (
    <span className={`badge badge-${tier.toLowerCase()}`}>
      <span className="badge-dot" aria-hidden="true" />
      {tier}
    </span>
  );
}

export function Badge({
  children, variant = "neutral",
}: { children: ReactNode; variant?: "neutral" | "success" | "warning" | "danger" | "info" | "accent" }) {
  return <span className={`badge badge-${variant}`}>{children}</span>;
}

/* ------------------------------------------------------------ Score meter -- */
export function ScoreMeter({ score, tier }: { score: number; tier?: string }) {
  const color = tier ? TIER_COLOR[tier] ?? "var(--accent)" : "var(--accent)";
  return (
    <div className="score-cell">
      <span className="score-value" style={{ color }}>{score.toFixed(1)}</span>
      {/* The number is already announced; the bar is a visual echo of it. */}
      <div className="score-track" aria-hidden="true">
        <div className="score-fill" style={{ width: `${Math.min(100, score)}%`, background: color }} />
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- Bar list -- */
/** One hue by default: a ranked bar list is a single measure, so colouring each
 *  bar differently would imply a category that is not there. A per-item colour
 *  is allowed only for semantic status (won/lost, outcome), never a rainbow. */
export function BarList({
  items, valueFormat = formatCompact, color = "var(--accent)",
}: {
  items: { label: string; value: number; meta?: string }[];
  valueFormat?: (v: number) => string;
  color?: string | ((item: { label: string; value: number; meta?: string }) => string);
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ul className="bar-list">
      {items.map((item) => (
        <li className="bar-row" key={item.label}>
          <span className="bar-label" title={item.label}>{item.label}</span>
          <span className="bar-value">
            {valueFormat(item.value)}
            {item.meta && <span className="faint"> · {item.meta}</span>}
          </span>
          <span className="bar-track" aria-hidden="true">
            <span
              className="bar-fill"
              style={{
                width: `${(item.value / max) * 100}%`,
                background: typeof color === "function" ? color(item) : color,
              }}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}

/* ---------------------------------------------------------------- Funnel -- */
export function Funnel({
  steps, color = "var(--accent)",
}: {
  steps: { name: string; value: number; meta?: string }[];
  color?: string;
}) {
  const max = Math.max(...steps.map((s) => s.value), 1);
  return (
    <ol className="funnel">
      {steps.map((step, i) => {
        const pct = (step.value / max) * 100;
        const prev = i > 0 ? steps[i - 1].value : null;
        const conversion = prev && prev > 0 ? (step.value / prev) * 100 : null;
        return (
          <li className="funnel-step" key={step.name}>
            <span className="funnel-name">{step.name}</span>
            <span
              className="funnel-bar"
              style={{ width: `${Math.max(pct, 2)}%`, background: color, opacity: 1 - i * 0.12 }}
            >
              {pct > 18 && formatCompact(step.value)}
            </span>
            <span className="funnel-meta">
              {pct <= 18 && <span>{formatCompact(step.value)} </span>}
              {conversion !== null && <span>{conversion.toFixed(1)}%</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/* ----------------------------------------------------------------- Table -- */
/**
 * A wide table has to scroll sideways on a narrow viewport, and a scrollable
 * region has to be reachable by keyboard (WCAG 2.1.1) — so it gets a tabindex
 * and an accessible name rather than being a bare overflow container.
 */
export function TableScroll({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label={label}>
      {children}
    </div>
  );
}

export type SortDirection = "asc" | "desc";

/**
 * A sortable column header. The click target is a real button so it is
 * focusable and operable from the keyboard, and `aria-sort` on the cell tells
 * a screen reader the current state — a bare `onClick` on a `<th>` gives
 * neither.
 */
export function SortHeader({
  label, columnKey, sort, order, onSort, numeric, style,
}: {
  label: string;
  columnKey: string;
  sort: string;
  order: SortDirection;
  onSort: (key: string) => void;
  numeric?: boolean;
  style?: React.CSSProperties;
}) {
  const active = sort === columnKey;
  return (
    <th
      scope="col"
      className={numeric ? "num" : undefined}
      aria-sort={active ? (order === "desc" ? "descending" : "ascending") : "none"}
      style={style}
    >
      <button type="button" className="th-sort" onClick={() => onSort(columnKey)}>
        {label}
        <span className="sort-arrow" aria-hidden="true">
          {active ? (order === "desc" ? "↓" : "↑") : "↕"}
        </span>
        <span className="sr-only">
          {active
            ? `, sorted ${order === "desc" ? "descending" : "ascending"}. Activate to reverse.`
            : ", not sorted. Activate to sort."}
        </span>
      </button>
    </th>
  );
}

/* ---------------------------------------------------------------- States -- */
export function Empty({
  children = "No results", action,
}: { children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty" role="status">
      <p className="empty-message">{children}</p>
      {action}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="spinner-wrap">
      <span className="spinner" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

export function LoadingCard({ height = 240, label = "Loading" }: { height?: number; label?: string }) {
  return (
    <div
      className="skeleton"
      style={{ height, borderRadius: "var(--radius-lg)" }}
      role="status"
      aria-busy="true"
      aria-label={label}
    />
  );
}

/** A skeleton shaped like the thing it stands in for, so the layout does not
 *  jump when the real content arrives. */
export function LoadingTable({ rows = 8, label = "Loading table" }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton-table" role="status" aria-busy="true" aria-label={label}>
      <div className="skeleton skeleton-row head" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton skeleton-row" style={{ opacity: 1 - i * 0.06 }} />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="insight warning" role="alert">
      <IconAlert size={16} />
      <div>
        <div className="strong">Could not load this data</div>
        <div className="small muted" style={{ marginTop: 2 }}>{message}</div>
        {onRetry && (
          <button className="btn btn-sm" style={{ marginTop: 10 }} onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function Insight({
  children, variant = "accent",
}: { children: ReactNode; variant?: "accent" | "warning" }) {
  return (
    <div className={`insight ${variant === "warning" ? "warning" : ""}`}>
      {variant === "warning" ? <IconAlert size={16} /> : <IconInfo size={16} />}
      <div>{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------ Page header -- */
export function PageHeader({
  title, description, actions,
}: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div style={{ minWidth: 0 }}>
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-desc">{description}</p>}
      </div>
      {actions && <div className="row gap-2 wrap ml-auto">{actions}</div>}
    </header>
  );
}
