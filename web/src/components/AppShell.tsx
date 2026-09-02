import { type ReactNode, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import {
  IconMap, IconMegaphone, IconMoon, IconOverview, IconStore, IconSun, IconFunnel, IconTarget,
} from "./icons";

const NAV = [
  { to: "/", label: "Overview", Icon: IconOverview, end: true },
  { to: "/opportunities", label: "Opportunities", Icon: IconTarget },
  { to: "/marketplace", label: "Marketplace", Icon: IconStore },
  { to: "/advertising", label: "Advertising", Icon: IconMegaphone },
  { to: "/pipeline", label: "Pipeline", Icon: IconFunnel },
  { to: "/coverage", label: "Coverage", Icon: IconMap },
];

type Theme = "dark" | "light";

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const stored = localStorage.getItem("olxads-theme");
      if (stored === "light" || stored === "dark") return stored;
    } catch {
      /* storage unavailable (private mode) — fall back to the default */
    }
    return "dark";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("olxads-theme", theme);
    } catch {
      /* non-fatal */
    }
  }, [theme]);

  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
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

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">OA</div>
          <div className="brand-text">
            <span className="brand-name">Ads Intelligence</span>
            <span className="brand-sub">OLX Marketplace</span>
          </div>
        </div>

        <nav className="nav">
          <div className="nav-section">Workspace</div>
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
                <span className="nav-badge">{hotCount}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span>Data as of {asOf ?? "—"}</span>
          <span>Synthetic dataset · v1.0</span>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <div className="topbar-title">{title}</div>
            {subtitle && <div className="topbar-sub">{subtitle}</div>}
          </div>
          <div className="topbar-actions">
            <button
              className="btn btn-ghost"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            >
              {theme === "dark" ? <IconSun size={15} /> : <IconMoon size={15} />}
            </button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
