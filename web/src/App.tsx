import { Suspense, lazy, useEffect } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { api, useAsync } from "./api/client";
import { LoadingCard } from "./components/ui";
import Landing from "./views/Landing";

// Route-level code splitting: the charting library is heavy and the queue —
// the view reps actually live in — does not need it up front.
const Overview = lazy(() => import("./views/Overview"));
const Opportunities = lazy(() => import("./views/Opportunities"));
const Marketplace = lazy(() => import("./views/Marketplace"));
const Advertising = lazy(() => import("./views/Advertising"));
const Pipeline = lazy(() => import("./views/Pipeline"));
const Coverage = lazy(() => import("./views/Coverage"));
const DeepDive = lazy(() => import("./views/DeepDive"));

const TITLES: { prefix: string; title: string; subtitle: string }[] = [
  { prefix: "/opportunities", title: "Opportunities", subtitle: "Ranked advertiser prospects with the evidence behind each one" },
  { prefix: "/marketplace", title: "Marketplace", subtitle: "Supply, demand and engagement across the platform" },
  { prefix: "/advertising", title: "Advertising", subtitle: "Current ad revenue, product mix and efficiency" },
  { prefix: "/pipeline", title: "Pipeline", subtitle: "Sales activity, conversion and rep performance" },
  { prefix: "/coverage", title: "Coverage", subtitle: "Where the sales team is over- and under-invested" },
  { prefix: "/deep-dive", title: "Deep Dive", subtitle: "Columnar analytics over the full metric history" },
  { prefix: "/app", title: "Overview", subtitle: "Where the untapped ad revenue is right now" },
  { prefix: "/", title: "Revenue intelligence", subtitle: "The money is already here" },
];

export default function App() {
  // Loaded once at the shell level: powers the nav badge and the as-of stamp.
  const { data: overview } = useAsync(() => api.overview(), []);
  const { pathname } = useLocation();
  const meta = TITLES.find((t) => pathname.startsWith(t.prefix)) ?? TITLES[TITLES.length - 1];

  // A client-side route change replaces the page without any of the cues a real
  // navigation gives: the document title never updates and a screen reader is
  // told nothing. Both are fixed here, once, for every route.
  useEffect(() => {
    document.title = `${meta.title} · OLX Ads Intelligence`;
  }, [meta.title]);

  // The marketing landing is its own page, outside the dashboard shell.
  if (pathname === "/") return <Landing />;

  return (
    <AppShell
      title={meta.title}
      subtitle={meta.subtitle}
      hotCount={overview?.kpis.hot_leads}
      asOf={overview?.as_of}
    >
      <p aria-live="polite" className="sr-only">{meta.title} page loaded</p>
      <Suspense fallback={<LoadingCard height={420} label={`Loading ${meta.title}`} />}>
        <Routes>
          <Route path="/app" element={<Overview />} />
          <Route path="/opportunities" element={<Opportunities />} />
          <Route path="/opportunities/:sellerId" element={<Opportunities />} />
          <Route path="/marketplace" element={<Marketplace />} />
          <Route path="/advertising" element={<Advertising />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/coverage" element={<Coverage />} />
          <Route path="/deep-dive" element={<DeepDive />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
