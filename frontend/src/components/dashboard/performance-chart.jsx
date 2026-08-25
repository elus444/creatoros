"use client";

import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function PerformanceChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data}>
        <defs>
          <linearGradient id="dashViews" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2170e4" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#2170e4" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <XAxis dataKey="label" hide />
        <YAxis hide />
        <Tooltip />
        <Area
          type="monotone"
          dataKey="views"
          stroke="#0058be"
          fill="url(#dashViews)"
          strokeWidth={2}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
