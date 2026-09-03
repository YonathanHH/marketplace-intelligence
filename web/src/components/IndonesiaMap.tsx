/** Choropleth of Indonesia for the Coverage view.
 *
 * Renders from a pre-projected asset (`src/data/indonesia.json`, built by
 * `scripts/build_geo.py` from public-domain Natural Earth data), so there is no
 * mapping library, no tile server and no runtime GeoJSON fetch.
 *
 * Two marks, deliberately:
 *  - **Fill** encodes the metric across the province's actual area.
 *  - **A centroid marker** gives every province with data a reliable hover and
 *    click target. Without it DKI Jakarta - the single most valuable territory
 *    in the dataset - would be a two-pixel speck and effectively unusable.
 *
 * Provinces the marketplace has no sellers in are drawn muted rather than
 * hidden, so the map reads as Indonesia and shows where the business isn't.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import { useThemeColors } from "../lib/theme";
import geo from "../data/indonesia.json";

export interface MapRow {
  province: string;
  value: number;
  detail: { label: string; value: string }[];
}

interface Props {
  rows: MapRow[];
  legendLabel: string;
  formatValue: (value: number) => string;
  onSelect?: (province: string) => void;
  height?: number;
}

const BIN_COUNT = 5;
// Explicit ramp tokens (see tokens.css) rather than a computed colour mix:
// at map scale the bins have to be distinguishable at a glance, in both themes.
//
// These are resolved to concrete colours before use. `var()` is only valid in a
// CSS property, and Recharts and this map both write colour into SVG `fill` and
// `stroke` *attributes*, where support for it is not something to rely on.
const binToken = (bin: number) => `var(--map-${bin + 1})`;
const NO_DATA_TOKEN = "var(--map-none)";

interface Hovered {
  name: string;
  x: number;
  y: number;
  row?: MapRow;
}

/** A province's tooltip summary, flattened for a screen reader. */
function describe(name: string, row?: MapRow): string {
  if (!row) return `${name}: no sellers in this province`;
  return `${name}. ${row.detail.map((d) => `${d.label}: ${d.value}`).join(". ")}`;
}

export function IndonesiaMap({
  rows, legendLabel, formatValue, onSelect, height = 380,
}: Props) {
  const [hovered, setHovered] = useState<Hovered | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const theme = useThemeColors();

  const binFill = (bin: number) => theme.resolve(binToken(bin), "#888");
  const noDataFill = theme.resolve(NO_DATA_TOKEN, "#888");

  // Keyboard focus has no pointer coordinates, so the tooltip is anchored to
  // the focused marker's own box instead.
  const showAtElement = useCallback((el: Element, name: string, row?: MapRow) => {
    const box = el.getBoundingClientRect();
    setHovered({ name, x: box.right, y: box.bottom, row });
  }, []);

  const { byProvince, thresholds, maxValue } = useMemo(() => {
    const map = new Map(rows.map((r) => [r.province, r]));
    const values = rows.map((r) => r.value).filter((v) => v > 0).sort((a, b) => a - b);

    // Quantile bins: headroom is heavily skewed, so equal-width bins would put
    // almost every province in the lowest bucket.
    const cuts: number[] = [];
    for (let i = 1; i < BIN_COUNT; i++) {
      const pos = (values.length - 1) * (i / BIN_COUNT);
      cuts.push(values[Math.round(pos)] ?? 0);
    }
    return {
      byProvince: map,
      thresholds: cuts,
      maxValue: values.length ? values[values.length - 1] : 0,
    };
  }, [rows]);

  const binOf = (value: number) => {
    let bin = 0;
    for (const cut of thresholds) if (value > cut) bin++;
    return bin;
  };

  const markerRadius = (value: number) => {
    if (maxValue <= 0) return 3;
    return 3.5 + Math.sqrt(Math.max(value, 0) / maxValue) * 9;
  };

  return (
    <div style={{ position: "relative" }}>
      {/* `group`, not `img`: the markers inside are real controls, and an `img`
          role would hide them from assistive technology entirely. */}
      <svg
        ref={svgRef}
        viewBox={geo.viewBox}
        width="100%"
        height={height}
        preserveAspectRatio="xMidYMid meet"
        role="group"
        aria-label={`Map of Indonesia shaded by ${legendLabel}. ${rows.length} provinces with sellers.`}
        style={{ display: "block", overflow: "visible" }}
        onMouseLeave={() => setHovered(null)}
      >
        {/* Provinces */}
        <g>
          {geo.provinces.map((province) => {
            const row = byProvince.get(province.name);
            const active = hovered?.name === province.name;
            return (
              /* Decorative: the fill carries the metric, but the focusable
                 control for each province is its centroid marker below. */
              <path
                key={province.name}
                d={province.d}
                fill={row ? binFill(binOf(row.value)) : noDataFill}
                stroke={theme.resolve(active ? "var(--text)" : "var(--border-strong)")}
                strokeWidth={active ? 1.5 : 0.5}
                strokeLinejoin="round"
                aria-hidden="true"
                style={{ cursor: row && onSelect ? "pointer" : "default", transition: "stroke 120ms" }}
                onMouseMove={(e) =>
                  setHovered({ name: province.name, x: e.clientX, y: e.clientY, row })
                }
                onClick={() => row && onSelect?.(province.name)}
              >
                <title>{province.name}</title>
              </path>
            );
          })}
        </g>

        {/* Centroid markers for provinces we actually operate in */}
        <g>
          {geo.provinces.map((province) => {
            const row = byProvince.get(province.name);
            if (!row) return null;
            const active = hovered?.name === province.name;
            return (
              <circle
                key={`m-${province.name}`}
                cx={province.cx}
                cy={province.cy}
                r={markerRadius(row.value)}
                fill={theme.resolve("var(--accent)")}
                fillOpacity={active ? 0.95 : 0.62}
                stroke={theme.resolve(active ? "var(--text)" : "var(--bg)")}
                strokeWidth={active ? 2 : 1.2}
                role={onSelect ? "button" : "img"}
                tabIndex={0}
                aria-label={
                  onSelect
                    ? `${describe(province.name, row)}. Open this territory's queue.`
                    : describe(province.name, row)
                }
                style={{ cursor: onSelect ? "pointer" : "default" }}
                onMouseMove={(e) =>
                  setHovered({ name: province.name, x: e.clientX, y: e.clientY, row })
                }
                onFocus={(e) => showAtElement(e.currentTarget, province.name, row)}
                onBlur={() => setHovered(null)}
                onClick={() => onSelect?.(province.name)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect?.(province.name);
                  }
                }}
              >
                <title>{province.name}</title>
              </circle>
            );
          })}
        </g>
      </svg>

      {/* Legend */}
      <div
        className="row gap-4 wrap"
        style={{ marginTop: "var(--space-3)", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}
      >
        <div className="row gap-2">
          <span>{legendLabel}</span>
          <span className="row" style={{ gap: 2 }} aria-hidden="true">
            {Array.from({ length: BIN_COUNT }, (_, i) => (
              <span
                key={i}
                style={{
                  width: 26, height: 10, background: binFill(i),
                  border: "1px solid var(--border)",
                  borderRadius: i === 0 ? "3px 0 0 3px" : i === BIN_COUNT - 1 ? "0 3px 3px 0" : 0,
                }}
              />
            ))}
          </span>
          {/* The bin boundaries as text, not as a `title` tooltip - the ramp is
              meaningless without them and a tooltip never reaches keyboard or
              touch. */}
          <span className="faint">
            {formatValue(0)} → {formatValue(maxValue)}
          </span>
        </div>
        <div className="row gap-2 faint">
          <span
            style={{
              width: 10, height: 10, borderRadius: 2,
              background: noDataFill, border: "1px solid var(--border-strong)",
            }}
          />
          <span>no sellers in dataset</span>
        </div>
        {onSelect && <span className="faint">Click a province to open its queue</span>}
      </div>

      {/* Tooltip */}
      {hovered && (
        <div
          className="tooltip"
          style={{
            position: "fixed",
            left: Math.min(hovered.x + 14, window.innerWidth - 240),
            top: hovered.y + 14,
            pointerEvents: "none",
            zIndex: 50,
          }}
        >
          <div className="tooltip-label">{hovered.name}</div>
          {hovered.row ? (
            hovered.row.detail.map((d) => (
              <div className="tooltip-row" key={d.label}>
                <span>{d.label}</span>
                <span className="value">{d.value}</span>
              </div>
            ))
          ) : (
            <div className="tooltip-row">
              <span className="faint">No sellers in this province</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
