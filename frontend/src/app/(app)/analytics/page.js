"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  BarChart3,
  Eye,
  Heart,
  Loader2,
  MessageCircle,
  Percent,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError, analyticsApi, projectsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const RANGES = [
  { value: 7, label: "7d" },
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
];

const PRIORITY_STYLES = {
  high: "bg-error-container text-error",
  medium: "bg-amber-100 text-amber-900",
  low: "bg-surface-container text-on-surface-variant",
};

function formatNumber(value) {
  if (value == null) return "0";
  return new Intl.NumberFormat("en-US", { notation: value >= 10000 ? "compact" : "standard" }).format(
    value,
  );
}

function formatPercent(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function MetricSkeleton() {
  return (
    <div className="h-28 animate-pulse rounded-xl border border-outline-variant/60 bg-surface-container/60" />
  );
}

function ChartSkeleton({ height = 280 }) {
  return (
    <div
      className="animate-pulse rounded-xl border border-outline-variant/60 bg-surface-container/40"
      style={{ height }}
    />
  );
}

function AnalyticsDashboard() {
  const { token } = useAuth();
  const searchParams = useSearchParams();
  const projectFromQuery = searchParams.get("project") || "";

  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(projectFromQuery);
  const [rangeDays, setRangeDays] = useState(30);
  const [summary, setSummary] = useState(null);
  const [coach, setCoach] = useState(null);
  const [loading, setLoading] = useState(true);
  const [coachLoading, setCoachLoading] = useState(false);
  const [error, setError] = useState("");
  const [coachError, setCoachError] = useState("");
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    if (!token) return;
    let active = true;
    async function loadProjects() {
      try {
        const data = await projectsApi.list(token);
        if (!active) return;
        setProjects(data);
        setProjectId((current) => current || data[0]?.id || "");
      } catch (err) {
        if (active) {
          setError(err instanceof ApiError ? err.message : "Unable to load projects.");
          setLoading(false);
        }
      }
    }
    loadProjects();
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => {
    if (!token || !projectId) {
      if (!projectId) setLoading(false);
      return;
    }
    let active = true;
    async function loadSummary() {
      setLoading(true);
      setError("");
      setCoach(null);
      try {
        const data = await analyticsApi.projectSummary(projectId, token, rangeDays);
        if (!active) return;
        setSummary(data);
        if (!data?.has_data) {
          setCoach(null);
        }
      } catch (err) {
        if (active) {
          setSummary(null);
          setError(err instanceof ApiError ? err.message : "Unable to load analytics.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    loadSummary();
    return () => {
      active = false;
    };
  }, [token, projectId, rangeDays]);

  const chartData = useMemo(() => {
    if (!summary?.series?.length) return [];
    return summary.series.map((point) => ({
      ...point,
      label: point.date.slice(5),
    }));
  }, [summary]);

  async function refreshFromYouTube() {
    if (!token || !projectId) return;
    setSyncing(true);
    setError("");
    try {
      await analyticsApi.sync(projectId, token);
      const data = await analyticsApi.projectSummary(projectId, token, rangeDays);
      setSummary(data);
      if (!data?.has_data) {
        setCoach(null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to refresh YouTube statistics.");
    } finally {
      setSyncing(false);
    }
  }

  async function runCoach() {
    if (!token || !projectId) return;
    setCoachLoading(true);
    setCoachError("");
    try {
      const data = await analyticsApi.coach(projectId, token, rangeDays);
      setCoach(data);
    } catch (err) {
      setCoachError(err instanceof ApiError ? err.message : "Unable to generate coach recommendations.");
    } finally {
      setCoachLoading(false);
    }
  }

  const totals = summary?.totals;

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <p className="font-label text-xs uppercase tracking-[0.08em] text-primary">Performance</p>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface md:text-4xl">
            Analytics
          </h1>
          <p className="max-w-2xl text-sm leading-6 text-on-surface-variant md:text-base">
            Live YouTube views, likes, and comments for Shorts published from this project.
          </p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="h-10 rounded-lg border border-outline-variant bg-surface-container-lowest px-3 text-sm text-on-surface"
            disabled={!projects.length}
          >
            {projects.length === 0 ? (
              <option value="">No projects</option>
            ) : (
              projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))
            )}
          </select>
          <div className="inline-flex rounded-lg border border-outline-variant bg-surface-container-lowest p-1">
            {RANGES.map((range) => (
              <button
                key={range.value}
                type="button"
                onClick={() => setRangeDays(range.value)}
                className={cn(
                  "rounded-md px-3 py-1.5 font-label text-xs uppercase tracking-[0.06em] transition",
                  rangeDays === range.value
                    ? "bg-primary text-on-primary"
                    : "text-on-surface-variant hover:bg-surface-container",
                )}
              >
                {range.label}
              </button>
            ))}
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={refreshFromYouTube}
            disabled={!projectId || loading || syncing}
          >
            {syncing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Refresh stats
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-error/30 bg-error-container/40 px-4 py-3 text-sm text-error">
          {error}
        </div>
      ) : null}

      {!projects.length && !loading ? (
        <EmptyState
          title="Create a project first"
          body="Analytics are scoped to a project. Create one, then publish Shorts to load YouTube statistics."
          href="/projects"
          label="Go to projects"
        />
      ) : null}

      {summary?.sync_error && !loading ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          {summary.sync_error}
        </div>
      ) : null}

      {projects.length > 0 && !loading && summary && !summary.has_data ? (
        <EmptyState
          title="No performance data yet"
          body="Publish a Short to see live YouTube views, likes, and comments. If you deleted the video on YouTube, this page clears after a refresh — old reports are not kept."
          href="/content"
          label="Open content library"
        />
      ) : null}

      {(loading || (summary && summary.has_data)) && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => <MetricSkeleton key={i} />)
              : [
                  {
                    label: "Total views",
                    value: formatNumber(totals.views),
                    icon: Eye,
                  },
                  {
                    label: "Total likes",
                    value: formatNumber(totals.likes),
                    icon: Heart,
                  },
                  {
                    label: "Total comments",
                    value: formatNumber(totals.comments),
                    icon: MessageCircle,
                  },
                  {
                    label: "Avg engagement",
                    value: formatPercent(totals.average_engagement_rate),
                    icon: Percent,
                  },
                ].map((metric, index) => (
                  <motion.article
                    key={metric.label}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.04 * index, duration: 0.3 }}
                    className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 shadow-[0_2px_4px_rgba(23,43,77,0.05)]"
                  >
                    <div className="mb-3 flex items-center justify-between">
                      <p className="font-label text-[11px] uppercase tracking-[0.08em] text-on-surface-variant">
                        {metric.label}
                      </p>
                      <metric.icon className="h-4 w-4 text-primary" />
                    </div>
                    <p className="font-display text-3xl font-semibold text-on-surface">{metric.value}</p>
                  </motion.article>
                ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <motion.section
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 md:p-6"
            >
              <div className="mb-4 flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-primary" />
                <h2 className="font-display text-lg font-semibold text-on-surface">Views over time</h2>
              </div>
              {loading ? (
                <ChartSkeleton />
              ) : (
                <div className="h-[260px] w-full min-w-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="viewsFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#2170e4" stopOpacity={0.28} />
                          <stop offset="100%" stopColor="#2170e4" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#c2c6d6" opacity={0.45} />
                      <XAxis dataKey="label" tick={{ fill: "#424754", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#424754", fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
                      <Tooltip
                        contentStyle={{
                          borderRadius: 12,
                          border: "1px solid #c2c6d6",
                          background: "#ffffff",
                        }}
                        labelFormatter={(_, payload) => payload?.[0]?.payload?.date || ""}
                      />
                      <Area
                        type="monotone"
                        dataKey="views"
                        stroke="#0058be"
                        fill="url(#viewsFill)"
                        strokeWidth={2}
                        name="Views"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </motion.section>

            <motion.section
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05, duration: 0.35 }}
              className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 md:p-6"
            >
              <div className="mb-4 flex items-center gap-2">
                <Percent className="h-4 w-4 text-primary" />
                <h2 className="font-display text-lg font-semibold text-on-surface">Engagement over time</h2>
              </div>
              {loading ? (
                <ChartSkeleton />
              ) : (
                <div className="h-[260px] w-full min-w-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#c2c6d6" opacity={0.45} />
                      <XAxis dataKey="label" tick={{ fill: "#424754", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#424754", fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
                      <Tooltip
                        formatter={(value) => [`${Number(value).toFixed(2)}%`, "Engagement"]}
                        contentStyle={{
                          borderRadius: 12,
                          border: "1px solid #c2c6d6",
                          background: "#ffffff",
                        }}
                        labelFormatter={(_, payload) => payload?.[0]?.payload?.date || ""}
                      />
                      <Line
                        type="monotone"
                        dataKey="engagement_rate"
                        stroke="#2170e4"
                        strokeWidth={2}
                        dot={false}
                        name="Engagement"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </motion.section>
          </div>

          <section className="space-y-4">
            <div className="flex items-end justify-between gap-3">
              <div>
                <h2 className="font-display text-xl font-semibold text-on-surface">Top content</h2>
                <p className="text-sm text-on-surface-variant">Best performers in this range.</p>
              </div>
            </div>
            {loading ? (
              <div className="grid gap-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-20 animate-pulse rounded-xl bg-surface-container/60" />
                ))}
              </div>
            ) : (
              <div className="grid gap-3">
                {(summary?.top_content || []).map((item, index) => (
                  <motion.div
                    key={item.content_id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.04 * index }}
                  >
                    <Link
                      href={`/content/${item.content_id}`}
                      className="flex flex-col gap-3 rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-4 transition hover:border-primary/40 hover:bg-surface-container-low sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-display text-base font-semibold text-on-surface">
                          {item.title}
                        </p>
                        <p className="truncate text-sm text-on-surface-variant">
                          {item.trend_title || "Untitled trend"}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-4 text-sm text-on-surface-variant">
                        <span>{formatNumber(item.views)} views</span>
                        <span>{formatNumber(item.likes)} likes</span>
                        <span>{formatPercent(item.engagement_rate)} eng.</span>
                      </div>
                    </Link>
                  </motion.div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-outline-variant/80 bg-[linear-gradient(135deg,#f1f3ff_0%,#ffffff_55%,#e8edff_100%)] p-5 md:p-7">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-primary">
                  <Sparkles className="h-4 w-4" />
                  <p className="font-label text-xs uppercase tracking-[0.08em]">Your AI Coach</p>
                </div>
                <h2 className="font-display text-2xl font-semibold text-on-surface">
                  Actionable recommendations
                </h2>
                <p className="max-w-xl text-sm leading-6 text-on-surface-variant">
                  Analytics Agent finds patterns in your stored metrics. Coach turns them into
                  concrete next steps — never invented numbers.
                </p>
              </div>
              <Button onClick={runCoach} disabled={coachLoading || loading || !summary?.has_data}>
                {coachLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Analyzing…
                  </>
                ) : (
                  "Generate coach tips"
                )}
              </Button>
            </div>

            {coachError ? (
              <p className="mt-4 text-sm text-error">{coachError}</p>
            ) : null}

            {coach?.status === "insufficient_data" ? (
              <p className="mt-5 rounded-lg border border-outline-variant/70 bg-white/70 px-4 py-3 text-sm text-on-surface-variant">
                {coach.message}
              </p>
            ) : null}

            {coach?.status === "failed" ? (
              <p className="mt-5 text-sm text-error">{coach.message || "Coach analysis failed."}</p>
            ) : null}

            {coach?.status === "ready" ? (
              <div className="mt-6 space-y-4">
                {coach.summary ? (
                  <p className="text-sm leading-6 text-on-surface">{coach.summary}</p>
                ) : null}
                <div className="grid gap-3 md:grid-cols-3">
                  {coach.recommendations.map((rec, index) => (
                    <motion.article
                      key={`${rec.title}-${index}`}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.05 * index }}
                      className="rounded-xl border border-outline-variant/70 bg-white/80 p-4 shadow-[0_2px_4px_rgba(23,43,77,0.04)]"
                    >
                      <div className="mb-3 flex items-center justify-between gap-2">
                        <h3 className="font-display text-base font-semibold text-on-surface">{rec.title}</h3>
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 font-label text-[10px] uppercase tracking-[0.06em]",
                            PRIORITY_STYLES[rec.priority] || PRIORITY_STYLES.low,
                          )}
                        >
                          {rec.priority}
                        </span>
                      </div>
                      <p className="text-sm leading-6 text-on-surface-variant">{rec.reason}</p>
                      <p className="mt-3 text-sm font-medium text-on-surface">
                        Action: <span className="font-normal text-on-surface-variant">{rec.action}</span>
                      </p>
                    </motion.article>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        </>
      )}
    </div>
  );
}

function EmptyState({ title, body, href, label }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-dashed border-outline-variant bg-surface-container-low/60 px-6 py-12 text-center"
    >
      <BarChart3 className="mx-auto mb-4 h-8 w-8 text-primary" />
      <h2 className="font-display text-xl font-semibold text-on-surface">{title}</h2>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-on-surface-variant">{body}</p>
      <Button asChild className="mt-6">
        <Link href={href}>{label}</Link>
      </Button>
    </motion.section>
  );
}

export default function AnalyticsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-6xl space-y-4">
          <div className="h-10 w-48 animate-pulse rounded bg-surface-container" />
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <MetricSkeleton key={i} />
            ))}
          </div>
        </div>
      }
    >
      <AnalyticsDashboard />
    </Suspense>
  );
}
