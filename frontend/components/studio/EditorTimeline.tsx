"use client";

import { useMemo, useState } from "react";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { timeLabel } from "@/components/studio/CaptionPanel";
import { useSignedMedia } from "@/hooks/useSignedMedia";
import type { CaptionTrack, StoryboardScene } from "@/types";

const LABEL_WIDTH = 118;
const MIN_TIMELINE_WIDTH = 650;

type TimelineItem = StoryboardScene & { start: number; end: number };

function SceneThumbnail({ scene }: { scene: StoryboardScene }) {
  const { url } = useSignedMedia(scene.visual_asset_id);
  return url ? (
    // The signed private URL is returned dynamically by the backend.
    // eslint-disable-next-line @next/next/no-img-element
    <img alt="" src={url} className="h-full w-12 shrink-0 object-cover" draggable={false} />
  ) : (
    <span className="flex h-full w-10 shrink-0 items-center justify-center bg-white/5">
      <StudioIcon name="film" size={14}/>
    </span>
  );
}

export function moveSceneId(ids: string[], source: string, target: string): string[] {
  const from = ids.indexOf(source);
  const to = ids.indexOf(target);
  if (from < 0 || to < 0 || from === to) return ids;
  const next = [...ids];
  next.splice(to, 0, next.splice(from, 1)[0]);
  return next;
}

export function timelineItems(scenes: StoryboardScene[]): TimelineItem[] {
  let offset = 0;
  return [...scenes].sort((a, b) => a.sequence - b.sequence).map(scene => {
    const start = offset;
    offset += Math.max(0, scene.duration_seconds);
    return { ...scene, start, end: offset };
  });
}

export function EditorTimeline({
  scenes, captions, selectedSceneId, playhead, isPlaying, canEdit,
  isSaving, onSelect, onSeek, onMove, onTogglePlay, onOpenCaptions,
}: {
  scenes: StoryboardScene[];
  captions: CaptionTrack | null;
  selectedSceneId: string | null;
  playhead: number;
  isPlaying: boolean;
  canEdit: boolean;
  isSaving: boolean;
  onSelect: (id: string) => void;
  onSeek: (seconds: number) => void;
  onMove: (source: string, target: string) => void;
  onTogglePlay: () => void;
  onOpenCaptions: () => void;
}) {
  const [pixelsPerSecond, setPixelsPerSecond] = useState(42);
  const [draggedSceneId, setDraggedSceneId] = useState<string | null>(null);
  const items = useMemo(() => timelineItems(scenes), [scenes]);
  const total = items.at(-1)?.end ?? 0;
  const timelineWidth = Math.max(MIN_TIMELINE_WIDTH, Math.ceil(total * pixelsPerSecond));
  const marks = [];
  const step = pixelsPerSecond < 30 ? 10 : pixelsPerSecond < 55 ? 5 : 2;
  for (let time = 0; time <= total; time += step) marks.push(time);
  const cueById = new Map(captions?.scenes.map(s => [s.scene_id, s.text]) ?? []);
  const lane = "relative overflow-hidden rounded-lg border border-white/5";
  const label = "sticky left-0 z-10 flex w-[118px] shrink-0 items-center gap-2 border-r border-white/10 bg-[#151826] px-3 text-[11px] font-semibold text-[#a9adc2]";

  function seekFromRuler(event: React.MouseEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    onSeek(Math.min(total, Math.max(0, (event.clientX - bounds.left) / pixelsPerSecond)));
  }

  return (
    <section aria-label="Video editing timeline" className="studio-surface overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-3">
          <h2 className="inline-flex items-center gap-2 text-sm font-semibold">
            <StudioIcon name="layers" size={16} className="text-[#bdadff]" /> Timeline
          </h2>
          <span className="hidden text-xs text-[#8990aa] sm:inline">{items.length} clips · 3 aligned tracks</span>
          <span className="rounded-md bg-white/5 px-2 py-1 font-mono text-xs text-[#d7dbf4]">
            {timeLabel(Math.min(playhead, total))} / {timeLabel(total)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onTogglePlay} title={isPlaying ? "Pause preview" : "Play preview"}
            aria-label={isPlaying ? "Pause preview" : "Play preview"}
            className="rounded-lg border border-white/15 bg-white/10 p-2 text-white hover:bg-white/20">
            <StudioIcon name={isPlaying ? "pause" : "play"} size={15}/>
          </button>
          <button type="button" onClick={() => onSeek(0)} title="Go to start" aria-label="Go to start"
            className="rounded-lg border border-white/10 px-2 py-2 text-xs text-[#b4b9d1] hover:bg-white/10">
            00:00
          </button>
          <label htmlFor="timeline-zoom" className="ml-1 text-[11px] text-[#a1a6bc]">Zoom</label>
          <input id="timeline-zoom" aria-label="Timeline zoom" type="range" min="20" max="90" step="5"
            value={pixelsPerSecond} onChange={event => setPixelsPerSecond(Number(event.target.value))}
            className="w-20 accent-violet-400 sm:w-28"/>
          <span className="w-9 text-right text-[10px] text-[#989db5]">{Math.round(pixelsPerSecond / 42 * 100)}%</span>
        </div>
      </div>
      <p className="border-b border-white/5 px-4 py-2 text-[11px] text-[#8f96ad]">
        Drag scene clips to reorder, or use Alt + ← / → on a focused clip. Changes are saved to the project; re-render to update the MP4.
      </p>
      <div className="max-h-[400px] overflow-auto bg-[#11131e] pb-4">
        <div className="min-w-max">
          <div className="flex h-9 border-b border-white/10">
            <div className={label}>Time ruler</div>
            <div role="slider" tabIndex={0} aria-label="Move playhead" aria-valuemin={0}
              aria-valuemax={Math.ceil(total)} aria-valuenow={Math.round(Math.min(playhead,total))}
              aria-valuetext={timeLabel(playhead)}
              onKeyDown={event => {
                if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                  event.preventDefault();
                  onSeek(playhead + (event.key === "ArrowRight" ? 1 : -1));
                }
                if (event.key === "Home") { event.preventDefault(); onSeek(0); }
                if (event.key === "End") { event.preventDefault(); onSeek(total); }
              }}
              onClick={seekFromRuler}
              className="relative h-full cursor-crosshair bg-[#131723] outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
              style={{ width: timelineWidth }}>
              {marks.map(time => (
                <div key={time} className="pointer-events-none absolute top-0 h-full border-l border-white/15" style={{ left: time * pixelsPerSecond }}>
                  <span className="pl-1.5 font-mono text-[10px] text-[#848da5]">{timeLabel(time)}</span>
                </div>
              ))}
            </div>
          </div>
          {([
            { id: "video", title: "Video", icon: "film" as const, color: "border-teal-500/40 bg-[#10323a]" },
            { id: "captions", title: "Captions", icon: "captions" as const, color: "border-orange-400/30 bg-[#372a28]" },
            { id: "voice", title: "Voiceover", icon: "audio" as const, color: "border-sky-400/30 bg-[#193045]" },
          ] as const).map(track => (
            <div key={track.id} className={`flex ${track.id === "video" ? "h-[86px]" : "h-[56px]"} border-b border-white/5`}>
              <div className={label}><StudioIcon name={track.icon} size={15}/>{track.title}</div>
              <div className="relative flex h-full items-center" style={{ width: timelineWidth }}>
                {items.map(item => {
                  const selected = selectedSceneId === item.id;
                  const width = item.duration_seconds * pixelsPerSecond;
                  return <div key={item.id}
                    className="absolute top-1/2 -translate-y-1/2 px-[2px]"
                    style={{ left: item.start * pixelsPerSecond, width }}>
                    {track.id === "video" ? (
                      <button type="button" draggable={canEdit && !isSaving}
                        aria-label={`Scene ${item.sequence}, ${item.duration_seconds.toFixed(1)} seconds. Drag to reorder.`}
                        aria-pressed={selected}
                        onDragStart={event => {
                          setDraggedSceneId(item.id);
                          event.dataTransfer.setData("text/plain", item.id);
                          event.dataTransfer.effectAllowed = "move";
                        }}
                        onDragEnd={() => setDraggedSceneId(null)}
                        onDragOver={event => { if (canEdit) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } }}
                        onDrop={event => {
                          event.preventDefault();
                          const source = event.dataTransfer.getData("text/plain") || draggedSceneId;
                          if (canEdit && !isSaving && source && source !== item.id) onMove(source, item.id);
                          setDraggedSceneId(null);
                        }}
                        onKeyDown={event => {
                          if (canEdit && event.altKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
                            event.preventDefault();
                            const other = items[item.sequence - 1 + (event.key === "ArrowLeft" ? -1 : 1)];
                            if (other) onMove(item.id, other.id);
                          }
                        }}
                        onClick={() => { onSelect(item.id); onSeek(item.start); }}
                        className={`flex h-[73px] w-full items-center gap-1 overflow-hidden rounded-md border text-left transition ${track.color}
                          ${selected ? "ring-2 ring-violet-400 ring-offset-1 ring-offset-[#11131e]" : "hover:brightness-125"}
                          ${draggedSceneId === item.id ? "opacity-50" : ""} ${canEdit ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"}`}>
                        <SceneThumbnail scene={item}/>
                        <span className="min-w-0 flex-1 px-1">
                          <span className="block truncate text-[11px] font-bold text-white">Scene {item.sequence}</span>
                          <span className="block text-[10px] text-[#a4c6cb]">{item.duration_seconds.toFixed(1)}s</span>
                        </span>
                      </button>
                    ) : (
                      <button type="button"
                        onClick={() => { onSelect(item.id); onSeek(item.start); if (track.id === "captions") onOpenCaptions(); }}
                        className={`${lane} h-10 w-full px-2 text-left text-[11px] leading-tight
                          ${track.color} ${selected ? "ring-1 ring-violet-400" : ""} hover:brightness-125`}>
                        <span className="block truncate text-[#e4e7ef]">
                          {track.id === "captions"
                            ? captions?.style === "none" ? "(Hidden)" : cueById.get(item.id) || "(Empty)"
                            : item.narration || "(No narration)"}
                        </span>
                      </button>
                    )}
                  </div>;
                })}
                <div className="pointer-events-none absolute bottom-0 top-0 z-10 w-[2px] bg-[#f4d269] shadow-[0_0_8px_#f4d26975]"
                  style={{ left: Math.min(Math.max(playhead, 0), total) * pixelsPerSecond }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap justify-between gap-2 border-t border-white/10 px-4 py-2 text-[11px] text-[#9ea4bd]">
        <span>Video clips, estimated caption cues and saved narration stay linked when scenes move.</span>
        {isSaving && <span role="status" className="text-violet-300">Saving timeline…</span>}
      </div>
    </section>
  );
}
