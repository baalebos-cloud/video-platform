"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DashboardShell } from "@/components/dashboard/Shell";
import { apiRequest, ApiError } from "@/lib/api/client";
import { StoryboardReview } from "@/components/studio/StoryboardReview";
import Link from "next/link";
import type { VideoStatusResponse } from "@/types";

const TERMINAL_STATUSES = new Set(["ready", "failed", "cancelled"]);
const POLL_INTERVAL_MS = 3000;

export default function VideoProgressPage() {
  const params = useParams<{ videoId: string }>();
  const [video, setVideo] = useState<VideoStatusResponse | null>(null);
  const [assetUrl, setAssetUrl] = useState<string | null>(null);
  const [assetError, setAssetError] = useState<string | null>(null);
  const [pollVersion, setPollVersion] = useState(0);
  const [startingRender, setStartingRender] = useState(false);
  const [rerenderError, setRerenderError] = useState<string | null>(null);

  async function refreshStatus() {
    try {
      const updated = await apiRequest<VideoStatusResponse>(`/videos/${params.videoId}`);
      setVideo(updated);
    } catch {
      setRerenderError("Unable to refresh the video status.");
    }
  }

  async function startRerender() {
    setRerenderError(null);
    setStartingRender(true);
    try {
      await apiRequest(`/videos/${params.videoId}/rerender`, { method: "POST" });
      setVideo((previous) => previous ? {
        ...previous, status: "rendering", progress: 85, current_stage: "rerender_queued",
      } : previous);
      setPollVersion((v) => v + 1);
    } catch (cause) {
      setRerenderError(cause instanceof ApiError ? cause.message : "Unable to start re-render.");
    } finally {
      setStartingRender(false);
    }
  }

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
  }, [params.videoId, pollVersion]);

  useEffect(() => {
    if (!video?.output_asset_id) return;
    let cancelled = false;
    setAssetUrl(null);
    setAssetError(null);
    apiRequest<{ signed_url: string }>(`/assets/${video.output_asset_id}`)
      .then((asset) => {
        if (!cancelled) setAssetUrl(asset.signed_url);
      })
      .catch(() => {
        if (!cancelled) setAssetError("Unable to load the video. Refresh the page to renew its download link.");
      });
    return () => { cancelled = true; };
  }, [video?.output_asset_id]);

  return (
    <DashboardShell>
      <h1 className="mb-3 text-2xl font-semibold">{video?.topic || "Video generation"}</h1>
      {video?.project_id && (
        <Link href={`/dashboard/projects/${video.project_id}`} className="mb-5 inline-block text-sm font-medium text-brand-700 hover:underline">
          Back to project
        </Link>
      )}
      {video && (
        <p className="mb-5 text-sm text-slate-500">
          {video.platform?.replace(/_/g, " ")} · {video.language} · {video.duration_seconds}s
        </p>
      )}
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
            {video.output_asset_id && (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-green-700">
                  {video.status === "rendering" ? "Previous video available while the new version renders." : "Your video is ready."}
                </p>
                {assetUrl ? (
                  <>
                    <video controls playsInline preload="metadata" className="w-full rounded-lg bg-black" src={assetUrl}>
                      Your browser does not support video playback.
                    </video>
                    <a href={assetUrl} target="_blank" rel="noopener noreferrer"
                      className="inline-flex self-start rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white">
                      Open or download video
                    </a>
                    <p className="text-xs text-slate-500">The private media link expires after 15 minutes. Reload to renew it.</p>
                  </>
                ) : (
                  <p className="text-sm text-slate-600">{assetError || "Preparing secure video link..."}</p>
                )}
              </div>
            )}
            {video.status === "failed" && (
                 <div className="flex flex-col gap-2">
              <p className="text-sm text-red-700">Generation failed.</p>
            {video.error_message && (
              <p className="break-words rounded bg-red-50 p-2 font-mono text-xs text-red-800">
            {video.error_message}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </Card>
      {video?.status === "ready" && (
        <div className="mt-5 space-y-3">
          {video.needs_rerender && (
            <Card className="max-w-xl">
              <p className="mb-3 text-sm text-amber-800">
                Storyboard images have changed. Your downloadable MP4 is still the previous version.
              </p>
              <button type="button" onClick={startRerender} disabled={startingRender}
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
                {startingRender ? "Queueing re-render..." : "Re-render video with updated scenes"}
              </button>
              <p className="mt-2 text-xs text-slate-500">
                Reuses saved narration and images. Videos without saved narration assets cannot use this option.
              </p>
            </Card>
          )}
          {rerenderError && <p role="alert" className="text-sm text-red-700">{rerenderError}</p>}
          {video.current_stage === "rerender_failed" && (
            <p role="alert" className="text-sm text-red-700">{video.error_message}</p>
          )}
          <StoryboardReview videoId={params.videoId} onChanged={refreshStatus} />
        </div>
      )}
    </DashboardShell>
  );
}
