import { api, useAsync } from "../api/client";
import { Bars, LineTrend } from "../components/charts";
import { BarList, Card, ErrorState, Kpi, LoadingCard, PageHeader } from "../components/ui";
import {
  formatIDR, formatMonth, formatNumber, formatPercent, SERIES, titleCase,
} from "../lib/format";

const OUTCOME_COLOR: Record<string, string> = {
  converted: "var(--success)",
  interested: "var(--accent)",
  follow_up_scheduled: "var(--info)",
  no_response: "var(--text-faint)",
  not_interested: "var(--danger)",
};

export default function Pipeline() {
  const { data, loading, error, reload } = useAsync(() => api.pipeline(), []);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <LoadingCard height={520} />;

  const t = data.totals;
  const winRate = t.accounts_touched ? (t.wins / t.accounts_touched) * 100 : 0;
  const openPipeline = data.stage_funnel
    .filter((s) => !s.stage.startsWith("closed"))
    .reduce((sum, s) => sum + s.monthly_headroom, 0);

  return (
    <>
      <PageHeader
        title="Sales pipeline"
        description="How outreach is actually performing: stage distribution, outcome mix, and per-rep results against the accounts they work."
      />

      <div className="grid grid-4">
        <Kpi label="Accounts touched" value={formatNumber(t.accounts_touched)} meta={`${formatNumber(t.activities)} logged activities`} />
        <Kpi label="Closed won" value={formatNumber(t.wins)} meta={`${formatPercent(winRate, 1)} of contacted accounts`} />
        <Kpi label="Open pipeline value" value={formatIDR(openPipeline)} meta="Monthly headroom in active stages" accent />
        <Kpi label="Avg deal value" value={formatIDR(t.avg_deal_value)} meta="Estimated at time of logging" />
      </div>

      <div className="grid grid-2">
        {/* A snapshot of where accounts currently sit — NOT a sequential funnel.
            Counts are not monotonic (more accounts sit in Qualified than in
            Prospecting), so rendering stage-to-stage "conversion" would be
            meaningless. A distribution is the honest chart here. */}
        <Card title="Stage distribution" subtitle="Accounts by their most recent deal stage">
          <BarList
            items={data.stage_funnel.map((s) => ({
              label: titleCase(s.stage),
              value: s.sellers,
              meta: formatIDR(s.monthly_headroom),
            }))}
            valueFormat={(v) => `${formatNumber(v)} accounts`}
            color={(item) =>
              item.label === "Closed Won" ? "var(--success)"
              : item.label === "Closed Lost" ? "var(--danger)"
              : "var(--accent)"
            }
          />
        </Card>

        <Card title="Outcome mix" subtitle="Every logged activity by result">
          <BarList
            items={data.outcomes.map((o) => ({
              label: titleCase(o.outcome),
              value: o.activities,
            }))}
            valueFormat={(v) => formatNumber(v)}
            color={(item) =>
              OUTCOME_COLOR[item.label.toLowerCase().replace(/ /g, "_")] ?? "var(--accent)"
            }
          />
        </Card>
      </div>

      <Card title="Activity over time" subtitle="Monthly outreach volume and wins">
        <LineTrend
          data={data.activity_trend}
          xKey="month"
          height={240}
          label="Monthly outreach activities, accounts touched and wins"
          series={[
            { key: "activities", name: "Activities", color: "var(--series-1)" },
            { key: "accounts_touched", name: "Accounts touched", color: "var(--series-2)" },
            { key: "wins", name: "Wins", color: "var(--series-6)" },
          ]}
          xFormatter={formatMonth}
          valueFormatter={(v) => formatNumber(v)}
        />
      </Card>

      <Card title="Rep performance" subtitle="Activity volume against accounts worked and closed" flush>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Rep</th>
                <th className="num">Activities</th>
                <th className="num">Accounts</th>
                <th className="num">Touches / account</th>
                <th className="num">Wins</th>
                <th className="num">Win rate</th>
                <th className="num">Pipeline value</th>
              </tr>
            </thead>
            <tbody>
              {data.reps.map((rep) => (
                <tr key={rep.sales_rep}>
                  <td className="cell-primary">{rep.sales_rep}</td>
                  <td className="num cell-muted">{formatNumber(rep.activities)}</td>
                  <td className="num cell-muted">{formatNumber(rep.accounts)}</td>
                  <td className="num cell-muted">
                    {(rep.activities / Math.max(rep.accounts, 1)).toFixed(2)}
                  </td>
                  <td className="num">{formatNumber(rep.wins)}</td>
                  <td className="num strong">{formatPercent(rep.win_rate_pct, 1)}</td>
                  <td className="num cell-muted">{formatIDR(rep.pipeline_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-2">
        <Card title="Activity type effectiveness" subtitle="Volume by channel">
          <Bars
            data={data.activity_types}
            xKey="activity_type"
            horizontal
            height={240}
            label="Number of logged activities by outreach type"
            series={[{ key: "activities", name: "Activities" }]}
            colorByIndex
            xFormatter={titleCase}
            valueFormatter={(v) => formatNumber(v)}
          />
        </Card>

        <Card
          title="Modelled win rate by segment"
          subtitle="Historical conversion, shrunk toward the base rate for small segments"
          flush
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Seller type</th>
                  <th>Account tier</th>
                  <th className="num">Contacted</th>
                  <th className="num">Win rate</th>
                </tr>
              </thead>
              <tbody>
                {data.win_rate_by_segment.slice(0, 10).map((row, i) => (
                  <tr key={`${row.seller_type}-${row.account_tier}`}>
                    <td>
                      <span className="row gap-2">
                        <span className="legend-swatch" style={{ background: SERIES[i % SERIES.length] }} />
                        {titleCase(row.seller_type)}
                      </span>
                    </td>
                    <td className="cell-muted">{titleCase(row.account_tier)}</td>
                    <td className="num cell-muted">{formatNumber(row.contacted)}</td>
                    <td className="num strong">{formatPercent(row.modeled_win_rate, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
