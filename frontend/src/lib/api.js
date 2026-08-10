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
