import { Link } from "react-router-dom";
import { api, useAsync } from "../api/client";
import { AreaTrend, Bars, Donut } from "../components/charts";
import { IconArrowUpRight } from "../components/icons";
import {
  BarList, Card, ErrorState, Insight, Kpi, LoadingCard, PageHeader, ScoreMeter, TierBadge,
} from "../components/ui";
import {
  formatCompact, formatIDR, formatNumber, formatPercent, TIER_COLOR,
} from "../lib/format";

export default function Overview() {
  const { data, loading, error, reload } = useAsync(() => api.overview(), []);
  const marketplace = useAsync(() => api.marketplace(), []);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) {
    return (
      <div className="grid grid-4">
        {Array.from({ length: 8 }).map((_, i) => <LoadingCard key={i} height={104} />)}
      </div>
    );
  }

  const k = data.kpis;
  const uncoveredShare = k.monthly_headroom > 0
    ? (k.uncovered_priority_headroom / k.monthly_headroom) * 100
    : 0;

  return (
    <>
      <PageHeader
        title="Revenue opportunity at a glance"
        description={
          `${formatNumber(k.total_sellers)} sellers analysed across marketplace activity, ad spend and ` +
          `sales coverage. Headroom is estimated from what comparable advertisers in the same category ` +
          `and traction band already pay - not from a flat assumption.`
        }
        actions={
          <Link to="/opportunities" className="btn btn-primary">
            Work the queue <IconArrowUpRight size={14} />
          </Link>
        }
      />

      {/* Headline commercial numbers */}
      <div className="grid grid-4">
        <Kpi
          accent
          label="Untapped monthly revenue"
          value={formatIDR(k.monthly_headroom)}
          meta={<><span>{formatIDR(k.annual_headroom)} annualised</span></>}
          hint="Per-seller spend headroom against comparable advertisers, summed."
        />
        <Kpi
          label="Risk-adjusted pipeline"
          value={formatIDR(k.expected_monthly_value)}
          meta={`Headroom x modelled win rate (avg ${formatPercent(k.avg_win_probability * 100, 1)})`}
          hint="Headroom after each segment's historical conversion rate is applied."
        />
        <Kpi
          label="Current ad revenue"
          value={formatIDR(k.current_monthly_revenue)}
          meta={`${formatNumber(k.advertisers)} advertisers · ${formatPercent(k.advertiser_penetration)} of sellers`}
        />
        <Kpi
          label="Hot leads"
          value={formatNumber(k.hot_leads)}
          meta={`${formatNumber(k.uncovered_priority_leads)} priority accounts never contacted`}
        />
      </div>

      <Insight variant={uncoveredShare > 15 ? "warning" : "accent"}>
        <strong>{formatIDR(k.uncovered_priority_headroom)}/month</strong> of estimated headroom sits with{" "}
        <strong>{formatNumber(k.uncovered_priority_leads)} Hot or Warm sellers who have never been
        contacted</strong> - {formatPercent(uncoveredShare)} of all identified opportunity. Sales coverage
        currently reaches {formatPercent(k.coverage_rate)} of the seller base, and it is not concentrated
        on the highest-potential accounts.
      </Insight>

      {/* Opportunity distribution + revenue split */}
      <div className="grid grid-2-1">
        <Card
          title="Marketplace demand trend"
          subtitle="Daily organic activity across all listings"
        >
          {marketplace.data ? (
            <AreaTrend
              data={marketplace.data.trend}
              xKey="date"
              height={250}
              label="Daily marketplace views and buyer contacts over the observed period"
              series={[
                { key: "views", name: "Views", color: "var(--series-1)" },
                { key: "leads", name: "Buyer contacts", color: "var(--series-6)" },
              ]}
              xFormatter={(v) => new Date(v).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}
              valueFormatter={(v) => formatNumber(v)}
            />
          ) : (
            <LoadingCard height={250} />
          )}
        </Card>

        <Card title="Opportunity mix" subtitle="Sellers and headroom by priority tier">
          <Donut
            data={data.tier_mix}
            nameKey="tier"
            valueKey="monthly_headroom"
            height={186}
            label="Share of monthly headroom by priority tier"
            colors={data.tier_mix.map((t) => TIER_COLOR[t.tier])}
            centerValue={formatIDR(k.monthly_headroom)}
            centerLabel="monthly headroom"
            valueFormatter={(v) => formatIDR(v)}
          />
          <div className="stack gap-2" style={{ marginTop: "var(--space-4)" }}>
            {data.tier_mix.map((t) => (
              <div className="row gap-2" key={t.tier} style={{ fontSize: "var(--text-sm)" }}>
                <span className="legend-swatch" style={{ background: TIER_COLOR[t.tier] }} />
                <span>{t.tier}</span>
                <span className="ml-auto num muted">{formatNumber(t.sellers)} sellers</span>
                <span className="num strong" style={{ minWidth: 64, textAlign: "right" }}>
                  {formatIDR(t.monthly_headroom)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Where the money is */}
      <div className="grid grid-2">
        <Card
          title="Headroom by category"
          subtitle="Untapped monthly revenue, largest first"
        >
          <BarList
            items={data.category_opportunity.slice(0, 9).map((c) => ({
              label: c.category,
              value: c.monthly_headroom,
              meta: `${c.advertisers}/${c.sellers} advertising`,
            }))}
            valueFormat={(v) => formatIDR(v)}
            color={(_, i) => `var(--series-${(i % 9) + 1})`}
          />
        </Card>

        <Card
          title="New business vs. expansion"
          subtitle="Where the headroom sits today"
        >
          <Bars
            data={[
              { segment: "Never advertised", value: k.new_logo_headroom },
              { segment: "Existing advertisers", value: k.upsell_headroom },
            ]}
            xKey="segment"
            height={200}
            label="Monthly headroom split between sellers who have never advertised and existing advertisers"
            series={[{ key: "value", name: "Monthly headroom" }]}
            colorByIndex
            valueFormatter={(v) => formatIDR(v)}
          />
          <div className="definition" style={{ marginTop: "var(--space-5)" }}>
            <div>
              <dt>New-logo headroom</dt>
              <dd>{formatIDR(k.new_logo_headroom)}</dd>
            </div>
            <div>
              <dt>Expansion headroom</dt>
              <dd>{formatIDR(k.upsell_headroom)}</dd>
            </div>
            <div>
              <dt>Marketplace views</dt>
              <dd>{formatCompact(data.marketplace.total_views)}</dd>
            </div>
            <div>
              <dt>Buyer contacts</dt>
              <dd>{formatCompact(data.marketplace.total_leads_generated)}</dd>
            </div>
          </div>
        </Card>
      </div>

      {/* Top leads */}
      <Card
        title="Today's top opportunities"
        subtitle="Highest-scoring accounts, ranked by the four-pillar model"
        flush
        actions={
          <Link to="/opportunities" className="btn btn-sm">
            View all
          </Link>
        }
      >
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th style={{ width: 40 }}>#</th>
                <th>Seller</th>
                <th>Category</th>
                <th className="num">Score</th>
                <th className="num">Monthly headroom</th>
                <th>Recommended play</th>
                <th>Why now</th>
              </tr>
            </thead>
            <tbody>
              {data.top_leads.map((lead) => (
                <tr key={lead.seller_id}>
                  <td className="num faint">{lead.rank}</td>
                  <td>
                    <Link to={`/opportunities/${lead.seller_id}`}>
                      <span className="cell-primary">{lead.seller_name}</span>
                      <span className="cell-secondary">{lead.city}, {lead.province}</span>
                    </Link>
                  </td>
                  <td className="cell-muted">{lead.primary_category}</td>
                  <td className="num">
                    <ScoreMeter score={lead.opportunity_score} tier={lead.priority_tier} />
                  </td>
                  <td className="num strong">{formatIDR(lead.monthly_spend_headroom)}</td>
                  <td>
                    <span className="badge badge-accent">{lead.recommended_product_label}</span>
                  </td>
                  <td className="cell-muted small" style={{ maxWidth: 320 }}>
                    <span className="truncate" style={{ display: "block" }} title={lead.reason}>
                      {lead.next_best_action} · {lead.touch_count === 0 ? "never contacted" : "in progress"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="row gap-3 small faint">
        <TierBadge tier="Hot" />
        <span>
          Scores combine organic traction, monetisation gap, seller readiness and outreach gap.
          Data as of {data.as_of}.
        </span>
      </div>
    </>
  );
}
