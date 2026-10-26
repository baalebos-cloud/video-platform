"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { DashboardShell } from "@/components/dashboard/Shell";
import { ApiError, apiRequest } from "@/lib/api/client";
import type { GenerateVideoResponse, Voice } from "@/types";

const PLATFORMS = ["youtube_shorts", "tiktok", "instagram_reels", "youtube_landscape"];
const VISUAL_STYLES = ["cinematic_realistic", "documentary", "animated", "product"];
const MAX_TOPIC_LENGTH = 1024;

function NewVideoForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project_id") ?? "";

  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState("English");
  const [locale, setLocale] = useState("en-US");
  const [duration, setDuration] = useState(60);
  const [platform, setPlatform] = useState(PLATFORMS[0]);
  const [visualStyle, setVisualStyle] = useState(VISUAL_STYLES[0]);
  const [voiceId, setVoiceId] = useState<string | undefined>(undefined);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiRequest<Voice[]>(`/voices?locale=${locale}`).then(setVoices).catch(() => setVoices([]));
  }, [locale]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!projectId) {
      setError("Missing project — open this page from a project's page.");
      return;
    }
    if (topic.trim().length < 3) {
      setError("Enter a topic of at least 3 characters.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await apiRequest<GenerateVideoResponse>("/videos/generate", {
        method: "POST",
        body: {
          project_id: projectId,
          topic: topic.trim(),
          language,
          locale,
          duration_seconds: duration,
          platform,
          visual_style: visualStyle,
          voice: voiceId ? { voice_id: voiceId } : {},
        },
      });
      router.push(`/studio/video/${result.video_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start generation");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <DashboardShell>
      <p className="studio-eyebrow mb-2">New production</p>
      <h1 className="mb-2 text-3xl font-bold">Create a new video</h1>
      <p className="mb-6 text-sm text-[#a5abc3]">Choose your content, format and voice before generating.</p>
      <section className="studio-surface max-w-3xl p-5 sm:p-7">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label htmlFor="video-topic" className="mb-2 block text-sm font-medium text-[#e0e2f1]">Topic / idea</label>
            <textarea
              id="video-topic"
              required
              minLength={3}
              maxLength={MAX_TOPIC_LENGTH}
              rows={3}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Five unbelievable ocean discoveries"
              className="studio-input"
            />
            <p className="mt-1 text-xs text-[#959bb5]">{topic.length}/{MAX_TOPIC_LENGTH} characters. Enter a short topic rather than a full production brief.</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium">Language<input className="studio-input mt-2" value={language} onChange={e => setLanguage(e.target.value)} required /></label>
            <label className="block text-sm font-medium">Locale<input className="studio-input mt-2" value={locale} onChange={e => setLocale(e.target.value)} required /></label>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-2 block text-sm font-medium text-[#e0e2f1]">Platform</label>
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="studio-input"
              >
                {PLATFORMS.map((p) => (
                  <option key={p} value={p}>
                    {p.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-[#e0e2f1]">Visual style</label>
              <select
                value={visualStyle}
                onChange={(e) => setVisualStyle(e.target.value)}
                className="studio-input"
              >
                {VISUAL_STYLES.map((s) => (
                  <option key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium">Duration (seconds)
              <input className="studio-input mt-2" type="number" min={5} max={180} value={duration}
                onChange={e => setDuration(Number(e.target.value))} />
            </label>
            <div>
              <label className="mb-2 block text-sm font-medium text-[#e0e2f1]">Voice</label>
              <select
                value={voiceId ?? ""}
                onChange={(e) => setVoiceId(e.target.value || undefined)}
                className="studio-input"
              >
                <option value="">Auto-select</option>
                {voices.map((v) => (
                  <option key={v.voice_id} value={v.voice_id}>
                    {v.voice_id} ({v.gender ?? "unspecified"})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <p className="text-xs text-[#959bb5]">
            Narration may use an AI-generated voice. Clearly disclose synthetic voices
            when sharing your video and use only content you have permission to publish.
          </p>
          {error && <p className="text-sm text-rose-300">{error}</p>}

          <button type="submit" disabled={submitting || !topic.trim()} className="studio-button mt-2 self-start">
            <StudioIcon name="sparkles" size={17} /> {submitting ? "Queueing…" : "Generate video"}
          </button>
        </form>
      </section>
    </DashboardShell>
  );
}

export default NewVideoForm;
