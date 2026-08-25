"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Check,
  Download,
  ExternalLink,
  Loader2,
  RefreshCw,
  Save,
  Sparkles,
  TriangleAlert,
  Upload,
  MonitorPlay,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/auth-context";
import { ApiError, contentApi, youtubeApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_STYLES = {
  GENERATED: "bg-blue-100 text-blue-800",
  REVIEW: "bg-amber-100 text-amber-900",
  APPROVED: "bg-emerald-100 text-emerald-800",
  EXPORTED: "bg-violet-100 text-violet-800",
  FAILED: "bg-error-container text-error",
  PENDING: "bg-surface-container text-on-surface-variant",
};

const PHASE_LABELS = {
  queued: "Queued",
  researching: "Researching",
  planning: "Planning",
  generating_video: "Generating video",
  processing: "Processing",
  ready: "Ready for review",
  failed: "Failed",
};

const SUGGEST_TARGETS = [
  { id: "script", label: "Narration" },
  { id: "titles", label: "Titles" },
  { id: "caption", label: "Caption" },
  { id: "hashtags", label: "Hashtags" },
];

function downloadMarkdown(filename, body) {
  const blob = new Blob([body], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function applyContentFields(data, setters) {
  setters.setContent(data);
  setters.setScript(data.script || "");
  setters.setTitlesText((data.titles || []).join("\n"));
  setters.setCaption(data.captions || "");
  setters.setHashtagsText((data.hashtags || []).join(" "));
}

export default function ContentWorkspacePage() {
  const { token } = useAuth();
  const params = useParams();
  const contentId = params.id;

  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [youtubeStatus, setYoutubeStatus] = useState(null);

  const [script, setScript] = useState("");
  const [titlesText, setTitlesText] = useState("");
  const [caption, setCaption] = useState("");
  const [hashtagsText, setHashtagsText] = useState("");

  const [suggestTarget, setSuggestTarget] = useState("titles");
  const [guidance, setGuidance] = useState("");
  const [suggestions, setSuggestions] = useState(null);

  const editable = content?.status === "GENERATED" || content?.status === "REVIEW";
  const canRegenerate = editable || content?.status === "FAILED";
  const generating =
    content?.status === "PENDING" ||
    (content?.generation_phase &&
      !["ready", "failed"].includes(content.generation_phase) &&
      content.status === "PENDING");
  const missingVideo =
    !content?.video_url &&
    !generating &&
    (content?.status === "FAILED" ||
      content?.status === "GENERATED" ||
      content?.status === "REVIEW");
  const publishedToYoutube = Boolean(
    content?.youtube_video_id && content?.publish_status === "published",
  );
  const canPublish =
    (content?.status === "APPROVED" || content?.status === "EXPORTED") &&
    Boolean(content?.video_url) &&
    !publishedToYoutube;
  const youtubeWatchUrl = content?.youtube_video_id
    ? `https://www.youtube.com/shorts/${content.youtube_video_id}`
    : null;

  const load = useCallback(async () => {
    if (!token || !contentId) return;
    setLoading(true);
    setError("");
    try {
      const data = await contentApi.get(contentId, token);
      applyContentFields(data, {
        setContent,
        setScript,
        setTitlesText,
        setCaption,
        setHashtagsText,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load workspace.");
      setContent(null);
    } finally {
      setLoading(false);
    }
  }, [token, contentId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!token || !contentId || !generating) return undefined;
    const timer = setInterval(async () => {
      try {
        const data = await contentApi.get(contentId, token);
        applyContentFields(data, {
          setContent,
          setScript,
          setTitlesText,
          setCaption,
          setHashtagsText,
        });
      } catch {
        /* keep polling; next tick may succeed */
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [token, contentId, generating]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    youtubeApi
      .status(token)
      .then((data) => {
        if (active) setYoutubeStatus(data);
      })
      .catch(() => {
        if (active) setYoutubeStatus(null);
      });
    return () => {
      active = false;
    };
  }, [token]);

  const dirty = useMemo(() => {
    if (!content) return false;
    const titles = titlesText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    const hashtags = hashtagsText
      .split(/[\s,]+/)
      .map((tag) => tag.replace(/^#/, "").trim())
      .filter(Boolean);
    return (
      script !== (content.script || "") ||
      caption !== (content.captions || "") ||
      JSON.stringify(titles) !== JSON.stringify(content.titles || []) ||
      JSON.stringify(hashtags) !== JSON.stringify(content.hashtags || [])
    );
  }, [content, script, titlesText, caption, hashtagsText]);

  async function runAction(key, fn, successMessage) {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      const result = await fn();
      if (result?.id && Object.hasOwn(result, "script")) {
        applyContentFields(result, {
          setContent,
          setScript,
          setTitlesText,
          setCaption,
          setHashtagsText,
        });
      }
      if (successMessage) setNotice(successMessage);
      return result;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed.");
      return null;
    } finally {
      setBusy("");
    }
  }

  async function handleSave() {
    const titles = titlesText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    const hashtags = hashtagsText
      .split(/[\s,]+/)
      .map((tag) => tag.replace(/^#/, "").trim())
      .filter(Boolean);
    await runAction(
      "save",
      () =>
        contentApi.update(
          contentId,
          { script, titles, captions: caption, hashtags },
          token,
        ),
      "Draft saved.",
    );
  }

  async function handleSuggest() {
    setBusy("suggest");
    setError("");
    setNotice("");
    try {
      const result = await contentApi.suggest(
        contentId,
        { target: suggestTarget, guidance: guidance || undefined },
        token,
      );
      setSuggestions(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to get suggestions.");
    } finally {
      setBusy("");
    }
  }

  function applySuggestion(value) {
    if (suggestTarget === "script") setScript(value);
    else if (suggestTarget === "caption") setCaption(value);
    else if (suggestTarget === "titles") setTitlesText(value);
    else if (suggestTarget === "hashtags") setHashtagsText(value.replace(/^#/, ""));
    setNotice("Suggestion applied — save to persist.");
  }

  async function handleExport() {
    const result = await runAction("export", () => contentApi.export(contentId, token));
    if (result?.body) {
      downloadMarkdown(result.filename, result.body);
      setNotice("Exported and downloaded.");
      await load();
    }
  }

  async function handlePublish() {
    if (!youtubeStatus?.connected) {
      setError("Connect YouTube in Settings before publishing.");
      return;
    }
    if (
      !window.confirm(
        "Publish this Short to your connected YouTube channel now? It will go live as a public Short.",
      )
    ) {
      return;
    }
    const result = await runAction(
      "publish",
      () => contentApi.publish(contentId, token),
      "Published to YouTube.",
    );
    if (result?.youtube_video_id) {
      setNotice(
        `Published to YouTube. Open the Short at youtube.com/shorts/${result.youtube_video_id}`,
      );
    }
  }

  async function handleConnectYouTube() {
    setBusy("youtube");
    setError("");
    try {
      const data = await youtubeApi.startOAuth(token);
      if (data?.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to start YouTube OAuth.");
      setBusy("");
    }
  }

  if (loading && !content) {
    return (
      <div className="flex items-center gap-2 text-sm text-on-surface-variant">
        <Loader2 className="h-4 w-4 animate-spin" />
        Opening workspace…
      </div>
    );
  }

  if (!content) {
    return (
      <div className="mx-auto max-w-lg space-y-4 text-center">
        <p className="text-sm text-error">{error || "Content not found."}</p>
        <Button asChild variant="outline">
          <Link href="/content">Back to library</Link>
        </Button>
      </div>
    );
  }

  const research = content.research || {};
  const strategy = content.strategy || {};
  const plan = content.video_plan || {};
  const phaseLabel =
    PHASE_LABELS[content.generation_phase] || content.generation_phase || content.status;

  return (
    <div className="-mx-4 -my-6 flex h-[calc(100vh-4rem)] flex-col md:-mx-6 md:-my-8">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-outline-variant/80 bg-surface-container-lowest/90 px-4 py-3 backdrop-blur md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <Button asChild variant="ghost" size="icon">
            <Link href="/content" aria-label="Back to library">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div className="min-w-0">
            <p className="truncate font-display text-lg font-semibold text-on-surface">
              {(content.titles && content.titles[0]) || content.trend_title || "Workspace"}
            </p>
            <p className="truncate text-xs text-on-surface-variant">
              {content.project_name} · {content.trend_title} · YouTube Short (9:16)
            </p>
          </div>
          <span
            className={cn(
              "rounded-full px-2.5 py-1 font-label text-[11px] font-semibold uppercase tracking-[0.06em]",
              STATUS_STYLES[content.status] || STATUS_STYLES.PENDING,
            )}
          >
            {generating ? phaseLabel : content.status}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!editable || busy === "save" || !dirty || generating}
            onClick={handleSave}
          >
            {busy === "save" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            Save
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={!canRegenerate || Boolean(busy) || generating}
            onClick={() =>
              runAction(
                "regenerate",
                () => contentApi.regenerate(contentId, token),
                "Video regenerated.",
              )
            }
          >
            {busy === "regenerate" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Regenerate
          </Button>
          {content.status === "GENERATED" ? (
            <Button
              size="sm"
              disabled={Boolean(busy) || !content.video_url}
              onClick={() =>
                runAction("review", () => contentApi.review(contentId, token), "Moved to review.")
              }
            >
              {busy === "review" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              Send to review
            </Button>
          ) : null}
          {content.status === "REVIEW" ? (
            <Button
              size="sm"
              disabled={Boolean(busy)}
              onClick={() =>
                runAction(
                  "approve",
                  () => contentApi.approve(contentId, token),
                  "Video approved.",
                )
              }
            >
              {busy === "approve" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              Approve
            </Button>
          ) : null}
          {content.status === "APPROVED" || content.status === "EXPORTED" ? (
            <>
              {publishedToYoutube && youtubeWatchUrl ? (
                <Button size="sm" variant="outline" asChild>
                  <a href={youtubeWatchUrl} target="_blank" rel="noreferrer">
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open on YouTube
                  </a>
                </Button>
              ) : (
                <Button
                  size="sm"
                  disabled={Boolean(busy) || !canPublish || !youtubeStatus?.connected}
                  onClick={handlePublish}
                >
                  {busy === "publish" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Upload className="h-3.5 w-3.5" />
                  )}
                  Publish to YouTube
                </Button>
              )}
              {content.status === "APPROVED" ? (
                <Button size="sm" variant="outline" disabled={Boolean(busy)} onClick={handleExport}>
                  {busy === "export" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Download className="h-3.5 w-3.5" />
                  )}
                  Export notes
                </Button>
              ) : null}
            </>
          ) : null}
        </div>
      </header>

      {(error || notice) && (
        <div className="shrink-0 px-4 pt-3 md:px-6">
          {error ? (
            <div className="flex items-start gap-2 rounded-lg border border-error/20 bg-error-container/60 px-4 py-2.5 text-sm text-error">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}
          {notice ? (
            <div className="rounded-lg border border-outline-variant/80 bg-surface-container-low px-4 py-2.5 text-sm text-on-surface-variant">
              {notice}
            </div>
          ) : null}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-0 overflow-hidden lg:grid-cols-[260px_minmax(0,1fr)_300px]">
        <motion.aside
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          className="min-h-0 overflow-y-auto border-b border-outline-variant/80 bg-surface-container-low/60 p-4 lg:border-b-0 lg:border-r"
        >
          <p className="font-label text-[11px] uppercase tracking-[0.08em] text-primary">
            Research
          </p>
          <h2 className="mt-2 font-display text-lg font-semibold text-on-surface">
            Context
          </h2>
          <p className="mt-3 text-sm leading-6 text-on-surface-variant">
            {research.summary || "Research appears when the Research Agent finishes."}
          </p>
          <Section title="Facts" items={research.facts} />
          <Section title="Audience insights" items={research.audience_insights} />
          <Section title="Opportunities" items={research.opportunities} />

          <div className="mt-6 border-t border-outline-variant/80 pt-4">
            <p className="font-label text-[11px] uppercase tracking-[0.08em] text-primary">
              Video plan
            </p>
            <p className="mt-2 text-sm font-medium text-on-surface">
              {strategy.angle || plan.concept || "Plan pending."}
            </p>
            <p className="mt-1 text-xs text-on-surface-variant">
              {strategy.target_audience}
            </p>
            <Section title="Hooks" items={strategy.hooks} />
            <Section title="Scenes" items={plan.scenes || strategy.structure} />
            {plan.visual_direction ? (
              <p className="mt-3 text-sm leading-6 text-on-surface-variant">
                {plan.visual_direction}
              </p>
            ) : null}
          </div>
        </motion.aside>

        <motion.section
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="min-h-0 overflow-y-auto bg-surface-container-lowest p-4 md:p-6"
        >
          <p className="font-label text-[11px] uppercase tracking-[0.08em] text-primary">
            Video preview
          </p>

          <div className="relative mx-auto mt-4 aspect-[9/16] max-h-[70vh] max-w-[360px] overflow-hidden rounded-xl border border-outline-variant/80 bg-on-surface/90">
            {content.video_url ? (
              <video
                key={content.video_url}
                controls
                preload="metadata"
                poster={content.thumbnail_url || undefined}
                className="h-full w-full object-cover"
                src={content.video_url}
              >
                Your browser does not support video playback.
              </video>
            ) : (
              <div className="flex h-full min-h-[220px] flex-col items-center justify-center gap-3 px-6 text-center text-surface-container-lowest">
                {generating ? (
                  <>
                    <Loader2 className="h-8 w-8 animate-spin opacity-80" />
                    <p className="font-display text-lg font-semibold">{phaseLabel}</p>
                    <p className="text-sm opacity-80">
                      Generation runs in the background — this page updates automatically.
                    </p>
                  </>
                ) : missingVideo ? (
                  <>
                    <TriangleAlert className="h-8 w-8 text-error" />
                    <p className="font-display text-lg font-semibold">
                      {content.status === "FAILED" ? "Generation failed" : "Video file is missing"}
                    </p>
                    <p className="text-sm opacity-80">
                      {content.error ||
                        "The provider finished, but the file was not saved. Click Regenerate."}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="font-display text-lg font-semibold">No video yet</p>
                    <p className="text-sm opacity-80">
                      A real video URL appears here once a configured video provider finishes.
                    </p>
                  </>
                )}
              </div>
            )}
          </div>

          <div className="mt-6 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="titles">Titles</Label>
              <textarea
                id="titles"
                rows={3}
                value={titlesText}
                onChange={(e) => setTitlesText(e.target.value)}
                disabled={!editable || generating}
                className="w-full rounded-lg border border-outline-variant/80 bg-surface px-3 py-2 text-sm text-on-surface outline-none ring-primary/30 focus:ring-2 disabled:opacity-60"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="script">Narration / dialogue notes</Label>
              <textarea
                id="script"
                rows={6}
                value={script}
                onChange={(e) => setScript(e.target.value)}
                disabled={!editable || generating}
                className="w-full rounded-lg border border-outline-variant/80 bg-surface px-3 py-2 text-sm leading-6 text-on-surface outline-none ring-primary/30 focus:ring-2 disabled:opacity-60"
              />
            </div>
          </div>
        </motion.section>

        <motion.aside
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
          className="min-h-0 overflow-y-auto border-t border-outline-variant/80 bg-surface-container-low/60 p-4 lg:border-l lg:border-t-0"
        >
          <p className="font-label text-[11px] uppercase tracking-[0.08em] text-primary">
            Publishing
          </p>
          <h2 className="mt-2 font-display text-lg font-semibold text-on-surface">
            YouTube
          </h2>
          <p className="mt-1 text-sm text-on-surface-variant">
            Approve the video, connect YouTube, then publish from this page. Tokens stay on the server.
          </p>

          <div className="mt-4 space-y-2 rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-3 text-sm">
            <p>
              Format:{" "}
              <span className="font-semibold text-on-surface">YouTube Short (9:16)</span>
            </p>
            <p>
              Publish status:{" "}
              <span className="font-semibold text-on-surface">
                {content.publish_status || "draft"}
              </span>
            </p>
            <p>
              YouTube ID:{" "}
              <span className="font-semibold text-on-surface">
                {content.youtube_video_id || "—"}
              </span>
            </p>
            <p>
              Channel:{" "}
              <span className="font-semibold text-on-surface">
                {youtubeStatus?.connected
                  ? youtubeStatus.channel_title || youtubeStatus.channel_id || "Connected"
                  : youtubeStatus?.oauth_configured
                    ? "Not connected"
                    : "OAuth not configured"}
              </span>
            </p>
          </div>

          {publishedToYoutube && youtubeWatchUrl ? (
            <Button className="mt-4 w-full" asChild>
              <a href={youtubeWatchUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="h-4 w-4" />
                Open Short on YouTube
              </a>
            </Button>
          ) : null}

          {canPublish && !youtubeStatus?.connected ? (
            <p className="mt-3 text-xs text-on-surface-variant">
              Connect YouTube first. Publishing uses the channel linked in Settings.
            </p>
          ) : null}

          {!youtubeStatus?.connected ? (
            <Button
              className="mt-4 w-full"
              variant="outline"
              disabled={busy === "youtube"}
              onClick={handleConnectYouTube}
            >
              {busy === "youtube" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <MonitorPlay className="h-4 w-4" />
              )}
              Connect YouTube
            </Button>
          ) : null}

          <div className="mt-8 border-t border-outline-variant/80 pt-4">
            <p className="font-label text-[11px] uppercase tracking-[0.08em] text-primary">
              AI suggestions
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {SUGGEST_TARGETS.map((target) => (
                <button
                  key={target.id}
                  type="button"
                  disabled={!editable || generating}
                  onClick={() => {
                    setSuggestTarget(target.id);
                    setSuggestions(null);
                  }}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                    suggestTarget === target.id
                      ? "border-primary bg-primary text-on-primary"
                      : "border-outline-variant bg-surface-container-lowest text-on-surface-variant",
                    (!editable || generating) && "opacity-50",
                  )}
                >
                  {target.label}
                </button>
              ))}
            </div>

            <div className="mt-4 space-y-2">
              <Label htmlFor="guidance">Guidance (optional)</Label>
              <Input
                id="guidance"
                value={guidance}
                onChange={(e) => setGuidance(e.target.value)}
                disabled={!editable || generating}
                placeholder="Sharper hook for the first 3 seconds"
              />
            </div>

            <Button
              className="mt-4 w-full"
              disabled={!editable || generating || busy === "suggest"}
              onClick={handleSuggest}
            >
              {busy === "suggest" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              {busy === "suggest" ? "Thinking…" : "Get suggestions"}
            </Button>

            {suggestions ? (
              <div className="mt-5 space-y-3">
                <p className="text-xs leading-5 text-on-surface-variant">
                  {suggestions.rationale}
                </p>
                {suggestions.suggestions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    disabled={!editable}
                    onClick={() => applySuggestion(item)}
                    className="w-full rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-3 text-left text-sm leading-6 text-on-surface transition-colors hover:border-primary/40 hover:bg-surface"
                  >
                    {item}
                  </button>
                ))}
              </div>
            ) : null}

            <div className="mt-6 space-y-2">
              <Label htmlFor="caption">Caption</Label>
              <textarea
                id="caption"
                rows={3}
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                disabled={!editable || generating}
                className="w-full rounded-lg border border-outline-variant/80 bg-surface px-3 py-2 text-sm text-on-surface outline-none ring-primary/30 focus:ring-2 disabled:opacity-60"
              />
              <Label htmlFor="hashtags">Hashtags</Label>
              <Input
                id="hashtags"
                value={hashtagsText}
                onChange={(e) => setHashtagsText(e.target.value)}
                disabled={!editable || generating}
                placeholder="easyrecipes onepanmeals"
              />
            </div>
          </div>
        </motion.aside>
      </div>
    </div>
  );
}

function Section({ title, items }) {
  if (!items?.length) return null;
  return (
    <div className="mt-4">
      <p className="text-xs font-semibold uppercase tracking-[0.04em] text-on-surface">
        {title}
      </p>
      <ul className="mt-1.5 list-disc space-y-1 pl-4 text-sm leading-5 text-on-surface-variant">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
