"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, authApi } from "@/lib/api";
import {
  clearSession,
  getStoredToken,
  getStoredUser,
  persistSession,
} from "@/lib/auth-storage";
import { sessionFromMe } from "@/lib/session";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [pending, setPending] = useState(false);

  const applySession = useCallback((accessToken, nextUser) => {
    persistSession(accessToken, nextUser);
    setToken(accessToken);
    setUser(nextUser);
  }, []);

  const refreshSession = useCallback(
    async (currentToken) => {
      const me = await authApi.me(currentToken);
      const next = sessionFromMe(me, currentToken);
      applySession(next.token, next.user);
      return next;
    },
    [applySession],
  );

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      const storedToken = getStoredToken();
      const storedUser = getStoredUser();

      if (!storedToken) {
        if (active) {
          setBootstrapping(false);
        }
        return;
      }

      try {
        const me = await authApi.me(storedToken);
        if (!active) return;
        const next = sessionFromMe(me, storedToken);
        applySession(next.token, next.user);
      } catch (err) {
        // Only drop the session on a real JWT rejection. Network errors,
        // backend reloads, and Redis 503s must not kick a valid login out.
        const authRejected = err instanceof ApiError && err.status === 401;
        if (authRejected) {
          clearSession();
          if (!active) return;
          setToken(null);
          setUser(null);
        } else if (active) {
          setToken(storedToken);
          setUser(storedUser);
        }
      } finally {
        if (active) setBootstrapping(false);
      }
    }

    bootstrap();
    return () => {
      active = false;
    };
  }, [applySession]);

  useEffect(() => {
    if (!token) return undefined;

    let isPingInFlight = false;

    async function pingSession() {
      // Guard against overlapping calls: the interval and the
      // visibilitychange listener can both fire pingSession close
      // together, which would otherwise fire two concurrent refreshes.
      if (isPingInFlight) return;

      isPingInFlight = true;
      try {
        await refreshSession(token);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          clearSession();
          setToken(null);
          setUser(null);
        } else if (err instanceof ApiError) {
          // Non-401 API errors (network hiccup, 5xx, etc.) shouldn't log
          // the user out, but they're worth surfacing for debugging.
          console.error("[Auth] Session refresh failed (non-401):", {
            status: err.status,
            message: err.message,
            code: err.code,
          });
        } else {
          console.error("[Auth] Unexpected session refresh error:", err);
        }
      } finally {
        isPingInFlight = false;
      }
    }

    const timer = setInterval(pingSession, 10 * 60 * 1000);

    function onVisible() {
      if (document.visibilityState === "visible") {
        pingSession();
      }
    }

    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refreshSession, token]);

  const login = useCallback(
    async ({ email, password }) => {
      setPending(true);
      try {
        const data = await authApi.login({ email, password });
        applySession(data.access_token, data.user);
        router.replace("/dashboard");
        return data;
      } finally {
        setPending(false);
      }
    },
    [applySession, router],
  );

  const register = useCallback(
    async ({ email, password, full_name }) => {
      setPending(true);
      try {
        const data = await authApi.register({ email, password, full_name });
        applySession(data.access_token, data.user);
        router.replace("/dashboard");
        return data;
      } finally {
        setPending(false);
      }
    },
    [applySession, router],
  );

  const logout = useCallback(async () => {
    setPending(true);
    try {
      if (token) {
        try {
          await authApi.logout(token);
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 401)) {
            throw error;
          }
        }
      }
    } finally {
      clearSession();
      setToken(null);
      setUser(null);
      setPending(false);
      router.replace("/login");
    }
  }, [router, token]);

  const value = useMemo(
    () => ({
      user,
      token,
      bootstrapping,
      pending,
      isAuthenticated: Boolean(token && user),
      login,
      register,
      logout,
    }),
    [bootstrapping, login, logout, pending, register, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
