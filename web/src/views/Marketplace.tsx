import { api, useAsync } from "../api/client";
import { AreaTrend, Bars, Donut } from "../components/charts";
import { BarList, Card, ErrorState, Funnel, Kpi, LoadingCard, PageHeader } from "../components/ui";
import { formatCompact, formatIDR, formatNumber, formatPercent, SERIES } from "../lib/format";

export default function Marketplace() {
  const { data, loading, error, reload } = useAsync(() => api.marketplace(), []);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <LoadingCard height={520} />;

  const f = data.funnel;
  const viewRate = f.impressions ? (f.views / f.impressions) * 100 : 0;
  const contactRate = f.views ? ((f.chats + f.phone_reveals) / f.views) * 100 : 0;
  const featured = data.featured_lift.find((s) => s.segment === "Featured");
  const standard = data.featured_lift.find((s) => s.segment === "Standard");
  const lift = featured && standard && standard.views_per_listing > 0
    ? featured.views_per_listing / standard.views_per_listing
    : null;

  return (
    <>
      <PageHeader
        title="Marketplace health"
        description="The demand side of the business: what sellers list, how buyers engage with it, and which categories generate the attention that advertising can amplify."
      />

      <div className="kpi-strip">
        <Kpi label="Total impressions" value={formatCompact(f.impressions)} meta="Search and browse surfaces" />
        <Kpi label="Listing views" value={formatCompact(f.views)} meta={`${formatPercent(viewRate)} of impressions`} />
        <Kpi label="Buyer contacts" value={formatCompact(f.chats + f.phone_reveals)} meta={`${formatPercent(contactRate, 2)} of views`} />
        <Kpi
          label="Featured lift"
          value={lift ? `${lift.toFixed(1)}x` : "—"}
          meta="Views per featured vs. standard listing"
          accent
        />
      </div>

      <Card title="Demand trend" subtitle="Daily impressions, views and buyer contacts">
        <AreaTrend
          data={data.trend}
          xKey="date"
          height={280}
          label="Daily impressions, listing views and buyer contacts across the marketplace"
          series={[
            { key: "impressions", name: "Impressions", color: "var(--series-2)" },
            { key: "views", name: "Views", color: "var(--series-1)" },
            { key: "leads", name: "Buyer contacts", color: "var(--series-6)" },
          ]}
          xFormatter={(v) => new Date(v).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}
          valueFormatter={(v) => formatNumber(v)}
        />
      </Card>

      <div className="grid grid-2">
        {/* Genuinely sequential steps only. Chats and phone reveals are two
            parallel outcomes of the same click, so listing them as consecutive
            funnel stages would imply a conversion between them that doesn't
            exist; they're summed into one "buyer contacts" step instead. */}
        <Card title="Engagement funnel" subtitle="Impression to buyer contact, all listings">
          <Funnel
            steps={[
              { name: "Impressions", value: f.impressions },
              { name: "Views", value: f.views },
              { name: "Contact clicks", value: f.clicks },
              { name: "Buyer contacts", value: f.chats + f.phone_reveals },
            ]}
          />
          <div className="row gap-4 small faint" style={{ marginTop: "var(--space-4)" }}>
            <span>{formatNumber(f.chats)} chats started</span>
            <span>{formatNumber(f.phone_reveals)} phone reveals</span>
          </div>
        </Card>

        <Card
          title="Featured vs. standard listings"
          subtitle="The performance gap that makes promotion sellable"
        >
          <Bars
            data={data.featured_lift}
            xKey="segment"
            height={200}
            label="Views and buyer contacts per listing, featured against standard"
            series={[
              { key: "views_per_listing", name: "Views per listing", color: "var(--series-1)" },
              { key: "leads_per_listing", name: "Contacts per listing", color: "var(--series-6)" },
            ]}
            valueFormatter={(v) => formatNumber(v, 1)}
          />
          <p className="small muted" style={{ marginTop: "var(--space-4)", lineHeight: 1.6 }}>
            Featured listings earn {lift ? `${lift.toFixed(1)}x` : "more"} the views and{" "}
            {featured && standard && standard.leads_per_listing > 0
              ? `${(featured.leads_per_listing / standard.leads_per_listing).toFixed(1)}x`
              : "more"}{" "}
            the buyer contacts of standard ones. This is the evidence base for every promotion pitch.
          </p>
        </Card>
      </div>

      <div className="grid grid-2">
        <Card title="Category performance" subtitle="Views and buyer contacts by category">
          <BarList
            items={data.categories.map((c) => ({
              label: c.category,
              value: c.views,
              meta: `${formatNumber(c.listings)} listings`,
            }))}
            valueFormat={formatCompact}
          />
        </Card>

        <Card title="Geographic distribution" subtitle="Views by province">
          <Bars
            data={data.provinces.slice(0, 9)}
            xKey="province"
            horizontal
            height={300}
            label="Listing views by province, highest first"
            series={[{ key: "views", name: "Views", color: "var(--series-2)" }]}
            valueFormatter={(v) => formatNumber(v)}
          />
        </Card>
      </div>

      <div className="grid grid-1-2">
        <Card title="Listing status mix">
          <Donut
            data={data.status_mix}
            nameKey="status"
            valueKey="listings"
            height={200}
            label="Listings split by status"
            centerValue={formatCompact(data.status_mix.reduce((a, s) => a + s.listings, 0))}
            centerLabel="listings"
            valueFormatter={(v) => formatNumber(v)}
          />
          <div className="legend" style={{ marginTop: "var(--space-4)", justifyContent: "center" }}>
            {data.status_mix.map((s, i) => (
              <span className="legend-item" key={s.status}>
                <span className="legend-swatch" style={{ background: SERIES[i % SERIES.length] }} />
                {s.status} ({formatNumber(s.listings)})
              </span>
            ))}
          </div>
        </Card>

        <Card title="Category detail" flush>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Category</th>
                  <th className="num">Sellers</th>
                  <th className="num">Listings</th>
                  <th className="num">Views</th>
                  <th className="num">Contacts</th>
                  <th className="num">Contact rate</th>
                  <th className="num">Avg price</th>
                </tr>
              </thead>
              <tbody>
                {data.categories.map((c) => (
                  <tr key={c.category}>
                    <td className="cell-primary">{c.category}</td>
                    <td className="num cell-muted">{formatNumber(c.sellers)}</td>
                    <td className="num cell-muted">{formatNumber(c.listings)}</td>
                    <td className="num">{formatCompact(c.views)}</td>
                    <td className="num cell-muted">{formatCompact(c.leads)}</td>
                    <td className="num cell-muted">
                      {formatPercent(c.views ? (c.leads / c.views) * 100 : 0, 2)}
                    </td>
                    <td className="num cell-muted">{formatIDR(c.avg_price)}</td>
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
