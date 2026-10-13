"use client";

import Link from "next/link";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { useSignedMedia } from "@/hooks/useSignedMedia";
import type { CreatorVideo } from "@/types";

function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

export function CreatorVideoCard({ video }: { video: CreatorVideo }) {
  const { url } = useSignedMedia(video.thumbnail_asset_id);
  const ready = video.status === "ready";
  return (
    <Link href={`/studio/video/${video.id}`}
      className="group overflow-hidden rounded-2xl border border-white/10 bg-[#181a26] transition hover:-translate-y-0.5 hover:border-violet-400/40 hover:shadow-xl hover:shadow-violet-900/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400">
      <div className="relative flex aspect-video items-center justify-center overflow-hidden bg-gradient-to-br from-[#34315d] via-[#242442] to-[#0d162a]">
        {url ? (
          // Private presigned media URLs are not compatible with the Next image optimizer.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={`Thumbnail for ${video.topic}`} loading="lazy" className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
        ) : (
          <><div className="absolute -left-12 top-4 h-36 w-36 rounded-full bg-violet-400/20 blur-3xl" />
          <div className="absolute -right-6 bottom-0 h-28 w-28 rounded-full bg-fuchsia-500/20 blur-3xl" />
          <StudioIcon name="film" size={48} className="text-white/30" /></>
        )}
        <span className="absolute left-3 top-3 rounded-md border border-white/20 bg-black/50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white backdrop-blur-sm">
          {statusLabel(video.status)}
        </span>
        <div className="absolute inset-0 flex items-center justify-center bg-black/0 transition group-hover:bg-black/25">
          <div className="flex h-12 w-12 scale-90 items-center justify-center rounded-full border border-white/30 bg-white/20 text-white opacity-0 backdrop-blur transition group-hover:scale-100 group-hover:opacity-100">
            <StudioIcon name={ready ? "play" : "arrow"} size={20} />
          </div>
        </div>
        <span className="absolute bottom-3 right-3 rounded-md bg-black/70 px-2 py-1 text-xs text-white">
          {video.duration_seconds}s
        </span>
      </div>
      <div className="space-y-2 p-4">
        <h3 className="line-clamp-2 min-h-[44px] text-sm font-semibold leading-6 text-white">{video.topic}</h3>
        <div className="flex items-center justify-between gap-2 text-xs text-[#979bb3]">
          <span className="capitalize">{video.platform.replace(/_/g, " ")}</span>
          <span>{new Date(video.created_at).toLocaleDateString()}</span>
        </div>
        {!ready && <div className="h-1 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full bg-violet-500" style={{ width: `${Math.max(0, Math.min(100, video.progress))}%` }} />
        </div>}
      </div>
    </Link>
  );
}
