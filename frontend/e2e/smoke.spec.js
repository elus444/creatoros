const { test, expect } = require("@playwright/test");

/**
 * Smoke journey with API mocks — no live Gemini/YouTube required.
 */

function json(route, status, body) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

test("critical creatoros journey (mocked API)", async ({ page }) => {
  const user = {
    id: "11111111-1111-1111-1111-111111111111",
    email: "smoke@example.com",
    full_name: "Smoke Tester",
  };
  const project = {
    id: "22222222-2222-2222-2222-222222222222",
    name: "Smoke Project",
    niche: "ai tools",
    audience: "creators",
    brand_voice: "clear",
    created_at: new Date().toISOString(),
  };
  const trend = {
    id: "33333333-3333-3333-3333-333333333333",
    project_id: project.id,
    title: "Rising AI short",
    source: "youtube",
    url: "https://example.com/t",
    score: 91,
    metrics: {},
    is_selected: true,
    created_at: new Date().toISOString(),
  };
  const content = {
    id: "44444444-4444-4444-4444-444444444444",
    project_id: project.id,
    trend_id: trend.id,
    format: "short",
    generation_phase: "ready",
    research: {
      summary: "Research summary",
      facts: ["Fact"],
      audience_insights: ["Insight"],
      opportunities: ["Opp"],
    },
    strategy: {
      angle: "Angle",
      hooks: ["Hook"],
      target_audience: "creators",
      structure: ["hook", "body"],
    },
    video_plan: {
      concept: "Smoke concept",
      scenes: ["hook", "body"],
      visual_direction: "Clean vertical",
      narration: "Smoke narration body",
      titles: ["Smoke Title"],
      caption: "Smoke caption",
      hashtags: ["smoke"],
      aspect_ratio: "9:16",
      duration_seconds: 30,
    },
    script: "Smoke narration body",
    titles: ["Smoke Title"],
    captions: "Smoke caption",
    hashtags: ["smoke"],
    video_url: "https://cdn.example.com/smoke.mp4",
    thumbnail_url: "https://cdn.example.com/smoke.jpg",
    publish_status: "ready",
    youtube_video_id: null,
    status: "GENERATED",
    error: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    project_name: project.name,
    trend_title: trend.title,
  };

  let contentStatus = "GENERATED";

  await page.route(/localhost:8000\/api\/v1\//, async (route) => {
    const req = route.request();
    const url = req.url();
    const method = req.method();

    if (method === "OPTIONS") {
      return route.fulfill({
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "http://127.0.0.1:3000",
          "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
          "Access-Control-Allow-Headers": "Authorization, Content-Type",
          "Access-Control-Allow-Credentials": "true",
        },
      });
    }

    const headers = {
      "Access-Control-Allow-Origin": "http://127.0.0.1:3000",
      "Access-Control-Allow-Credentials": "true",
    };

    const fulfill = (status, body) =>
      route.fulfill({
        status,
        contentType: "application/json",
        headers,
        body: JSON.stringify(body),
      });

    if (url.includes("/auth/register") && method === "POST") {
      return fulfill(201, { access_token: "smoke-token", user, token_type: "bearer" });
    }
    if (url.includes("/auth/me")) {
      return fulfill(200, { ...user, access_token: "smoke-token", token_type: "bearer" });
    }
    if (url.includes("/auth/logout")) {
      return fulfill(200, { message: "ok" });
    }
    if (url.includes("/projects") && method === "GET" && !url.includes("/trends")) {
      return fulfill(200, url.endsWith(`/projects/${project.id}`) ? project : [project]);
    }
    if (url.includes("/projects") && method === "POST") {
      return fulfill(201, project);
    }
    if (url.includes("/trends/collect") && method === "POST") {
      return fulfill(200, {
        trends: [trend],
        collected: 1,
        sources_used: ["youtube"],
        warnings: [],
      });
    }
    if (url.includes("/trends") && method === "GET") {
      return fulfill(200, [trend]);
    }
    if (url.includes("/select") && method === "POST") {
      return fulfill(200, { ...trend, is_selected: true });
    }
    if (url.includes("/content/generate") && method === "POST") {
      contentStatus = "GENERATED";
      return fulfill(202, {
        success: true,
        job_id: "55555555-5555-5555-5555-555555555555",
        content_id: content.id,
        status: "queued",
        generation_phase: "queued",
      });
    }
    if (url.includes("/integrations/video")) {
      return fulfill(200, {
        provider: "replicate",
        supported_providers: [{ id: "replicate", label: "Replicate" }],
        model_id: null,
        has_key: false,
        configured: false,
        source: null,
      });
    }
    if (url.includes("/youtube/status")) {
      return fulfill(200, {
        connected: false,
        needs_reconnect: false,
        channel_id: null,
        channel_title: null,
        channel_thumbnail_url: null,
        oauth_configured: false,
        redirect_uri: "http://localhost:8000/api/v1/youtube/oauth/callback",
      });
    }
    if (/\/content\/[0-9a-f-]+$/i.test(url) && method === "GET") {
      return fulfill(200, { ...content, status: contentStatus });
    }
    if (url.includes("/content") && method === "GET") {
      return fulfill(200, [{ ...content, status: contentStatus }]);
    }
    if (url.includes("/review") && method === "POST") {
      contentStatus = "REVIEW";
      return fulfill(200, { ...content, status: contentStatus });
    }
    if (url.includes("/approve") && method === "POST") {
      contentStatus = "APPROVED";
      return fulfill(200, { ...content, status: contentStatus });
    }
    if (url.includes("/analytics/projects/") && url.includes("/sync") && method === "POST") {
      return fulfill(200, {
        synced: 0,
        published: 0,
        skipped: false,
        cleared: 0,
        message: "No published YouTube videos in this project yet.",
      });
    }
    if (url.includes("/analytics/projects/") && method === "GET") {
      return fulfill(200, {
        project_id: project.id,
        range_days: 30,
        totals: {
          views: 0,
          likes: 0,
          comments: 0,
          average_engagement_rate: 0,
          content_with_metrics: 0,
          daily_rows: 0,
        },
        series: [],
        top_content: [],
        has_data: false,
        published_count: 0,
        sync_error: null,
      });
    }
    if (url.includes("/automation/status")) {
      return fulfill(200, { automation_configured: false, recent_jobs: [] });
    }
    if (url.includes("/health")) {
      return fulfill(200, { status: "ok", service: "creatoros", database: "ok", redis: "ok" });
    }
    return fulfill(200, {});
  });

  await page.goto("/");
  await expect(page.getByText(/creatoros/i).first()).toBeVisible();

  await page.goto("/register");
  await page.locator("#full_name").fill("Smoke Tester");
  await page.locator("#email").fill("smoke@example.com");
  await page.locator("#password").fill("SecurePass123!");

  await Promise.all([
    page.waitForURL(/dashboard/, { timeout: 15_000 }),
    page.getByRole("button", { name: /create account/i }).click(),
  ]);

  await page.goto("/projects");
  await expect(page.getByText(/Projects|Smoke Project/i).first()).toBeVisible();

  await page.goto("/trends");
  await expect(page.getByText(/Rising AI|Trends|Collect/i).first()).toBeVisible({
    timeout: 15_000,
  });

  await page.goto(`/content/${content.id}`);
  await expect(page.getByText(/Smoke Title|Video preview|Research/i).first()).toBeVisible({
    timeout: 15_000,
  });

  const reviewBtn = page.getByRole("button", { name: /send to review/i });
  if (await reviewBtn.count()) {
    await reviewBtn.first().click();
  }
  const approveBtn = page.getByRole("button", { name: /^approve$/i });
  if (await approveBtn.count()) {
    await approveBtn.first().click();
  }

  await page.goto("/analytics");
  await expect(
    page.getByText(/Analytics|performance will appear|Create a project/i).first(),
  ).toBeVisible({ timeout: 15_000 });
});
