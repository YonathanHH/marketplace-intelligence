/**
 * Deep Dive — the analyses that need a columnar engine.
 *
 * Everything on this page comes from `/api/analytics/olap`, which serves the
 * results of the DuckDB pass run at build time (olxads/olap.py). Each card
 * answers one commercial question and shows the numbers behind it, because a
 * finding a rep cannot audit is a finding a rep will not use.
 */

import { Link } from "react-router-dom";
import { api, useAsync } from "../api/client";
import { Bars, LineTrend } from "../components/charts";
import { IconArrowUpRight } from "../components/icons";
import {
  Card, ErrorState, Insight, Kpi, LoadingCard, PageHeader, TableScroll,
} from "../components/ui";
import { formatCompact, formatIDR, formatNumber, formatPercent } from "../lib/format";
import type { OlapAnalytics } from "../api/types";

export default function DeepDive() {
  const { data, loading, error, reload } = useAsync(() => api.olap(), []);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) {
    return (
      <>
        <LoadingCard height={92} label="Loading analytical engine details" />
        <div className="grid grid-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <LoadingCard key={i} height={104} label="Loading headline figures" />
          ))}
        </div>
        <LoadingCard height={360} label="Loading deep-dive analytics" />
      </>
    );
  }

  const h = data.headlines;

  return (
    <>
      <PageHeader
        title="Deep dive"
        description={
          "Six analyses that need a columnar engine: demand decay, category momentum, " +
          "revenue concentration, traction distribution and a point-in-time review of past " +
          "outreach. Computed over the full metric fact at build time, not sampled."
        }
      />

      <EngineStrip engine={data.engine} />

      <div className="grid grid-4">
        <Kpi
          accent
          label="Week-3 organic reach"
          value={formatPercent(h.retention_week3 ?? 0, 0)}
          meta="of a listing's first-week daily views"
          hint="The gap paid re-promotion is sold into."
        />
        <Kpi
          label="Revenue in the top 5%"
          value={formatPercent(h.top_5pct_revenue_share ?? 0, 1)}
          meta={`Top 20% carry ${formatPercent(h.top_20pct_revenue_share ?? 0, 1)}`}
          hint="Concentration risk across the current advertiser book."
        />
        <Kpi
          label="Out-performing non-advertisers"
          value={formatNumber(h.underdog_sellers)}
          meta={`${formatIDR(h.underdog_headroom)}/mo of headroom`}
          hint="Sellers with no ad spend whose organic demand beats the median paying seller in their own category."
        />
        <Kpi
          label="Conversion lift from traction"
          value={`${h.conversion_lift ?? "—"}×`}
          meta={`${formatPercent(h.conversion_bottom_quintile ?? 0, 1)} → ${formatPercent(
            h.conversion_top_quintile ?? 0, 1
          )} across quintiles`}
          hint="Measured against each seller's traction on the day they were actually called."
        />
      </div>

      <DecayCard data={data} />

      <div className="grid grid-2">
        <MomentumCard data={data} />
        <ConcentrationCard data={data} />
      </div>

      <DistributionCard data={data} />
      <ConversionCard data={data} />
    </>
  );
}

/* ---------------------------------------------------------------- Engine -- */

function EngineStrip({ engine }: { engine: OlapAnalytics["engine"] }) {
  return (
    <div className="engine-strip">
      <span className="engine-pill">
        DuckDB {engine.version ?? ""}
      </span>
      <span>
        {formatNumber(engine.fact_rows ?? 0)} fact rows scanned
      </span>
      <span className="sep" aria-hidden="true">·</span>
      <span>
        six analyses in {formatNumber((engine.build_ms ?? 0) / 1000, 1)}s at build time
      </span>
      <span className="sep" aria-hidden="true">·</span>
      <span className="faint">
        results materialised into SQLite, so serving stays dependency-free
      </span>
    </div>
  );
}

/* ------------------------------------------------------------ 1. Decay --- */

function DecayCard({ data }: { data: OlapAnalytics }) {
  const overall = data.listing_decay_overall;
  const week0 = overall[0];
  const last = overall[overall.length - 1];

  // Per-category curves, wide-form so one line per category can be plotted.
  const categories = Array.from(new Set(data.listing_decay.map((r) => r.category)));
  const weeks = Array.from(new Set(data.listing_decay.map((r) => r.week_since_post))).sort(
    (a, b) => a - b
  );
  const series = weeks.map((week) => {
    const row: Record<string, number | string> = { week: `Week ${week}` };
    for (const category of categories) {
      const match = data.listing_decay.find(
        (r) => r.category === category && r.week_since_post === week
      );
      if (match) row[category] = match.retention_index;
    }
    return row;
  });

  return (
    <Card
      title="Organic demand decays within a fortnight"
      subtitle="Average daily views per listing, indexed to its own first week — every category, same shape"
    >
      <div className="grid grid-2-1" style={{ gap: "var(--space-5)" }}>
        <LineTrend
          data={series}
          xKey="week"
          height={280}
          label={
            `Listing demand decay by category. Indexed to week 0 at 100, falling to about ` +
            `${Math.round(last?.retention_index ?? 0)} by week ${last?.week_since_post ?? 0}.`
          }
          series={categories.map((category) => ({ key: category, name: category }))}
          valueFormatter={(v) => `${v.toFixed(0)}% of week 0`}
          referenceY={{ value: 100, label: "week 0" }}
        />

        <div className="stack gap-4">
          <p className="small muted" style={{ lineHeight: 1.6, margin: 0 }}>
            A new listing pulls{" "}
            <strong className="strong" style={{ color: "var(--text)" }}>
              {formatNumber(week0?.avg_daily_views ?? 0, 1)} views a day
            </strong>{" "}
            in its first week, and{" "}
            <strong className="strong" style={{ color: "var(--text)" }}>
              {formatNumber(last?.avg_daily_views ?? 0, 1)}
            </strong>{" "}
            by week {last?.week_since_post}. The collapse is the same in all{" "}
            {categories.length} categories, which makes it a property of the ranking surface
            rather than of any one market — and the reason Bump Up and Search Boost have
            something real to sell.
          </p>

          <TableScroll label="Demand decay week by week">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">Week</th>
                  <th scope="col" className="num">Views/day</th>
                  <th scope="col" className="num">Contacts/day</th>
                  <th scope="col" className="num">vs week 0</th>
                </tr>
              </thead>
              <tbody>
                {overall.map((row) => (
                  <tr key={row.week_since_post}>
                    <th scope="row" className="cell-primary">Week {row.week_since_post}</th>
                    <td className="num">{formatNumber(row.avg_daily_views, 1)}</td>
                    <td className="num cell-muted">{formatNumber(row.avg_daily_leads, 2)}</td>
                    <td className="num strong">{formatPercent(row.retention_index, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        </div>
      </div>
    </Card>
  );
}

/* --------------------------------------------------------- 2. Momentum --- */

function MomentumCard({ data }: { data: OlapAnalytics }) {
  const rows = data.category_momentum;
  const rising = rows.filter((r) => (r.momentum_pct ?? 0) > 0);

  return (
    <Card
      title="Category momentum"
      subtitle="Last four complete weeks of demand against the four before them"
    >
      <Bars
        data={rows.map((r) => ({ ...r, momentum_pct: r.momentum_pct ?? 0 }))}
        xKey="category"
        horizontal
        height={280}
        label={
          `Week-on-week demand momentum by category. ` +
          `${rising.length} of ${rows.length} categories are growing.`
        }
        series={[{ key: "momentum_pct", name: "Momentum" }]}
        colorByIndex
        valueFormatter={(v) => formatPercent(v, 1)}
      />
      <p className="small faint" style={{ marginTop: "var(--space-4)", lineHeight: 1.55 }}>
        Only {rising.length} of {rows.length} categories grew. Partial weeks at each end of the
        window are dropped, so a half-collected week cannot read as a crash.
      </p>
    </Card>
  );
}

/* ---------------------------------------------------- 3. Concentration --- */

function ConcentrationCard({ data }: { data: OlapAnalytics }) {
  const rows = data.revenue_concentration;
  const curve = rows.map((r) => ({
    advertiser_pct: `${r.advertiser_pct}%`,
    cum_revenue_pct: r.cum_revenue_pct,
    even: r.advertiser_pct,
  }));

  return (
    <Card
      title="Revenue concentration"
      subtitle="Cumulative share of ad revenue as advertisers are added, largest first"
    >
      <LineTrend
        data={curve}
        xKey="advertiser_pct"
        height={280}
        label={
          `Lorenz curve of ad revenue. The top 5 percent of advertisers carry ` +
          `${formatPercent(data.headlines.top_5pct_revenue_share ?? 0, 1)} of spend.`
        }
        series={[
          { key: "cum_revenue_pct", name: "Cumulative revenue" },
          { key: "even", name: "If spend were even", color: "var(--text-faint)", dashed: true },
        ]}
        valueFormatter={(v) => formatPercent(v, 1)}
      />
      <p className="small faint" style={{ marginTop: "var(--space-4)", lineHeight: 1.55 }}>
        The distance between the two lines is the concentration risk: the top{" "}
        {formatPercent(20, 0)} of accounts carry{" "}
        {formatPercent(data.headlines.top_20pct_revenue_share ?? 0, 1)} of revenue. Widening the
        base is what the opportunity queue is for.
      </p>
    </Card>
  );
}

/* ---------------------------------------------------- 4. Distribution ---- */

function DistributionCard({ data }: { data: OlapAnalytics }) {
  const rows = data.traction_percentiles;
  const scaleMax = Math.max(...rows.map((r) => r.p90), 1);
  const pct = (value: number) => `${(value / scaleMax) * 100}%`;

  return (
    <Card
      title="Where the unsold demand actually sits"
      subtitle="Organic views per seller, p10 to p90 by category, with the median advertiser marked"
    >
      <Insight>
        <strong>{formatNumber(data.headlines.underdog_sellers)} sellers</strong> who have never
        bought advertising already out-perform the median <em>paying</em> seller in their own
        category — {formatIDR(data.headlines.underdog_headroom)}/month of headroom sitting in
        accounts that look, on demand alone, like existing customers.{" "}
        <Link to="/opportunities?advertiser_status=never&tier=Hot&tier=Warm">
          Open that segment <IconArrowUpRight size={12} />
        </Link>
      </Insight>

      <div style={{ marginTop: "var(--space-5)" }}>
        <div className="legend" style={{ marginBottom: "var(--space-3)" }}>
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: "var(--accent-soft)", border: "1px solid var(--accent-border)" }} />
            p25–p75
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: "var(--accent)", width: 3 }} />
            Median seller
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: "var(--tier-cool)", width: 3 }} />
            Median advertiser
          </span>
          <span className="legend-item faint">Whisker spans p10–p90</span>
        </div>

        {rows.map((row) => (
          <div className="dist-row" key={row.category}>
            <span className="dist-name" title={row.category}>{row.category}</span>
            <div
              className="dist-plot"
              role="img"
              aria-label={
                `${row.category}: median ${Math.round(row.p50)} views, ` +
                `p10 ${Math.round(row.p10)} to p90 ${Math.round(row.p90)}. ` +
                `Median advertiser ${Math.round(row.median_advertiser)}, ` +
                `median non-advertiser ${Math.round(row.median_non_advertiser)}.`
              }
            >
              <span
                className="dist-whisker"
                style={{ left: pct(row.p10), width: pct(row.p90 - row.p10) }}
              />
              <span
                className="dist-box"
                style={{ left: pct(row.p25), width: pct(row.p75 - row.p25) }}
              />
              <span className="dist-marker median" style={{ left: pct(row.p50) }} />
              <span className="dist-marker advertiser" style={{ left: pct(row.median_advertiser) }} />
            </div>
            <span className="dist-value">
              {formatCompact(row.p50)} median ·{" "}
              <strong className="strong">{row.non_advertisers_above_median}</strong> above
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------ 5. Conversion ---- */

function ConversionCard({ data }: { data: OlapAnalytics }) {
  const rows = data.conversion_by_traction;
  const best = Math.max(...rows.map((r) => r.conversion_rate_pct), 0.01);

  return (
    <Card
      title="Did past outreach convert better on high-traction sellers?"
      subtitle="Every logged activity matched to the seller's trailing 28-day views on the day of the call"
    >
      <div className="grid grid-1-2" style={{ gap: "var(--space-5)" }}>
        <div className="stack gap-4">
          <p className="small muted" style={{ margin: 0, lineHeight: 1.6 }}>
            Scores are computed as of today, so grading historical outreach against them would be
            hindsight. This reconstructs each seller's traction <em>as it stood on the call date</em>{" "}
            and sorts the {formatNumber(rows.reduce((n, r) => n + r.activities, 0))} logged
            activities into quintiles by it.
          </p>
          <p className="small muted" style={{ margin: 0, lineHeight: 1.6 }}>
            Conversion rises{" "}
            <strong className="strong" style={{ color: "var(--text)" }}>
              {data.headlines.conversion_lift}&times;
            </strong>{" "}
            from the least to the most trafficked quintile. That is the premise the opportunity
            model rests on, measured against outreach that happened before the model existed.
          </p>
          <pre className="sql-block" tabIndex={0} aria-label="The point-in-time join, in SQL">
{`ASOF LEFT JOIN rolling t
  ON a.seller_id = t.seller_id
 AND a.activity_date >= t.date`}
          </pre>
          <p className="small faint" style={{ margin: 0, lineHeight: 1.55 }}>
            An <span className="mono">ASOF JOIN</span> takes the most recent row at or before each
            call — a point-in-time lookup SQLite cannot express, and the reason this analysis runs
            on DuckDB.
          </p>
        </div>

        <ol className="ladder">
          {rows.map((row) => (
            <li className="ladder-step" key={row.quintile}>
              <span className="ladder-label">
                Quintile {row.quintile}
                <small>
                  {formatCompact(row.views_floor)}–{formatCompact(row.views_ceiling)} views ·{" "}
                  {row.conversions}/{row.activities} won
                </small>
              </span>
              <span
                className={`ladder-bar ${row.conversion_rate_pct === best ? "best" : ""}`}
                style={{ width: `${(row.conversion_rate_pct / best) * 100}%` }}
                aria-hidden="true"
              />
              <span className="ladder-value">{formatPercent(row.conversion_rate_pct, 2)}</span>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  );
}
