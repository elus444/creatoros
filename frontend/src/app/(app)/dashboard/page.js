"use client";

import { motion } from "framer-motion";

import { useAuth } from "@/context/auth-context";

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function DashboardPage() {
  const { user } = useAuth();
  const firstName = user?.full_name?.split(" ")[0] || user?.email?.split("@")[0] || "Creator";

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface md:text-4xl">
            {getGreeting()}, {firstName}
          </h1>
          <p className="max-w-xl text-sm leading-6 text-on-surface-variant md:text-base">
            Your creatoros workspace is ready. Trend intelligence, multi-agent generation, and
            analytics land in later milestones.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {[
          {
            title: "Authentication",
            body: "Secure JWT session with protected routes and logout revocation.",
            status: "Live",
          },
          {
            title: "Application shell",
            body: "Sidebar, header, and responsive navigation for the product loop.",
            status: "Live",
          },
          {
            title: "Next up",
            body: "Milestone 2 adds project-scoped trend discovery and ranking.",
            status: "Queued",
          },
        ].map((card, index) => (
          <motion.article
            key={card.title}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 * index, duration: 0.35 }}
            className="rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 shadow-[0_2px_4px_rgba(23,43,77,0.05)]"
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="font-display text-lg font-semibold text-on-surface">{card.title}</h2>
              <span className="rounded-full bg-surface-container px-2.5 py-1 font-label text-[11px] uppercase tracking-[0.06em] text-primary">
                {card.status}
              </span>
            </div>
            <p className="text-sm leading-6 text-on-surface-variant">{card.body}</p>
          </motion.article>
        ))}
      </div>

      <section className="rounded-xl border border-outline-variant/80 bg-[linear-gradient(135deg,#f1f3ff_0%,#ffffff_55%,#e8edff_100%)] p-6 md:p-8">
        <p className="font-label text-xs uppercase tracking-[0.08em] text-primary">
          Product loop
        </p>
        <h2 className="mt-2 font-display text-2xl font-semibold text-on-surface">
          Foundation complete
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-on-surface-variant md:text-base">
          You can register, sign in, access the protected application, and log out. Remaining
          milestones will unlock trends, AI generation, review, automation, and analytics without
          changing this shell.
        </p>
      </section>
    </div>
  );
}
