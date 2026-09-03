/** Thin typed fetch wrapper + a small data-loading hook. */

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ActivityInput, AdvertisingAnalytics, CoverageAnalytics, FilterOptions,
  LeadsResponse, MarketplaceAnalytics, OlapAnalytics, Overview, PipelineAnalytics, SellerDetail,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

/** Build a query string, expanding array values into repeated keys. */
export function toQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" ) continue;
    if (Array.isArray(value)) {
      value.forEach((v) => search.append(key, String(v)));
    } else {
      search.append(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  overview: () => request<Overview>("/overview"),
  leads: (params: Record<string, unknown>) => request<LeadsResponse>(`/leads${toQuery(params)}`),
  filters: () => request<FilterOptions>("/leads/filters"),
  seller: (id: string) => request<SellerDetail>(`/sellers/${id}`),
  marketplace: () => request<MarketplaceAnalytics>("/analytics/marketplace"),
  advertising: () => request<AdvertisingAnalytics>("/analytics/advertising"),
  pipeline: () => request<PipelineAnalytics>("/analytics/pipeline"),
  coverage: () => request<CoverageAnalytics>("/analytics/coverage"),
  olap: () => request<OlapAnalytics>("/analytics/olap"),
  logActivity: (id: string, payload: ActivityInput) =>
    request<{ activity_id: string; seller: unknown }>(`/sellers/${id}/activities`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  exportUrl: (params: Record<string, unknown>) => `${BASE}/leads/export${toQuery(params)}`,
};

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Runs an async loader and tracks its state. `deps` controls re-fetching; a
 * request counter guards against a slow earlier response overwriting a newer
 * one when filters change quickly.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(loader, deps);

  useEffect(() => {
    const id = ++requestId.current;
    let active = true;
    setLoading(true);
    setError(null);
    run()
      .then((result) => {
        if (active && id === requestId.current) setData(result);
      })
      .catch((err: unknown) => {
        if (active && id === requestId.current) {
          setError(err instanceof Error ? err.message : "Request failed");
        }
      })
      .finally(() => {
        if (active && id === requestId.current) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [run, nonce]);

  return { data, loading, error, reload: () => setNonce((n) => n + 1) };
}
