"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { DashboardShell } from "@/components/dashboard/Shell";
import { ApiError, apiRequest } from "@/lib/api/client";
import type { GenerateVideoResponse, Voice } from "@/types";

const PLATFORMS = ["youtube_shorts", "tiktok", "instagram_reels", "youtube_landscape"];
const VISUAL_STYLES = ["cinematic_realistic", "documentary", "animated", "product"];

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
    setSubmitting(true);
    setError(null);
    try {
      const result = await apiRequest<GenerateVideoResponse>("/videos/generate", {
        method: "POST",
        body: {
          project_id: projectId,
          topic,
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
      <h1 className="mb-6 text-2xl font-semibold">Create a new video</h1>
      <Card className="max-w-2xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Topic / idea</label>
            <textarea
              required
              rows={3}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Five unbelievable ocean discoveries"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input label="Language" value={language} onChange={(e) => setLanguage(e.target.value)} />
            <Input label="Locale" value={locale} onChange={(e) => setLocale(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Platform</label>
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                {PLATFORMS.map((p) => (
                  <option key={p} value={p}>
                    {p.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Visual style</label>
              <select
                value={visualStyle}
                onChange={(e) => setVisualStyle(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
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
            <Input
              label="Duration (seconds)"
              type="number"
              min={5}
              max={600}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
            />
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Voice</label>
              <select
                value={voiceId ?? ""}
                onChange={(e) => setVoiceId(e.target.value || undefined)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
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

          {error && <p className="text-sm text-red-600">{error}</p>}

          <Button type="submit" loading={submitting} className="mt-2 self-start">
            Generate video
          </Button>
        </form>
      </Card>
    </DashboardShell>
  );
}

export default NewVideoForm;
