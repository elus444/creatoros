"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";

export function AuthModeTabs({ active }) {
  return (
    <div
      className="grid grid-cols-2 rounded-full bg-surface-container-low p-1"
      role="tablist"
      aria-label="Account"
    >
      <Link
        href="/login"
        role="tab"
        aria-selected={active === "login"}
        className={cn(
          "rounded-full px-4 py-2 text-center text-sm font-semibold transition-colors",
          active === "login"
            ? "bg-surface-container-lowest text-on-surface shadow-sm"
            : "text-on-surface-variant hover:text-on-surface",
        )}
      >
        Sign in
      </Link>
      <Link
        href="/register"
        role="tab"
        aria-selected={active === "register"}
        className={cn(
          "rounded-full px-4 py-2 text-center text-sm font-semibold transition-colors",
          active === "register"
            ? "bg-surface-container-lowest text-on-surface shadow-sm"
            : "text-on-surface-variant hover:text-on-surface",
        )}
      >
        Create account
      </Link>
    </div>
  );
}
