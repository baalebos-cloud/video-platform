"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { DashboardShell } from "@/components/dashboard/Shell";
import { CaptionPanel, timeLabel } from "@/components/studio/CaptionPanel";
import { SceneInspector } from "@/components/studio/SceneInspector";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { useSignedMedia } from "@/hooks/useSignedMedia";
import { apiRequest, ApiError } from "@/lib/api/client";
import type { CaptionTrack, StoryboardScene, VideoStatusResponse } from "@/types";

const TERMINAL_STATUSES = new Set(["ready", "failed", "cancelled"]);
const POLL_INTERVAL_MS = 3000;

function SceneFrame({ assetId, selected, onSelect }: {
  assetId: string | null; selected: boolean; onSelect: () => void;
}) {
  const { url } = useSignedMedia(assetId);
  return <button type="button" onClick={onSelect}
    aria-pressed={selected}
    className={`relative h-[86px] w-[82px] shrink-0 overflow-hidden rounded-lg border transition ${selected
      ? "border-violet-400 ring-2 ring-violet-400/40" : "border-white/10 hover:border-white/30"}`}>
    {url ? (
      // Media is signed at runtime and cannot be optimized through Next.
      // eslint-disable-next-line @next/next/no-img-element
      <img src={url} alt="" className="h-full w-full object-cover" />
    ) : <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-violet-800/40 to-[#20223d] text-[#a79cce]">
      <StudioIcon name="film" />
    </div>}
  </button>;
}

export default function VideoEditorPage() {
  const params = useParams<{ videoId: string }>();
  const [video, setVideo] = useState<VideoStatusResponse | null>(null);
  const [scenes, setScenes] = useState<StoryboardScene[]>([]);
  const [captions, setCaptions] = useState<CaptionTrack | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [tab, setTab] = useState<"scene" | "captions">("scene");
  const [previewMode, setPreviewMode] = useState<"scene" | "video">("scene");
  const [pollVersion, setPollVersion] = useState(0);
  const [rerendering, setRerendering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshVideo = useCallback(async () => {
    const value = await apiRequest<VideoStatusResponse>(`/videos/${params.videoId}`);
    setVideo(value);
  }, [params.videoId]);

  const refreshScenes = useCallback(async () => {
    const result = await apiRequest<StoryboardScene[]>(`/videos/${params.videoId}/storyboard`);
    setScenes(result);
    setSelectedSceneId(current => current && result.some(s => s.id === current) ? current : result[0]?.id || null);
  }, [params.videoId]);

  const refreshCaptions = useCallback(async () => {
    const result = await apiRequest<CaptionTrack>(`/videos/${params.videoId}/captions`);
    setCaptions(result);
  }, [params.videoId]);

  const refreshAll = useCallback(async () => {
    try {
      await Promise.all([refreshVideo(), refreshScenes(), refreshCaptions()]);
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to refresh studio.");
    }
  }, [refreshVideo, refreshScenes, refreshCaptions]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const state = await apiRequest<VideoStatusResponse>(`/videos/${params.videoId}`);
        if (!active) return;
        setVideo(state);
        if (!TERMINAL_STATUSES.has(state.status)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        if (active) {
          setError("Unable to load video status. Retrying…");
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      }
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [params.videoId, pollVersion]);

  useEffect(() => {
    if (video?.status !== "ready") return;
    let active = true;
    Promise.all([
      apiRequest<StoryboardScene[]>(`/videos/${params.videoId}/storyboard`),
      apiRequest<CaptionTrack>(`/videos/${params.videoId}/captions`),
    ]).then(([sceneData, captionData]) => {
      if (!active) return;
      setScenes(sceneData);
      setCaptions(captionData);
      setSelectedSceneId(id => id && sceneData.some(s => s.id === id) ? id : sceneData[0]?.id || null);
    }).catch(() => { if (active) setError("Unable to load scene editor."); });
    return () => { active = false; };
  }, [params.videoId, video?.status]);

  async function startRerender() {
    setRerendering(true);
    setError(null);
    try {
      await apiRequest(`/videos/${params.videoId}/rerender`, { method: "POST" });
      setVideo(current => current ? { ...current, status: "rendering", current_stage: "rerender_queued", progress: 85 } : current);
      setPollVersion(value => value + 1);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to queue re-render.");
    } finally { setRerendering(false); }
  }

  const selected = scenes.find(s => s.id === selectedSceneId) || null;
  const selectedCaption = captions?.scenes.find(s => s.scene_id === selectedSceneId);
  const { url: sceneImage } = useSignedMedia(selected?.visual_asset_id);
  const { url: videoUrl, error: mediaError } = useSignedMedia(video?.output_asset_id);
  const canEdit = video?.status === "ready";
  const portrait = video?.platform !== "youtube_landscape";
  const sceneCue = selectedCaption?.text || "";

  return (
    <DashboardShell wide>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <Link href={video?.project_id ? `/dashboard/projects/${video.project_id}` : "/dashboard"}
            className="mb-2 inline-flex items-center gap-2 text-xs text-[#a09db9] hover:text-white">
            <StudioIcon name="back" size={14} /> Back to project
          </Link>
          <h1 className="truncate text-xl font-bold sm:text-2xl">{video?.topic || "Video editor"}</h1>
          <p className="mt-1 text-xs text-[#9298b0]">
            {video?.platform?.replace(/_/g, " ") || "Loading platform"} · {video?.duration_seconds ?? "—"}s · {video?.status?.replace(/_/g, " ") || "Loading"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void refreshAll()} className="studio-button-secondary">
            <StudioIcon name="refresh" size={16} /> Refresh
          </button>
          {video?.needs_rerender && canEdit && <button type="button" disabled={rerendering}
            onClick={() => void startRerender()} className="studio-button">
            <StudioIcon name="sparkles" size={16} /> {rerendering ? "Queueing…" : "Re-render video"}
          </button>}
          {videoUrl && <a href={videoUrl} target="_blank" rel="noopener noreferrer" className="studio-button">
            <StudioIcon name="download" size={16} /> Open MP4
          </a>}
        </div>
      </div>

      {error && <p role="alert" className="mb-5 rounded-xl border border-rose-400/20 bg-rose-500/10 p-4 text-sm text-rose-300">{error}</p>}
      {video?.needs_rerender && <p className="mb-5 rounded-xl border border-amber-400/20 bg-amber-400/10 p-3 text-sm text-amber-200">
        Unsaved to video: your edited scenes or captions have changed. Click Re-render video to update the MP4.
      </p>}
      {video && video.status !== "ready" && <div className="studio-surface mb-5 p-4">
        <div className="mb-2 flex justify-between text-xs text-[#b4b6c9]">
          <span className="capitalize">{video.current_stage?.replace(/_/g, " ") || video.status.replace(/_/g, " ")}</span>
          <span>{video.progress}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full bg-violet-500 transition-all" style={{ width: `${video.progress}%` }} />
        </div>
        {video.error_message && <p className="mt-3 text-sm text-rose-300">{video.error_message}</p>}
        {video.output_asset_id && <p className="mt-2 text-xs text-[#a1a5bd]">The previous video remains available while re-rendering.</p>}
      </div>}

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(215px,0.8fr)_minmax(0,2fr)_minmax(275px,1fr)]">
        <aside className="studio-surface min-w-0 p-4">
          <div className="mb-5 flex items-center justify-between">
            <div><p className="studio-eyebrow mb-1">Storyboard</p><h2 className="text-sm font-semibold">Scenes</h2></div>
            <span className="rounded-lg bg-white/[0.05] px-2.5 py-1 text-xs text-[#b9bbd0]">{scenes.length}</span>
          </div>
          <div className="max-h-[650px] space-y-2 overflow-y-auto">
            {scenes.map(scene => {
              const active = scene.id === selectedSceneId;
              return <div key={scene.id}
                className={`flex w-full items-center gap-3 rounded-xl border p-2 text-left transition ${active
                  ? "border-violet-400/40 bg-violet-500/15"
                  : "border-transparent bg-[#111320] hover:border-white/10"}`}>
                <SceneFrame assetId={scene.visual_asset_id} selected={active} onSelect={() => { setSelectedSceneId(scene.id); setPreviewMode("scene"); }} />
                <button type="button" onClick={() => { setSelectedSceneId(scene.id); setPreviewMode("scene"); }}
                  className="min-w-0 flex-1 text-left">
                  <span className="block text-xs font-semibold text-white">Scene {scene.sequence}</span>
                  <span className="mt-1 block text-[11px] text-[#969bb5]">{scene.duration_seconds.toFixed(1)}s</span>
                  <span className="mt-1 block truncate text-[11px] text-[#b0b4c9]">{scene.narration}</span>
                </button>
              </div>;
            })}
            {!scenes.length && <p className="px-2 py-8 text-center text-xs text-[#9398b1]">
              {canEdit ? "No storyboard scenes found." : "Scenes appear when generation finishes."}
            </p>}
          </div>
        </aside>

        <section className="studio-surface min-w-0 overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-4">
            <div><p className="studio-eyebrow mb-1">Live workspace</p><h2 className="text-sm font-semibold">Preview</h2></div>
            <div className="inline-flex rounded-xl border border-white/10 bg-[#111320] p-1">
              {(["scene", "video"] as const).map(mode => <button type="button" key={mode}
                onClick={() => setPreviewMode(mode)} disabled={mode === "video" && !videoUrl}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition ${previewMode === mode
                  ? "bg-[#36304f] text-white" : "text-[#9da2ba] hover:text-white"} disabled:opacity-40`}>{mode === "scene" ? "Scene view" : "Rendered MP4"}</button>)}
            </div>
          </div>
          <div className="flex min-h-[500px] items-center justify-center bg-[#0f101b] px-4 py-7">
            <div className={`relative w-full overflow-hidden rounded-xl border border-white/10 bg-gradient-to-b from-[#292340] to-[#101120] shadow-2xl shadow-black/40 ${portrait ? "max-w-[270px]" : "max-w-[680px]"}`}
              style={{ aspectRatio: portrait ? "9 / 16" : "16 / 9" }}>
              {previewMode === "video" && videoUrl ? (
                <video controls playsInline preload="metadata" src={videoUrl} className="h-full w-full object-contain bg-black">
                  Your browser does not support playback.
                </video>
              ) : sceneImage ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={sceneImage} alt={`Generated visual for scene ${selected?.sequence || ""}`}
                    className="h-full w-full object-cover" />
                  <div className="pointer-events-none absolute inset-x-2 bottom-9 flex justify-center text-center">
                    {sceneCue && <span className={`max-w-[90%] px-2 py-1 text-base leading-tight studio-caption-${captions?.style || "classic"}`}>
                      {sceneCue}
                    </span>}
                  </div>
                </>
              ) : <div className="flex h-full flex-col items-center justify-center gap-3 text-[#a99de0]">
                <StudioIcon name="film" size={42} />
                <span className="text-xs">{mediaError ? "Preview unavailable" : "Select a scene to preview"}</span>
              </div>}
            </div>
          </div>
          <div className="border-t border-white/10 px-4 py-3 text-xs text-[#a2a6bc]">
            {previewMode === "scene" ? "Storyboard image and subtitle preview. The MP4 updates after re-rendering." :
              "Saved MP4 preview using a private, expiring media link."}
          </div>
        </section>

        <aside className="studio-surface min-w-0">
          <div className="grid grid-cols-2 border-b border-white/10 p-2">
            <button type="button" onClick={() => setTab("scene")}
              className={`flex items-center justify-center gap-2 rounded-lg px-3 py-3 text-xs font-semibold ${tab === "scene" ? "bg-violet-500/15 text-[#d1bfff]" : "text-[#9da1ba] hover:text-white"}`}>
              <StudioIcon name="layers" size={16} /> Scene
            </button>
            <button type="button" onClick={() => setTab("captions")}
              className={`flex items-center justify-center gap-2 rounded-lg px-3 py-3 text-xs font-semibold ${tab === "captions" ? "bg-violet-500/15 text-[#d1bfff]" : "text-[#9da1ba] hover:text-white"}`}>
              <StudioIcon name="captions" size={16} /> Captions
            </button>
          </div>
          <div className="max-h-[720px] overflow-y-auto p-4">
            {tab === "scene" ? <SceneInspector videoId={params.videoId}
              scene={selected} canEdit={canEdit} onUpdated={refreshAll} /> :
              <CaptionPanel videoId={params.videoId} track={captions} selectedSceneId={selectedSceneId}
                onSelect={id => { setSelectedSceneId(id); setPreviewMode("scene"); }}
                onUpdated={refreshAll} enabled={canEdit} />}
          </div>
        </aside>
      </div>

      <section className="studio-surface mt-5 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <StudioIcon name="film" size={17} className="text-[#b6a0fa]" /> Timeline
          </div>
          <span className="text-xs text-[#9b9fb8]">{scenes.length} scenes · {timeLabel(scenes.reduce((sum, scene) => sum + scene.duration_seconds, 0))} total</span>
        </div>
        <div className="overflow-x-auto p-4">
          <div className="flex min-w-max items-start gap-2">
            {scenes.map(scene => (
              <div key={scene.id} className="w-[100px] shrink-0">
                <SceneFrame assetId={scene.visual_asset_id} selected={scene.id === selectedSceneId}
                  onSelect={() => { setSelectedSceneId(scene.id); setPreviewMode("scene"); }} />
                <div className="mt-2 flex justify-between text-[10px] text-[#9da1b9]">
                  <span>Scene {scene.sequence}</span><span>{scene.duration_seconds.toFixed(1)}s</span>
                </div>
              </div>
            ))}
            {!scenes.length && <p className="text-xs text-[#9398af]">Timeline clips will appear after the first render.</p>}
          </div>
          <div className="mt-5 flex items-center gap-3 rounded-xl border border-violet-500/10 bg-violet-500/5 p-3 text-xs text-[#a6a6c7]">
            <StudioIcon name="audio" size={18} /> Voiceover and timed subtitles are aligned approximately by scene duration.
          </div>
        </div>
      </section>
    </DashboardShell>
  );
}
