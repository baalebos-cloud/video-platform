"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { DashboardShell } from "@/components/dashboard/Shell";
import { apiRequest } from "@/lib/api/client";
import type { Project } from "@/types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [niche, setNiche] = useState("");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);

  async function loadProjects() {
    const data = await apiRequest<Project[]>("/projects");
    setProjects(data);
    setLoading(false);
  }

  useEffect(() => {
    loadProjects();
  }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await apiRequest<Project>("/projects", { method: "POST", body: { name, niche: niche || undefined } });
      setName("");
      setNiche("");
      await loadProjects();
    } finally {
      setCreating(false);
    }
  }

  return (
    <DashboardShell>
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
      </div>

      <Card className="mb-8">
        <h2 className="mb-4 text-sm font-semibold text-slate-700">New project</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div className="min-w-[200px] flex-1">
            <Input label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="min-w-[200px] flex-1">
            <Input label="Niche (optional)" value={niche} onChange={(e) => setNiche(e.target.value)} />
          </div>
          <Button type="submit" loading={creating}>
            Create project
          </Button>
        </form>
      </Card>

      {loading ? (
        <p className="text-sm text-slate-500">Loading projects...</p>
      ) : projects.length === 0 ? (
        <p className="text-sm text-slate-500">No projects yet — create one above to get started.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Link key={project.id} href={`/dashboard/projects/${project.id}`}>
              <Card className="h-full transition-shadow hover:shadow-md">
                <h3 className="font-semibold text-slate-900">{project.name}</h3>
                {project.niche && <p className="mt-1 text-sm text-slate-500">{project.niche}</p>}
              </Card>
            </Link>
          ))}
        </div>
      )}
    </DashboardShell>
  );
}
