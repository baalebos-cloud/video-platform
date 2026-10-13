"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { DashboardShell } from "@/components/dashboard/Shell";
import { ProjectVideos } from "@/components/studio/ProjectVideos";
import { StudioIcon } from "@/components/ui/StudioIcon";

export default function ProjectStudioPage() {
  const { projectId } = useParams<{ projectId: string }>();

  return <DashboardShell>
    <div className="mb-7 flex flex-wrap items-center justify-between gap-4">
      <div>
        <Link href={`/dashboard/projects/${projectId}`}
          className="mb-3 inline-flex items-center gap-2 text-xs text-[#aca7c3] hover:text-white">
          <StudioIcon name="back" size={14} /> Back to project
        </Link>
        <p className="studio-eyebrow mb-2">Production workspace</p>
        <h1 className="text-3xl font-bold">Project studio</h1>
        <p className="mt-2 text-sm text-[#a0a5bc]">Review generated videos and continue creating.</p>
      </div>
      <Link href={`/studio/new?project_id=${projectId}`} className="studio-button">
        <StudioIcon name="plus" size={17} /> New video
      </Link>
    </div>
    <ProjectVideos projectId={projectId} />
  </DashboardShell>;
}
