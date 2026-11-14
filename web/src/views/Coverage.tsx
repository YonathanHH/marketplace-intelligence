import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, useAsync } from "../api/client";
import { Bars } from "../components/charts";
import { IndonesiaMap } from "../components/IndonesiaMap";
import { Card, ErrorState, Insight, Kpi, LoadingCard, PageHeader, TierBadge } from "../components/ui";
import { daysAgo, formatCompact, formatIDR, formatNumber, formatPercent } from "../lib/format";
import type { CoverageAnalytics } from "../api/types";

type ProvinceRow = CoverageAnalytics["by_province"][number];
type MapMetric = "headroom" | "coverage" | "uncovered";

/** What the choropleth encodes. Each answers a different territory question. */
const MAP_METRICS: Record<MapMetric, {
  label: string;
  subtitle: string;
  value: (p: ProvinceRow) => number;
  format: (v: number) => string;
}> = {
  headroom: {
    label: "Uncovered headroom",
    subtitle: "Monthly revenue sitting with sellers nobody has called, by province",
    value: (p) => p.uncovered_headroom,
    format: (v) => formatIDR(v),
  },
  uncovered: {
    label: "Missed priority accounts",
    subtitle: "Hot and Warm sellers with no outreach on record, by province",
    value: (p) => p.uncovered_priority,
    format: (v) => formatCompact(v),
  },
  coverage: {
    label: "Coverage rate",
    subtitle: "Share of sellers the team has contacted at least once, by province",
    value: (p) => p.coverage_pct,
    format: (v) => formatPercent(v),
  },
};

export default function Coverage() {
  const { data, loading, error, reload } = useAsync(() => api.coverage(), []);
  const [metric, setMetric] = useState<MapMetric>("headroom");
  const navigate = useNavigate();

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <LoadingCard height={520} />;

  const e = data.effort_quality;
  const touched = e.well_targeted + e.low_value_touched;
  const precision = touched ? (e.well_targeted / touched) * 100 : 0;
  const recall = e.well_targeted + e.missed_priority
    ? (e.well_targeted / (e.well_targeted + e.missed_priority)) * 100
    : 0;
  const totalUncovered = data.by_province.reduce((sum, p) => sum + p.uncovered_headroom, 0);

  return (
    <>
      <PageHeader
        title="Coverage and targeting quality"
        description="Whether sales effort is landing on the accounts worth calling. Every contacted seller is compared against what the opportunity model says they were worth."
      />

      <div className="kpi-strip">
        <Kpi
          label="Targeting precision"
          value={formatPercent(precision, 1)}
          meta={`${formatNumber(e.well_targeted)} of ${formatNumber(touched)} contacted were Hot/Warm`}
        />
        <Kpi
          label="Priority coverage"
          value={formatPercent(recall, 1)}
          meta={`${formatNumber(e.missed_priority)} priority accounts never contacted`}
        />
        <Kpi
          label="Uncovered headroom"
          value={formatIDR(totalUncovered)}
          meta="Monthly value in never-contacted accounts"
          accent
        />
        <Kpi
          label="Effort on low-value"
          value={formatNumber(e.low_value_touched)}
          meta="Contacted accounts scoring Cool or Low"
        />
      </div>

      <Insight variant="warning">
        Sales has contacted <strong>{formatNumber(e.low_value_touched)} Cool/Low accounts</strong> while
        leaving <strong>{formatNumber(e.missed_priority)} Hot/Warm accounts untouched</strong>. Only{" "}
        {formatPercent(precision, 1)} of outreach effort landed on accounts the model rates as priority -
        the single clearest efficiency gain available to the team.
      </Insight>

      <Card
        title="Territory map"
        subtitle={MAP_METRICS[metric].subtitle}
        actions={
          <div className="row gap-1">
            {(Object.keys(MAP_METRICS) as MapMetric[]).map((key) => (
              <button
                key={key}
                className={`chip ${metric === key ? "active" : ""}`}
                onClick={() => setMetric(key)}
              >
                {MAP_METRICS[key].label}
              </button>
            ))}
          </div>
        }
      >
        <IndonesiaMap
          rows={data.by_province.map((p) => ({
            province: p.province,
            value: MAP_METRICS[metric].value(p),
            detail: [
              { label: "Sellers", value: formatNumber(p.sellers) },
              { label: "Contacted", value: `${formatNumber(p.contacted)} (${formatPercent(p.coverage_pct)})` },
              { label: "Priority leads", value: formatNumber(p.priority_leads) },
              { label: "Missed priority", value: formatNumber(p.uncovered_priority) },
              { label: "Uncovered headroom", value: formatIDR(p.uncovered_headroom) },
            ],
          }))}
          legendLabel={MAP_METRICS[metric].label}
          formatValue={MAP_METRICS[metric].format}
          onSelect={(province) =>
            navigate(
              `/opportunities?province=${encodeURIComponent(province)}&contact_status=uncontacted`
            )
          }
        />
      </Card>

      {/* The map shows the geographic pattern; these give the exact ordering. */}
      <div className="grid grid-2">
        <Card title="Top territories by unworked value" subtitle="Uncovered headroom, ranked">
          <Bars
            data={data.by_province.slice(0, 9)}
            xKey="province"
            horizontal
            height={300}
            label="Uncovered monthly headroom by province, largest first"
            series={[{ key: "uncovered_headroom", name: "Uncovered headroom" }]}
            valueFormatter={(v) => formatIDR(v)}
          />
        </Card>

        <Card title="Coverage rate by category" subtitle="Share of sellers ever contacted">
          <Bars
            data={data.by_category}
            xKey="category"
            horizontal
            height={300}
            label="Share of sellers contacted at least once, by category"
            series={[{ key: "coverage_pct", name: "Coverage %", color: "var(--series-2)" }]}
            valueFormatter={(v) => formatPercent(v)}
          />
        </Card>
      </div>

      <Card title="Territory detail" subtitle="Coverage and unworked opportunity per province" flush>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Province</th>
                <th className="num">Sellers</th>
                <th className="num">Contacted</th>
                <th className="num">Coverage</th>
                <th className="num">Priority leads</th>
                <th className="num">Uncovered priority</th>
                <th className="num">Uncovered headroom</th>
              </tr>
            </thead>
            <tbody>
              {data.by_province.map((p) => (
                <tr key={p.province}>
                  <td className="cell-primary">{p.province}</td>
                  <td className="num cell-muted">{formatNumber(p.sellers)}</td>
                  <td className="num cell-muted">{formatNumber(p.contacted)}</td>
                  <td className="num">
                    <span className="row gap-2" style={{ justifyContent: "flex-end" }}>
                      {formatPercent(p.coverage_pct)}
                      <span className="score-track" style={{ width: 44 }}>
                        <span
                          className="score-fill"
                          style={{
                            width: `${Math.min(100, p.coverage_pct)}%`,
                            background: p.coverage_pct < 35 ? "var(--danger)" : "var(--success)",
                          }}
                        />
                      </span>
                    </span>
                  </td>
                  <td className="num cell-muted">{formatNumber(p.priority_leads)}</td>
                  <td className="num" style={{ color: p.uncovered_priority > 20 ? "var(--warning)" : undefined }}>
                    {formatNumber(p.uncovered_priority)}
                  </td>
                  <td className="num strong">{formatIDR(p.uncovered_headroom)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card
        title="Stalled priority accounts"
        subtitle="Contacted at least once, no follow-up booked, over 60 days cold"
        flush
      >
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Seller</th>
                <th>Category</th>
                <th>Province</th>
                <th className="num">Score</th>
                <th>Tier</th>
                <th className="num">Last touch</th>
                <th>Owner</th>
                <th className="num">Headroom /mo</th>
              </tr>
            </thead>
            <tbody>
              {data.stale_priority_accounts.map((s) => (
                <tr key={s.seller_id}>
                  <td>
                    <Link to={`/opportunities/${s.seller_id}`} className="cell-primary">
                      {s.seller_name}
                    </Link>
                  </td>
                  <td className="cell-muted">{s.primary_category}</td>
                  <td className="cell-muted">{s.province}</td>
                  <td className="num strong">{s.opportunity_score.toFixed(1)}</td>
                  <td><TierBadge tier={s.priority_tier} /></td>
                  <td className="num cell-muted">{daysAgo(s.days_since_last_contact)}</td>
                  <td className="cell-muted">{s.last_sales_rep}</td>
                  <td className="num strong">{formatIDR(s.monthly_spend_headroom)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
