"use client";

import { useEffect, useState } from "react";
import { apiRequest, ApiError } from "@/lib/api/client";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { ClipTimingInspector } from "@/components/studio/ClipTimingInspector";
import { PersonalNarrationPanel } from "@/components/studio/PersonalNarrationPanel";
import type { StoryboardScene } from "@/types";

export function SceneInspector({ videoId, scene, canEdit, onUpdated }: {
  videoId: string;
  scene: StoryboardScene | null;
  canEdit: boolean;
  onUpdated: () => Promise<void>;
}) {
  const [prompt, setPrompt] = useState("");
  const [saved, setSaved] = useState("");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPrompt(scene?.visual_prompt || "");
    setSaved(scene?.visual_prompt || "");
    setSuccess(null);
    setError(null);
  }, [scene?.id, scene?.visual_prompt]);

  async function savePrompt() {
    if (!scene) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await apiRequest<{ visual_prompt: string }>(
        `/videos/${videoId}/storyboard/scenes/${scene.id}`,
        { method: "PATCH", body: { visual_prompt: prompt } },
      );
      setSaved(result.visual_prompt);
      setPrompt(result.visual_prompt);
      await onUpdated();
      setSuccess("Visual prompt saved. Generate an image to see the changes.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not update prompt.");
    } finally {
      setSaving(false);
    }
  }

  async function generateImage() {
    if (!scene) return;
    setGenerating(true);
    setError(null);
    setSuccess(null);
    try {
      await apiRequest(`/videos/${videoId}/storyboard/scenes/${scene.id}/regenerate`, { method: "POST" });
      await onUpdated();
      setSuccess("New scene image generated. Re-render to update your MP4.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Image generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  if (!scene) return <p className="text-sm text-[#999db7]">Select a scene from the timeline to edit it.</p>;
  return <div className="space-y-6">
    <div>
      <p className="studio-eyebrow mb-2">Selected clip</p>
      <h3 className="text-lg font-semibold">Scene {scene.sequence}</h3>
      <p className="mt-1 text-xs text-[#999fb8]">{scene.duration_seconds.toFixed(1)} seconds · Generated scene</p>
    </div>
    <ClipTimingInspector videoId={videoId} scene={scene}
      canEdit={canEdit} onUpdated={onUpdated}/>
    <div className="border-t border-white/10 pt-5">
      <p className="studio-eyebrow mb-2">Narration</p>
      <p className="rounded-xl bg-[#111320] p-4 text-sm leading-relaxed text-[#c6cada]">{scene.narration || "No narration supplied."}</p>
      <p className="mt-2 text-xs text-[#8d92aa]">The generated script is read-only. You can replace its spoken voice with your own recording below.</p>
      <PersonalNarrationPanel videoId={videoId} scene={scene}
        canEdit={canEdit} onUpdated={onUpdated}/>
    </div>
    <div className="border-t border-white/10 pt-5">
      <label htmlFor="visual-prompt" className="mb-2 block text-sm font-semibold">Visual prompt</label>
      <textarea id="visual-prompt" rows={7} maxLength={3000} value={prompt}
        disabled={!canEdit} onChange={event => setPrompt(event.target.value)}
        className="studio-input resize-y leading-relaxed" />
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="studio-button-secondary" type="button"
          disabled={!canEdit || saving || generating || prompt.trim().length < 3 || prompt === saved}
          onClick={() => void savePrompt()}>
          <StudioIcon name="check" size={15} /> {saving ? "Saving…" : "Save prompt"}
        </button>
        <button className="studio-button" type="button"
          disabled={!canEdit || saving || generating || prompt !== saved}
          onClick={() => void generateImage()}>
          <StudioIcon name="sparkles" size={15} />
          {generating ? "Generating…" : "Regenerate"}
        </button>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-[#8f94ac]">
        Generating a new image may use AI credits. The video updates after re-rendering.
      </p>
    </div>
    {success && <p role="status" className="rounded-lg bg-emerald-400/10 p-3 text-xs text-emerald-300">{success}</p>}
    {error && <p role="alert" className="rounded-lg bg-rose-500/10 p-3 text-xs text-rose-300">{error}</p>}
  </div>;
}
