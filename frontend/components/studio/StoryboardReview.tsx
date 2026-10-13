"use client";

import { useEffect, useState } from "react";
import { apiRequest, ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { StoryboardScene } from "@/types";

function SceneCard({ videoId, scene }: { videoId: string; scene: StoryboardScene }) {
  const [prompt, setPrompt] = useState(scene.visual_prompt);
  const [savedPrompt, setSavedPrompt] = useState(scene.visual_prompt);
  const [assetId, setAssetId] = useState(scene.visual_asset_id);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setImageUrl(null);
    if (assetId) {
      apiRequest<{ signed_url: string }>(`/assets/${assetId}`)
        .then((asset) => { if (active) setImageUrl(asset.signed_url); })
        .catch(() => { if (active) setImageUrl(null); });
    }
    return () => { active = false; };
  }, [assetId]);

  async function savePrompt() {
    setError(null); setNotice(null); setSaving(true);
    try {
      const result = await apiRequest<{ visual_prompt: string }>(
        `/videos/${videoId}/storyboard/scenes/${scene.id}`,
        { method: "PATCH", body: { visual_prompt: prompt } }
      );
      setPrompt(result.visual_prompt);
      setSavedPrompt(result.visual_prompt);
      setNotice("Prompt saved. Regenerate the scene image to update the storyboard preview.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to save prompt.");
    } finally { setSaving(false); }
  }

  async function regenerateVisual() {
    if (prompt !== savedPrompt) {
      setError("Save the updated prompt before regenerating the image.");
      return;
    }
    setError(null); setNotice(null); setGenerating(true);
    try {
      const result = await apiRequest<{ visual_asset_id: string }>(
        `/videos/${videoId}/storyboard/scenes/${scene.id}/regenerate`, { method: "POST" }
      );
      setAssetId(result.visual_asset_id);
      setNotice("Storyboard image updated. The already-rendered MP4 has not changed.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not regenerate this image.");
    } finally { setGenerating(false); }
  }

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">Scene {scene.sequence}</h3>
        <span className="text-xs text-slate-500">{scene.duration_seconds.toFixed(1)}s</span>
      </div>
      {imageUrl ? (
        // Images are private signed URLs, not eligible for Next's remote optimizer.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imageUrl} alt={`Scene ${scene.sequence} storyboard preview`} className="max-h-56 w-full rounded-lg bg-black object-contain" />
      ) : <div className="flex h-32 items-center justify-center rounded-lg bg-slate-100 text-sm text-slate-500">
        {assetId ? "Preview unavailable" : "No scene image saved"}
      </div>}
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Narration (read-only)</p>
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{scene.narration || "—"}</p>
      </div>
      {scene.on_screen_text && <p className="text-sm text-slate-600">On-screen text: {scene.on_screen_text}</p>}
      <label htmlFor={`scene-prompt-${scene.id}`} className="block text-sm font-medium">Visual prompt</label>
      <textarea id={`scene-prompt-${scene.id}`} rows={3} value={prompt}
        maxLength={3000} onChange={(e) => setPrompt(e.target.value)}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500" />
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={prompt.trim().length < 3 || prompt === savedPrompt || generating}
          loading={saving} onClick={savePrompt}>Save prompt</Button>
        <Button disabled={prompt !== savedPrompt || saving} loading={generating} onClick={regenerateVisual}>
          Regenerate scene image
        </Button>
      </div>
      {notice && <p role="status" className="text-xs text-green-700">{notice}</p>}
      {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
    </Card>
  );
}

export function StoryboardReview({ videoId }: { videoId: string }) {
  const [scenes, setScenes] = useState<StoryboardScene[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    apiRequest<StoryboardScene[]>(`/videos/${videoId}/storyboard`)
      .then((data) => { if (active) setScenes(data); })
      .catch(() => { if (active) setError("Unable to load storyboard."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [videoId]);
  return (
    <section className="mt-8" aria-label="Storyboard scenes">
      <h2 className="mb-2 text-lg font-semibold">Storyboard review</h2>
      <p className="mb-4 text-sm text-amber-800">
        Visual prompt edits and image regeneration update the storyboard preview only.
        The exported MP4 remains unchanged until a future re-render workflow is implemented.
      </p>
      {loading ? <p className="text-sm text-slate-500">Loading storyboard...</p>
        : error ? <p role="alert" className="text-sm text-red-700">{error}</p>
        : scenes.length === 0 ? <p className="text-sm text-slate-500">No scenes available.</p>
        : <div className="grid gap-4 md:grid-cols-2">
            {scenes.map((scene) => <SceneCard key={scene.id} videoId={videoId} scene={scene} />)}
          </div>}
    </section>
  );
}
