"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  Network,
  PenLine,
  Rocket,
  Search,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";

const features = [
  {
    title: "Trend Discovery",
    body: "Surface rising topics before they peak with cross-platform signals.",
    icon: TrendingUp,
  },
  {
    title: "Multi-Agent Research",
    body: "Coordinate research, strategy, and writing agents in one pipeline.",
    icon: Network,
  },
  {
    title: "Review & Launch",
    body: "Edit, approve, and move content through a clear production loop.",
    icon: Rocket,
  },
];

const agents = [
  {
    title: "Research Agent",
    body: "Maps angles, sources, and audience context from a selected trend.",
    icon: Search,
  },
  {
    title: "Strategy Agent",
    body: "Turns research into positioning, hooks, and platform plans.",
    icon: BarChart3,
  },
  {
    title: "Content Agent",
    body: "Drafts scripts, titles, captions, and hashtags ready for review.",
    icon: PenLine,
  },
];

const workflow = [
  "Discover trends",
  "Research",
  "Plan",
  "Generate",
  "Review",
  "Improve",
];

export function HomePage() {
  const { isAuthenticated, bootstrapping } = useAuth();
  const signedIn = !bootstrapping && isAuthenticated;

  return (
    <div className="min-h-screen bg-background text-on-background">
      <header className="sticky top-0 z-50 border-b border-outline-variant/40 bg-surface-container-lowest/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-on-primary">
              c
            </span>
            <span className="font-display text-xl font-bold tracking-tight text-on-surface">
              creatoros
            </span>
          </Link>

          <nav className="hidden items-center gap-8 md:flex">
            <a href="#product" className="text-sm font-medium text-on-surface-variant hover:text-primary">
              Product
            </a>
            <a href="#agents" className="text-sm font-medium text-on-surface-variant hover:text-primary">
              Agents
            </a>
            <a href="#workflow" className="text-sm font-medium text-on-surface-variant hover:text-primary">
              Workflow
            </a>
          </nav>

          <div className="flex items-center gap-2 sm:gap-3">
            {signedIn ? (
              <Button asChild>
                <Link href="/dashboard">Open workspace</Link>
              </Button>
            ) : (
              <>
                <Button asChild variant="ghost">
                  <Link href="/login">Sign in</Link>
                </Button>
                <Button asChild>
                  <Link href="/register">Create account</Link>
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden px-4 pb-16 pt-14 sm:px-6 sm:pt-20 lg:px-8 lg:pb-24">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,#e0e8ff_0%,#f9f9ff_62%)]" />
          <div className="pointer-events-none absolute -left-24 top-24 h-56 w-56 rounded-full bg-primary/10 blur-3xl" />
          <div className="pointer-events-none absolute -right-16 top-40 h-64 w-64 rounded-full bg-secondary/10 blur-3xl" />

          <div className="relative mx-auto max-w-7xl text-center">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45 }}
              className="space-y-8"
            >
              <div className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/10 px-3 py-1 font-label text-[11px] font-semibold uppercase tracking-[0.08em] text-primary">
                <Sparkles className="h-3.5 w-3.5" />
                The AI content operating system
              </div>

              <div className="mx-auto max-w-4xl space-y-5">
                <h1 className="font-display text-4xl font-bold tracking-tight text-on-surface sm:text-5xl lg:text-7xl lg:leading-[1.05]">
                  Your AI Content{" "}
                  <span className="bg-[linear-gradient(135deg,#0058be_0%,#316bf3_100%)] bg-clip-text text-transparent">
                    Operating System
                  </span>
                </h1>
                <p className="mx-auto max-w-2xl text-base leading-7 text-on-surface-variant sm:text-lg">
                  Turn trends into reviewed, publish-ready content with a multi-agent workflow built
                  for serious creators.
                </p>
              </div>

              <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
                {signedIn ? (
                  <Button asChild size="lg" className="min-w-[200px] rounded-full px-8">
                    <Link href="/dashboard">
                      Open workspace
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                ) : (
                  <>
                    <Button asChild size="lg" className="min-w-[200px] rounded-full px-8">
                      <Link href="/login">
                        Sign in
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                    <Button
                      asChild
                      variant="outline"
                      size="lg"
                      className="min-w-[200px] rounded-full bg-surface-container-lowest/80 px-8"
                    >
                      <Link href="/register">Create a free account</Link>
                    </Button>
                  </>
                )}
              </div>
              {!signedIn ? (
                <p className="text-sm text-on-surface-variant">
                  New to creatoros?{" "}
                  <Link href="/register" className="font-semibold text-primary hover:underline">
                    Create a free account
                  </Link>
                </p>
              ) : null}
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.12 }}
              className="relative mx-auto mt-14 max-w-5xl"
            >
              <div className="absolute -inset-3 rounded-[28px] bg-[linear-gradient(135deg,rgba(0,88,190,0.18),rgba(49,107,243,0.12))] blur-2xl" />
              <div className="relative overflow-hidden rounded-2xl border border-outline-variant/70 bg-surface-container-lowest shadow-[0_24px_60px_rgba(23,43,77,0.12)]">
                <div className="flex items-center gap-2 border-b border-outline-variant/60 bg-surface-container-low px-4 py-3">
                  <span className="h-2.5 w-2.5 rounded-full bg-outline-variant" />
                  <span className="h-2.5 w-2.5 rounded-full bg-outline-variant" />
                  <span className="h-2.5 w-2.5 rounded-full bg-outline-variant" />
                  <span className="ml-3 font-label text-[11px] uppercase tracking-[0.08em] text-outline">
                    creatoros workspace
                  </span>
                </div>
                <div className="grid gap-4 p-4 sm:grid-cols-[200px_1fr] sm:p-5">
                  <div className="hidden space-y-2 rounded-xl bg-surface-container-low p-3 sm:block">
                    {["Dashboard", "Trends", "Content", "Analytics"].map((item, index) => (
                      <div
                        key={item}
                        className={`rounded-lg px-3 py-2 text-left text-sm ${
                          index === 0
                            ? "bg-primary font-semibold text-on-primary"
                            : "text-on-surface-variant"
                        }`}
                      >
                        {item}
                      </div>
                    ))}
                  </div>
                  <div className="space-y-4">
                    <div className="rounded-xl border border-outline-variant/70 bg-[linear-gradient(160deg,#f1f3ff_0%,#ffffff_55%,#e8edff_100%)] p-5 text-left">
                      <p className="font-label text-[11px] uppercase tracking-[0.08em] text-primary">
                        Content strategy
                      </p>
                      <p className="mt-2 font-display text-xl font-semibold text-on-surface">
                        Trend → Research → Strategy → Draft
                      </p>
                      <p className="mt-2 max-w-xl text-sm leading-6 text-on-surface-variant">
                        A calm operations surface for discovering opportunities, generating packages,
                        and improving what performs.
                      </p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-3">
                      {["Research ready", "Strategy queued", "Draft in review"].map((label) => (
                        <div
                          key={label}
                          className="rounded-xl border border-outline-variant/70 bg-surface-container-lowest px-4 py-3 text-left"
                        >
                          <p className="font-label text-[10px] uppercase tracking-[0.08em] text-outline">
                            Agent
                          </p>
                          <p className="mt-1 text-sm font-semibold text-on-surface">{label}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </section>

        <section className="border-y border-outline-variant/40 bg-surface py-10">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <p className="text-center font-label text-xs uppercase tracking-[0.14em] text-on-surface-variant">
              Built for creators publishing across
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-x-10 gap-y-4 text-sm font-semibold text-on-surface/55">
              {["YouTube", "X / Twitter", "TikTok", "LinkedIn"].map((name) => (
                <span key={name}>{name}</span>
              ))}
            </div>
          </div>
        </section>

        <section id="product" className="px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="font-display text-3xl font-bold tracking-tight text-on-surface sm:text-4xl">
                Engineered for growth
              </h2>
              <p className="mt-3 text-on-surface-variant">
                One product loop from opportunity to improvement — without tool sprawl.
              </p>
            </div>
            <div className="mt-12 grid gap-5 md:grid-cols-3">
              {features.map((feature, index) => {
                const Icon = feature.icon;
                return (
                  <motion.article
                    key={feature.title}
                    initial={{ opacity: 0, y: 14 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, amount: 0.4 }}
                    transition={{ delay: index * 0.06, duration: 0.35 }}
                    className="rounded-2xl border border-outline-variant/60 bg-surface-container-lowest p-7 shadow-[0_2px_4px_rgba(23,43,77,0.04)]"
                  >
                    <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-surface-container text-primary">
                      <Icon className="h-5 w-5" />
                    </div>
                    <h3 className="font-display text-xl font-semibold text-on-surface">
                      {feature.title}
                    </h3>
                    <p className="mt-3 text-sm leading-6 text-on-surface-variant">{feature.body}</p>
                  </motion.article>
                );
              })}
            </div>
          </div>
        </section>

        <section id="workflow" className="bg-surface-container-low px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="font-display text-3xl font-bold tracking-tight text-on-surface sm:text-4xl">
                The daily content engine
              </h2>
              <p className="mt-3 text-on-surface-variant">
                A predictable path from signal to shipped content.
              </p>
            </div>
            <div className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {workflow.map((step, index) => (
                <div
                  key={step}
                  className="flex items-center gap-4 rounded-xl border border-outline-variant/50 bg-surface-container-lowest px-4 py-4"
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 font-label text-xs font-semibold text-primary">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="font-display text-lg font-semibold text-on-surface">{step}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="agents" className="px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="font-display text-3xl font-bold tracking-tight text-on-surface sm:text-4xl">
                Meet your AI team
              </h2>
              <p className="mt-3 text-on-surface-variant">
                Specialized agents, orchestrated by creatoros — never freestyle chat chaos.
              </p>
            </div>
            <div className="mt-12 grid gap-5 md:grid-cols-3">
              {agents.map((agent) => {
                const Icon = agent.icon;
                return (
                  <article
                    key={agent.title}
                    className="rounded-2xl border border-outline-variant/60 bg-surface-container-lowest p-7"
                  >
                    <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-surface-container text-primary">
                      <Icon className="h-5 w-5" />
                    </div>
                    <h3 className="font-display text-xl font-semibold text-on-surface">
                      {agent.title}
                    </h3>
                    <p className="mt-3 text-sm leading-6 text-on-surface-variant">{agent.body}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section className="px-4 pb-20 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-5xl rounded-3xl bg-[linear-gradient(135deg,#0058be_0%,#2170e4_55%,#316bf3_100%)] px-6 py-14 text-center text-on-primary sm:px-10">
            <h2 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
              {signedIn ? "Pick up where you left off" : "Ready to run content like a system?"}
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-on-primary/85 sm:text-base">
              {signedIn
                ? "Your workspace is waiting — trends, Shorts, and publishing in one place."
                : "Sign in to your workspace, or create a free account if you are new."}
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              {signedIn ? (
                <Button
                  asChild
                  size="lg"
                  className="min-w-[200px] rounded-full bg-surface-container-lowest text-primary hover:bg-white"
                >
                  <Link href="/dashboard">Open workspace</Link>
                </Button>
              ) : (
                <>
                  <Button
                    asChild
                    size="lg"
                    className="min-w-[200px] rounded-full bg-surface-container-lowest text-primary hover:bg-white"
                  >
                    <Link href="/login">Sign in</Link>
                  </Button>
                  <Button
                    asChild
                    variant="outline"
                    size="lg"
                    className="min-w-[200px] rounded-full border-white/40 bg-transparent text-on-primary hover:bg-white/10"
                  >
                    <Link href="/register">Create account</Link>
                  </Button>
                </>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-outline-variant/50 px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-on-primary">
              c
            </span>
            <span className="font-display font-semibold text-on-surface">creatoros</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            {signedIn ? (
              <Link href="/dashboard" className="font-semibold text-primary hover:underline">
                Open workspace
              </Link>
            ) : (
              <>
                <Link href="/login" className="font-semibold text-primary hover:underline">
                  Sign in
                </Link>
                <Link href="/register" className="font-semibold text-on-surface hover:underline">
                  Create account
                </Link>
              </>
            )}
            <p className="text-on-surface-variant">
              AI content business automation for modern creators.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
