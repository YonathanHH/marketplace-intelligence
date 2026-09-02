/** Recharts wrappers themed to the design tokens.

Charts read colours from CSS variables so they follow the light/dark theme, and
share one categorical palette so a category keeps the same colour everywhere.
*/

import type { ReactNode } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { formatCompact, SERIES } from "../lib/format";

const AXIS = { stroke: "var(--border-strong)", tickLine: false, axisLine: false };

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

export function ChartFrame({ height = 260, children }: { height?: number; children: ReactNode }) {
  return (
    <div className="chart-frame" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        {children as never}
      </ResponsiveContainer>
    </div>
  );
}

/* ------------------------------------------------------------ Area trend -- */
export function AreaTrend({
  data, xKey, series, height = 260, xFormatter, valueFormatter, stacked,
}: {
  data: Record<string, unknown>[];
  xKey: string;
  series: { key: string; name: string; color?: string }[];
  height?: number;
  xFormatter?: (v: string) => string;
  valueFormatter?: (v: number, name: string) => string;
  stacked?: boolean;
}) {
  return (
    <ChartFrame height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color ?? SERIES[i % SERIES.length]} stopOpacity={0.32} />
              <stop offset="100%" stopColor={s.color ?? SERIES[i % SERIES.length]} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormatter} minTickGap={28} />
        <YAxis {...AXIS} width={48} tickFormatter={(v: number) => formatCompact(v)} />
        <Tooltip
          content={<ChartTooltip formatter={valueFormatter} labelFormatter={xFormatter} />}
          cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
        />
        {series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stackId={stacked ? "1" : undefined}
            stroke={s.color ?? SERIES[i % SERIES.length]}
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
  data, xKey, series, height = 240, xFormatter, valueFormatter,
}: {
  data: Record<string, unknown>[];
  xKey: string;
  series: { key: string; name: string; color?: string }[];
  height?: number;
  xFormatter?: (v: string) => string;
  valueFormatter?: (v: number, name: string) => string;
}) {
  return (
    <ChartFrame height={height}>
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormatter} minTickGap={24} />
        <YAxis {...AXIS} width={48} tickFormatter={(v: number) => formatCompact(v)} />
        <Tooltip
          content={<ChartTooltip formatter={valueFormatter} labelFormatter={xFormatter} />}
          cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
        />
        {series.length > 1 && (
          <Legend
            iconType="circle"
            iconSize={7}
            wrapperStyle={{ fontSize: 11.5, color: "var(--text-muted)", paddingTop: 8 }}
          />
        )}
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stroke={s.color ?? SERIES[i % SERIES.length]}
            strokeWidth={1.9}
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
  data, xKey, series, height = 260, horizontal, xFormatter, valueFormatter, colorByIndex,
}: {
  data: Record<string, unknown>[];
  xKey: string;
  series: { key: string; name: string; color?: string }[];
  height?: number;
  horizontal?: boolean;
  xFormatter?: (v: string) => string;
  valueFormatter?: (v: number, name: string) => string;
  colorByIndex?: boolean;
}) {
  return (
    <ChartFrame height={height}>
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
          cursor={{ fill: "var(--surface-hover)" }}
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
            fill={s.color ?? SERIES[i % SERIES.length]}
            radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
            maxBarSize={horizontal ? 20 : 46}
          >
            {colorByIndex &&
              data.map((_, idx) => <Cell key={idx} fill={SERIES[idx % SERIES.length]} />)}
          </Bar>
        ))}
      </BarChart>
    </ChartFrame>
  );
}

/* ----------------------------------------------------------------- Donut -- */
export function Donut({
  data, nameKey, valueKey, height = 220, colors, centerLabel, centerValue, valueFormatter,
}: {
  data: Record<string, unknown>[];
  nameKey: string;
  valueKey: string;
  height?: number;
  colors?: string[];
  centerLabel?: string;
  centerValue?: string;
  valueFormatter?: (v: number, name: string) => string;
}) {
  const palette = colors ?? SERIES;
  return (
    <div style={{ position: "relative" }}>
      <ChartFrame height={height}>
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
              <Cell key={i} fill={palette[i % palette.length]} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip formatter={valueFormatter} />} />
        </PieChart>
      </ChartFrame>
      {centerValue && (
        <div
          style={{
            position: "absolute", inset: 0, display: "grid", placeContent: "center",
            textAlign: "center", pointerEvents: "none",
          }}
        >
          <div style={{ fontSize: "var(--text-xl)", fontWeight: 680, letterSpacing: "-0.02em" }}>
            {centerValue}
          </div>
          {centerLabel && (
            <div style={{ fontSize: "var(--text-xs)", color: "var(--text-faint)" }}>{centerLabel}</div>
          )}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- Sparkline -- */
export function Sparkline({
  data, dataKey, height = 40, color = "var(--accent)",
}: {
  data: Record<string, unknown>[];
  dataKey: string;
  height?: number;
  color?: string;
}) {
  return (
    <ChartFrame height={height}>
      <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={`spark-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey={dataKey}
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#spark-${dataKey})`}
          dot={false}
        />
      </AreaChart>
    </ChartFrame>
  );
}
