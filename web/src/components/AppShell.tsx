import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useModalFocus } from "../lib/modal";
import {
  IconClose, IconLayers, IconMap, IconMegaphone, IconMenu, IconMoon, IconOverview,
  IconStore, IconSun, IconFunnel, IconTarget,
} from "./icons";

const NAV = [
  { to: "/", label: "Overview", Icon: IconOverview, end: true },
  { to: "/opportunities", label: "Opportunities", Icon: IconTarget },
  { to: "/marketplace", label: "Marketplace", Icon: IconStore },
  { to: "/advertising", label: "Advertising", Icon: IconMegaphone },
  { to: "/pipeline", label: "Pipeline", Icon: IconFunnel },
  { to: "/coverage", label: "Coverage", Icon: IconMap },
  { to: "/deep-dive", label: "Deep Dive", Icon: IconLayers },
];

type Theme = "dark" | "light";

const THEME_KEY = "olxads-theme";

/**
 * Theme. Light — the framed-sheet direction — is the default; a stored value
 * means the user chose explicitly and always wins. The toggle is the only way
 * to change it, so the product never flips under someone mid-session.
 */
function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const stored = localStorage.getItem(THEME_KEY);
      if (stored === "light" || stored === "dark") return stored;
    } catch {
      /* storage unavailable (private mode) — fall through to the default */
    }
    return "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch {
        /* non-fatal */
      }
      return next;
    });
  }, []);

  return [theme, toggle];
}

/** The mark: four ascending bars — the opportunity ladder, shortest to tallest.
 *  Drawn rather than a letterform so it reads at 26px and themes with accent. */
function BrandMark() {
  return (
    <div className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <rect x="1" y="16" width="4" height="6" />
        <rect x="7" y="12" width="4" height="10" />
        <rect x="13" y="8" width="4" height="14" />
        <rect x="19" y="4" width="4" height="18" />
      </svg>
    </div>
  );
}

/** Below the sidebar breakpoint the nav becomes a modal overlay, so it gets
 *  the same focus handling as any other dialog. */
function useMobileNav(pathname: string) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useModalFocus<HTMLDivElement>(open, () => setOpen(false));

  // Navigating dismisses it; that is the only reason it was opened.
  useEffect(() => setOpen(false), [pathname]);

  // Focus the first link rather than the panel, so the first Tab moves down
  // the nav instead of straight back out of it.
  useEffect(() => {
    if (open) panelRef.current?.querySelector<HTMLElement>("a, button")?.focus();
  }, [open, panelRef]);

  return { open, setOpen, panelRef, triggerRef };
}

function NavList({ hotCount }: { hotCount?: number }) {
  return (
    <>
      <div className="nav-section" aria-hidden="true">Workspace</div>
      {NAV.map(({ to, label, Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
        >
          <Icon size={16} className="nav-icon" />
          {label}
          {to === "/opportunities" && hotCount !== undefined && (
            <span className="nav-badge">
              {hotCount}
              <span className="sr-only"> hot leads</span>
            </span>
          )}
        </NavLink>
      ))}
    </>
  );
}

export function AppShell({
  children, title, subtitle, hotCount, asOf,
}: {
  children: ReactNode;
  title: string;
  subtitle?: string;
  hotCount?: number;
  asOf?: string;
}) {
  const [theme, toggleTheme] = useTheme();
  const { pathname } = useLocation();
  const nav = useMobileNav(pathname);

  return (
    <div className="app">
      {/* First thing in the tab order: a keyboard user should not have to walk
          the whole nav on every route to reach the content. */}
      <a className="skip-link" href="#main-content">Skip to main content</a>

      <aside className="sidebar">
        <div className="brand">
          <BrandMark />
          <div className="brand-text">
            <span className="brand-name">Ads Intelligence</span>
            <span className="brand-sub">OLX Marketplace</span>
          </div>
        </div>

        <nav className="nav" aria-label="Primary">
          <NavList hotCount={hotCount} />
        </nav>

        <div className="sidebar-footer">
          <span>Data as of {asOf ?? "—"}</span>
          <span>Synthetic dataset · v1.0</span>
        </div>
      </aside>

      {/* Mobile: the same nav as an overlay. Rendered only while open so its
          links stay out of the tab order the rest of the time. */}
      {nav.open && (
        <>
          <div className="nav-backdrop" onClick={() => nav.setOpen(false)} aria-hidden="true" />
          <div
            className="nav-panel"
            id="mobile-nav"
            ref={nav.panelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
          >
            <div className="nav-panel-head">
              <div className="brand">
                <BrandMark />
                <div className="brand-text">
                  <span className="brand-name">Ads Intelligence</span>
                  <span className="brand-sub">OLX Marketplace</span>
                </div>
              </div>
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => {
                  nav.setOpen(false);
                  nav.triggerRef.current?.focus();
                }}
                aria-label="Close navigation"
              >
                <IconClose size={18} />
              </button>
            </div>
            <nav className="nav" aria-label="Primary">
              <NavList hotCount={hotCount} />
            </nav>
            <div className="sidebar-footer">
              <span>Data as of {asOf ?? "—"}</span>
            </div>
          </div>
        </>
      )}

      <div className="main">
        <header className="topbar">
          <button
            ref={nav.triggerRef}
            className="btn btn-ghost btn-icon nav-trigger"
            onClick={() => nav.setOpen(true)}
            aria-expanded={nav.open}
            aria-controls="mobile-nav"
            aria-label="Open navigation"
          >
            <IconMenu size={18} />
          </button>

          <div className="topbar-heading">
            <div className="topbar-title">{title}</div>
            {subtitle && <div className="topbar-sub">{subtitle}</div>}
          </div>

          <div className="topbar-actions">
            <button
              className="btn btn-ghost btn-icon"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            >
              {theme === "dark" ? <IconSun size={15} /> : <IconMoon size={15} />}
            </button>
          </div>
        </header>

        <main className="content" id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
