"use client";

import { motion } from "framer-motion";
import Link from "next/link";

export function AuthShell({
  eyebrow = "creatoros",
  title,
  subtitle,
  children,
  footer,
}) {
  return (
    <div className="min-h-screen bg-background text-on-background">
      <div className="mx-auto flex min-h-screen max-w-[1440px] items-stretch p-4 md:p-6">
        <div className="grid w-full overflow-hidden rounded-2xl border border-outline-variant/70 bg-surface-container-lowest shadow-[0_10px_40px_rgba(23,43,77,0.08)] lg:grid-cols-2">
          <motion.aside
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
            className="relative hidden overflow-hidden bg-[linear-gradient(160deg,#e8edff_0%,#f1f3ff_45%,#d7e2ff_100%)] p-10 lg:flex lg:flex-col lg:justify-between"
          >
            <div className="pointer-events-none absolute inset-0">
              <div className="absolute -left-10 top-16 h-40 w-40 rounded-full bg-primary/10 blur-2xl" />
              <div className="absolute bottom-10 right-8 h-48 w-48 rounded-full bg-secondary/15 blur-3xl" />
              <div className="absolute left-1/3 top-1/3 h-24 w-24 rotate-12 rounded-xl border border-white/50 bg-white/30 backdrop-blur-sm" />
            </div>

            <div className="relative z-10 space-y-6">
              <Link href="/" className="inline-flex items-center gap-2">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-sm font-bold text-on-primary">
                  c
                </span>
                <span className="font-display text-2xl font-bold tracking-tight text-primary">
                  {eyebrow}
                </span>
              </Link>
              <div className="max-w-md space-y-3">
                <h1 className="font-display text-4xl font-bold leading-tight tracking-tight text-on-surface">
                  {title}
                </h1>
                <p className="text-base leading-7 text-on-surface-variant">{subtitle}</p>
              </div>
            </div>

            <div className="relative z-10 rounded-xl border border-white/60 bg-white/55 p-5 backdrop-blur-md">
              <p className="font-label text-xs uppercase tracking-[0.08em] text-primary">
                Content operations loop
              </p>
              <p className="mt-2 text-sm leading-6 text-on-surface-variant">
                Discover trends, generate with agents, review, and improve — in one calm workspace.
              </p>
            </div>
          </motion.aside>

          <motion.main
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: "easeOut", delay: 0.05 }}
            className="flex flex-col justify-center bg-surface-container-lowest px-6 py-10 sm:px-10 lg:px-14"
          >
            <div className="mb-8 lg:hidden">
              <Link href="/" className="inline-flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-on-primary">
                  c
                </span>
                <span className="font-display text-xl font-bold text-primary">{eyebrow}</span>
              </Link>
            </div>
            {children}
            {footer ? <div className="mt-8">{footer}</div> : null}
          </motion.main>
        </div>
      </div>
    </div>
  );
}
