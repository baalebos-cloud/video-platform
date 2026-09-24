"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DashboardShell } from "@/components/dashboard/Shell";

export default function ProjectStudioPage() {
  const params = useParams<{ projectId: string }>();

  return (
    <DashboardShell>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Studio</h1>
        <Link href={`/studio/new?project_id=${params.projectId}`}>
          <Button>New video</Button>
        </Link>
      </div>
      <Card>
        <p className="text-sm text-slate-500">
          Scene-by-scene editing (script, storyboard, voice, timeline) lands here once a video has completed its
          planning stage. For now, track an in-progress generation from its own status page at
          <code className="mx-1 rounded bg-slate-100 px-1.5 py-0.5">/studio/[videoId]</code>.
        </p>
      </Card>
    </DashboardShell>
  );
}
