/** Landing page — "The money is already here" (tasteskill v2, sentence-as-layout).
 *  The headline is the layout: a poster-scale sentence with the product's own
 *  evidence inline where a word would sit. Every figure is read from the live
 *  API, and every picture is a real crop of the dashboard, marked data-ui. */

import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, useAsync } from "../api/client";
import { BrandMark, useTheme } from "../components/AppShell";
import { Bars, LineTrend } from "../components/charts";
import { IconArrowUpRight, IconMoon, IconSun } from "../components/icons";
import { LoadingCard, ScoreMeter, TierBadge } from "../components/ui";
import { formatIDR, formatNumber, formatPercent } from "../lib/format";
import "../styles/landing.css";

/** Parts arrive as they scroll into view; the headline never waits. Re-runs when
 *  data lands so figures rendered after the first paint are observed too. */
function useReveal(ref: { current: HTMLElement | null }, deps: unknown[]) {
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const els = Array.from(root.querySelectorAll<HTMLElement>("[data-reveal]:not(.is-in)"));
    if (!("IntersectionObserver" in window)) {
      els.forEach((el) => el.classList.add("is-in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("is-in");
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.1, rootMargin: "0px 0px -8% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/** Split a number into the whole and decimal parts of a decimal-aligned ledger. */
function ledger(value: number, decimals = 0) {
  const [whole, dec] = value.toFixed(decimals).split(".");
  return { whole, dec: dec ? `.${dec}` : "" };
}

export default function Landing() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [theme, toggleTheme] = useTheme();
  const [query, setQuery] = useState("Vehicles");

  const overview = useAsync(() => api.overview(), []);
  const coverage = useAsync(() => api.coverage(), []);
  const olap = useAsync(() => api.olap(), []);
  const leadId = overview.data?.top_leads?.[0]?.seller_id;
  const seller = useAsync(
    () => (leadId ? api.seller(leadId) : Promise.resolve(null)),
    [leadId],
  );

  useReveal(rootRef, [overview.data, coverage.data, olap.data, seller.data]);

  const k = overview.data?.kpis;
  const tierMix = overview.data?.tier_mix ?? [];
  const totalHeadroom = tierMix.reduce((s, t) => s + t.monthly_headroom, 0) || 1;
  const tierShares = tierMix.map((t) => ({
    tier: t.tier,
    value: (t.monthly_headroom / totalHeadroom) * 100,
  }));

  const figures = k
    ? [
        { ...ledger(k.monthly_headroom / 1e6), cap: "Rp million · monthly headroom" },
        { ...ledger(k.annual_headroom / 1e9, 1), cap: "Rp billion · annual headroom" },
        { ...ledger(k.current_monthly_revenue / 1e6), cap: "Rp million · revenue today" },
        { ...ledger(k.uncovered_priority_headroom / 1e6), cap: "Rp million · priority uncovered" },
        { ...ledger(k.advertiser_penetration), cap: "percent · sellers advertising" },
      ]
    : [];

  const eq = coverage.data?.effort_quality;
  const effortSegs = eq
    ? [
        { label: "Well targeted", count: eq.well_targeted, color: "var(--accent)", clause: "Priority accounts, contacted" },
        { label: "Low value, touched", count: eq.low_value_touched, color: "var(--warning)", clause: "Effort where headroom is thin" },
        { label: "Priority, missed", count: eq.missed_priority, color: "var(--tier-hot)", clause: "High headroom, never called" },
        { label: "Correctly skipped", count: eq.correctly_skipped, color: "var(--border-strong)", clause: "Low priority, left alone" },
      ]
    : [];

  // The one live thing: type a category or province, read its real coverage.
  const match = useMemo(() => {
    const c = coverage.data;
    const q = query.trim().toLowerCase();
    if (!c || !q) return null;
    const cat = c.by_category.find((x) => x.category.toLowerCase() === q);
    if (cat) return { label: cat.category, headroom: cat.uncovered_headroom, priority: cat.uncovered_priority, pct: cat.coverage_pct };
    const prov = c.by_province.find((x) => x.province.toLowerCase() === q);
    if (prov) return { label: prov.province, headroom: prov.uncovered_headroom, priority: prov.uncovered_priority, pct: prov.coverage_pct };
    return null;
  }, [coverage.data, query]);

  const decayData = (olap.data?.listing_decay_overall ?? []).map((d) => ({
    week: `W${d.week_since_post}`,
    retention: d.retention_index,
  }));
  const convData = (olap.data?.conversion_by_traction ?? []).map((d) => ({
    quintile: `Q${d.quintile}`,
    rate: d.conversion_rate_pct,
  }));
  const eng = olap.data?.engine;
  const topLeads = overview.data?.top_leads ?? [];
  const s = seller.data?.seller;

  const pillars = s
    ? [
        { name: "Marketplace traction", score: s.marketplace_score, measures: "Views, chats and listing depth against peers", evidence: `${formatNumber(s.total_views)} views · ${formatNumber(s.total_chats)} chats` },
        { name: "Advertising gap", score: s.advertising_gap_score, measures: "Headroom between observed and benchmark spend", evidence: `${formatIDR(s.observed_monthly_spend)} observed · ${formatIDR(s.benchmark_monthly_spend)} benchmark` },
        { name: "Seller quality", score: s.seller_score, measures: "Rating, response rate and tenure", evidence: `${s.rating_avg?.toFixed(2) ?? "—"} rating · ${formatPercent(s.response_rate_pct)} response` },
        { name: "Sales gap", score: s.sales_gap_score, measures: "Untouched priority against the ranked queue", evidence: `${s.touch_count} touches · rank #${s.rank}` },
      ]
    : [];

  const features: { title: string; body: string; fragTitle: string; frag: ReactNode }[] = [
    {
      title: "Demand decays fast",
      body: "A listing loses most of its attention in the first week. Outreach is timed to the window where a seller still cares.",
      fragTitle: "Retention index · week since post",
      frag: olap.data ? (
        <LineTrend
          data={decayData}
          xKey="week"
          series={[{ key: "retention", name: "Retention", color: "var(--accent)" }]}
          height={190}
          label="Listing demand retention falls from 100 at week 0 to about 15 by week 2"
          valueFormatter={(v) => v.toFixed(0)}
        />
      ) : (
        <LoadingCard height={190} />
      ),
    },
    {
      title: "Traction predicts the win",
      body: "Sellers in the top traction quintile convert about four times the bottom. The score weights real demand, not guesswork.",
      fragTitle: "Conversion rate · traction quintile",
      frag: olap.data ? (
        <Bars
          data={convData}
          xKey="quintile"
          series={[{ key: "rate", name: "Conversion", color: "var(--accent)" }]}
          height={190}
          label="Conversion rate rises from 0.79 percent in the bottom traction quintile to 3.16 percent in the fourth"
          valueFormatter={(v) => `${v.toFixed(2)}%`}
        />
      ) : (
        <LoadingCard height={190} />
      ),
    },
    {
      title: "Columnar, not a spreadsheet",
      body: "The full metric history is aggregated in DuckDB at build time, so the dashboard reads results instead of recomputing them.",
      fragTitle: "Build-time OLAP engine",
      frag: (
        <dl className="engine-rows">
          <div className="engine-row"><dt>Engine</dt><dd>{eng?.name ?? "—"}</dd></div>
          <div className="engine-row"><dt>Version</dt><dd>{eng?.version ?? "—"}</dd></div>
          <div className="engine-row"><dt>Fact rows</dt><dd>{formatNumber(eng?.fact_rows)}</dd></div>
          <div className="engine-row"><dt>Build time</dt><dd>{eng?.build_ms != null ? `${(eng.build_ms / 1000).toFixed(1)}s` : "—"}</dd></div>
        </dl>
      ),
    },
    {
      title: "A queue, ranked",
      body: "Every seller is ranked by headroom and win probability, with the evidence attached. Reps start at the top of the list.",
      fragTitle: "Top of the queue · opportunity score",
      frag: (
        <table className="data">
          <thead>
            <tr><th scope="col">Seller</th><th scope="col" className="num">Score</th><th scope="col">Tier</th></tr>
          </thead>
          <tbody>
            {topLeads.slice(0, 3).map((l) => (
              <tr key={l.seller_id}>
                <td>{l.seller_name}</td>
                <td className="num">{l.opportunity_score.toFixed(1)}</td>
                <td><TierBadge tier={l.priority_tier} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      ),
    },
  ];

  return (
    <div className="landing" ref={rootRef}>
      <header className="land-nav">
        <Link className="land-brand" to="/">
          <BrandMark />
          <span className="land-brand-text">
            <span className="land-brand-name">Ads Intelligence</span>
            <span className="land-brand-sub">OLX Marketplace</span>
          </span>
        </Link>
        <nav className="land-links" aria-label="Sections">
          <a href="#proof">The benchmark</a>
          <a href="#features">Under the hood</a>
          <button
            className="btn btn-ghost btn-icon"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? <IconSun size={15} /> : <IconMoon size={15} />}
          </button>
          <Link className="btn btn-sm land-cta-link" to="/app">Open dashboard</Link>
        </nav>
      </header>

      <main>
        {/* Hero: the sentence, with the product's own evidence inline. */}
        <section className="land-hero">
          <div className="hero-main">
            <h1 className="land-sentence">
              <span className="line">The money is</span>
              <span className="line">
                already{" "}
                <span className="hero-slot" data-ui aria-hidden="true">
                  <span className="gap-list">
                    {tierShares.map((t) => (
                      <span className="gap-row" key={t.tier}>
                        <span className="gap-bars">
                          <span className="gap-line">
                            <span className="gap-bar-track">
                              <span className="gap-bar-fill value" style={{ width: `${t.value}%` }} />
                            </span>
                          </span>
                        </span>
                      </span>
                    ))}
                  </span>
                </span>
                <span className="sr-only">here</span>.
              </span>
            </h1>
            <p className="land-support" data-reveal>
              Revenue intelligence for the OLX marketplace. It ranks every seller by the ad
              revenue left on the table, and shows the evidence behind each number.
            </p>
            <div className="land-hero-actions" data-reveal>
              <Link className="cta-btn" to="/app">
                Open the dashboard <IconArrowUpRight size={18} />
              </Link>
              <span className="land-hero-note">
                Synthetic dataset · {formatNumber(k?.total_sellers)} sellers · as of {overview.data?.as_of ?? "—"}
              </span>
            </div>
          </div>
          {k && (
            <div className="hero-aside" data-reveal>
              <span className="hero-aside-num">
                {figures[0].whole}
                <span className="fig-dec">{figures[0].dec}</span>
              </span>
              <span className="hero-aside-cap">Rp million · left on the table every month</span>
            </div>
          )}
        </section>

        {/* Stats: a ledger aligned on the decimal. */}
        <section className="land-section">
          <div className="land-grid">
            <div className="stats-head" data-reveal>
              <h2 className="land-h2">The size of it</h2>
              <p className="land-lede">
                Across {formatNumber(k?.total_sellers)} sellers, the gap between what advertisers
                spend today and what their traction supports.
              </p>
            </div>
            <div className="stats-figures" data-reveal>
              {figures.map((f) => (
                <Fragment key={f.cap}>
                  <span className="fig-num fig-whole">{f.whole}</span>
                  <span className="fig-num fig-dec">{f.dec}</span>
                  <span className="fig-cap">{f.cap}</span>
                </Fragment>
              ))}
            </div>
          </div>
        </section>

        {/* Effort: the whole base as one bar, sized by true counts. */}
        <section className="land-section">
          <h2 className="effort-head" data-reveal>Busy in the wrong places.</h2>
          <p className="effort-lede" data-reveal>
            Of {formatNumber(k?.total_sellers)} sellers, the team has touched {formatNumber(k?.contacted_sellers)}.
            But {formatNumber(eq?.missed_priority)} priority accounts, the ones with the most headroom, have
            never been called, while {formatNumber(eq?.low_value_touched)} low-value accounts have.
          </p>
          <div className="effort-bar" data-ui data-reveal>
            {effortSegs.map((seg) => (
              <span key={seg.label} className="effort-seg" style={{ flexGrow: seg.count, background: seg.color }} />
            ))}
          </div>
          <ul className="effort-legend">
            {effortSegs.map((seg) => (
              <li className="effort-item" key={seg.label} data-reveal>
                <span className="effort-key">
                  <span className="effort-swatch" style={{ background: seg.color }} />
                  <span className="effort-label">{seg.label}</span>
                </span>
                <span className="effort-count">{formatNumber(seg.count)}</span>
                <span className="effort-clause">{seg.clause}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* Proof: a stepped heading over a four-pillar evidence table. */}
        <section className="land-section" id="proof">
          <div className="land-grid">
            <h2 className="land-h2 proof-head" data-reveal>
              The number is a benchmark,
              <span className="indent">not a guess.</span>
            </h2>
            <p className="proof-lede" data-reveal>
              Each seller is scored on four pillars, measured against peers in the same category
              and traction band. This is the top of the queue, with its own numbers attached.
            </p>
            <div className="proof-frag" data-ui data-reveal>
              <p className="proof-caption">
                Every score is built from this seller's own numbers: <strong>{s?.seller_name ?? "—"}</strong>,
                {" "}{s?.primary_category ?? "—"}, ranked #{s?.rank ?? "—"} of {formatNumber(k?.total_sellers)}.
              </p>
              <div className="proof-table">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Pillar</th>
                      <th scope="col">Score</th>
                      <th scope="col">What it measures</th>
                      <th scope="col">This seller</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pillars.map((p) => (
                      <tr key={p.name}>
                        <th scope="row">{p.name}</th>
                        <td><ScoreMeter score={p.score} /></td>
                        <td>{p.measures}</td>
                        <td>{p.evidence}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="proof-note" data-reveal>
              Benchmark basis: {s?.benchmark_basis ?? "—"} · {formatNumber(s?.benchmark_comparables)} comparable
              sellers · observed spend {formatIDR(s?.observed_monthly_spend)}.
            </p>
          </div>
        </section>

        {/* Showcase: the headline you can type. */}
        <section className="land-section">
          <h2 className="show-head" data-reveal>Point it at your patch</h2>
          <div className="show-line" data-reveal>
            <input
              className="show-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Type a category or province"
              aria-label="Category or province"
              spellCheck={false}
              autoComplete="off"
            />
          </div>
          <div className="show-answer" data-ui data-reveal>
            {match ? (
              <div className="show-answer-grid">
                <div className="show-metric">
                  <span className="show-metric-value">{formatIDR(match.headroom)}</span>
                  <span className="show-metric-label">Uncovered monthly headroom</span>
                </div>
                <div className="show-metric">
                  <span className="show-metric-value">{formatNumber(match.priority)}</span>
                  <span className="show-metric-label">Priority sellers never called</span>
                </div>
                <div className="show-metric">
                  <span className="show-metric-value">{formatPercent(match.pct)}</span>
                  <span className="show-metric-label">Of sellers contacted</span>
                </div>
              </div>
            ) : (
              <p className="show-empty">
                {coverage.data
                  ? `No category or province matches “${query}”. Try Vehicles, Property or Jawa Barat.`
                  : "Loading coverage…"}
              </p>
            )}
          </div>
          <div className="show-examples" data-reveal>
            <span className="show-examples-label">Try</span>
            {["Vehicles", "Jawa Barat", "Property"].map((ex) => (
              <button key={ex} type="button" className="show-example" onClick={() => setQuery(ex)}>
                {ex}
              </button>
            ))}
          </div>
        </section>

        {/* Features: rows with the product in the margin. */}
        <section className="land-section" id="features">
          <div className="land-grid">
            <div className="feat-head" data-reveal>
              <h2 className="land-h2">Under the hood</h2>
              <p className="land-lede">
                Four models, one queue. Every number on this page comes from the same engine the
                dashboard runs on.
              </p>
            </div>
            <div className="feat-rows">
              {features.map((f) => (
                <div className="feat-row" key={f.title} data-reveal>
                  <div>
                    <h3 className="feat-title">{f.title}</h3>
                    <p className="feat-body">{f.body}</p>
                  </div>
                  <div className="feat-frag frag" data-ui>
                    <div className="frag-title">{f.fragTitle}</div>
                    {f.frag}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* The close: one inverted field, the idea again. */}
        <section className="land-cta">
          <h2 className="cta-head" data-reveal>Call the right sellers.</h2>
          <div className="cta-foot" data-reveal>
            <p className="cta-support">
              The queue is ranked, the evidence is attached, and the headroom is real. Open the
              dashboard and start at the top of the list.
            </p>
            <Link className="cta-btn" to="/app">
              Open the dashboard <IconArrowUpRight size={18} />
            </Link>
          </div>
        </section>
      </main>

      <footer className="land-footer">
        <div className="foot-cols" data-reveal>
          <div>
            <h3>Workspace</h3>
            <ul>
              <li><Link to="/app">Overview</Link></li>
              <li><Link to="/opportunities">Opportunities</Link></li>
              <li><Link to="/pipeline">Pipeline</Link></li>
              <li><Link to="/coverage">Coverage</Link></li>
            </ul>
          </div>
          <div>
            <h3>Analysis</h3>
            <ul>
              <li><Link to="/marketplace">Marketplace</Link></li>
              <li><Link to="/advertising">Advertising</Link></li>
              <li><Link to="/deep-dive">Deep Dive</Link></li>
            </ul>
          </div>
          <div>
            <h3>The model</h3>
            <ul>
              <li className="dim">Four-pillar opportunity score</li>
              <li className="dim">Category + traction benchmarks</li>
              <li className="dim">DuckDB columnar engine</li>
            </ul>
          </div>
          <div>
            <h3>Dataset</h3>
            <ul>
              <li className="dim">{formatNumber(k?.total_sellers)} synthetic sellers</li>
              <li className="dim">OLX Indonesia marketplace</li>
              <li className="dim">Data as of {overview.data?.as_of ?? "—"}</li>
            </ul>
          </div>
        </div>
        <div className="foot-word" data-reveal>
          <BrandMark /> Ads Intelligence
        </div>
        <div className="foot-meta">
          <span>OLX Marketplace · Revenue intelligence</span>
          <span>Synthetic dataset · v1.0</span>
        </div>
      </footer>
    </div>
  );
}