/** Recharts wrappers themed to the design tokens.

Two things every chart here gets that a bare Recharts chart does not:

**Theme-correct colour.** Recharts writes colours into SVG `fill`/`stroke`
*attributes*, where `var(--token)` does not reliably resolve, so every colour
goes through `useThemeColors` (lib/theme.ts) first. That also lets the
categorical palette differ between light and dark, which it has to: no single
mid-tone set clears the 3:1 non-text contrast threshold against both a
near-black and a white ground.

**A non-visual equivalent.** An `<svg>` full of paths conveys nothing to a
screen reader. Every chart takes a `label` describing what it plots and renders
inside a `role="img"` figure, with the underlying numbers reachable from the
surrounding card. Charts are never the only place a number appears.
*/

import { type ReactNode } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { formatCompact } from "../lib/format";
import { useThemeColors } from "../lib/theme";

// Axis and tick lines are off; the tick *labels* are styled from CSS in
// app.css, where var() resolves normally.
const AXIS = { tickLine: false, axisLine: false } as const;

/* ------------------------------------------------------------- Tooltip -- */

interface TooltipPayloadItem {
  name?: string;
  value?: number | string;
  color?: string;
  dataKey?: string | number;
  payload?: Record<string, unknown>;
}

function ChartTooltip({
  active, payload, label, formatter, labelFormatter,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string | number;
  formatter?: (value: number, name: string) => string;
  labelFormatter?: (label: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      {label !== undefined && (
        <div className="tooltip-label">
          {labelFormatter ? labelFormatter(String(label)) : String(label)}
        </div>
      )}
      {payload.map((item, i) => (
        <div className="tooltip-row" key={`${item.dataKey}-${i}`}>
          <span className="swatch" style={{ background: item.color }} />
          <span>{item.name}</span>
          <span className="value">
            {formatter
              ? formatter(Number(item.value), String(item.name))
              : formatCompact(Number(item.value))}
          </span>
        </div>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- Frame -- */

export function ChartFrame({
  height = 260, label, children,
}: {
  height?: number;
  /** What the chart shows, for anyone who cannot see it. */
  label: string;
  children: ReactNode;
}) {
  return (
    <figure className="chart-frame" style={{ height }} role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height="100%">
        {children as never}
      </ResponsiveContainer>
    </figure>
  );
}

/* ------------------------------------------------------------ Area trend -- */
export function AreaTrend({
  data, xKey, series, height = 260, xFormatter, valueFormatter, stacked, label,
}: {
  data: Record<string, unknown>[];
  xKey: string;
  series: { key: string; name: string; color?: string }[];
  height?: number;
  xFormatter?: (v: string) => string;
  valueFormatter?: (v: number, name: string) => string;
  stacked?: boolean;
  label: string;
}) {
  const palette = useThemeColors();
  const colors = series.map((s, i) => palette.resolve(s.color, palette.series[i % palette.series.length]));

  return (
    <ChartFrame height={height} label={label}>
      <AreaChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colors[i]} stopOpacity={0.32} />
              <stop offset="100%" stopColor={colors[i]} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormatter} minTickGap={28} />
        <YAxis {...AXIS} width={48} tickFormatter={(v: number) => formatCompact(v)} />
        <Tooltip
          content={<ChartTooltip formatter={valueFormatter} labelFormatter={xFormatter} />}
          cursor={{ stroke: palette.resolve("var(--border-strong)"), strokeWidth: 1 }}
        />
        {series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stackId={stacked ? "1" : undefined}
            stroke={colors[i]}
            strokeWidth={1.8}
            fill={`url(#grad-${s.key})`}
            dot={false}
            activeDot={{ r: 3.5, strokeWidth: 0 }}
          />
        ))}
      </AreaChart>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------ Line trend -- */
export function LineTrend({
  data, xKey, series, height = 240, xFormatter, valueFormatter, label, referenceY,
}: {
  data: Record<string, unknown>[];
  xKey: string;
  series: { key: string; name: string; color?: string; dashed?: boolean }[];
  height?: number;
  xFormatter?: (v: string) => string;
  valueFormatter?: (v: number, name: string) => string;
  label: string;
  /** Horizontal marker — e.g. a baseline the series should be read against. */
  referenceY?: { value: number; label: string };
}) {
  const palette = useThemeColors();

  return (
    <ChartFrame height={height} label={label}>
      <LineChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormatter} minTickGap={24} />
        <YAxis {...AXIS} width={48} tickFormatter={(v: number) => formatCompact(v)} />
        <Tooltip
          content={<ChartTooltip formatter={valueFormatter} labelFormatter={xFormatter} />}
          cursor={{ stroke: palette.resolve("var(--border-strong)"), strokeWidth: 1 }}
        />
        {referenceY && (
          <ReferenceLine
            y={referenceY.value}
            stroke={palette.resolve("var(--text-faint)")}
            strokeDasharray="4 4"
            label={{
              value: referenceY.label,
              position: "insideTopRight",
              fill: palette.resolve("var(--text-faint)"),
              fontSize: 11,
            }}
          />
        )}
        {series.length > 1 && (
          <Legend
            iconType="plainline"
            iconSize={14}
            wrapperStyle={{ fontSize: 11.5, color: "var(--text-muted)", paddingTop: 8 }}
          />
        )}
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stroke={palette.resolve(s.color, palette.series[i % palette.series.length])}
            strokeWidth={1.9}
            strokeDasharray={s.dashed ? "5 4" : undefined}
            dot={false}
            activeDot={{ r: 3.5, strokeWidth: 0 }}
          />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------- Bar chart -- */
export function Bars({
  data, xKey, series, height = 260, horizontal, xFormatter, valueFormatter, colorByIndex, label,
}: {
  data: Record<string, unknown>[];
  xKey: string;
  series: { key: string; name: string; color?: string }[];
  height?: number;
  horizontal?: boolean;
  xFormatter?: (v: string) => string;
  valueFormatter?: (v: number, name: string) => string;
  colorByIndex?: boolean;
  label: string;
}) {
  const palette = useThemeColors();

  return (
    <ChartFrame height={height} label={label}>
      <BarChart
        data={data}
        layout={horizontal ? "vertical" : "horizontal"}
        margin={{ top: 6, right: 12, bottom: 0, left: horizontal ? 8 : 0 }}
        barCategoryGap={horizontal ? "22%" : "28%"}
      >
        <CartesianGrid vertical={horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" {...AXIS} tickFormatter={(v: number) => formatCompact(v)} />
            <YAxis type="category" dataKey={xKey} {...AXIS} width={132} tickFormatter={xFormatter} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormatter} minTickGap={12} />
            <YAxis {...AXIS} width={48} tickFormatter={(v: number) => formatCompact(v)} />
          </>
        )}
        <Tooltip
          content={<ChartTooltip formatter={valueFormatter} labelFormatter={xFormatter} />}
          cursor={{ fill: palette.resolve("var(--surface-hover)") }}
        />
        {series.length > 1 && (
          <Legend
            iconType="circle"
            iconSize={7}
            wrapperStyle={{ fontSize: 11.5, color: "var(--text-muted)", paddingTop: 8 }}
          />
        )}
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.name}
            fill={palette.resolve(s.color, palette.series[i % palette.series.length])}
            radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
            maxBarSize={horizontal ? 20 : 46}
          >
            {colorByIndex &&
              data.map((_, idx) => (
                <Cell key={idx} fill={palette.series[idx % palette.series.length]} />
              ))}
          </Bar>
        ))}
      </BarChart>
    </ChartFrame>
  );
}

/* ----------------------------------------------------------------- Donut -- */
export function Donut({
  data, nameKey, valueKey, height = 220, colors, centerLabel, centerValue, valueFormatter, label,
}: {
  data: Record<string, unknown>[];
  nameKey: string;
  valueKey: string;
  height?: number;
  colors?: string[];
  centerLabel?: string;
  centerValue?: string;
  valueFormatter?: (v: number, name: string) => string;
  label: string;
}) {
  const palette = useThemeColors();
  const resolved = (colors ?? palette.series).map((c, i) =>
    palette.resolve(c, palette.series[i % palette.series.length])
  );

  return (
    <div style={{ position: "relative" }}>
      <ChartFrame height={height} label={label}>
        <PieChart>
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey={nameKey}
            innerRadius="62%"
            outerRadius="88%"
            paddingAngle={2}
            stroke="none"
          >
            {data.map((_, i) => (
              <Cell key={i} fill={resolved[i % resolved.length]} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip formatter={valueFormatter} />} />
        </PieChart>
      </ChartFrame>
      {centerValue && (
        <div className="donut-center" aria-hidden="true">
          <div className="donut-center-value">{centerValue}</div>
          {centerLabel && <div className="donut-center-label">{centerLabel}</div>}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- Sparkline -- */
export function Sparkline({
  data, dataKey, height = 40, color = "var(--accent)", label,
}: {
  data: Record<string, unknown>[];
  dataKey: string;
  height?: number;
  color?: string;
  label: string;
}) {
  const palette = useThemeColors();
  const stroke = palette.resolve(color);

  return (
    <ChartFrame height={height} label={label}>
      <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={`spark-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={0.3} />
            <stop offset="100%" stopColor={stroke} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey={dataKey}
          stroke={stroke}
          strokeWidth={1.5}
          fill={`url(#spark-${dataKey})`}
          dot={false}
        />
      </AreaChart>
    </ChartFrame>
  );
}
