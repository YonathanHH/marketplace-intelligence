import { useCallback, useEffect, useMemo, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, useAsync } from "../api/client";
import { IconChevronLeft, IconChevronRight, IconDownload, IconSearch, IconX } from "../components/icons";
import { Card, Empty, ErrorState, LoadingCard, ScoreMeter, Spinner } from "../components/ui";
import { daysAgo, formatCompact, formatIDR, formatNumber } from "../lib/format";
import SellerDrawer from "./SellerDrawer";

const TIERS = ["Hot", "Warm", "Cool", "Low"];

const COLUMNS: { key: string; label: string; numeric?: boolean; sortable?: boolean }[] = [
  { key: "seller_name", label: "Seller", sortable: true },
  { key: "primary_category", label: "Category" },
  { key: "opportunity_score", label: "Score", numeric: true, sortable: true },
  { key: "monthly_spend_headroom", label: "Headroom /mo", numeric: true, sortable: true },
  { key: "expected_monthly_value", label: "Risk-adj.", numeric: true, sortable: true },
  { key: "total_views", label: "Views 30d", numeric: true, sortable: true },
  { key: "recommended_product", label: "Play" },
  { key: "next_best_action", label: "Next action" },
  { key: "days_since_last_contact", label: "Last touch", numeric: true, sortable: true },
];

export default function Opportunities() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { sellerId } = useParams();

  const query = useMemo(() => ({
    q: params.get("q") ?? "",
    tier: params.getAll("tier"),
    category: params.get("category") ?? "",
    province: params.get("province") ?? "",
    seller_type: params.get("seller_type") ?? "",
    advertiser_status: params.get("advertiser_status") ?? "any",
    contact_status: params.get("contact_status") ?? "any",
    sort: params.get("sort") ?? "opportunity_score",
    order: params.get("order") ?? "desc",
    page: Number(params.get("page") ?? 1),
    page_size: 25,
  }), [params]);

  const { data, loading, error, reload } = useAsync(() => api.leads(query), [JSON.stringify(query)]);
  const filters = useAsync(() => api.filters(), []);

  /** Merge a patch into the URL params; any change resets pagination. */
  const update = useCallback((patch: Record<string, string | string[] | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(patch)) {
      next.delete(key);
      if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
      else if (value) next.set(key, value);
    }
    if (!("page" in patch)) next.delete("page");
    setParams(next, { replace: true });
  }, [params, setParams]);

  // Typing shouldn't fire a request per keystroke; the timer is held in a ref
  // so re-renders don't lose or duplicate it.
  const searchTimer = useRef<number | undefined>(undefined);
  const debouncedSearch = useCallback((value: string) => {
    window.clearTimeout(searchTimer.current);
    searchTimer.current = window.setTimeout(() => update({ q: value || null }), 280);
  }, [update]);

  useEffect(() => () => window.clearTimeout(searchTimer.current), []);

  const toggleTier = (tier: string) => {
    const current = query.tier;
    update({ tier: current.includes(tier) ? current.filter((t) => t !== tier) : [...current, tier] });
  };

  // Carry the current filters through to the drawer route and back, so closing
  // the drawer returns to the same filtered queue. A bare trailing "?" (when no
  // filters are set) does not navigate reliably, so only append when non-empty.
  const withFilters = useCallback((path: string) => {
    const qs = params.toString();
    return qs ? `${path}?${qs}` : path;
  }, [params]);

  const setSort = (key: string) => {
    if (query.sort === key) {
      update({ sort: key, order: query.order === "desc" ? "asc" : "desc" });
    } else {
      update({ sort: key, order: "desc" });
    }
  };

  const activeFilters =
    query.tier.length +
    (query.category ? 1 : 0) +
    (query.province ? 1 : 0) +
    (query.seller_type ? 1 : 0) +
    (query.advertiser_status !== "any" ? 1 : 0) +
    (query.contact_status !== "any" ? 1 : 0) +
    (query.q ? 1 : 0);

  return (
    <>
      {/* ---------------------------------------------------------- Filters -- */}
      <Card>
        <div className="stack gap-4">
          <div className="row gap-3 wrap">
            <div className="search" style={{ flex: "1 1 260px", maxWidth: 340 }}>
              <IconSearch />
              <input
                className="input"
                placeholder="Search seller, ID or city..."
                defaultValue={query.q}
                onChange={(e) => debouncedSearch(e.target.value)}
              />
            </div>

            <div className="row gap-2">
              {TIERS.map((tier) => (
                <button
                  key={tier}
                  className={`chip ${query.tier.includes(tier) ? "active" : ""}`}
                  onClick={() => toggleTier(tier)}
                >
                  {tier}
                </button>
              ))}
            </div>

            <div className="row gap-2 ml-auto">
              {activeFilters > 0 && (
                <button className="btn btn-ghost btn-sm" onClick={() => setParams({}, { replace: true })}>
                  <IconX size={12} /> Clear {activeFilters}
                </button>
              )}
              <a className="btn btn-sm" href={api.exportUrl({ ...query, page_size: 200 })}>
                <IconDownload size={13} /> Export CSV
              </a>
            </div>
          </div>

          <div className="grid grid-5" style={{ gap: "var(--space-3)" }}>
            <label className="field">
              <span className="field-label">Category</span>
              <select
                className="select"
                value={query.category}
                onChange={(e) => update({ category: e.target.value || null })}
              >
                <option value="">All categories</option>
                {filters.data?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>

            <label className="field">
              <span className="field-label">Province</span>
              <select
                className="select"
                value={query.province}
                onChange={(e) => update({ province: e.target.value || null })}
              >
                <option value="">All provinces</option>
                {filters.data?.provinces.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>

            <label className="field">
              <span className="field-label">Seller type</span>
              <select
                className="select"
                value={query.seller_type}
                onChange={(e) => update({ seller_type: e.target.value || null })}
              >
                <option value="">All types</option>
                {filters.data?.seller_types.map((t) => (
                  <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field-label">Ad status</span>
              <select
                className="select"
                value={query.advertiser_status}
                onChange={(e) => update({ advertiser_status: e.target.value })}
              >
                <option value="any">Any</option>
                <option value="never">Never advertised</option>
                <option value="active">Existing advertiser</option>
              </select>
            </label>

            <label className="field">
              <span className="field-label">Sales contact</span>
              <select
                className="select"
                value={query.contact_status}
                onChange={(e) => update({ contact_status: e.target.value })}
              >
                <option value="any">Any</option>
                <option value="uncontacted">Never contacted</option>
                <option value="contacted">Previously contacted</option>
              </select>
            </label>
          </div>
        </div>
      </Card>

      {/* ------------------------------------------------------------ Table -- */}
      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data && loading ? (
        <LoadingCard height={480} />
      ) : (
        <Card
          flush
          title={`${formatNumber(data?.total ?? 0)} matching sellers`}
          subtitle={
            data
              ? `${formatIDR(data.aggregate.monthly_headroom)} monthly headroom · ` +
                `${formatIDR(data.aggregate.expected_monthly_value)} risk-adjusted`
              : undefined
          }
          actions={loading ? <Spinner /> : undefined}
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th style={{ width: 44 }}>#</th>
                  {COLUMNS.map((col) => (
                    <th
                      key={col.key}
                      className={`${col.numeric ? "num" : ""} ${col.sortable ? "sortable" : ""}`}
                      onClick={col.sortable ? () => setSort(col.key) : undefined}
                    >
                      {col.label}
                      {query.sort === col.key && (
                        <span className="sort-arrow">{query.order === "desc" ? "↓" : "↑"}</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data?.rows.map((lead) => (
                  <tr
                    key={lead.seller_id}
                    className="clickable"
                    onClick={() => navigate(withFilters(`/opportunities/${lead.seller_id}`))}
                  >
                    <td className="num faint">{lead.rank}</td>
                    <td>
                      <span className="cell-primary">{lead.seller_name}</span>
                      <span className="cell-secondary">
                        {lead.city} · {lead.seller_type.replace(/_/g, " ")} · {lead.account_tier}
                      </span>
                    </td>
                    <td className="cell-muted">{lead.primary_category}</td>
                    <td className="num">
                      <ScoreMeter score={lead.opportunity_score} tier={lead.priority_tier} />
                    </td>
                    <td className="num strong">{formatIDR(lead.monthly_spend_headroom)}</td>
                    <td className="num cell-muted">{formatIDR(lead.expected_monthly_value)}</td>
                    <td className="num cell-muted">{formatCompact(lead.total_views)}</td>
                    <td>
                      <span className="badge badge-accent">{lead.recommended_product_label}</span>
                    </td>
                    <td className="cell-muted">{lead.next_best_action}</td>
                    <td className="num cell-muted">{daysAgo(lead.days_since_last_contact)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && data.rows.length === 0 && <Empty>No sellers match these filters.</Empty>}
          </div>

          {data && data.total_pages > 1 && (
            <div className="pagination">
              <span>
                Page {data.page} of {formatNumber(data.total_pages)}
              </span>
              <div className="spacer" />
              <button
                className="btn btn-sm"
                disabled={data.page <= 1}
                onClick={() => update({ page: String(data.page - 1) })}
              >
                <IconChevronLeft size={13} /> Prev
              </button>
              <button
                className="btn btn-sm"
                disabled={data.page >= data.total_pages}
                onClick={() => update({ page: String(data.page + 1) })}
              >
                Next <IconChevronRight size={13} />
              </button>
            </div>
          )}
        </Card>
      )}

      {sellerId && (
        <SellerDrawer
          sellerId={sellerId}
          onClose={() => navigate(withFilters("/opportunities"))}
          onChanged={reload}
        />
      )}
    </>
  );
}
