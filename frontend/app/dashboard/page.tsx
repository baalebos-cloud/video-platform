"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { DashboardShell } from "@/components/dashboard/Shell";
import { CreatorVideoCard } from "@/components/studio/CreatorVideoCard";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { apiRequest, ApiError } from "@/lib/api/client";
import type { CreatorOverview, Project } from "@/types";

const metricCards = [
  { key: "total_videos", label: "Total videos", icon: "film" },
  { key: "ready_videos", label: "Ready to share", icon: "play" },
  { key: "projects", label: "Active projects", icon: "folder" },
  { key: "views", label: "Recorded views", icon: "eye" },
] as const;

export default function CreatorDashboardPage() {
  const [overview, setOverview] = useState<CreatorOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showNewProject, setShowNewProject] = useState(false);
  const [name, setName] = useState("");
  const [niche, setNiche] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiRequest<CreatorOverview>("/creator/overview");
      setOverview(data);
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to load your workspace.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await apiRequest<Project>("/projects", {
        method: "POST", body: { name: name.trim(), niche: niche.trim() || null },
      });
      setName("");
      setNiche("");
      setShowNewProject(false);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to create project.");
    } finally {
      setCreating(false);
    }
  }

  const projects = overview?.projects || [];
  const startUrl = projects.length ? `/studio/new?project_id=${projects[0].id}` : null;
  return (
    <DashboardShell>
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="studio-eyebrow mb-2">Your creative command center</p>
          <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">Creator dashboard</h1>
          <p className="mt-2 text-sm text-[#a0a4bd]">Your ideas, videos and performance, all in one place.</p>
        </div>
        {startUrl ? (
          <Link href={startUrl} className="studio-button"><StudioIcon name="plus" /> Create video</Link>
        ) : <button className="studio-button" onClick={() => setShowNewProject(true)}>
          <StudioIcon name="plus" /> Create your first project
        </button>}
      </div>

      {error && <div role="alert" className="mb-6 rounded-xl border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-200">
        {error} <button type="button" className="ml-3 underline" onClick={() => void load()}>Retry</button>
      </div>}

      <div className="relative mb-7 overflow-hidden rounded-3xl border border-violet-400/20 bg-gradient-to-r from-[#3c286c] via-[#342650] to-[#1c1e3e] p-6 sm:p-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-[#b85dea]/20 blur-3xl" />
        <div className="pointer-events-none absolute right-20 bottom-[-110px] h-60 w-60 rounded-full bg-[#6661ec]/30 blur-3xl" />
        <div className="relative z-10 max-w-xl">
          <span className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-semibold text-[#e6d7ff]">
            <StudioIcon name="sparkles" size={14} /> AI-powered creation
          </span>
          <h2 className="text-2xl font-bold leading-snug text-white sm:text-3xl">Bring your next big idea to life.</h2>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-[#d4c8eb]">
            Turn a topic into a storyboard, voiceover and finished video. Refine every scene in your editor.
          </p>
          {startUrl ? <Link href={startUrl} className="studio-button mt-6 bg-white text-white">
            Start creating <StudioIcon name="arrow" />
          </Link> : <button type="button" onClick={() => setShowNewProject(true)} className="studio-button mt-6">
            Create a project <StudioIcon name="arrow" />
          </button>}
        </div>
        <div aria-hidden className="pointer-events-none absolute -right-3 top-4 hidden h-[260px] w-[230px] rotate-[11deg] rounded-[28px] border-8 border-[#0c0e1c] bg-gradient-to-br from-[#7463ea] via-[#4b327c] to-[#16172d] shadow-2xl shadow-violet-950 sm:block">
          <div className="mx-auto mt-[56px] flex h-24 w-24 items-center justify-center rounded-full bg-white/10 text-white/70">
            <StudioIcon name="play" size={40} />
          </div>
          <div className="mx-auto mt-5 h-2 w-32 rounded-full bg-white/20" />
          <div className="mx-auto mt-3 h-2 w-24 rounded-full bg-white/10" />
        </div>
      </div>

      <div className="mb-9 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metricCards.map((item, index) => (
          <div key={item.key} className="studio-stat">
            <div className="mb-5 flex items-center justify-between">
              <span className="text-xs font-medium text-[#a3a7be]">{item.label}</span>
              <span className={`rounded-xl p-2.5 ${index % 2 ? "bg-sky-400/10 text-sky-300" : "bg-violet-400/10 text-[#b8a0ff]"}`}>
                <StudioIcon name={item.icon} size={18} />
              </span>
            </div>
            <strong className="text-3xl font-semibold tracking-tight text-white">
              {overview ? overview.stats[item.key].toLocaleString() : "—"}
            </strong>
          </div>
        ))}
      </div>

      <section className="mb-9">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div><p className="studio-eyebrow mb-1">Create & manage</p><h2 className="text-xl font-semibold">Your projects</h2></div>
          <button type="button" className="studio-button-secondary" onClick={() => setShowNewProject(true)}>
            <StudioIcon name="plus" size={16} /> New project
          </button>
        </div>
        {overview && projects.length === 0 ? (
          <div className="studio-surface-soft px-6 py-10 text-center">
            <StudioIcon name="folder" size={34} className="mx-auto mb-3 text-violet-300" />
            <h3 className="font-semibold">No projects yet</h3>
            <p className="mt-1 text-sm text-[#a0a4bd]">Create a project to start generating videos.</p>
          </div>
        ) : <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {projects.map((project, index) => (
            <Link key={project.id} href={`/dashboard/projects/${project.id}`}
              className="group studio-surface flex min-h-[126px] flex-col justify-between p-5 transition hover:border-violet-400/40">
              <div className="flex items-start justify-between">
                <span className={`rounded-xl p-2.5 ${index % 2 ? "bg-sky-400/10 text-sky-300" : "bg-violet-400/10 text-violet-300"}`}>
                  <StudioIcon name="folder" size={19} />
                </span>
                <StudioIcon name="arrow" className="text-[#737792] transition group-hover:translate-x-1 group-hover:text-white" />
              </div>
              <div><h3 className="mt-3 line-clamp-1 text-sm font-semibold">{project.name}</h3>
                <p className="mt-1 text-xs text-[#9296ac]">{project.niche || "Creative project"}</p>
              </div>
            </Link>
          ))}
        </div>}
      </section>

      <section>
        <div className="mb-5 flex items-center justify-between">
          <div><p className="studio-eyebrow mb-1">Your library</p><h2 className="text-xl font-semibold">Recent videos</h2></div>
          <Link href="/dashboard/analytics" className="flex items-center gap-1.5 text-sm font-medium text-[#bdadff] hover:text-white">
            View analytics <StudioIcon name="arrow" size={16} />
          </Link>
        </div>
        {overview && overview.recent_videos.length === 0 ? (
          <div className="studio-surface-soft px-6 py-12 text-center">
            <StudioIcon name="film" size={32} className="mx-auto mb-3 text-violet-300" />
            <h3 className="font-semibold">Your video library is empty</h3>
            <p className="mt-1 text-sm text-[#a0a4bd]">New videos will appear here automatically.</p>
          </div>
        ) : <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {overview?.recent_videos.map((video) => <CreatorVideoCard key={video.id} video={video} />)}
        </div>}
      </section>

      {showNewProject && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
        onClick={() => setShowNewProject(false)}>
        <div role="dialog" aria-modal="true" aria-labelledby="create-project-heading" className="studio-surface w-full max-w-md p-6 shadow-2xl"
          onClick={e => e.stopPropagation()}>
          <div className="mb-5 flex items-center justify-between">
            <h2 id="create-project-heading" className="text-lg font-semibold">Create a project</h2>
            <button type="button" onClick={() => setShowNewProject(false)} aria-label="Close dialog"
              className="rounded-lg px-2 text-xl text-[#a0a4bd] hover:text-white">×</button>
          </div>
          <form onSubmit={createProject} className="space-y-4">
            <label className="block text-xs font-semibold text-[#b8bcd1]">Project name
              <input autoFocus required maxLength={255} value={name} onChange={e => setName(e.target.value)}
                className="studio-input mt-2" placeholder="e.g. My tech channel" />
            </label>
            <label className="block text-xs font-semibold text-[#b8bcd1]">Niche (optional)
              <input value={niche} onChange={e => setNiche(e.target.value)}
                className="studio-input mt-2" placeholder="e.g. Tech & education" />
            </label>
            <button disabled={creating || !name.trim()} type="submit" className="studio-button w-full">
              {creating ? "Creating…" : "Create project"}
            </button>
          </form>
        </div>
      </div>}
    </DashboardShell>
  );
}
