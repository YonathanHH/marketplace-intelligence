/** Shared UI primitives, all styled from the design tokens. */

import type { ReactNode } from "react";
import { formatCompact, TIER_COLOR } from "../lib/format";
import { IconAlert, IconInfo } from "./icons";

/* ------------------------------------------------------------------ Card -- */
export function Card({
  title, subtitle, actions, children, flush, className = "",
}: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode;
  children: ReactNode; flush?: boolean; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-header">
          {title && (
            <div>
              <div className="card-title">{title}</div>
              {subtitle && <div className="card-subtitle">{subtitle}</div>}
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
export function Kpi({
  label, value, meta, accent, tooltip,
}: {
  label: string; value: ReactNode; meta?: ReactNode; accent?: boolean; tooltip?: string;
}) {
  return (
    <div className={`kpi ${accent ? "kpi-accent" : ""}`} title={tooltip}>
      <div className="kpi-label">
        {label}
        {tooltip && <IconInfo size={12} className="faint" />}
      </div>
      <div className="kpi-value">{value}</div>
      {meta && <div className="kpi-meta">{meta}</div>}
    </div>
  );
}

/* ----------------------------------------------------------------- Badge -- */
export function TierBadge({ tier }: { tier: string }) {
  return (
    <span className={`badge badge-${tier.toLowerCase()}`}>
      <span className="badge-dot" />
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
      <div className="score-track">
        <div className="score-fill" style={{ width: `${Math.min(100, score)}%`, background: color }} />
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- Bar list -- */
export function BarList({
  items, valueFormat = formatCompact, color = "var(--accent)",
}: {
  items: { label: string; value: number; meta?: string }[];
  valueFormat?: (v: number) => string;
  color?: string | ((item: { label: string; value: number }, i: number) => string);
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="bar-list">
      {items.map((item, i) => (
        <div className="bar-row" key={item.label}>
          <div className="bar-label" title={item.label}>{item.label}</div>
          <div className="bar-value">
            {valueFormat(item.value)}
            {item.meta && <span className="faint"> · {item.meta}</span>}
          </div>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{
                width: `${(item.value / max) * 100}%`,
                background: typeof color === "function" ? color(item, i) : color,
              }}
            />
          </div>
        </div>
      ))}
    </div>
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
    <div className="funnel">
      {steps.map((step, i) => {
        const pct = (step.value / max) * 100;
        const prev = i > 0 ? steps[i - 1].value : null;
        const conversion = prev && prev > 0 ? (step.value / prev) * 100 : null;
        return (
          <div className="funnel-step" key={step.name}>
            <div className="funnel-name">{step.name}</div>
            <div
              className="funnel-bar"
              style={{
                width: `${Math.max(pct, 2)}%`,
                background: color,
                opacity: 1 - i * 0.12,
              }}
            >
              {pct > 18 && formatCompact(step.value)}
            </div>
            <div className="funnel-meta">
              {pct <= 18 && <span>{formatCompact(step.value)} </span>}
              {conversion !== null && <span>{conversion.toFixed(1)}%</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------- States -- */
export function Empty({ children = "No results" }: { children?: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Spinner() {
  return <span className="spinner" role="status" aria-label="Loading" />;
}

export function LoadingCard({ height = 240 }: { height?: number }) {
  return <div className="skeleton" style={{ height, borderRadius: "var(--radius-lg)" }} />;
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
      {actions && <div className="row gap-2 ml-auto">{actions}</div>}
    </header>
  );
}
