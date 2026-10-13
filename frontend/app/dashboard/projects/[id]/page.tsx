"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DashboardShell } from "@/components/dashboard/Shell";
import { apiRequest } from "@/lib/api/client";
import type { Project } from "@/types";
import { ProjectVideos } from "@/components/studio/ProjectVideos";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);

  useEffect(() => {
    apiRequest<Project>(`/projects/${params.id}`).then(setProject);
  }, [params.id]);

  return (
    <DashboardShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{project?.name ?? "Loading..."}</h1>
          {project?.niche && <p className="text-sm text-slate-500">{project.niche}</p>}
        </div>
        <Link href={`/studio/new?project_id=${params.id}`}>
          <Button>New video</Button>
        </Link>
      </div>
      <ProjectVideos projectId={params.id} />
    </DashboardShell>
  );
}
