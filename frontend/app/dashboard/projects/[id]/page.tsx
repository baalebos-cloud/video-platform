"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { DashboardShell } from "@/components/dashboard/Shell";
import { ProjectVideos } from "@/components/studio/ProjectVideos";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { apiRequest } from "@/lib/api/client";
import type { Project } from "@/types";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    apiRequest<Project>(`/projects/${params.id}`).then(value => { if (active) setProject(value); })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [params.id]);

  return <DashboardShell>
    <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
      <div>
        <Link href="/dashboard" className="mb-3 inline-flex items-center gap-2 text-xs text-[#aca6c6] hover:text-white">
          <StudioIcon name="back" size={14} /> All projects
        </Link>
        <h1 className="text-3xl font-bold">{project?.name || (error ? "Project unavailable" : "Loading project…")}</h1>
        <p className="mt-1 text-sm text-[#999eb8]">{project?.niche || "Video collection"}</p>
      </div>
      <Link href={`/studio/new?project_id=${params.id}`} className="studio-button">
        <StudioIcon name="plus" size={17} /> New video
      </Link>
    </div>
    {error && <p role="alert" className="mb-5 text-sm text-rose-300">This project could not be loaded.</p>}
    <ProjectVideos projectId={params.id} />
  </DashboardShell>;
}
