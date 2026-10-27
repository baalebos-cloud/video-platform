"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { DashboardShell } from "@/components/dashboard/Shell";
import { CaptionPanel, timeLabel } from "@/components/studio/CaptionPanel";
import { EditorTimeline, moveSceneId, timelineItems } from "@/components/studio/EditorTimeline";
import { SceneInspector } from "@/components/studio/SceneInspector";
import { StudioIcon, type StudioIconName } from "@/components/ui/StudioIcon";
import { useSignedMedia } from "@/hooks/useSignedMedia";
import { apiRequest, ApiError } from "@/lib/api/client";
import type { CaptionTrack, StoryboardScene, VideoStatusResponse } from "@/types";

const TERMINAL = new Set(["ready", "failed", "cancelled"]);
const POLL_MS = 3000;
type Tool = "media" | "captions" | "audio" | "effects";
type Inspector = "scene" | "captions";
type PreviewMode = "scene" | "video";

const TOOLS: { id: Tool; label: string; icon: StudioIconName }[] = [
  { id: "media", label: "Media", icon: "film" },
  { id: "captions", label: "Captions", icon: "captions" },
  { id: "audio", label: "Audio", icon: "audio" },
  { id: "effects", label: "Effects", icon: "sparkles" },
];

function SceneLibraryFrame({ scene, active, onChoose }: {
  scene: StoryboardScene; active: boolean; onChoose: () => void;
}) {
  const { url } = useSignedMedia(scene.visual_asset_id);
  return <button type="button" onClick={onChoose} aria-pressed={active}
    className={`flex w-full items-center gap-3 rounded-xl border p-2 text-left transition
      ${active ? "border-violet-400/60 bg-violet-500/15" : "border-white/5 bg-[#111320] hover:border-white/20"}`}>
    <div className="h-[66px] w-[65px] shrink-0 overflow-hidden rounded-lg bg-[#23283a]">
      {url ? (
        // Signed media comes from the authenticated API at runtime.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="h-full w-full object-cover"/>
      ) : <span className="flex h-full items-center justify-center text-[#9288c5]"><StudioIcon name="film"/></span>}
    </div>
    <span className="min-w-0 flex-1">
      <span className="block text-xs font-bold text-white">Scene {scene.sequence}</span>
      <span className="mt-1 block text-[11px] text-[#a5abc4]">{scene.duration_seconds.toFixed(1)}s · Saved asset</span>
      <span className="mt-1 block truncate text-[11px] text-[#c1c4d5]">{scene.narration}</span>
    </span>
  </button>;
}

export default function VideoEditorPage() {
  const params = useParams<{ videoId: string }>();
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [video, setVideo] = useState<VideoStatusResponse | null>(null);
  const [scenes, setScenes] = useState<StoryboardScene[]>([]);
  const [captions, setCaptions] = useState<CaptionTrack | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [tool, setTool] = useState<Tool>("media");
  const [inspector, setInspector] = useState<Inspector>("scene");
  const [previewMode, setPreviewMode] = useState<PreviewMode>("video");
  const [playhead, setPlayhead] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [pollVersion, setPollVersion] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const [rerendering, setRerendering] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const refreshVideo = useCallback(async () => {
    const result = await apiRequest<VideoStatusResponse>(`/videos/${params.videoId}`);
    setVideo(result);
  }, [params.videoId]);

  const refreshScenes = useCallback(async () => {
    const result = await apiRequest<StoryboardScene[]>(`/videos/${params.videoId}/storyboard`);
    setScenes(result);
    setSelectedSceneId(current => current && result.some(s => s.id === current) ? current : result[0]?.id ?? null);
  }, [params.videoId]);

  const refreshCaptions = useCallback(async () => {
    setCaptions(await apiRequest<CaptionTrack>(`/videos/${params.videoId}/captions`));
  }, [params.videoId]);

  const refreshAll = useCallback(async () => {
    try {
      await Promise.all([refreshVideo(), refreshScenes(), refreshCaptions()]);
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to refresh editor.");
    }
  }, [refreshVideo, refreshScenes, refreshCaptions]);

  useEffect(() => {
    let active = true;
    let timeout: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const state = await apiRequest<VideoStatusResponse>(`/videos/${params.videoId}`);
        if (!active) return;
        setVideo(state);
        if (!TERMINAL.has(state.status)) timeout = setTimeout(poll, POLL_MS);
      } catch {
        if (active) {
          setError("Unable to load video status. Retrying…");
          timeout = setTimeout(poll, POLL_MS);
        }
      }
    }
    void poll();
    return () => { active = false; clearTimeout(timeout); };
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
      setSelectedSceneId(id => id && sceneData.some(s => s.id === id) ? id : sceneData[0]?.id ?? null);
    }).catch(() => { if (active) setError("Unable to load editor scenes."); });
    return () => { active = false; };
  }, [params.videoId, video?.status]);

  const items = useMemo(() => timelineItems(scenes), [scenes]);
  const pendingNarration = scenes.filter(scene => scene.audio_state === "pending").length;
  const totalSeconds = items.at(-1)?.end ?? 0;
  const selected = scenes.find(s => s.id === selectedSceneId) ?? null;
  const selectedCaption = captions?.scenes.find(s => s.scene_id === selectedSceneId);
  const { url: sceneImage } = useSignedMedia(selected?.visual_asset_id);
  const { url: renderedUrl, error: mediaError } = useSignedMedia(video?.output_asset_id);
  const canEdit = video?.status === "ready";
  const portrait = video?.platform !== "youtube_landscape";
  const previewIsStale = Boolean(video?.needs_rerender);
  const canSeekRendered = Boolean(renderedUrl && !previewIsStale);

  const seekTo = useCallback((seconds: number) => {
    const safeTime = Math.max(0, Math.min(seconds, totalSeconds));
    setPlayhead(safeTime);
    const frame = items.find(s => safeTime >= s.start && (safeTime < s.end || s.end === totalSeconds)) ?? items.at(-1);
    if (frame) setSelectedSceneId(frame.id);
    if (canSeekRendered && videoRef.current) videoRef.current.currentTime = safeTime;
  }, [canSeekRendered, items, totalSeconds]);

  const chooseScene = useCallback((id: string) => {
    const item = items.find(s => s.id === id);
    setSelectedSceneId(id);
    if (item) {
      setPlayhead(item.start);
      if (canSeekRendered && videoRef.current) videoRef.current.currentTime = item.start;
    }
  }, [items, canSeekRendered]);

  const togglePlay = useCallback(() => {
    const player = videoRef.current;
    if (!player || !canSeekRendered) {
      setPreviewMode("scene");
      setFeedback("Re-render the current edits before playing the updated timeline.");
      return;
    }
    setPreviewMode("video");
    if (player.paused) void player.play().catch(() => setError("Preview playback unavailable."));
    else player.pause();
  }, [canSeekRendered]);

  const moveScene = useCallback(async (from: string, to: string) => {
    if (!canEdit || reordering) return;
    const ids = scenes.map(s => s.id);
    const nextIds = moveSceneId(ids, from, to);
    if (nextIds === ids) return;
    setReordering(true);
    setError(null);
    setFeedback(null);
    videoRef.current?.pause();
    try {
      await apiRequest(`/videos/${params.videoId}/storyboard/order`, {
        method: "PATCH", body: { scene_ids: nextIds },
      });
      await Promise.all([refreshVideo(), refreshScenes(), refreshCaptions()]);
      setPreviewMode("scene");
      setPlayhead(0);
      setSelectedSceneId(from);
      setFeedback("Scene order saved. Re-render to update the downloadable MP4.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to save the scene order.");
      await refreshScenes().catch(() => undefined);
    } finally {
      setReordering(false);
    }
  }, [canEdit, reordering, scenes, params.videoId, refreshVideo, refreshScenes, refreshCaptions]);

  async function startRerender() {
    setRerendering(true);
    setError(null);
    try {
      await apiRequest(`/videos/${params.videoId}/rerender`, { method: "POST" });
      setVideo(current => current ? { ...current, status: "rendering", current_stage: "rerender_queued", progress: 85 } : current);
      setFeedback("Your timeline edits are being rendered into a new MP4.");
      setPollVersion(v => v + 1);
      setExportOpen(false);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to start re-render.");
    } finally { setRerendering(false); }
  }

  async function downloadVideo() {
    if (!video?.output_asset_id) return;
    setDownloading(true);
    setError(null);
    try {
      const asset = await apiRequest<{ signed_url: string }>(
        `/assets/${video.output_asset_id}?download=true`,
      );
      window.location.assign(asset.signed_url);
      setExportOpen(false);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to download MP4.");
    } finally { setDownloading(false); }
  }

  async function retryVideo() {
    setRetrying(true);
    setError(null);
    try {
      const result = await apiRequest<{ video_id: string }>(
        `/videos/${params.videoId}/retry`, { method: "POST" },
      );
      router.push(`/studio/video/${result.video_id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to retry video.");
      setRetrying(false);
    }
  }

  return (
    <DashboardShell editorMode>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-4">
        <div className="min-w-0 flex-1">
          <Link href={video?.project_id ? `/dashboard/projects/${video.project_id}` : "/dashboard"}
            className="mb-2 inline-flex items-center gap-2 text-xs text-[#a3a8c2] hover:text-white">
            <StudioIcon name="back" size={14}/> Back to project
          </Link>
          <h1 className="max-w-[950px] truncate text-base font-semibold sm:text-lg">{video?.topic || "Video Editor"}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-[#9da5bc]">
            <span>{video?.platform?.replace(/_/g, " ") ?? "Video"}</span>
            <span>·</span><span>{video?.duration_seconds ?? "—"}s requested</span>
            <span>·</span><span className={video?.status === "ready" ? "text-emerald-300" : ""}>{video?.status ?? "loading"}</span>
            <span>·</span>
            <span>{video?.needs_rerender ? "Edits saved · export out of date" : "Synced to last render"}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => void refreshAll()} className="studio-button-secondary">
            <StudioIcon name="refresh" size={15}/> Refresh
          </button>
          {video?.status === "failed" && <button type="button" className="studio-button"
            disabled={retrying} onClick={() => void retryVideo()}>
            <StudioIcon name="refresh" size={16}/> {retrying ? "Creating retry…" : "Retry as new video"}
          </button>}
          {video?.needs_rerender && canEdit && <button type="button" className="studio-button-secondary"
            disabled={rerendering} onClick={() => void startRerender()}>
            <StudioIcon name="refresh" size={16}/> {rerendering ? "Queueing…" : "Re-render edits"}
          </button>}
          <button type="button" className="studio-button" onClick={() => setExportOpen(true)}
            disabled={!video?.output_asset_id || pendingNarration > 0}>
            <StudioIcon name="download" size={17}/> Export
          </button>
        </div>
      </div>

      {error && <p role="alert" className="mb-4 rounded-lg border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-300">{error}</p>}
      {feedback && <p role="status" className="mb-4 rounded-lg border border-teal-400/20 bg-teal-500/10 p-3 text-sm text-teal-200">{feedback}</p>}
      {pendingNarration > 0 && <p role="status" className="mb-4 rounded-lg border border-violet-400/20 bg-violet-500/10 px-4 py-3 text-xs text-violet-100">
        Your recorded-voice video has {pendingNarration} scene{pendingNarration === 1 ? "" : "s"} still awaiting narration.
        Select each scene, record or upload your voice, then click Re-render edits. Export is disabled until the recordings are saved.
      </p>}
      {video?.needs_rerender && <p className="mb-4 rounded-lg border border-amber-400/20 bg-amber-400/10 px-4 py-2 text-xs text-amber-200">
        Scene order, visuals or captions have changed. The existing MP4 is still available, but it will not include your edits until you re-render.
      </p>}
      {video && video.status !== "ready" && <div className="studio-surface mb-4 p-4">
        <div className="mb-2 flex justify-between text-xs text-[#bbc0d4]">
          <span className="capitalize">{video.current_stage?.replace(/_/g, " ") || video.status.replace(/_/g, " ")}</span>
          <span>{video.progress}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full bg-violet-500 transition-all" style={{width:`${video.progress}%`}}/>
        </div>
        {video.error_message && <p className="mt-3 text-xs text-rose-300">{video.error_message}</p>}
      </div>}

      <div className="mb-4 grid min-w-0 gap-3 lg:grid-cols-[minmax(265px,0.95fr)_minmax(340px,2.2fr)_minmax(290px,1fr)]">
        <aside aria-label="Editor tools" className="studio-surface flex min-h-[500px] min-w-0 overflow-hidden">
          <nav aria-label="Editing tools" className="flex w-[70px] shrink-0 flex-col gap-2 border-r border-white/10 bg-[#11131e] px-2 py-4">
            {TOOLS.map(item => <button type="button" key={item.id}
              onClick={() => { setTool(item.id); if (item.id === "captions") setInspector("captions"); }}
              aria-pressed={tool === item.id} title={item.label}
              className={`flex flex-col items-center gap-1.5 rounded-lg px-1 py-3 text-[10px] transition
                ${tool === item.id ? "bg-violet-500/20 text-[#d4c5ff]" : "text-[#929ab2] hover:bg-white/5 hover:text-white"}`}>
              <StudioIcon name={item.icon} size={20}/>{item.label}
            </button>)}
          </nav>
          <div className="min-w-0 flex-1 p-3">
            <p className="studio-eyebrow mb-1">{tool === "media" ? "Media library" : tool === "captions" ? "Subtitle tools" : tool === "audio" ? "Audio assets" : "Visual effects"}</p>
            <h2 className="mb-4 text-sm font-semibold">
              {tool === "media" ? `Generated scenes (${scenes.length})` : tool === "captions" ? "Editable captions" : tool === "audio" ? "Scene voiceovers" : "Cinematic styling"}
            </h2>
            {tool === "media" && <div className="max-h-[540px] space-y-2 overflow-y-auto pr-1">
              {items.map(scene => <SceneLibraryFrame key={scene.id} scene={scene}
                active={scene.id === selectedSceneId} onChoose={() => { chooseScene(scene.id); setInspector("scene"); }}/>)}
              {!items.length && <p className="py-6 text-xs text-[#989db6]">Your generated clips will appear here.</p>}
              <p className="pt-2 text-[11px] leading-relaxed text-[#838ba6]">Drag clips in the timeline to change their order. Scene assets remain attached to their original clip.</p>
            </div>}
            {tool === "captions" && <div className="space-y-3 text-xs text-[#b1b6ca]">
              <p>Captions come from narration and can be corrected before export.</p>
              <p className="text-[#8f96ad]">{captions?.scenes.length ?? 0} scene cues · {captions?.style === "none" ? "captions hidden" : captions?.style ?? "loading"} style</p>
              <button type="button" className="studio-button-secondary w-full" onClick={() => setInspector("captions")}>
                <StudioIcon name="edit" size={14}/> Open caption editor
              </button>
              <p>Subtitle timings are scene-based estimates, not speech-aligned word timestamps.</p>
            </div>}
            {tool === "audio" && <div className="max-h-[510px] space-y-2 overflow-y-auto">
              <p className="mb-3 text-xs text-[#9ea5bc]">The generated narration is saved with each scene and displayed on the voice track.</p>
              {items.map(item => <button type="button" key={item.id} onClick={() => { chooseScene(item.id); setInspector("scene"); }}
                className="w-full rounded-lg border border-white/5 bg-white/[0.03] p-3 text-left text-xs hover:bg-white/[0.06]">
                <span className="mb-1 block font-semibold text-sky-200">Scene {item.sequence} · {item.duration_seconds.toFixed(1)}s</span>
                <span className="line-clamp-3 leading-relaxed text-[#bac0d4]">{item.narration || "No narration"}</span>
              </button>)}
            </div>}
            {tool === "effects" && <div className="space-y-3 text-xs leading-relaxed text-[#abb2ca]">
              <div className="rounded-xl border border-violet-400/15 bg-violet-500/5 p-3">
                <StudioIcon name="sparkles" size={20} className="mb-2 text-violet-300"/>
                <p className="font-semibold text-white">Cinematic motion</p>
                <p className="mt-2">Your renderer supports restrained motion on generated still images. Stock footage uses its original movement.</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                <p className="mb-1 font-semibold text-white">Fade transitions</p>
                <p>Choose a scene, then open Clip → Trim & transition to apply a 0.25-second fade through black with an audio fade.</p>
              </div>
              <p className="text-[#8d93af]">Custom keyframes, layered effects and arbitrary filter presets are not yet supported by the renderer.</p>
            </div>}
          </div>
        </aside>

        <section aria-label="Video preview" className="studio-surface flex min-w-0 flex-col overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-3">
            <div><p className="studio-eyebrow mb-1">Player</p><h2 className="text-sm font-semibold">Preview</h2></div>
            <div className="inline-flex rounded-lg border border-white/10 bg-[#10121d] p-1">
              <button type="button" onClick={() => setPreviewMode("scene")} aria-pressed={previewMode === "scene"}
                className={`rounded-md px-3 py-1.5 text-xs ${previewMode === "scene" ? "bg-violet-500/25 text-white" : "text-[#a1a7bd]"}`}>Scene</button>
              <button type="button" onClick={() => setPreviewMode("video")} aria-pressed={previewMode === "video"}
                disabled={!renderedUrl} className={`rounded-md px-3 py-1.5 text-xs disabled:opacity-30 ${previewMode === "video" ? "bg-violet-500/25 text-white" : "text-[#a1a7bd]"}`}>Rendered MP4</button>
            </div>
          </div>
          <div className="flex min-h-[450px] flex-1 items-center justify-center bg-[#0b0d17] p-4">
            <div className={`relative w-full overflow-hidden rounded-md border border-white/10 bg-[#151626] shadow-2xl shadow-black/50
              ${portrait ? "max-w-[245px]" : "max-w-[700px]"}`}
              style={{aspectRatio:portrait ? "9 / 16" : "16 / 9"}}>
              <video ref={videoRef} controls playsInline preload="metadata" src={renderedUrl ?? undefined}
                aria-label="Last rendered video"
                onTimeUpdate={event => {
                  const t = event.currentTarget.currentTime;
                  setPlayhead(t);
                  if (!previewIsStale) {
                    const match = items.find(s => t >= s.start && t < s.end);
                    if (match) setSelectedSceneId(match.id);
                  }
                }}
                onPlay={() => setIsPlaying(true)} onPause={() => setIsPlaying(false)} onEnded={() => setIsPlaying(false)}
                className={`${previewMode === "video" ? "h-full w-full" : "hidden"} bg-black object-contain`}>
                Your browser does not support MP4 playback.
              </video>
              {previewMode === "scene" && (sceneImage ? <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={sceneImage} alt={`Preview of scene ${selected?.sequence ?? ""}`}
                  className="h-full w-full object-cover"/>
                {selectedCaption?.text && captions?.style !== "none" && <div className="pointer-events-none absolute inset-x-3 bottom-12 text-center">
                  <span className={`inline-block px-2 py-1 text-base studio-caption-${captions?.style || "classic"}`}>{selectedCaption.text}</span>
                </div>}
              </> : <div className="flex h-full flex-col items-center justify-center gap-3 text-[#959cb8]">
                <StudioIcon name="film" size={40}/>
                <span className="text-xs">{mediaError ? "Media unavailable" : "Select a scene to preview"}</span>
              </div>)}
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 px-4 py-3 text-[11px] text-[#afb4c9]">
            <span>{previewMode === "video" ? "Last rendered MP4" : `Storyboard scene ${selected?.sequence ?? "—"}`}</span>
            <span className="font-mono">{timeLabel(playhead)} / {timeLabel(totalSeconds)}</span>
            {previewIsStale && <span className="text-amber-300">Timeline changes not in MP4 yet</span>}
          </div>
        </section>

        <aside aria-label="Clip properties" className="studio-surface min-w-0 overflow-hidden">
          <div className="grid grid-cols-2 border-b border-white/10 p-2">
            {(["scene", "captions"] as const).map(tab => <button type="button" key={tab}
              onClick={() => setInspector(tab)} aria-pressed={inspector === tab}
              className={`flex items-center justify-center gap-2 rounded-lg px-2 py-3 text-xs font-semibold
                ${inspector === tab ? "bg-violet-500/20 text-[#d2c2ff]" : "text-[#999fb6] hover:text-white"}`}>
              <StudioIcon name={tab === "scene" ? "layers" : "captions"} size={15}/>
              {tab === "scene" ? "Clip" : "Captions"}
            </button>)}
          </div>
          <div className="max-h-[590px] overflow-y-auto p-4">
            {inspector === "scene" ? <>
              <SceneInspector videoId={params.videoId} scene={selected} canEdit={canEdit}
                onUpdated={async () => {
                  await refreshAll();
                  videoRef.current?.pause();
                  setPreviewMode("scene");
                  setPlayhead(0);
                }}/>
              {selected && <div className="mt-5 border-t border-white/10 pt-5">
                <p className="studio-eyebrow mb-3">Clip order</p>
                <div className="flex gap-2">
                  <button type="button" className="studio-button-secondary flex-1 !px-2 !text-xs"
                    disabled={!canEdit || reordering || selected.sequence <= 1}
                    onClick={() => { const previous = items[selected.sequence - 2]; if (previous) void moveScene(selected.id, previous.id); }}>
                    <StudioIcon name="back" size={14}/> Move left
                  </button>
                  <button type="button" className="studio-button-secondary flex-1 !px-2 !text-xs"
                    disabled={!canEdit || reordering || selected.sequence >= items.length}
                    onClick={() => { const next = items[selected.sequence]; if (next) void moveScene(selected.id, next.id); }}>
                    Move right <StudioIcon name="arrow" size={14}/>
                  </button>
                </div>
              </div>}
            </> : <CaptionPanel videoId={params.videoId} track={captions} selectedSceneId={selectedSceneId}
              onSelect={id => chooseScene(id)} onUpdated={refreshAll} enabled={canEdit}/>}
          </div>
        </aside>
      </div>

      <EditorTimeline scenes={scenes} captions={captions} selectedSceneId={selectedSceneId}
        playhead={playhead} isPlaying={isPlaying} canEdit={canEdit} isSaving={reordering}
        onSelect={chooseScene} onSeek={seekTo} onMove={(from,to) => void moveScene(from,to)}
        onTogglePlay={togglePlay} onOpenCaptions={() => setInspector("captions")}/>

      {exportOpen && <div role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setExportOpen(false); }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
        <section role="dialog" aria-modal="true" aria-label="Export video"
          className="w-full max-w-[520px] rounded-2xl border border-white/15 bg-[#191b27] p-6 shadow-2xl">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div><p className="studio-eyebrow mb-1">Export settings</p><h2 className="text-xl font-semibold">Download your video</h2></div>
            <button type="button" onClick={() => setExportOpen(false)} className="text-sm text-[#b5b9ce] hover:text-white" aria-label="Close export dialog">Close</button>
          </div>
          <p className="mb-4 text-xs text-[#a6aec6]">The current renderer uses the following fixed, verified output settings. Other resolutions and frame rates are not yet available.</p>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {[
              ["Format", "MP4"],
              ["Resolution", portrait ? "1080 × 1920" : "1920 × 1080"],
              ["Frame rate", "24 fps"],
              ["Video codec", "H.264"],
              ["Audio codec", "AAC"],
              ["Captions", captions?.style === "none" ? "Off" : captions?.style || "Classic"],
            ].map(([label, value]) => <div key={label} className="rounded-lg border border-white/5 bg-[#10121e] p-3">
              <dt className="text-xs text-[#8d96b0]">{label}</dt><dd className="mt-1 font-semibold text-white">{value}</dd>
            </div>)}
          </dl>
          {video?.needs_rerender && <p className="my-4 rounded-xl border border-amber-400/20 bg-amber-500/10 p-3 text-xs text-amber-200">
            Your saved timeline changes are not yet in the existing MP4. Re-render to include them, or download the previous version.
          </p>}
          <div className="mt-6 flex flex-wrap justify-end gap-2">
            <button type="button" onClick={() => setExportOpen(false)} className="studio-button-secondary">Cancel</button>
            {canEdit && video?.needs_rerender && <button type="button" className="studio-button-secondary"
              disabled={rerendering} onClick={() => void startRerender()}>
              {rerendering ? "Queueing…" : "Re-render edits"}
            </button>}
            <button type="button" className="studio-button" disabled={!video?.output_asset_id || downloading || pendingNarration > 0}
              onClick={() => void downloadVideo()}>
              <StudioIcon name="download" size={16}/> {downloading ? "Preparing…" : video?.needs_rerender ? "Download previous MP4" : "Download MP4"}
            </button>
          </div>
        </section>
      </div>}
    </DashboardShell>
  );
}
