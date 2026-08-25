"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Workflow } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError, automationApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_STYLES = {
  queued: "bg-surface-container text-on-surface-variant",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-error-container text-error",
};

function timeAgo(dateString) {
  if (!dateString) return "—";
  const seconds = Math.floor((Date.now() - new Date(dateString).getTime()) / 1000);
  if (Number.isNaN(seconds)) return "—";
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function AutomationPage() {
  const { token } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    let active = true;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const snapshot = await automationApi.status(token);
        if (active) setData(snapshot);
      } catch (err) {
        if (active) {
          setError(err instanceof ApiError ? err.message : "Unable to load automation status.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    const timer = setInterval(load, 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [token]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface md:text-4xl">
          Automation
        </h1>
        <p className="max-w-2xl text-sm leading-6 text-on-surface-variant md:text-base">
          n8n triggers creatoros over secured HTTP. FastAPI still owns collectors, scoring,
          and AI agents — see{" "}
          <code className="rounded bg-surface-container px-1.5 py-0.5 text-xs">
            docs/n8n-integration.md
          </code>
          .
        </p>
      </div>

      {loading && !data ? (
        <div className="flex items-center gap-2 text-sm text-on-surface-variant">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading automation status…
        </div>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-error/20 bg-error-container/60 px-4 py-3 text-sm text-error">
          {error}
        </div>
      ) : null}

      {data ? (
        <>
          <div className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 shadow-[0_2px_4px_rgba(23,43,77,0.05)]">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-container text-primary">
                <Workflow className="h-5 w-5" />
              </div>
              <div>
                <p className="font-display text-lg font-semibold text-on-surface">
                  Webhook bridge
                </p>
                <p className="mt-1 text-sm text-on-surface-variant">
                  {data.automation_configured
                    ? "N8N_WEBHOOK_SECRET is configured. n8n can call automation endpoints."
                    : "Set N8N_WEBHOOK_SECRET in .env and restart the backend to enable n8n."}
                </p>
              </div>
            </div>
          </div>

          <section className="space-y-3">
            <h2 className="font-display text-xl font-semibold text-on-surface">
              Recent jobs
            </h2>
            {data.recent_jobs?.length ? (
              <ul className="space-y-2">
                {data.recent_jobs.map((job) => (
                  <li
                    key={job.job_id}
                    className="flex flex-col gap-2 rounded-xl border border-outline-variant/80 bg-surface-container-lowest px-4 py-3 md:flex-row md:items-center md:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-on-surface">
                        {job.kind}
                      </p>
                      <p className="mt-0.5 text-xs text-on-surface-variant">
                        {job.job_id.slice(0, 8)}… · {timeAgo(job.updated_at || job.created_at)}
                        {job.content_id ? ` · content ${job.content_id.slice(0, 8)}…` : ""}
                      </p>
                      {job.error ? (
                        <p className="mt-1 text-xs text-error">{job.error}</p>
                      ) : null}
                    </div>
                    <span
                      className={cn(
                        "inline-flex w-fit rounded-full px-2.5 py-1 font-label text-[11px] font-semibold uppercase tracking-[0.06em]",
                        STATUS_STYLES[job.status] || STATUS_STYLES.queued,
                      )}
                    >
                      {job.status}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-xl border border-dashed border-outline-variant/80 p-8 text-center">
                <p className="text-sm text-on-surface-variant">
                  No automation jobs yet. Trigger a collect/generate call from n8n.
                </p>
                <Button asChild variant="outline" className="mt-4">
                  <Link href="/trends">Collect trends manually</Link>
                </Button>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
