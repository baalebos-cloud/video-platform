"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api/client";
import { CreatorVideoCard } from "@/components/studio/CreatorVideoCard";
import { StudioIcon } from "@/components/ui/StudioIcon";
import type { CreatorVideo, ProjectVideoPage } from "@/types";

const PAGE_SIZE = 12;

export function ProjectVideos({ projectId }: { projectId: string }) {
  const [page, setPage] = useState<ProjectVideoPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => { setOffset(0); }, [projectId, filter]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    const status = filter === "all" ? "" : `&status=${encodeURIComponent(filter)}`;
    apiRequest<ProjectVideoPage>(`/projects/${projectId}/videos?limit=${PAGE_SIZE}&offset=${offset}${status}`)
      .then(data => { if (active) setPage(data); })
      .catch(() => { if (active) { setPage(null); setError(true); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId, offset, filter, version]);

  return <section aria-label="Project videos">
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div><p className="studio-eyebrow mb-1">Video collection</p><h2 className="text-xl font-semibold">Your videos</h2></div>
      <div className="flex gap-2">
        <label htmlFor="video-filter" className="sr-only">Filter videos by status</label>
        <select id="video-filter" value={filter} onChange={e => setFilter(e.target.value)} className="studio-input">
          <option value="all">All statuses</option><option value="ready">Ready</option>
          <option value="queued">Queued</option><option value="rendering">Rendering</option>
          <option value="failed">Failed</option>
        </select>
        <button type="button" onClick={() => setVersion(n => n + 1)} className="studio-button-secondary">
          <StudioIcon name="refresh" size={16} /> Refresh
        </button>
      </div>
    </div>
    {error && <p role="alert" className="mb-5 text-sm text-rose-300">Unable to load this project&apos;s videos.</p>}
    {loading ? <p className="text-sm text-[#a0a4bd]">Loading video library…</p>
      : page?.items.length ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {page.items.map((video) => <CreatorVideoCard key={video.id}
            video={{ ...video, project_id: projectId } as CreatorVideo} />)}
        </div>
      ) : !error ? <div className="studio-surface-soft py-14 text-center">
        <StudioIcon name="film" size={32} className="mx-auto mb-3 text-violet-300" />
        <p className="text-sm font-semibold">No videos found</p>
        <p className="mt-1 text-xs text-[#9ca0ba]">Create a new video or change your status filter.</p>
      </div> : null}
    {page && page.total > PAGE_SIZE && <div className="mt-6 flex items-center justify-between gap-4">
      <button type="button" disabled={offset === 0 || loading} className="studio-button-secondary"
        onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
      <span className="text-xs text-[#999db8]">{offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} of {page.total}</span>
      <button type="button" disabled={offset + PAGE_SIZE >= page.total || loading} className="studio-button-secondary"
        onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
    </div>}
  </section>;
}
