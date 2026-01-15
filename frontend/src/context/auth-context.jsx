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

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [pending, setPending] = useState(false);

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
        setToken(storedToken);
        setUser(me);
        persistSession(storedToken, me);
      } catch {
        clearSession();
        if (!active) return;
        setToken(null);
        setUser(null);
      } finally {
        if (active) setBootstrapping(false);
      }

      if (storedUser && !active) {
        return;
      }
    }

    bootstrap();
    return () => {
      active = false;
    };
  }, []);

  const applySession = useCallback((accessToken, nextUser) => {
    persistSession(accessToken, nextUser);
    setToken(accessToken);
    setUser(nextUser);
  }, []);

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
