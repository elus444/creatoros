"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  Circle,
  FolderKanban,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Sparkles,
  TrendingUp,
  TriangleAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError, contentApi, projectsApi, trendsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const SOURCE_META = {
  youtube: { label: "YouTube", icon: Play, className: "bg-red-100 text-red-700" },
  google_trends: {
    label: "Google Trends",
    icon: Search,
    className: "bg-blue-100 text-blue-700",
  },
};

function sourceMeta(source) {
  return (
    SOURCE_META[source] || {
      label: source,
      icon: TrendingUp,
      className: "bg-surface-container text-on-surface-variant",
    }
  );
}

function timeAgo(dateString) {
  const seconds = Math.floor((Date.now() - new Date(dateString).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function TrendsContent() {
  const { token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectIdParam = searchParams.get("project");

  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [activeProjectId, setActiveProjectId] = useState(projectIdParam || "");

  const [trends, setTrends] = useState([]);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [trendsError, setTrendsError] = useState("");
  const [collecting, setCollecting] = useState(false);
  const [collectMessage, setCollectMessage] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [selectingId, setSelectingId] = useState(null);
  const [generatingId, setGeneratingId] = useState(null);

  useEffect(() => {
    if (!token) return;
    let active = true;

    async function loadProjects() {
      setProjectsLoading(true);
      try {
        const data = await projectsApi.list(token);
        if (!active) return;
        setProjects(data);
        setActiveProjectId((current) => {
          if (current && data.some((project) => project.id === current)) return current;
          return data[0]?.id || "";
        });
      } catch {
        if (active) setProjects([]);
      } finally {
        if (active) setProjectsLoading(false);
      }
    }

    loadProjects();
    return () => {
      active = false;
    };
  }, [token]);

  const loadTrends = useCallback(
    async (projectId) => {
      if (!projectId || !token) return;
      setTrendsLoading(true);
      setTrendsError("");
      try {
        const data = await trendsApi.list(projectId, token);
        setTrends(data);
      } catch (err) {
        setTrendsError(err instanceof ApiError ? err.message : "Unable to load trends.");
      } finally {
        setTrendsLoading(false);
      }
    },
    [token],
  );

  useEffect(() => {
    if (activeProjectId) {
      // Deferred: react-hooks/set-state-in-effect flags setCollectMessage
      // (and loadTrends()'s internal setState) as direct setState in effect.
      queueMicrotask(() => {
        setCollectMessage(null);
        loadTrends(activeProjectId);
      });
    }
  }, [activeProjectId, loadTrends]);

  function handleSelectProject(projectId) {
    setActiveProjectId(projectId);
    router.replace(`/trends?project=${projectId}`);
  }

  async function handleCollect() {
    if (!activeProjectId) return;
    setCollecting(true);
    setCollectMessage(null);
    setTrendsError("");
    try {
      const result = await trendsApi.collect(activeProjectId, token);
      setTrends(result.trends);
      setCollectMessage({
        collected: result.collected,
        warnings: result.warnings,
        sources: result.sources_used,
      });
    } catch (err) {
      setTrendsError(err instanceof ApiError ? err.message : "Unable to collect trends.");
    } finally {
      setCollecting(false);
    }
  }

  async function handleSelect(trendId) {
    if (!activeProjectId) return;
    setSelectingId(trendId);
    try {
      const updated = await trendsApi.select(activeProjectId, trendId, token);
      setTrends((prev) =>
        prev.map((trend) => ({
          ...trend,
          is_selected: trend.id === updated.id ? updated.is_selected : false,
        })),
      );
    } catch (err) {
      setTrendsError(err instanceof ApiError ? err.message : "Unable to select trend.");
    } finally {
      setSelectingId(null);
    }
  }

  async function handleGenerate(trendId) {
    setGeneratingId(trendId);
    setTrendsError("");
    try {
      const result = await contentApi.generate(trendId, token, {
        format: "short",
        asyncMode: true,
      });
      const contentId = result.content_id || result.id;
      if (!contentId) {
        throw new Error("Generation did not return a content id.");
      }
      router.push(`/content/${contentId}`);
    } catch (err) {
      const existingId = err instanceof ApiError ? err.details?.content_id : null;
      if (err instanceof ApiError && err.status === 409 && existingId) {
        router.push(`/content/${existingId}`);
        return;
      }
      setTrendsError(
        err instanceof ApiError ? err.message : "Unable to start video generation.",
      );
    } finally {
      setGeneratingId(null);
    }
  }

  const activeProject = useMemo(
    () => projects.find((project) => project.id === activeProjectId),
    [projects, activeProjectId],
  );

  if (!projectsLoading && projects.length === 0) {
    return (
      <div className="mx-auto max-w-3xl">
        <div className="rounded-xl border border-dashed border-outline-variant/80 bg-surface-container-lowest p-10 text-center">
          <FolderKanban className="mx-auto h-8 w-8 text-outline" />
          <p className="mt-3 font-display text-lg font-semibold text-on-surface">
            Create a project first
          </p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-on-surface-variant">
            Trends are collected per project so results stay relevant to a specific niche.
          </p>
          <Button asChild className="mt-5">
            <Link href="/projects">Go to projects</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface md:text-4xl">
            Trends
          </h1>
          <p className="max-w-xl text-sm leading-6 text-on-surface-variant md:text-base">
            English-language YouTube Shorts for your niche — kids-safe, ranked,
            then turned into vertical 9:16 videos.
          </p>
        </div>
        <Button onClick={handleCollect} disabled={collecting || !activeProjectId}>
          {collecting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {collecting ? "Collecting…" : "Collect trends"}
        </Button>
      </div>

      {projects.length > 1 ? (
        <div className="flex flex-wrap gap-2">
          {projects.map((project) => (
            <button
              key={project.id}
              type="button"
              onClick={() => handleSelectProject(project.id)}
              className={cn(
                "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
                project.id === activeProjectId
                  ? "border-primary bg-primary text-on-primary"
                  : "border-outline-variant bg-surface-container-lowest text-on-surface-variant hover:bg-surface-container-low",
              )}
            >
              {project.name}
            </button>
          ))}
        </div>
      ) : null}

      {activeProject?.niche ? (
        <p className="text-sm text-on-surface-variant">
          Searching for{" "}
          <span className="font-semibold text-on-surface">{activeProject.niche}</span>
        </p>
      ) : null}

      {collectMessage ? (
        <div className="space-y-2">
          <div className="rounded-lg border border-outline-variant/80 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface-variant">
            Collected{" "}
            <span className="font-semibold text-on-surface">{collectMessage.collected}</span>{" "}
            new trend{collectMessage.collected === 1 ? "" : "s"}
            {collectMessage.sources.length > 0
              ? ` from ${collectMessage.sources.join(", ")}`
              : ""}
            .
          </div>
          {collectMessage.warnings.map((warning) => (
            <div
              key={warning}
              className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800"
            >
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{warning}</span>
            </div>
          ))}
        </div>
      ) : null}

      {trendsError ? (
        <div
          role="alert"
          className="sticky top-2 z-20 rounded-lg border border-error/20 bg-error-container px-4 py-3 text-sm font-medium text-error shadow-sm"
        >
          {trendsError}
        </div>
      ) : null}

      {trendsLoading ? (
        <div className="flex items-center gap-2 text-sm text-on-surface-variant">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading trends…
        </div>
      ) : trends.length === 0 ? (
        <div className="rounded-xl border border-dashed border-outline-variant/80 bg-surface-container-lowest p-10 text-center">
          <TrendingUp className="mx-auto h-8 w-8 text-outline" />
          <p className="mt-3 font-display text-lg font-semibold text-on-surface">
            No trends yet
          </p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-on-surface-variant">
            Click &quot;Collect trends&quot; to pull real, ranked YouTube Shorts
            for your niche.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          <AnimatePresence initial={false}>
            {trends.map((trend) => {
              const meta = sourceMeta(trend.source);
              const SourceIcon = meta.icon;
              const expanded = expandedId === trend.id;
              return (
                <motion.li
                  key={trend.id}
                  layout
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className={cn(
                    "rounded-xl border bg-surface-container-lowest shadow-[0_2px_4px_rgba(23,43,77,0.05)] transition-colors",
                    trend.is_selected ? "border-primary" : "border-outline-variant/80",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => setExpandedId(expanded ? null : trend.id)}
                    className="flex w-full items-center gap-4 px-5 py-4 text-left"
                  >
                    <div
                      className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                        meta.className,
                      )}
                    >
                      <SourceIcon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-on-surface">{trend.title}</p>
                      <p className="mt-0.5 text-xs text-on-surface-variant">
                        {meta.label} · {timeAgo(trend.created_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="rounded-full bg-surface-container px-2.5 py-1 font-label text-xs font-semibold text-primary">
                        {trend.score.toFixed(0)}
                      </span>
                      <ChevronDown
                        className={cn(
                          "h-4 w-4 text-outline transition-transform",
                          expanded && "rotate-180",
                        )}
                      />
                    </div>
                  </button>

                  <AnimatePresence initial={false}>
                    {expanded ? (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-outline-variant/80 px-5 py-4">
                          <div className="flex flex-wrap gap-4 text-sm text-on-surface-variant">
                            {Object.entries(trend.metrics || {}).map(([key, value]) => (
                              <span key={key}>
                                <span className="font-semibold text-on-surface">
                                  {String(value)}
                                </span>{" "}
                                {key}
                              </span>
                            ))}
                          </div>
                          <div className="flex items-center gap-2">
                            <a
                              href={trend.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
                            >
                              View source
                              <ArrowUpRight className="h-3.5 w-3.5" />
                            </a>
                            <Button
                              size="sm"
                              variant={trend.is_selected ? "secondary" : "outline"}
                              onClick={() => handleSelect(trend.id)}
                              disabled={selectingId === trend.id || generatingId === trend.id}
                            >
                              {selectingId === trend.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : trend.is_selected ? (
                                <CheckCircle2 className="h-3.5 w-3.5" />
                              ) : (
                                <Circle className="h-3.5 w-3.5" />
                              )}
                              {trend.is_selected ? "Selected" : "Select"}
                            </Button>
                            {trend.is_selected ? (
                              <Button
                                size="sm"
                                onClick={() => handleGenerate(trend.id)}
                                disabled={generatingId === trend.id}
                              >
                                {generatingId === trend.id ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <Sparkles className="h-3.5 w-3.5" />
                                )}
                                {generatingId === trend.id ? "Starting…" : "Generate Short"}
                              </Button>
                            ) : null}
                          </div>
                        </div>
                      </motion.div>
                    ) : null}
                  </AnimatePresence>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      )}
    </div>
  );
}

export default function TrendsPage() {
  return (
    <Suspense
      fallback={<div className="text-sm text-on-surface-variant">Loading…</div>}
    >
      <TrendsContent />
    </Suspense>
  );
}
