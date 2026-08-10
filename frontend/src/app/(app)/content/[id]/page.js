"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import { ApiError, contentApi } from "@/lib/api";

export default function ContentPackagePage() {
  const { token } = useAuth();
  const params = useParams();
  const contentId = params.id;
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token || !contentId) return;
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const data = await contentApi.get(contentId, token);
        if (active) setContent(data);
      } catch (err) {
        if (active) setError(err instanceof ApiError ? err.message : "Unable to load content.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [token, contentId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-on-surface-variant">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading content package…
      </div>
    );
  }

  if (!content) {
    return (
      <div className="space-y-4 text-center">
        <p className="text-sm text-error">{error || "Content not found."}</p>
        <Button asChild variant="outline"><Link href="/trends">Back to trends</Link></Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface">
          Content package
        </h1>
        <p className="text-sm text-on-surface-variant">Status: {content.status}</p>
      </div>
      {content.research ? (
        <section className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5">
          <h2 className="font-display text-lg font-semibold">Research</h2>
          <p className="mt-2 text-sm text-on-surface-variant">{content.research.summary}</p>
        </section>
      ) : null}
      {content.strategy ? (
        <section className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5">
          <h2 className="font-display text-lg font-semibold">Strategy</h2>
          <p className="mt-2 text-sm text-on-surface-variant">{content.strategy.angle}</p>
        </section>
      ) : null}
      {content.script ? (
        <section className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 space-y-3">
          <h2 className="font-display text-lg font-semibold">Script</h2>
          <p className="whitespace-pre-wrap text-sm leading-7 text-on-surface-variant">{content.script}</p>
          {content.titles?.length ? (
            <ul className="list-disc pl-5 text-sm text-on-surface-variant">
              {content.titles.map((title) => <li key={title}>{title}</li>)}
            </ul>
          ) : null}
          {content.captions ? <p className="text-sm text-on-surface-variant">{content.captions}</p> : null}
          {content.hashtags?.length ? (
            <p className="text-sm text-on-surface-variant">{content.hashtags.map((tag) => #).join(" ")}</p>
          ) : null}
        </section>
      ) : (
        <div className="rounded-xl border border-dashed p-8 text-center">
          <Sparkles className="mx-auto h-8 w-8 text-outline" />
          <p className="mt-3 text-sm text-on-surface-variant">No script generated yet.</p>
        </div>
      )}
    </div>
  );
}
