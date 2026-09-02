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

import { useMemo, useState } from "react";
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
const binFill = (bin: number) => `var(--map-${bin + 1})`;
const NO_DATA_FILL = "var(--map-none)";

interface Hovered {
  name: string;
  x: number;
  y: number;
  row?: MapRow;
}

export function IndonesiaMap({
  rows, legendLabel, formatValue, onSelect, height = 380,
}: Props) {
  const [hovered, setHovered] = useState<Hovered | null>(null);

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
      <svg
        viewBox={geo.viewBox}
        width="100%"
        height={height}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Map of Indonesia shaded by ${legendLabel}`}
        style={{ display: "block", overflow: "visible" }}
        onMouseLeave={() => setHovered(null)}
      >
        {/* Provinces */}
        <g>
          {geo.provinces.map((province) => {
            const row = byProvince.get(province.name);
            const active = hovered?.name === province.name;
            return (
              <path
                key={province.name}
                d={province.d}
                fill={row ? binFill(binOf(row.value)) : NO_DATA_FILL}
                stroke={active ? "var(--text)" : "var(--border-strong)"}
                strokeWidth={active ? 1.5 : 0.5}
                strokeLinejoin="round"
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
                fill="var(--accent)"
                fillOpacity={active ? 0.95 : 0.62}
                stroke="var(--bg)"
                strokeWidth={1.2}
                style={{ cursor: onSelect ? "pointer" : "default" }}
                onMouseMove={(e) =>
                  setHovered({ name: province.name, x: e.clientX, y: e.clientY, row })
                }
                onClick={() => onSelect?.(province.name)}
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
          <span className="row" style={{ gap: 2 }}>
            {Array.from({ length: BIN_COUNT }, (_, i) => (
              <span
                key={i}
                title={
                  i === 0
                    ? `up to ${formatValue(thresholds[0] ?? 0)}`
                    : i === BIN_COUNT - 1
                      ? `above ${formatValue(thresholds[BIN_COUNT - 2] ?? 0)}`
                      : `${formatValue(thresholds[i - 1] ?? 0)} - ${formatValue(thresholds[i] ?? 0)}`
                }
                style={{
                  width: 26, height: 10, background: binFill(i),
                  border: "1px solid var(--border)",
                  borderRadius: i === 0 ? "3px 0 0 3px" : i === BIN_COUNT - 1 ? "0 3px 3px 0" : 0,
                }}
              />
            ))}
          </span>
          <span className="faint">low → high</span>
        </div>
        <div className="row gap-2 faint">
          <span
            style={{
              width: 10, height: 10, borderRadius: 2,
              background: NO_DATA_FILL, border: "1px solid var(--border-strong)",
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
