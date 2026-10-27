"use client";

import { useEffect, useState } from "react";
import { apiRequest, ApiError } from "@/lib/api/client";
import type { StoryboardScene } from "@/types";

type Transition = StoryboardScene["transition_in"];

export function ClipTimingInspector({ videoId, scene, canEdit, onUpdated }: {
  videoId: string;
  scene: StoryboardScene;
  canEdit: boolean;
  onUpdated: () => Promise<void>;
}) {
  const [duration, setDuration] = useState(String(scene.duration_seconds));
  const [transition, setTransition] = useState<Transition>(scene.transition_in ?? "cut");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    setDuration(String(scene.duration_seconds));
    setTransition(scene.transition_in ?? "cut");
    setError(null);
    setFeedback(null);
  }, [scene.id, scene.duration_seconds, scene.transition_in]);

  const maxDuration = Math.min(scene.max_duration_seconds ?? scene.duration_seconds, 60);
  const parsed = Number(duration);
  const validDuration = Number.isFinite(parsed) && parsed >= 0.5 && parsed <= maxDuration;
  const durationChanged = validDuration && Math.abs(parsed - scene.duration_seconds) > 0.001;
  const transitionChanged = transition !== (scene.transition_in ?? "cut");
  const changed = durationChanged || transitionChanged;

  async function saveEdits() {
    if (!canEdit || !validDuration || !changed) return;
    setSaving(true);
    setError(null);
    setFeedback(null);
    try {
      await apiRequest(`/videos/${videoId}/storyboard/scenes/${scene.id}/edit`, {
        method: "PATCH",
        body: {
          duration_seconds: Math.round(parsed * 100) / 100,
          transition_in: transition,
        },
      });
      await onUpdated();
      setFeedback("Clip edit saved. Re-render to apply it to the MP4.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not save clip changes.");
    } finally {
      setSaving(false);
    }
  }

  return <div className="border-t border-white/10 pt-5">
    <p className="studio-eyebrow mb-2">Clip editing</p>
    <h4 className="mb-3 text-sm font-semibold text-white">Trim & transition</h4>

    <label htmlFor="clip-duration" className="block text-xs font-semibold text-[#c5c9da]">
      Playback duration
    </label>
    <div className="mt-2 flex items-center gap-3">
      <input id="clip-duration" type="number" min={0.5} max={maxDuration} step={0.1}
        inputMode="decimal" disabled={!canEdit || saving}
        value={duration} onChange={event => setDuration(event.target.value)}
        aria-invalid={!validDuration}
        className="studio-input min-w-0 flex-1" />
      <span className="shrink-0 text-xs text-[#a0a6be]">seconds</span>
    </div>
    <input type="range" aria-label="Trim clip end" min={0.5}
      max={Math.max(0.5, maxDuration)} step={0.1}
      value={validDuration ? parsed : scene.duration_seconds}
      disabled={!canEdit || saving || maxDuration <= 0.5}
      onChange={event => setDuration(event.target.value)}
      className="mt-3 w-full accent-violet-400"/>
    <p className="mt-1 text-[11px] leading-relaxed text-[#939ab5]">
      Original: {maxDuration.toFixed(1)}s. This shortens the end of the clip,
      including its narration and subtitle timing, without deleting its source media.
    </p>
    {!validDuration && <p role="alert" className="mt-2 text-xs text-rose-300">
      Enter a duration between 0.5s and {maxDuration.toFixed(1)}s.
    </p>}
    <button type="button" className="mt-2 text-xs text-violet-300 hover:text-white"
      disabled={!canEdit || saving || maxDuration <= scene.duration_seconds}
      onClick={() => setDuration(String(maxDuration))}>
      Restore original length
    </button>

    <label htmlFor="clip-transition" className="mt-5 block text-xs font-semibold text-[#c5c9da]">
      Transition into this scene
    </label>
    <select id="clip-transition" value={transition}
      onChange={event => setTransition(event.target.value as Transition)}
      disabled={!canEdit || saving} className="studio-input mt-2">
      <option value="cut">Cut (instant)</option>
      <option value="fade_black">Fade through black (0.25s)</option>
    </select>
    <p className="mt-2 text-[11px] leading-relaxed text-[#939ab5]">
      {scene.sequence === 1
        ? "The first scene has no preceding clip; its incoming transition has no effect until reordered."
        : "Fade applies to the end of the previous clip and the start of this one, including audio."}
    </p>

    <button type="button" className="studio-button mt-4 w-full"
      disabled={!canEdit || saving || !validDuration || !changed}
      onClick={() => void saveEdits()}>
      {saving ? "Saving clip…" : "Save clip edits"}
    </button>
    {feedback && <p role="status" className="mt-2 text-xs text-emerald-300">{feedback}</p>}
    {error && <p role="alert" className="mt-2 text-xs text-rose-300">{error}</p>}
  </div>;
}
