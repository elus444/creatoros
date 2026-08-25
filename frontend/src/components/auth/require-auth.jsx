"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/context/auth-context";

export function RequireAuth({ children }) {
  const router = useRouter();
  const { bootstrapping, isAuthenticated } = useAuth();

  useEffect(() => {
    if (!bootstrapping && !isAuthenticated) {
      router.replace("/login");
    }
  }, [bootstrapping, isAuthenticated, router]);

  if (bootstrapping) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="rounded-xl border border-outline-variant bg-surface-container-lowest px-6 py-4 text-sm text-on-surface-variant shadow-sm">
          Restoring your session…
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return children;
}
