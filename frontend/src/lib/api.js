const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(message, status, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

async function parseError(response) {
  let detail = "Something went wrong.";
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") {
      detail = data.detail;
    } else if (data?.detail && typeof data.detail === "object" && data.detail.message) {
      detail = data.detail.message;
    } else if (Array.isArray(data?.detail)) {
      detail = data.detail.map((item) => item.msg || JSON.stringify(item)).join(", ");
    }
  } catch {
    detail = response.statusText || detail;
  }
  return new ApiError(detail, response.status);
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
  generate: (trendId, token) =>
    apiRequest("/content/generate", {
      method: "POST",
      body: { trend_id: trendId },
      token,
    }),
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
  regenerate: (contentId, token) =>
    apiRequest(`/content/${contentId}/regenerate`, { method: "POST", token }),
  suggest: (contentId, payload, token) =>
    apiRequest(`/content/${contentId}/suggest`, {
      method: "POST",
      body: payload,
      token,
    }),
};
