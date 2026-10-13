"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api/client";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { ProjectVideo, ProjectVideoPage } from "@/types";

const PAGE_SIZE = 12;

function VideoThumbnail({ assetId, topic }: { assetId: string | null; topic: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setSrc(null);
    if (assetId) {
      apiRequest<{ signed_url: string }>(`/assets/${assetId}`)
        .then((asset) => { if (active) setSrc(asset.signed_url); })
        .catch(() => { if (active) setSrc(null); });
    }
    return () => { active = false; };
  }, [assetId]);

  return (
    <div className="relative flex h-36 items-center justify-center overflow-hidden rounded-lg bg-slate-100 text-slate-400">
      {src ? (
        // Signed S3/MinIO URLs have dynamic hosts; Next image optimization is inappropriate.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={`Thumbnail for ${topic}`} loading="lazy" className="h-full w-full object-cover" />
      ) : <span className="text-sm">Video preview</span>}
    </div>
  );
}

export function ProjectVideos({ projectId }: { projectId: string }) {
  const [page, setPage] = useState<ProjectVideoPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setOffset(0); }, [projectId, filter]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    const status = filter === "all" ? "" : `&status=${encodeURIComponent(filter)}`;
    apiRequest<ProjectVideoPage>(`/projects/${projectId}/videos?limit=${PAGE_SIZE}&offset=${offset}${status}`)
      .then((result) => { if (active) setPage(result); })
      .catch(() => { if (active) { setPage(null); setError("Unable to load project videos."); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId, filter, offset, refresh]);

  return (
    <section aria-label="Project videos" className="mt-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Videos</h2>
        <div className="flex items-center gap-2">
          <label htmlFor="video-status-filter" className="text-sm text-slate-600">Status</label>
          <select id="video-status-filter" className="rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
            value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All</option><option value="ready">Ready</option>
            <option value="queued">Queued</option><option value="rendering">Rendering</option>
            <option value="failed">Failed</option>
          </select>
          <Button variant="secondary" onClick={() => setRefresh((value) => value + 1)}>Refresh</Button>
        </div>
      </div>
      {error && <p role="alert" className="mb-4 text-sm text-red-700">{error}</p>}
      {loading ? (
        <p className="text-sm text-slate-500">Loading videos...</p>
      ) : page?.items.length ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {page.items.map((video: ProjectVideo) => (
            <Link key={video.id} href={`/studio/video/${video.id}`} className="block rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500">
              <Card className="h-full transition-shadow hover:shadow-md">
                <VideoThumbnail assetId={video.thumbnail_asset_id} topic={video.topic} />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <StatusBadge status={video.status} />
                  <span className="text-xs text-slate-500">{new Date(video.created_at).toLocaleDateString()}</span>
                </div>
                <h3 className="mt-2 line-clamp-2 font-semibold text-slate-900">{video.topic}</h3>
                <p className="mt-1 text-xs text-slate-500">{video.platform.replace(/_/g, " ")} · {video.duration_seconds}s</p>
                {video.status !== "ready" && <p className="mt-1 text-xs text-slate-500">Progress: {video.progress}%</p>}
              </Card>
            </Link>
          ))}
        </div>
      ) : !error ? <p className="text-sm text-slate-500">No videos match this filter. Create a video to get started.</p> : null}
      {page && page.total > PAGE_SIZE && (
        <div className="mt-5 flex items-center justify-between gap-3">
          <Button variant="secondary" disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
          <span className="text-xs text-slate-600">
            {page.total ? offset + 1 : 0}–{Math.min(offset + PAGE_SIZE, page.total)} of {page.total}
          </span>
          <Button variant="secondary" disabled={offset + PAGE_SIZE >= page.total || loading}
            onClick={() => setOffset(offset + PAGE_SIZE)}>Next</Button>
        </div>
      )}
    </section>
  );
}
