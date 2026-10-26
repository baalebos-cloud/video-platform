"use client";

import { useEffect, useState } from "react";
import { apiRequest, ApiError } from "@/lib/api/client";
import { StudioIcon } from "@/components/ui/StudioIcon";
import type { CaptionScene, CaptionStyle, CaptionTrack } from "@/types";

const STYLES: { id: CaptionStyle; name: string; description: string }[] = [
  { id: "none", name: "Clean video", description: "No burned-in captions" },
  { id: "classic", name: "Classic", description: "Crisp & readable" },
  { id: "bold", name: "Bold", description: "High impact" },
  { id: "social", name: "Social", description: "Bright highlight" },
  { id: "minimal", name: "Minimal", description: "Understated" },
];

export function timeLabel(seconds: number): string {
  const minute = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${String(minute).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

export function CaptionPanel({ videoId, track, selectedSceneId, onSelect, onUpdated, enabled }: {
  videoId: string;
  track: CaptionTrack | null;
  selectedSceneId: string | null;
  onSelect: (sceneId: string) => void;
  onUpdated: () => Promise<void>;
  enabled: boolean;
}) {
  const current: CaptionScene | undefined = track?.scenes.find(s => s.scene_id === selectedSceneId);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [styleSaving, setStyleSaving] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState<Record<string, string>>({});
  const [bulkSaving, setBulkSaving] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    setText(current?.text ?? "");
    setFeedback(null);
    setError(null);
  }, [current?.scene_id, current?.text]);

  useEffect(() => {
    setBulkText(Object.fromEntries((track?.scenes || []).map(scene => [scene.scene_id, scene.text])));
  }, [track?.scenes]);

  async function saveAllCaptions() {
    if (!track || !enabled) return;
    setBulkSaving(true);
    setError(null);
    try {
      const edits = track.scenes.filter(scene => bulkText[scene.scene_id] !== scene.text)
        .map(scene => ({scene_id: scene.scene_id, text: bulkText[scene.scene_id] ?? ""}));
      if (!edits.length) return;
      await apiRequest(`/videos/${videoId}/captions/batch`, {method: "PATCH", body: {edits}});
      await onUpdated();
      setFeedback("All updated captions saved. Re-render to update the video.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to save multiple captions.");
    } finally { setBulkSaving(false); }
  }

  async function exportSrt() {
    setExporting(true);
    setError(null);
    try {
      const response = await fetch(`/api/gateway/videos/${videoId}/captions/srt`,
        {credentials: "same-origin", cache: "no-store"});
      if (!response.ok) throw new Error("Subtitles unavailable");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `baalebos-${videoId}.srt`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Unable to export SRT subtitles.");
    } finally { setExporting(false); }
  }

  async function saveCaption() {
    if (!current) return;
    setSaving(true);
    setError(null);
    setFeedback(null);
    try {
      await apiRequest(`/videos/${videoId}/captions`, {
        method: "PATCH", body: { scene_id: current.scene_id, text },
      });
      await onUpdated();
      setFeedback("Subtitle saved. Re-render to update the exported MP4.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to save subtitle.");
    } finally {
      setSaving(false);
    }
  }

  async function setStyle(style: CaptionStyle) {
    if (style === track?.style) return;
    setStyleSaving(true);
    setError(null);
    try {
      await apiRequest(`/videos/${videoId}/captions`, {
        method: "PATCH", body: { style },
      });
      await onUpdated();
      setFeedback("Caption style saved. Re-render to apply it to your MP4.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to save caption style.");
    } finally {
      setStyleSaving(false);
    }
  }

  return <div className="space-y-6">
    <div>
      <p className="studio-eyebrow mb-2">Subtitle appearance</p>
      <h3 className="mb-3 text-base font-semibold">Caption styles</h3>
      <div className="grid grid-cols-2 gap-2">
        {STYLES.map(style => (
          <button key={style.id} type="button" disabled={!enabled || styleSaving}
            onClick={() => void setStyle(style.id)}
            aria-pressed={track?.style === style.id}
            className={`rounded-xl border p-3 text-left transition ${track?.style === style.id
              ? "border-violet-400/70 bg-violet-400/10"
              : "border-white/10 bg-white/[0.025] hover:border-white/25"} disabled:cursor-not-allowed disabled:opacity-50`}>
            <span className={`mb-2 block text-lg studio-caption-${style.id}`}>{style.id === "none" ? "×" : "Aa"}</span>
            <strong className="block text-xs text-white">{style.name}</strong>
            <small className="mt-1 block text-[10px] text-[#969bb5]">{style.description}</small>
          </button>
        ))}
      </div>
    </div>
    <div className="border-t border-white/10 pt-5">
      <p className="studio-eyebrow mb-2">Subtitle timeline</p>
      <h3 className="mb-3 text-base font-semibold">Scene captions</h3>
      <div className="max-h-[270px] space-y-2 overflow-y-auto pr-1">
        {track?.scenes.map(cue => (
          <button type="button" key={cue.scene_id} onClick={() => onSelect(cue.scene_id)}
            className={`w-full rounded-xl border px-3 py-3 text-left transition ${selectedSceneId === cue.scene_id
              ? "border-violet-400/50 bg-violet-500/10"
              : "border-white/[0.08] bg-[#111320] hover:border-white/20"}`}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-semibold text-[#ccbaff]">Scene {cue.sequence}</span>
              <span className="font-mono text-[10px] text-[#979cb7]">
                {timeLabel(cue.start_seconds)} – {timeLabel(cue.end_seconds)}
              </span>
            </div>
            <p className="line-clamp-2 text-xs leading-relaxed text-[#dee0ed]">
              {cue.text || "(Captions hidden for this scene)"}
            </p>
          </button>
        ))}
        {track && !track.scenes.length && <p className="text-xs text-[#969bb5]">No subtitle scenes yet.</p>}
      </div>
    </div>
    {track && <div className="border-t border-white/10 pt-5">
      <h3 className="mb-2 text-sm font-semibold">Caption tools</h3>
      <p className="mb-3 text-xs text-[#9fa4bc]">
        Download editable subtitles or change several scene captions together.
        Export timings are estimated from the saved audio duration.
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="studio-button-secondary" disabled={exporting}
          onClick={() => void exportSrt()}>
          {exporting ? "Exporting…" : "Download SRT"}
        </button>
        <button type="button" className="studio-button-secondary"
          disabled={!enabled} onClick={() => setBulkOpen(value => !value)}>
          {bulkOpen ? "Close batch editor" : "Edit all captions"}
        </button>
      </div>
      {bulkOpen && <div className="mt-4 space-y-3">
        {track.scenes.map(cue => <label key={cue.scene_id} className="block text-xs text-[#b4b8cf]">
          Scene {cue.sequence}
          <textarea className="studio-input mt-1" rows={3} maxLength={1000}
            value={bulkText[cue.scene_id] ?? ""} disabled={!enabled || bulkSaving}
            onChange={event => setBulkText(prev => ({...prev,[cue.scene_id]:event.target.value}))}/>
        </label>)}
        <button type="button" className="studio-button"
          disabled={!enabled || bulkSaving || !track.scenes.some(
            scene => bulkText[scene.scene_id] !== scene.text)}
          onClick={() => void saveAllCaptions()}>
          {bulkSaving ? "Saving all…" : "Save changed captions"}
        </button>
      </div>}
    </div>}
    {current && <div className="border-t border-white/10 pt-5">
      <label htmlFor="caption-content" className="mb-2 block text-sm font-semibold">
        Edit scene {current.sequence} captions
      </label>
      <textarea id="caption-content" rows={4} maxLength={1000} value={text}
        disabled={!enabled} onChange={event => setText(event.target.value)}
        className="studio-input resize-y leading-relaxed" />
      <p className="mt-2 text-xs text-[#9b9eb8]">You are editing on-screen subtitles, not the voiceover.</p>
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-[11px] text-[#8489a4]">{text.length}/1000</span>
        <button type="button" disabled={!enabled || saving || text === current.text}
          onClick={() => void saveCaption()} className="studio-button">
          <StudioIcon name="check" size={16} /> {saving ? "Saving…" : "Save captions"}
        </button>
      </div>
    </div>}
    <p className="text-xs leading-relaxed text-[#8b90ac]">
      Timings are based on each scene&apos;s narration duration, not word-by-word speech alignment.
    </p>
    {feedback && <p role="status" className="text-xs text-emerald-300">{feedback}</p>}
    {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
  </div>;
}
