"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DashboardShell } from "@/components/dashboard/Shell";
import { apiRequest } from "@/lib/api/client";
import type { VideoStatusResponse } from "@/types";

const TERMINAL_STATUSES = new Set(["ready", "failed", "cancelled"]);
const POLL_INTERVAL_MS = 3000;

export default function VideoProgressPage() {
  const params = useParams<{ videoId: string }>();
  const [video, setVideo] = useState<VideoStatusResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const data = await apiRequest<VideoStatusResponse>(`/videos/${params.videoId}`);
        if (cancelled) return;
        setVideo(data);
        if (!TERMINAL_STATUSES.has(data.status)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [params.videoId]);

  return (
    <DashboardShell>
      <h1 className="mb-6 text-2xl font-semibold">Video generation</h1>
      <Card className="max-w-xl">
        {!video ? (
          <p className="text-sm text-slate-500">Loading status...</p>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <StatusBadge status={video.status} />
              <span className="text-sm text-slate-500">{video.progress}%</span>
            </div>
            <ProgressBar value={video.progress} />
            {video.current_stage && (
              <p className="text-sm text-slate-600">
                Current stage: <span className="font-medium">{video.current_stage.replace(/_/g, " ")}</span>
              </p>
            )}
            {video.status === "ready" && (
              <p className="text-sm text-green-700">
                Your video is ready. Fetch its signed download URL via the asset endpoint once the video record
                exposes its output_asset_id to the frontend.
              </p>
            )}
            {video.status === "failed" && (
              <p className="text-sm text-red-700">Generation failed. Check the job&apos;s error details or try again.</p>
            )}
          </div>
        )}
      </Card>
    </DashboardShell>
  );
}
