import { api, useAsync } from "../api/client";
import { Bars, Donut, LineTrend } from "../components/charts";
import { Card, ErrorState, Insight, Kpi, LoadingCard, PageHeader } from "../components/ui";
import {
  formatCompact, formatIDR, formatMonth, formatNumber, formatPercent, SERIES, titleCase,
} from "../lib/format";

export default function Advertising() {
  const { data, loading, error, reload } = useAsync(() => api.advertising(), []);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <LoadingCard height={520} />;

  const t = data.totals;
  const budgetUtilisation = t.total_budget ? (t.total_spend / t.total_budget) * 100 : 0;
  const bestValue = [...data.by_type].sort((a, b) => a.cost_per_conversion - b.cost_per_conversion)[0];

  return (
    <>
      <PageHeader
        title="Advertising performance"
        description="What the existing advertiser base spends, which products they buy, and how efficiently that spend converts into buyer contacts."
      />

      <div className="grid grid-4">
        <Kpi label="Total ad spend" value={formatIDR(t.total_spend)} meta={`${formatNumber(t.campaigns)} campaigns`} accent />
        <Kpi label="Active advertisers" value={formatNumber(t.advertisers)} meta="Sellers with at least one campaign" />
        <Kpi label="Blended CTR" value={formatPercent(t.blended_ctr, 2)} meta="Clicks per impression, all placements" />
        <Kpi label="Cost per conversion" value={formatIDR(t.blended_cpa)} meta={`${formatCompact(t.conversions)} conversions`} />
      </div>

      {bestValue && (
        <Insight>
          <strong>{titleCase(bestValue.campaign_type)}</strong> is the most efficient placement at{" "}
          <strong>{formatIDR(bestValue.cost_per_conversion)}</strong> per conversion and a{" "}
          {formatPercent(bestValue.ctr_pct, 2)} click-through rate. Budget utilisation across all
          campaigns is {formatPercent(budgetUtilisation)}, so there is committed budget still unspent.
        </Insight>
      )}

      <Card title="Ad revenue trend" subtitle="Monthly spend and active advertiser count">
        <LineTrend
          data={data.revenue_trend}
          xKey="month"
          height={260}
          series={[
            { key: "spend", name: "Spend (IDR)", color: "#7c6bff" },
            { key: "advertisers", name: "Advertisers", color: "#35c07f" },
          ]}
          xFormatter={formatMonth}
          valueFormatter={(v, name) => (name.includes("Spend") ? formatIDR(v) : formatNumber(v))}
        />
      </Card>

      <div className="grid grid-2">
        <Card title="Spend by product" subtitle="Which placements generate the revenue">
          <Bars
            data={data.by_type}
            xKey="campaign_type"
            horizontal
            height={240}
            series={[{ key: "spend", name: "Spend" }]}
            colorByIndex
            xFormatter={titleCase}
            valueFormatter={(v) => formatIDR(v)}
          />
        </Card>

        <Card title="Spend by category" subtitle="Where advertiser demand concentrates">
          <Donut
            data={data.by_category}
            nameKey="category"
            valueKey="spend"
            height={240}
            centerValue={formatIDR(t.total_spend)}
            centerLabel="total spend"
            valueFormatter={(v) => formatIDR(v)}
          />
        </Card>
      </div>

      <Card title="Product efficiency" subtitle="Every placement compared on reach, cost and conversion" flush>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Placement</th>
                <th className="num">Campaigns</th>
                <th className="num">Spend</th>
                <th className="num">Impressions</th>
                <th className="num">CTR</th>
                <th className="num">CPC</th>
                <th className="num">Conv. rate</th>
                <th className="num">Cost / conversion</th>
              </tr>
            </thead>
            <tbody>
              {data.by_type.map((row, i) => (
                <tr key={row.campaign_type}>
                  <td>
                    <span className="row gap-2">
                      <span className="legend-swatch" style={{ background: SERIES[i % SERIES.length] }} />
                      <span className="cell-primary" style={{ display: "inline" }}>
                        {titleCase(row.campaign_type)}
                      </span>
                    </span>
                  </td>
                  <td className="num cell-muted">{formatNumber(row.campaigns)}</td>
                  <td className="num strong">{formatIDR(row.spend)}</td>
                  <td className="num cell-muted">{formatCompact(row.impressions)}</td>
                  <td className="num">{formatPercent(row.ctr_pct, 2)}</td>
                  <td className="num cell-muted">{formatIDR(row.cpc)}</td>
                  <td className="num cell-muted">{formatPercent(row.conversion_rate, 1)}</td>
                  <td className="num">{formatIDR(row.cost_per_conversion)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-2">
        <Card
          title="Adoption by account tier"
          subtitle="Penetration and remaining headroom per plan"
          flush
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Account tier</th>
                  <th className="num">Sellers</th>
                  <th className="num">Advertising</th>
                  <th className="num">Penetration</th>
                  <th className="num">Revenue /mo</th>
                  <th className="num">Headroom /mo</th>
                </tr>
              </thead>
              <tbody>
                {data.penetration.map((row) => (
                  <tr key={row.account_tier}>
                    <td className="cell-primary">{titleCase(row.account_tier)}</td>
                    <td className="num cell-muted">{formatNumber(row.sellers)}</td>
                    <td className="num cell-muted">{formatNumber(row.advertisers)}</td>
                    <td className="num">{formatPercent(row.penetration_pct)}</td>
                    <td className="num">{formatIDR(row.monthly_revenue)}</td>
                    <td className="num strong">{formatIDR(row.monthly_headroom)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Spend distribution" subtitle="How many sellers sit in each monthly spend band">
          <Bars
            data={data.spend_distribution}
            xKey="band"
            horizontal
            height={260}
            series={[{ key: "sellers", name: "Sellers" }]}
            colorByIndex
            valueFormatter={(v) => formatNumber(v)}
          />
        </Card>
      </div>
    </>
  );
}
