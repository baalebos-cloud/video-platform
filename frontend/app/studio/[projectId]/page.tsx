"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { DashboardShell } from "@/components/dashboard/Shell";
import { ProjectVideos } from "@/components/studio/ProjectVideos";

export default function ProjectStudioPage() {
  const params = useParams<{ projectId: string }>();
  return (
    <DashboardShell>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Project studio</h1>
        <Link href={`/studio/new?project_id=${params.projectId}`}><Button>New video</Button></Link>
      </div>
      <ProjectVideos projectId={params.projectId} />
    </DashboardShell>
  );
}
