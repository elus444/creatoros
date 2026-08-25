"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { FolderKanban, Loader2, Plus, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/auth-context";
import { ApiError, projectsApi } from "@/lib/api";

function emptyForm() {
  return { name: "", niche: "", audience: "", brand_voice: "" };
}

export default function ProjectsPage() {
  const { token } = useAuth();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    if (!token) return;
    let active = true;

    async function load() {
      setLoading(true);
      setLoadError("");
      try {
        const data = await projectsApi.list(token);
        if (active) setProjects(data);
      } catch (err) {
        if (active) {
          setLoadError(
            err instanceof ApiError ? err.message : "Unable to load projects.",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => {
      active = false;
    };
  }, [token]);

  async function handleCreate(event) {
    event.preventDefault();
    setFormError("");
    if (!form.name.trim()) {
      setFormError("Give your project a name.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await projectsApi.create(
        {
          name: form.name.trim(),
          niche: form.niche.trim() || null,
          audience: form.audience.trim() || null,
          brand_voice: form.brand_voice.trim() || null,
        },
        token,
      );
      setProjects((prev) => [created, ...prev]);
      setForm(emptyForm());
      setShowForm(false);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Unable to create project.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface md:text-4xl">
            Projects
          </h1>
          <p className="max-w-xl text-sm leading-6 text-on-surface-variant md:text-base">
            Each project scopes its own trends, content, and analytics — pick a niche and
            audience so trend collection knows what to search for.
          </p>
        </div>
        <Button onClick={() => setShowForm((prev) => !prev)}>
          <Plus className="h-4 w-4" />
          New project
        </Button>
      </div>

      {showForm ? (
        <motion.form
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          onSubmit={handleCreate}
          className="space-y-5 rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-6"
        >
          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Project name</Label>
              <Input
                id="name"
                placeholder="Cooking Channel"
                value={form.name}
                onChange={(event) => setForm((f) => ({ ...f, name: event.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="niche">Niche</Label>
              <Input
                id="niche"
                placeholder="air fryer recipes"
                value={form.niche}
                onChange={(event) => setForm((f) => ({ ...f, niche: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="audience">Audience</Label>
              <Input
                id="audience"
                placeholder="Busy home cooks, 25-45"
                value={form.audience}
                onChange={(event) => setForm((f) => ({ ...f, audience: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="brand_voice">Brand voice</Label>
              <Input
                id="brand_voice"
                placeholder="Friendly, fast, no-fluff"
                value={form.brand_voice}
                onChange={(event) =>
                  setForm((f) => ({ ...f, brand_voice: event.target.value }))
                }
              />
            </div>
          </div>

          {formError ? (
            <div className="rounded-lg border border-error/20 bg-error-container/60 px-3 py-2 text-sm text-error">
              {formError}
            </div>
          ) : null}

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {submitting ? "Creating…" : "Create project"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
          </div>
        </motion.form>
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-on-surface-variant">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading projects…
        </div>
      ) : loadError ? (
        <div className="rounded-lg border border-error/20 bg-error-container/60 px-4 py-3 text-sm text-error">
          {loadError}
        </div>
      ) : projects.length === 0 ? (
        <div className="rounded-xl border border-dashed border-outline-variant/80 bg-surface-container-lowest p-10 text-center">
          <FolderKanban className="mx-auto h-8 w-8 text-outline" />
          <p className="mt-3 font-display text-lg font-semibold text-on-surface">
            No projects yet
          </p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-on-surface-variant">
            Create your first project to start collecting and ranking real trends for its
            niche.
          </p>
          <Button className="mt-5" onClick={() => setShowForm(true)}>
            <Plus className="h-4 w-4" />
            New project
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {projects.map((project, index) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.04 * index, duration: 0.3 }}
              className="flex flex-col justify-between rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5 shadow-[0_2px_4px_rgba(23,43,77,0.05)]"
            >
              <div>
                <h2 className="font-display text-lg font-semibold text-on-surface">
                  {project.name}
                </h2>
                {project.niche ? (
                  <p className="mt-1 text-sm text-on-surface-variant">{project.niche}</p>
                ) : (
                  <p className="mt-1 text-sm italic text-outline">No niche set</p>
                )}
              </div>
              <Link
                href={`/trends?project=${project.id}`}
                className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
              >
                <TrendingUp className="h-4 w-4" />
                View trends
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
