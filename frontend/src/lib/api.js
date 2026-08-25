const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(message, status, details = null, code = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
    this.code = code;
  }
}

async function parseError(response) {
  let detail = "Unable to complete that request. Please try again.";
  let details = null;
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") {
      detail = data.detail;
    } else if (data?.detail && typeof data.detail === "object" && data.detail.message) {
      detail = data.detail.message;
      details = data.detail;
    } else if (Array.isArray(data?.detail)) {
      detail = data.detail.map((item) => item.msg || JSON.stringify(item)).join(", ");
      details = data.detail;
    }
  } catch {
    detail = response.statusText || detail;
  }
  return new ApiError(detail, response.status, details);
}

export async function apiRequest(path, { method = "GET", body, token } = {}) {
  const headers = {
    Accept: "application/json",
  };

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  if (!response.ok) {
    // Login/register return 401 for bad credentials — keep the API detail.
    // Only app-auth endpoints mean the JWT itself is gone. YouTube and other
    // 401/403s must keep their own messages (reconnect channel, etc.).
    const isAppSessionCheck =
      path === "/auth/me" ||
      path.startsWith("/auth/me/") ||
      path.startsWith("/auth/logout");
    if (response.status === 401 && isAppSessionCheck) {
      throw new ApiError(
        "Your session has expired. Please log in again.",
        401,
        null,
        "session_expired",
      );
    }
    if (response.status === 429) {
      throw new ApiError("Too many requests. Please wait a moment and try again.", 429);
    }
    throw await parseError(response);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export const authApi = {
  register: (payload) =>
    apiRequest("/auth/register", { method: "POST", body: payload }),
  login: (payload) => apiRequest("/auth/login", { method: "POST", body: payload }),
  logout: (token) => apiRequest("/auth/logout", { method: "POST", token }),
  me: (token) => apiRequest("/auth/me", { token }),
};

export const projectsApi = {
  list: (token) => apiRequest("/projects", { token }),
  create: (payload, token) =>
    apiRequest("/projects", { method: "POST", body: payload, token }),
  get: (projectId, token) => apiRequest(`/projects/${projectId}`, { token }),
};

export const trendsApi = {
  list: (projectId, token) =>
    apiRequest(`/projects/${projectId}/trends`, { token }),
  collect: (projectId, token, query) =>
    apiRequest(`/projects/${projectId}/trends/collect`, {
      method: "POST",
      body: query ? { query } : {},
      token,
    }),
  select: (projectId, trendId, token) =>
    apiRequest(`/projects/${projectId}/trends/${trendId}/select`, {
      method: "POST",
      token,
    }),
};

export const contentApi = {
  list: (token, projectId) =>
    apiRequest(projectId ? `/content?project_id=${projectId}` : "/content", { token }),
  generate: (trendId, token, { asyncMode = true } = {}) =>
    apiRequest("/content/generate", {
      method: "POST",
      body: { trend_id: trendId, format: "short", async_mode: asyncMode },
      token,
    }),
  job: (jobId, token) => apiRequest(`/content/jobs/${jobId}`, { token }),
  get: (contentId, token) => apiRequest(`/content/${contentId}`, { token }),
  update: (contentId, payload, token) =>
    apiRequest(`/content/${contentId}`, {
      method: "PATCH",
      body: payload,
      token,
    }),
  review: (contentId, token) =>
    apiRequest(`/content/${contentId}/review`, { method: "POST", token }),
  approve: (contentId, token) =>
    apiRequest(`/content/${contentId}/approve`, { method: "POST", token }),
  export: (contentId, token) =>
    apiRequest(`/content/${contentId}/export`, { method: "POST", token }),
  publish: (contentId, token) =>
    apiRequest(`/content/${contentId}/publish`, { method: "POST", token }),
  regenerate: (contentId, token) =>
    apiRequest(`/content/${contentId}/regenerate`, { method: "POST", token }),
  suggest: (contentId, payload, token) =>
    apiRequest(`/content/${contentId}/suggest`, {
      method: "POST",
      body: payload,
      token,
    }),
};

export const youtubeApi = {
  status: (token) => apiRequest("/youtube/status", { token }),
  startOAuth: (token) => apiRequest("/youtube/oauth/start", { token }),
  disconnect: (token) =>
    apiRequest("/youtube/connection", { method: "DELETE", token }),
};

export const integrationsApi = {
  video: (token) => apiRequest("/integrations/video", { token }),
  saveVideo: (payload, token) =>
    apiRequest("/integrations/video", { method: "PUT", body: payload, token }),
  clearVideo: (token) =>
    apiRequest("/integrations/video", { method: "DELETE", token }),
  testVideo: (payload, token) =>
    apiRequest("/integrations/video/test", { method: "POST", body: payload, token }),
};

export const automationApi = {
  status: (token) => apiRequest("/automation/status", { token }),
};

export const analyticsApi = {
  ingest: (payload, token) =>
    apiRequest("/analytics/ingest", { method: "POST", body: payload, token }),
  projectSummary: (projectId, token, rangeDays = 30) =>
    apiRequest(`/analytics/projects/${projectId}?range_days=${rangeDays}`, { token }),
  contentSummary: (contentId, token, rangeDays = 90) =>
    apiRequest(`/analytics/content/${contentId}?range_days=${rangeDays}`, { token }),
  sync: (projectId, token) =>
    apiRequest(`/analytics/projects/${projectId}/sync`, { method: "POST", token }),
  coach: (projectId, token, rangeDays = 30) =>
    apiRequest(`/analytics/projects/${projectId}/coach?range_days=${rangeDays}`, {
      method: "POST",
      token,
    }),
};
