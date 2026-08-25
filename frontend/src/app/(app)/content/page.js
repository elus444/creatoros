"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { FolderKanban, Loader2, Sparkles, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError, contentApi, projectsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_STYLES = {
  PENDING: "bg-surface-container text-on-surface-variant",
  GENERATED: "bg-blue-100 text-blue-800",
  REVIEW: "bg-amber-100 text-amber-900",
  APPROVED: "bg-emerald-100 text-emerald-800",
  EXPORTED: "bg-violet-100 text-violet-800",
  FAILED: "bg-error-container text-error",
};

function timeAgo(dateString) {
  const seconds = Math.floor((Date.now() - new Date(dateString).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function ContentLibrary() {
  const { token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectFilter = searchParams.get("project") || "";

  const [projects, setProjects] = useState([]);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    let active = true;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const [projectData, contentData] = await Promise.all([
          projectsApi.list(token),
          contentApi.list(token, projectFilter || undefined),
        ]);
        if (!active) return;
        setProjects(projectData);
        setItems(contentData);
      } catch (err) {
        if (active) {
          setError(err instanceof ApiError ? err.message : "Unable to load content library.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => {
      active = false;
    };
  }, [token, projectFilter]);

  const emptyCopy = useMemo(() => {
    if (projects.length === 0) {
      return {
        title: "Create a project first",
        body: "Content packages are generated from project trends.",
        href: "/projects",
        label: "Go to projects",
      };
    }
    return {
      title: "No videos yet",
      body: "Select an English trend and generate a 9:16 YouTube Short.",
      href: "/trends",
      label: "Go to trends",
    };
  }, [projects.length]);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface md:text-4xl">
            Videos
          </h1>
          <p className="max-w-xl text-sm leading-6 text-on-surface-variant md:text-base">
            Generated videos ready for review, approval, and YouTube publishing.
          </p>
        </div>
        <Button asChild>
          <Link href="/trends">
            <TrendingUp className="h-4 w-4" />
            Generate from trends
          </Link>
        </Button>
      </div>

      {projects.length > 1 ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => router.replace("/content")}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
              !projectFilter
                ? "border-primary bg-primary text-on-primary"
                : "border-outline-variant bg-surface-container-lowest text-on-surface-variant hover:bg-surface-container-low",
            )}
          >
            All projects
          </button>
          {projects.map((project) => (
            <button
              key={project.id}
              type="button"
              onClick={() => router.replace(`/content?project=${project.id}`)}
              className={cn(
                "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
                projectFilter === project.id
                  ? "border-primary bg-primary text-on-primary"
                  : "border-outline-variant bg-surface-container-lowest text-on-surface-variant hover:bg-surface-container-low",
              )}
            >
              {project.name}
            </button>
          ))}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-error/20 bg-error-container/60 px-4 py-3 text-sm text-error">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-on-surface-variant">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading library…
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-outline-variant/80 bg-surface-container-lowest p-10 text-center">
          {projects.length === 0 ? (
            <FolderKanban className="mx-auto h-8 w-8 text-outline" />
          ) : (
            <Sparkles className="mx-auto h-8 w-8 text-outline" />
          )}
          <p className="mt-3 font-display text-lg font-semibold text-on-surface">
            {emptyCopy.title}
          </p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-on-surface-variant">
            {emptyCopy.body}
          </p>
          <Button asChild className="mt-5">
            <Link href={emptyCopy.href}>{emptyCopy.label}</Link>
          </Button>
        </div>
      ) : (
        <ul className="space-y-3">
          <AnimatePresence initial={false}>
            {items.map((item) => (
              <motion.li
                key={item.id}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest shadow-[0_2px_4px_rgba(23,43,77,0.05)]"
              >
                <Link
                  href={`/content/${item.id}`}
                  className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center md:justify-between"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-on-surface">
                      {(item.titles && item.titles[0]) || item.trend_title || "Untitled"}
                    </p>
                    <p className="mt-0.5 text-xs text-on-surface-variant">
                      {item.project_name || "Project"} · Short ·{" "}
                      {timeAgo(item.created_at)}
                      {item.generation_phase && item.status === "PENDING"
                        ? ` · ${item.generation_phase}`
                        : ""}
                    </p>
                  </div>
                  <span
                    className={cn(
                      "inline-flex w-fit rounded-full px-2.5 py-1 font-label text-[11px] font-semibold uppercase tracking-[0.06em]",
                      STATUS_STYLES[item.status] || STATUS_STYLES.PENDING,
                    )}
                  >
                    {item.status}
                  </span>
                </Link>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </div>
  );
}

export default function ContentLibraryPage() {
  return (
    <Suspense fallback={<div className="text-sm text-on-surface-variant">Loading…</div>}>
      <ContentLibrary />
    </Suspense>
  );
}
