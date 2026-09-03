import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, useAsync } from "../api/client";
import { AreaTrend } from "../components/charts";
import { IconCheck, IconSparkle, IconX } from "../components/icons";
import {
  Badge, Card, Empty, ErrorState, LoadingCard, TierBadge,
} from "../components/ui";
import {
  daysAgo, formatCompact, formatDate, formatIDR, formatNumber, formatPercent, titleCase,
} from "../lib/format";
import { useModalFocus } from "../lib/modal";
import type { SellerDetail } from "../api/types";

const TABS = ["Opportunity", "Traction", "Advertising", "Activity"] as const;
type Tab = (typeof TABS)[number];

const PILLARS = [
  {
    key: "marketplace_score" as const,
    name: "Marketplace",
    color: "var(--accent)",
    desc: "Organic demand, ranked against sellers in the same category",
  },
  {
    key: "advertising_gap_score" as const,
    name: "Advertising gap",
    color: "var(--info)",
    desc: "How under-monetised they are versus comparable advertisers",
  },
  {
    key: "seller_score" as const,
    name: "Seller readiness",
    color: "var(--success)",
    desc: "Verification, rating, responsiveness and tenure",
  },
  {
    key: "sales_gap_score" as const,
    name: "Coverage gap",
    color: "var(--warning)",
    desc: "How overdue this account is for outreach",
  },
];

const OUTCOMES = ["interested", "not_interested", "converted", "no_response", "follow_up_scheduled"];
const ACTIVITY_TYPES = ["cold_call", "email", "meeting", "demo", "proposal_sent", "follow_up", "renewal_call"];
const DEAL_STAGES = ["prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"];

export default function SellerDrawer({
  sellerId, onClose, onChanged,
}: {
  sellerId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<Tab>("Opportunity");
  const { data, loading, error, reload } = useAsync(() => api.seller(sellerId), [sellerId]);
  const drawerRef = useModalFocus<HTMLElement>(true, onClose);
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  // Focus lands on the close button rather than the panel, so the first Tab
  // goes forward into the content instead of out of the dialog.
  useEffect(() => {
    if (!loading && data) closeRef.current?.focus();
  }, [loading, data]);

  // Arrow keys move between tabs, which is what the tab pattern promises.
  const onTabKey = useCallback((e: React.KeyboardEvent, index: number) => {
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = TABS[(index + delta + TABS.length) % TABS.length];
    setTab(next);
    document.getElementById(`tab-${next}`)?.focus();
  }, []);

  const s = data?.seller;

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside
        className="drawer"
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        {error ? (
          <div style={{ padding: "var(--space-6)" }}>
            <h2 id={titleId} className="sr-only">Seller detail</h2>
            <ErrorState message={error} onRetry={reload} />
            <button className="btn btn-sm" style={{ marginTop: 12 }} onClick={onClose}>
              Close
            </button>
          </div>
        ) : loading || !data || !s ? (
          <div style={{ padding: "var(--space-6)" }} className="stack gap-4">
            <h2 id={titleId} className="sr-only">Loading seller detail</h2>
            <LoadingCard height={96} label="Loading seller detail" />
            <LoadingCard height={220} label="Loading score breakdown" />
          </div>
        ) : (
          <>
            <header className="drawer-header">
              <div style={{ minWidth: 0 }}>
                <div className="row gap-2 wrap" style={{ marginBottom: 4 }}>
                  <TierBadge tier={s.priority_tier} />
                  <Badge variant="neutral">{s.account_tier}</Badge>
                  {s.is_verified ? <Badge variant="success">Verified</Badge> : null}
                  {!s.has_ads && <Badge variant="info">Never advertised</Badge>}
                  {s.touch_count === 0 && <Badge variant="warning">Never contacted</Badge>}
                </div>
                <h2
                  id={titleId}
                  style={{ fontSize: "var(--text-lg)", fontWeight: 680, letterSpacing: "-0.02em" }}
                >
                  {s.seller_name}
                </h2>
                <div className="small faint" style={{ marginTop: 2 }}>
                  {s.seller_id} · {titleCase(s.seller_type)} · {s.primary_category} · {s.city}, {s.province}
                </div>
              </div>
              <button
                ref={closeRef}
                className="drawer-close"
                onClick={onClose}
                aria-label={`Close ${s.seller_name} detail`}
              >
                <IconX size={18} />
              </button>
            </header>

            {/* Real ARIA tabs: only the selected tab is in the tab order, and
                arrow keys move between them (WAI-ARIA tabs pattern). */}
            <div className="tabs" role="tablist" aria-label="Seller detail sections">
              {TABS.map((t, i) => (
                <button
                  key={t}
                  id={`tab-${t}`}
                  role="tab"
                  type="button"
                  aria-selected={tab === t}
                  aria-controls={`panel-${t}`}
                  tabIndex={tab === t ? 0 : -1}
                  className={`tab ${tab === t ? "active" : ""}`}
                  onClick={() => setTab(t)}
                  onKeyDown={(e) => onTabKey(e, i)}
                >
                  {t}
                  {t === "Activity" && s.touch_count > 0 && ` (${s.touch_count})`}
                  {t === "Advertising" && data.campaigns.length > 0 && ` (${data.campaigns.length})`}
                </button>
              ))}
            </div>

            <div
              className="drawer-body"
              role="tabpanel"
              id={`panel-${tab}`}
              aria-labelledby={`tab-${tab}`}
              tabIndex={0}
            >
              {tab === "Opportunity" && <OpportunityTab data={data} />}
              {tab === "Traction" && <TractionTab data={data} />}
              {tab === "Advertising" && <AdvertisingTab data={data} />}
              {tab === "Activity" && (
                <ActivityTab
                  data={data}
                  onLogged={() => {
                    reload();
                    onChanged();
                  }}
                />
              )}
            </div>
          </>
        )}
      </aside>
    </>
  );
}

/* ------------------------------------------------------------ Opportunity -- */
function OpportunityTab({ data }: { data: SellerDetail }) {
  const s = data.seller;
  return (
    <>
      <div className="grid grid-3">
        <div className="kpi kpi-accent">
          <div className="kpi-label">Opportunity score</div>
          <div className="kpi-value">{s.opportunity_score.toFixed(1)}</div>
          <div className="kpi-meta">{s.priority_tier} priority · rank #{s.rank}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Monthly headroom</div>
          <div className="kpi-value sm">{formatIDR(s.monthly_spend_headroom)}</div>
          <div className="kpi-meta">{formatIDR(s.annual_revenue_potential)} annualised</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Risk-adjusted value</div>
          <div className="kpi-value sm">{formatIDR(s.expected_monthly_value)}</div>
          <div className="kpi-meta">{formatPercent(s.win_probability * 100, 1)} modelled win rate</div>
        </div>
      </div>

      <Card title="Why this score" subtitle="Four pillars, combined multiplicatively">
        <div className="grid grid-2" style={{ gap: "var(--space-5)" }}>
          {PILLARS.map((p) => (
            <div className="pillar" key={p.key}>
              <div className="pillar-head">
                <span className="pillar-name">{p.name}</span>
                <span className="pillar-score" style={{ color: p.color }}>
                  {Number(s[p.key]).toFixed(0)}
                </span>
              </div>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${Math.min(100, Number(s[p.key]))}%`, background: p.color }}
                />
              </div>
              <div className="pillar-desc">{p.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card
        title="Talking points"
        subtitle="Evidence a rep can open the call with"
        actions={<IconSparkle size={15} className="faint" />}
      >
        {s.talking_points.length ? (
          <ul className="talking-points">
            {s.talking_points.map((point, i) => <li key={i}><span>{point}</span></li>)}
          </ul>
        ) : (
          <Empty>No standout signals for this account.</Empty>
        )}
      </Card>

      <div className="grid grid-2">
        <Card title="Recommended play">
          <div className="stack gap-3">
            <div className="row gap-2">
              <span className="badge badge-accent">{s.recommended_product_label}</span>
              <span className="badge badge-neutral">{s.next_best_action}</span>
            </div>
            <p className="small muted" style={{ lineHeight: 1.6 }}>
              Sized for {formatNumber(s.active_listing_count)} active listings in {s.primary_category}.
              Target spend of {formatIDR(s.benchmark_monthly_spend)}/month matches what comparable
              sellers already invest.
            </p>
            <dl className="definition">
              <div>
                <dt>Current spend</dt>
                <dd>{formatIDR(s.observed_monthly_spend)}/mo</dd>
              </div>
              <div>
                <dt>Benchmark</dt>
                <dd>{formatIDR(s.benchmark_monthly_spend)}/mo</dd>
              </div>
            </dl>
          </div>
        </Card>

        <Card
          title="How the benchmark was derived"
          subtitle={`Basis: ${s.benchmark_basis} · ${s.benchmark_comparables} comparables`}
        >
          {data.comparables.length ? (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Comparable seller</th>
                    <th className="num">Views</th>
                    <th className="num">Spends /mo</th>
                  </tr>
                </thead>
                <tbody>
                  {data.comparables.slice(0, 5).map((c) => (
                    <tr key={c.seller_id}>
                      <td className="truncate" style={{ maxWidth: 190 }}>{c.seller_name}</td>
                      <td className="num cell-muted">{formatCompact(c.total_views)}</td>
                      <td className="num">{formatIDR(c.observed_monthly_spend)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>No direct comparables; fell back to a wider cohort.</Empty>
          )}
        </Card>
      </div>

      <Card title="Account profile">
        <dl className="definition">
          <div><dt>Rating</dt><dd>{s.rating_avg ? `${s.rating_avg.toFixed(2)} (${s.rating_count})` : "—"}</dd></div>
          <div><dt>Response rate</dt><dd>{formatPercent(s.response_rate_pct)}</dd></div>
          <div><dt>Response time</dt><dd>{s.response_time_hours}h</dd></div>
          <div><dt>Tenure</dt><dd>{s.tenure_years.toFixed(1)}y</dd></div>
          <div><dt>Listings</dt><dd>{formatNumber(s.listing_count)} ({formatNumber(s.active_listing_count)} active)</dd></div>
          <div><dt>Sold</dt><dd>{formatNumber(s.sold_listing_count)}</dd></div>
          <div><dt>Avg price</dt><dd>{formatIDR(s.avg_price_idr)}</dd></div>
          <div><dt>Last active</dt><dd>{daysAgo(s.days_since_active)}</dd></div>
        </dl>
      </Card>
    </>
  );
}

/* --------------------------------------------------------------- Traction -- */
function TractionTab({ data }: { data: SellerDetail }) {
  const s = data.seller;
  return (
    <>
      <div className="grid grid-4">
        <div className="kpi"><div className="kpi-label">Impressions</div><div className="kpi-value sm">{formatCompact(s.total_impressions)}</div></div>
        <div className="kpi"><div className="kpi-label">Views</div><div className="kpi-value sm">{formatCompact(s.total_views)}</div></div>
        <div className="kpi"><div className="kpi-label">Buyer chats</div><div className="kpi-value sm">{formatCompact(s.total_chats)}</div></div>
        <div className="kpi">
          <div className="kpi-label">View → contact</div>
          <div className="kpi-value sm">{formatPercent(s.lead_quality_ratio, 2)}</div>
        </div>
      </div>

      <Card title="Daily traction" subtitle="Organic performance across all their listings">
        {data.traction_trend.length ? (
          <AreaTrend
            data={data.traction_trend}
            xKey="date"
            height={220}
            label={`Daily views and buyer contacts for ${s.seller_name}`}
            series={[
              { key: "views", name: "Views", color: "var(--series-1)" },
              { key: "leads", name: "Buyer contacts", color: "var(--series-6)" },
            ]}
            xFormatter={(v) => new Date(v).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}
            valueFormatter={(v) => formatNumber(v)}
          />
        ) : (
          <Empty>No metrics recorded.</Empty>
        )}
      </Card>

      <Card title="Top listings" subtitle="Ranked by views" flush>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Listing</th>
                <th className="num">Price</th>
                <th>Status</th>
                <th className="num">Views</th>
                <th className="num">Contacts</th>
              </tr>
            </thead>
            <tbody>
              {data.listings.slice(0, 12).map((l) => (
                <tr key={l.listing_id}>
                  <td>
                    <span className="cell-primary" title={l.title}>{l.title}</span>
                    <span className="cell-secondary">
                      {l.subcategory} · {l.condition}
                      {l.is_featured ? " · featured" : ""}
                    </span>
                  </td>
                  <td className="num cell-muted">{formatIDR(l.price_idr)}</td>
                  <td><Badge variant={l.status === "active" ? "success" : "neutral"}>{l.status}</Badge></td>
                  <td className="num">{formatNumber(l.views)}</td>
                  <td className="num cell-muted">{formatNumber(l.leads)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data.listings.length && <Empty>No listings.</Empty>}
        </div>
      </Card>
    </>
  );
}

/* ------------------------------------------------------------ Advertising -- */
function AdvertisingTab({ data }: { data: SellerDetail }) {
  const s = data.seller;
  if (!data.campaigns.length) {
    return (
      <Card title="No advertising history">
        <p className="muted small" style={{ lineHeight: 1.6 }}>
          This seller has never run a campaign. Comparable {s.primary_category} sellers at the same
          traction level spend about <strong>{formatIDR(s.benchmark_monthly_spend)}/month</strong>,
          which is the basis for the {formatIDR(s.monthly_spend_headroom)} monthly headroom on this account.
        </p>
      </Card>
    );
  }
  return (
    <>
      <div className="grid grid-4">
        <div className="kpi"><div className="kpi-label">Total spend</div><div className="kpi-value sm">{formatIDR(s.total_ad_spend)}</div></div>
        <div className="kpi"><div className="kpi-label">Campaigns</div><div className="kpi-value sm">{formatNumber(s.campaign_count)}</div></div>
        <div className="kpi"><div className="kpi-label">Conversions</div><div className="kpi-value sm">{formatNumber(s.total_conversions)}</div></div>
        <div className="kpi"><div className="kpi-label">Monthly run-rate</div><div className="kpi-value sm">{formatIDR(s.observed_monthly_spend)}</div></div>
      </div>

      <Card title="Campaign history" flush>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Period</th>
                <th className="num">Spend</th>
                <th className="num">Clicks</th>
                <th className="num">Conv.</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.campaigns.map((c) => (
                <tr key={c.campaign_id}>
                  <td>
                    <span className="cell-primary">{titleCase(c.campaign_type)}</span>
                    <span className="cell-secondary">{c.campaign_id}</span>
                  </td>
                  <td className="cell-muted small">
                    {formatDate(c.start_date)} – {formatDate(c.end_date)}
                  </td>
                  <td className="num">{formatIDR(c.spend_idr)}</td>
                  <td className="num cell-muted">{formatNumber(c.clicks)}</td>
                  <td className="num cell-muted">{formatNumber(c.conversions)}</td>
                  <td>
                    <Badge variant={c.status === "active" ? "success" : "neutral"}>{c.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

/* --------------------------------------------------------------- Activity -- */
function ActivityTab({
  data, onLogged,
}: {
  data: SellerDetail;
  onLogged: () => void;
}) {
  const s = data.seller;
  const [form, setForm] = useState({
    sales_rep: s.last_sales_rep ?? "Dewi Anggraini",
    activity_type: "cold_call",
    outcome: "interested",
    deal_stage: "prospecting",
    next_follow_up_date: "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      await api.logActivity(s.seller_id, {
        ...form,
        next_follow_up_date: form.next_follow_up_date || null,
      });
      setSaved(true);
      onLogged();
      setTimeout(() => setSaved(false), 2600);
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Could not log activity");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Card title="Log an activity" subtitle="Recording a touch rescores this account immediately">
        <form className="stack gap-4" onSubmit={submit}>
          <div className="grid grid-3" style={{ gap: "var(--space-3)" }}>
            <label className="field">
              <span className="field-label">Rep</span>
              <input
                className="input"
                value={form.sales_rep}
                onChange={(e) => setForm({ ...form, sales_rep: e.target.value })}
                required
              />
            </label>
            <label className="field">
              <span className="field-label">Activity</span>
              <select
                className="select"
                value={form.activity_type}
                onChange={(e) => setForm({ ...form, activity_type: e.target.value })}
              >
                {ACTIVITY_TYPES.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Outcome</span>
              <select
                className="select"
                value={form.outcome}
                onChange={(e) => setForm({ ...form, outcome: e.target.value })}
              >
                {OUTCOMES.map((o) => <option key={o} value={o}>{titleCase(o)}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Deal stage</span>
              <select
                className="select"
                value={form.deal_stage}
                onChange={(e) => setForm({ ...form, deal_stage: e.target.value })}
              >
                {DEAL_STAGES.map((d) => <option key={d} value={d}>{titleCase(d)}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Next follow-up</span>
              <input
                className="input"
                type="date"
                value={form.next_follow_up_date}
                onChange={(e) => setForm({ ...form, next_follow_up_date: e.target.value })}
              />
            </label>
            <div className="field" style={{ justifyContent: "flex-end" }}>
              <button className="btn btn-primary" type="submit" disabled={saving}>
                {saving ? "Saving..." : saved ? <><IconCheck size={13} /> Logged</> : "Log activity"}
              </button>
            </div>
          </div>
          <p aria-live="polite" className="small" style={{ margin: 0, color: err ? "var(--danger)" : "var(--success)" }}>
            {err ?? (saved ? "Activity logged. This account has been rescored." : "")}
          </p>
        </form>
      </Card>

      <Card title="Activity history">
        {data.activities.length ? (
          <div className="timeline">
            {data.activities.map((a) => (
              <div className="timeline-item" key={a.activity_id}>
                <div className="timeline-dot">
                  <span
                    style={{
                      width: 7, height: 7, borderRadius: "50%",
                      background:
                        a.outcome === "converted" ? "var(--success)"
                        : a.outcome === "not_interested" ? "var(--danger)"
                        : a.outcome === "no_response" ? "var(--text-faint)"
                        : "var(--accent)",
                    }}
                  />
                </div>
                <div className="timeline-body">
                  <div className="timeline-title">
                    {titleCase(a.activity_type)}
                    <Badge
                      variant={
                        a.outcome === "converted" ? "success"
                        : a.outcome === "not_interested" ? "danger"
                        : "neutral"
                      }
                    >
                      {titleCase(a.outcome)}
                    </Badge>
                    <span className="badge badge-neutral">{titleCase(a.deal_stage)}</span>
                  </div>
                  <div className="timeline-meta">
                    {formatDate(a.activity_date)} · {a.sales_rep} · via {a.channel.replace(/_/g, " ")}
                    {a.next_follow_up_date && ` · follow-up ${formatDate(a.next_follow_up_date)}`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty>No outreach recorded for this account yet.</Empty>
        )}
      </Card>
    </>
  );
}
