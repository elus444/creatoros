"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CheckCircle2,
  Copy,
  Loader2,
  Lock,
  PlugZap,
  Trash2,
  TriangleAlert,
  Unplug,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/auth-context";
import { ApiError, integrationsApi, youtubeApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const OAUTH_MESSAGES = {
  connected: {
    tone: "success",
    text: "YouTube channel connected. You can publish approved Shorts from the video workspace.",
  },
  cancelled: {
    tone: "warn",
    text: "YouTube connection was cancelled. No channel was linked.",
  },
  denied: {
    tone: "error",
    text: "YouTube access was denied. You can try connecting again.",
  },
  error: {
    tone: "error",
    text: "YouTube connection failed. Check backend Google OAuth env vars and try again.",
  },
};

function SettingsContent() {
  const { token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const oauthFlag = searchParams.get("youtube");
  const oauthReason = searchParams.get("reason");

  const [status, setStatus] = useState(null);
  const [video, setVideo] = useState(null);
  const [provider, setProvider] = useState("replicate");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [replaceKey, setReplaceKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [banner, setBanner] = useState(null);

  const loadAll = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [nextStatus, nextVideo] = await Promise.all([
        youtubeApi.status(token),
        integrationsApi.video(token),
      ]);
      setStatus(nextStatus);
      setVideo(nextVideo);
      setProvider(nextVideo.provider || "replicate");
      setModelId(nextVideo.model_id || "");
      setApiKey("");
      setReplaceKey(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load integrations.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    // Deferred: react-hooks/set-state-in-effect flags loadAll()'s internal
    // synchronous setLoading(true) call as happening directly in the effect.
    queueMicrotask(() => {
      loadAll();
    });
  }, [loadAll]);

  useEffect(() => {
    if (!oauthFlag) return;
    const preset = OAUTH_MESSAGES[oauthFlag] || OAUTH_MESSAGES.error;
    let text = preset.text;
    if (oauthFlag === "error" && oauthReason === "not_configured") {
      text =
        "YouTube OAuth is not configured on the server. Set YOUTUBE_OAUTH_CLIENT_ID and YOUTUBE_OAUTH_CLIENT_SECRET, then connect again.";
    }
    if (oauthFlag === "error" && oauthReason === "invalid_state") {
      text = "This connect attempt expired. Click Connect YouTube and try again.";
    }
    if (oauthFlag === "error" && oauthReason === "token_exchange") {
      text = "Google did not complete the token exchange. Check backend OAuth env vars.";
    }
    if (oauthFlag === "error" && oauthReason === "invalid_client") {
      text =
        "Google rejected the OAuth client. Check YOUTUBE_OAUTH_CLIENT_ID and YOUTUBE_OAUTH_CLIENT_SECRET on the backend.";
    }
    // Deferred: react-hooks/set-state-in-effect flags setBanner (and the
    // loadAll() call right after) as direct setState in the effect body.
    queueMicrotask(() => {
      setBanner({ tone: preset.tone, text });
      router.replace("/settings");
      loadAll();
    });
  }, [oauthFlag, oauthReason, router, loadAll]);

  async function handleSaveVideo(event) {
    event.preventDefault();
    setBusy("save-video");
    setError("");
    try {
      const payload = {
        provider,
        model_id: modelId.trim() || null,
      };
      const nextKey = apiKey.trim();
      if (nextKey) {
        payload.api_key = nextKey;
      }
      const saved = await integrationsApi.saveVideo(payload, token);
      setVideo(saved);
      setApiKey("");
      setReplaceKey(false);
      setBanner({
        tone: "success",
        text: "Video provider saved. The API key is stored encrypted on the server and is not shown again.",
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save video provider.");
    } finally {
      setBusy("");
    }
  }

  async function handleClearVideo() {
    if (!window.confirm("Remove the saved video provider API key from this account?")) {
      return;
    }
    setBusy("clear-video");
    setError("");
    try {
      await integrationsApi.clearVideo(token);
      await loadAll();
      setBanner({
        tone: "success",
        text: "Saved video provider removed. Generation will use backend env credentials if they are set.",
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to remove video provider.");
    } finally {
      setBusy("");
    }
  }

  async function handleTestVideo() {
    setBusy("test-video");
    setError("");
    try {
      const payload = { provider };
      const nextKey = apiKey.trim();
      if (nextKey) {
        payload.api_key = nextKey;
      }
      const result = await integrationsApi.testVideo(payload, token);
      setBanner({
        tone: "success",
        text: result.account
          ? `Replicate connection succeeded (${result.account}).`
          : result.message || "Replicate connection succeeded.",
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to test Replicate.");
    } finally {
      setBusy("");
    }
  }

  async function handleCopyRedirect() {
    const redirectUri =
      status?.redirect_uri || "http://localhost:8000/api/v1/youtube/oauth/callback";
    try {
      await navigator.clipboard.writeText(redirectUri);
      setBanner({
        tone: "success",
        text: "Redirect URI copied. Use it in the Google Cloud OAuth client that backs the backend env vars.",
      });
    } catch {
      setError("Could not copy. Select the redirect URI and copy it manually.");
    }
  }

  async function handleConnect() {
    setBusy("connect");
    setError("");
    try {
      const data = await youtubeApi.startOAuth(token);
      if (!data?.authorization_url) {
        throw new Error("Missing Google authorization URL.");
      }
      window.location.assign(data.authorization_url);
    } catch (err) {
      setBusy("");
      setError(
        err instanceof ApiError
          ? err.message
          : "Unable to start YouTube connection.",
      );
    }
  }

  async function handleDisconnect() {
    if (!window.confirm("Disconnect this YouTube channel from Creator OS?")) {
      return;
    }
    setBusy("disconnect");
    setError("");
    try {
      await youtubeApi.disconnect(token);
      setBanner({
        tone: "success",
        text: "YouTube channel disconnected.",
      });
      await loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to disconnect YouTube.");
    } finally {
      setBusy("");
    }
  }

  const connected = Boolean(status?.connected);
  const needsReconnect = Boolean(status?.needs_reconnect);
  const youtubeConfigured = Boolean(status?.oauth_configured);
  const videoHasKey = Boolean(video?.has_key);
  const redirectUri =
    status?.redirect_uri || "http://localhost:8000/api/v1/youtube/oauth/callback";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface md:text-4xl">
          Settings
        </h1>
        <p className="max-w-xl text-sm leading-6 text-on-surface-variant md:text-base">
          Integrations. Provider keys and YouTube tokens stay encrypted on the
          server. They are never shown in this browser after you save.
        </p>
      </div>

      {banner ? (
        <div
          role="status"
          className={cn(
            "rounded-lg border px-4 py-3 text-sm",
            banner.tone === "success" &&
              "border-emerald-200 bg-emerald-50 text-emerald-900",
            banner.tone === "warn" &&
              "border-amber-200 bg-amber-50 text-amber-950",
            banner.tone === "error" &&
              "border-error/20 bg-error-container text-error",
          )}
        >
          {banner.text}
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="rounded-lg border border-error/20 bg-error-container px-4 py-3 text-sm text-error"
        >
          {error}
        </div>
      ) : null}

      <section className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-6 shadow-sm">
        <div>
          <p className="font-label text-[11px] uppercase tracking-[0.08em] text-primary">
            Integrations
          </p>
          <h2 className="mt-1 font-display text-xl font-semibold text-on-surface">
            Video provider
          </h2>
          <p className="mt-1 max-w-md text-sm text-on-surface-variant">
            Choose Replicate, set a model ID, and save an API key. Generation
            uses this provider without changing the rest of the app.
          </p>
        </div>

        {loading ? (
          <div className="mt-6 flex items-center gap-2 text-sm text-on-surface-variant">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading integrations…
          </div>
        ) : (
          <form className="mt-6 space-y-4" autoComplete="off" onSubmit={handleSaveVideo}>
            <div>
              <Label htmlFor="video-provider">Provider</Label>
              <select
                id="video-provider"
                className="mt-1.5 h-11 w-full rounded-lg border border-outline-variant bg-surface-container-lowest px-3 text-sm text-on-surface"
                value={provider}
                onChange={(event) => setProvider(event.target.value)}
              >
                {(video?.supported_providers || [{ id: "replicate", label: "Replicate" }]).map(
                  (option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ),
                )}
              </select>
            </div>
            <div>
              <Label htmlFor="video-model">Model ID</Label>
              <Input
                id="video-model"
                className="mt-1.5"
                value={modelId}
                onChange={(event) => setModelId(event.target.value)}
                placeholder="minimax/video-01"
                autoComplete="off"
              />
              <p className="mt-1.5 text-xs text-on-surface-variant">
                Replicate model name, such as minimax/video-01, or a version hash.
              </p>
            </div>
            <div>
              <Label htmlFor="video-api-key">Provider API key</Label>
              {videoHasKey && !replaceKey ? (
                <div className="mt-1.5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <p className="flex items-center gap-2 text-sm text-on-surface-variant">
                    <Lock className="h-4 w-4 text-outline" />
                    Key is saved on the server
                    {video?.source === "env" ? " from backend environment" : ""} and is
                    not shown again.
                  </p>
                  {video?.source === "settings" ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setReplaceKey(true)}
                    >
                      Replace key
                    </Button>
                  ) : (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setReplaceKey(true)}
                    >
                      Save a key for this account
                    </Button>
                  )}
                </div>
              ) : (
                <>
                  <Input
                    id="video-api-key"
                    className="mt-1.5"
                    type="password"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    placeholder="r8_…"
                    autoComplete="off"
                    data-1p-ignore="true"
                    data-lpignore="true"
                    required={!videoHasKey}
                  />
                  {videoHasKey ? (
                    <button
                      type="button"
                      className="mt-1.5 text-xs text-on-surface-variant underline-offset-2 hover:underline"
                      onClick={() => {
                        setReplaceKey(false);
                        setApiKey("");
                      }}
                    >
                      Keep the saved key
                    </button>
                  ) : null}
                </>
              )}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Button type="submit" disabled={Boolean(busy)}>
                {busy === "save-video" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Save provider
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleTestVideo}
                disabled={Boolean(busy)}
              >
                {busy === "test-video" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Test connection
              </Button>
              {video?.source === "settings" ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleClearVideo}
                  disabled={Boolean(busy)}
                >
                  {busy === "clear-video" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  Remove saved key
                </Button>
              ) : null}
            </div>
          </form>
        )}
      </section>

      <section className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-6 shadow-sm">
        <div>
          <p className="font-label text-[11px] uppercase tracking-[0.08em] text-primary">
            Integrations
          </p>
          <h2 className="mt-1 font-display text-xl font-semibold text-on-surface">
            YouTube
          </h2>
          <p className="mt-1 max-w-md text-sm text-on-surface-variant">
            Connect the channel that will receive Shorts. Google client ID and
            secret stay in backend environment variables. Tokens are encrypted
            on the server.
          </p>
        </div>

        {loading ? (
          <div className="mt-6 flex items-center gap-2 text-sm text-on-surface-variant">
            <Loader2 className="h-4 w-4 animate-spin" />
            Checking connection…
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            <div>
              <Label htmlFor="youtube-redirect">Authorized redirect URI</Label>
              <div className="mt-1.5 flex gap-2">
                <Input id="youtube-redirect" readOnly value={redirectUri} />
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleCopyRedirect}
                  aria-label="Copy redirect URI"
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <p className="mt-1.5 text-xs text-on-surface-variant">
                Paste this into the Google Cloud OAuth client used by the backend.
              </p>
            </div>

            <div className="rounded-lg border border-outline-variant/70 bg-surface-container-low/60 p-4">
              {connected || needsReconnect ? (
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3">
                    {status?.channel_thumbnail_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={status.channel_thumbnail_url}
                        alt=""
                        className="h-12 w-12 rounded-full object-cover"
                      />
                    ) : (
                      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-700">
                        <PlugZap className="h-5 w-5" />
                      </span>
                    )}
                    <div>
                      <p className="flex items-center gap-2 text-sm font-semibold text-on-surface">
                        {status?.channel_title || "YouTube channel"}
                        {!needsReconnect ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                            <CheckCircle2 className="h-3 w-3" />
                            Connected
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                            <TriangleAlert className="h-3 w-3" />
                            Reconnect needed
                          </span>
                        )}
                      </p>
                      {status?.channel_id ? (
                        <p className="mt-0.5 font-label text-xs text-outline">
                          {status.channel_id}
                        </p>
                      ) : null}
                      {needsReconnect ? (
                        <p className="mt-1 text-xs text-on-surface-variant">
                          The saved Google token expired. Connect again to refresh
                          access. No tokens are shown here.
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {needsReconnect ? (
                      <Button onClick={handleConnect} disabled={busy === "connect"}>
                        {busy === "connect" ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <PlugZap className="h-4 w-4" />
                        )}
                        Reconnect
                      </Button>
                    ) : null}
                    <Button
                      variant="outline"
                      onClick={handleDisconnect}
                      disabled={busy === "disconnect"}
                    >
                      {busy === "disconnect" ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Unplug className="h-4 w-4" />
                      )}
                      Disconnect
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-on-surface">Not connected</p>
                    <p className="mt-1 text-sm text-on-surface-variant">
                      {youtubeConfigured
                        ? "Authorize your channel with Google. Creator OS only requests permission to upload videos and read the channel name."
                        : "Set YOUTUBE_OAUTH_CLIENT_ID and YOUTUBE_OAUTH_CLIENT_SECRET on the backend, then connect."}
                    </p>
                  </div>
                  <Button
                    onClick={handleConnect}
                    disabled={busy === "connect" || !youtubeConfigured}
                  >
                    {busy === "connect" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <PlugZap className="h-4 w-4" />
                    )}
                    Connect YouTube
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 text-sm text-on-surface-variant">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading settings…
        </div>
      }
    >
      <SettingsContent />
    </Suspense>
  );
}
