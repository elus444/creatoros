"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Eye,
  Loader2,
  Percent,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError, analyticsApi, projectsApi } from "@/lib/api";

const DashboardChart = dynamic(() => import("@/components/dashboard/performance-chart"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[220px] items-center justify-center text-sm text-on-surface-variant">
      Loading chart…
    </div>
  ),
});

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US", {
    notation: value >= 10000 ? "compact" : "standard",
  }).format(value || 0);
}

export default function DashboardPage() {
  const { user, token } = useAuth();
  const firstName = user?.full_name?.split(" ")[0] || user?.email?.split("@")[0] || "Creator";

  const [project, setProject] = useState(null);
  const [summary, setSummary] = useState(null);
  const [coach, setCoach] = useState(null);
  const [loading, setLoading] = useState(true);
  const [coachLoading, setCoachLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const projects = await projectsApi.list(token);
        if (!active) return;
        const first = projects[0] || null;
        setProject(first);
        if (!first) {
          setSummary(null);
          return;
        }
        const data = await analyticsApi.projectSummary(first.id, token, 30);
        if (!active) return;
        setSummary(data);
      } catch (err) {
        if (active) {
          setError(err instanceof ApiError ? err.message : "Unable to load dashboard analytics.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [token]);

  const chartData = useMemo(
    () =>
      (summary?.series || []).map((point) => ({
        ...point,
        label: point.date.slice(5),
      })),
    [summary],
  );

  async function loadCoach() {
    if (!token || !project) return;
    setCoachLoading(true);
    try {
      const data = await analyticsApi.coach(project.id, token, 30);
      setCoach(data);
    } catch (err) {
      setCoach({
        status: "failed",
        message: err instanceof ApiError ? err.message : "Coach unavailable.",
        recommendations: [],
      });
    } finally {
      setCoachLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface md:text-4xl">
            {getGreeting()}, {firstName}
          </h1>
          <p className="max-w-xl text-sm leading-6 text-on-surface-variant md:text-base">
            Video performance, publishing momentum, and AI Coach guidance.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/analytics">
            Open analytics
            <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      </div>

      {error ? (
        <div className="rounded-xl border border-error/30 bg-error-container/40 px-4 py-3 text-sm text-error">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-on-surface-variant">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading performance…
        </div>
      ) : null}

      {!loading && !project ? (
        <section className="rounded-xl border border-dashed border-outline-variant bg-surface-container-low/50 p-8 text-center">
          <h2 className="font-display text-xl font-semibold text-on-surface">Start with a project</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-on-surface-variant">
            Create a project, collect English trends, generate videos, then measure performance here.
          </p>
          <Button asChild className="mt-5">
            <Link href="/projects">Create project</Link>
          </Button>
        </section>
      ) : null}

      {!loading && project && summary && !summary.has_data ? (
        <section className="rounded-xl border border-outline-variant/80 bg-[linear-gradient(135deg,#f1f3ff_0%,#ffffff_55%,#e8edff_100%)] p-6 md:p-8">
          <p className="font-label text-xs uppercase tracking-[0.08em] text-primary">Measure → Improve</p>
          <h2 className="mt-2 font-display text-2xl font-semibold text-on-surface">
            No performance data yet for {project.name}
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-on-surface-variant">
            Publish Shorts from the video workspace. Analytics then pulls live YouTube
            views, likes, and comments — it does not invent numbers.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button asChild>
              <Link href="/content">Video library</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/analytics">Analytics</Link>
            </Button>
          </div>
        </section>
      ) : null}

      {!loading && summary?.has_data ? (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              {
                title: "Total views",
                value: formatNumber(summary.totals.views),
                body: `Last 30 days · ${project?.name || "Project"}`,
                icon: Eye,
              },
              {
                title: "Engagement",
                value: `${Number(summary.totals.average_engagement_rate).toFixed(2)}%`,
                body: "Average across daily snapshots",
                icon: Percent,
              },
              {
                title: "Top video",
                value: summary.top_content?.[0]?.title || "—",
                body: summary.top_content?.[0]
                  ? `${formatNumber(summary.top_content[0].views)} views`
                  : "No ranked videos yet",
                icon: TrendingUp,
              },
            ].map((card, index) => (
              <motion.article
                key={card.title}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 * index, duration: 0.35 }}
                className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 shadow-[0_2px_4px_rgba(23,43,77,0.05)]"
              >
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h2 className="font-display text-lg font-semibold text-on-surface">{card.title}</h2>
                  <card.icon className="h-4 w-4 text-primary" />
                </div>
                <p className="truncate font-display text-2xl font-semibold text-on-surface">{card.value}</p>
                <p className="mt-2 text-sm leading-6 text-on-surface-variant">{card.body}</p>
              </motion.article>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
            <section className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 md:p-6">
              <h2 className="font-display text-lg font-semibold text-on-surface">Performance trend</h2>
              <p className="mt-1 text-sm text-on-surface-variant">Views over the last 30 days</p>
              <div className="mt-4 h-[220px] w-full min-w-0">
                <DashboardChart data={chartData} />
              </div>
            </section>

            <section className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 md:p-6">
              <div className="flex items-center gap-2 text-primary">
                <Sparkles className="h-4 w-4" />
                <h2 className="font-display text-lg font-semibold text-on-surface">AI Coach</h2>
              </div>
              <p className="mt-2 text-sm text-on-surface-variant">
                Get 3+ grounded recommendations from your stored metrics.
              </p>
              <Button className="mt-4" onClick={loadCoach} disabled={coachLoading}>
                {coachLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Coaching…
                  </>
                ) : (
                  "Get recommendations"
                )}
              </Button>

              {coach?.status === "insufficient_data" ? (
                <p className="mt-4 text-sm text-on-surface-variant">{coach.message}</p>
              ) : null}
              {coach?.status === "failed" ? (
                <p className="mt-4 text-sm text-error">{coach.message}</p>
              ) : null}
              {coach?.status === "ready" ? (
                <ul className="mt-4 space-y-3">
                  {coach.recommendations.slice(0, 3).map((rec) => (
                    <li key={rec.title} className="rounded-lg bg-surface-container-low px-3 py-2">
                      <p className="text-sm font-medium text-on-surface">{rec.title}</p>
                      <p className="text-xs leading-5 text-on-surface-variant">{rec.action}</p>
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}
