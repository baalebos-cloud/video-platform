"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { DashboardShell } from "@/components/dashboard/Shell";
import { ApiError, apiRequest } from "@/lib/api/client";
import type { GenerateVideoResponse, Voice } from "@/types";
import { VoiceProfileStudio, type VoiceProfile } from "@/components/studio/VoiceProfileStudio";

const PLATFORMS = ["youtube_shorts", "tiktok", "instagram_reels", "youtube_landscape"];
const VISUAL_STYLES = ["cinematic_realistic", "documentary", "animated", "product"];
const MAX_TOPIC_LENGTH = 1024;
const DURATION_PRESETS = [30, 60, 90, 120, 180] as const;
const MAX_DURATION_SECONDS = 180;
const LANGUAGE_OPTIONS = [
  { label: "English", locale: "en-NG" },
  { label: "Nigerian Pidgin", locale: "pcm-NG" },
  { label: "Yoruba", locale: "yo-NG" },
] as const;
type LanguageOption = typeof LANGUAGE_OPTIONS[number]["label"];
type VoiceMode = "auto" | "recorded" | "cloned";

function NewVideoForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project_id") ?? "";

  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState<LanguageOption>("English");
  const [locale, setLocale] = useState("en-NG");
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("auto");
  const [voiceProfiles, setVoiceProfiles] = useState<VoiceProfile[]>([]);
  const [cloneReady, setCloneReady] = useState(false);
  const [voiceProfileId, setVoiceProfileId] = useState("");
  const [duration, setDuration] = useState(180);
  const [platform, setPlatform] = useState(PLATFORMS[0]);
  const [visualStyle, setVisualStyle] = useState(VISUAL_STYLES[0]);
  const [captionStyle, setCaptionStyle] = useState<"none" | "classic" | "bold">("none");
  const [voiceId, setVoiceId] = useState<string | undefined>(undefined);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (voiceMode !== "auto" || language !== "English") {
      setVoices([]);
      setVoiceId(undefined);
      return;
    }
    apiRequest<Voice[]>(`/voices?locale=${locale}`).then(setVoices).catch(() => setVoices([]));
  }, [locale, language, voiceMode]);

  async function refreshVoiceProfiles() {
    try {
      const profiles = await apiRequest<VoiceProfile[]>("/voice-profiles");
      setVoiceProfiles(profiles);
    } catch {
      setVoiceProfiles([]);
    }
  }

  useEffect(() => {
    void refreshVoiceProfiles();
    apiRequest<{automatic_cloning: boolean}>("/voice-profiles/capabilities")
      .then(result => setCloneReady(result.automatic_cloning))
      .catch(() => setCloneReady(false));
  }, []);

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
    if (!Number.isInteger(duration) || duration < 5 || duration > MAX_DURATION_SECONDS) {
      setError("Select a duration between 5 seconds and 3 minutes.");
      return;
    }
    if (voiceMode === "cloned" && (!cloneReady || !voiceProfileId ||
        !voiceProfiles.some(profile => profile.id === voiceProfileId && profile.language === language))) {
      setError("Select a saved voice profile and configure licensed synthesis first.");
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
          caption_style: captionStyle,
          voice: { mode: voiceMode, ...(voiceMode === "auto" && voiceId ? { voice_id: voiceId } : {}), ...(voiceMode === "cloned" ? { profile_id: voiceProfileId } : {}) },
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

          <div>
            <label htmlFor="narration-language" className="mb-2 block text-sm font-medium">
              Narration language
            </label>
            <select id="narration-language" className="studio-input" value={language}
              onChange={event => {
                const option = LANGUAGE_OPTIONS.find(o => o.label === event.target.value);
                if (!option) return;
                setLanguage(option.label);
                setLocale(option.locale);
                setVoiceMode(option.label === "English" ? "auto" : "recorded");
                setVoiceProfileId("");
                setVoiceId(undefined);
              }}>
              {LANGUAGE_OPTIONS.map(option =>
                <option key={option.locale} value={option.label}>{option.label}</option>)}
            </select>
            <p className="mt-2 text-xs text-[#989fbb]">
              Gemini writes the script in your chosen language. Pidgin and Yoruba
              use recorded narration because the current AI voice cannot speak them reliably.
            </p>
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
            <div>
              <label htmlFor="video-duration" className="mb-2 block text-sm font-medium">
                Video length <span className="text-violet-300">{Math.floor(duration / 60)}:{String(duration % 60).padStart(2, "0")}</span>
              </label>
              <div aria-label="Video length presets" className="mb-2 flex flex-wrap gap-1.5">
                {DURATION_PRESETS.map(seconds => (
                  <button type="button" key={seconds} aria-pressed={duration === seconds}
                    onClick={() => setDuration(seconds)}
                    className={`rounded-lg border px-2 py-1.5 text-xs transition ${duration === seconds
                      ? "border-violet-400 bg-violet-500/20 text-white"
                      : "border-white/15 text-[#a7afcb] hover:bg-white/5"}`}>
                    {seconds === 180 ? "Full video · 3 min" : seconds === 90 ? "1 min 30s" : seconds < 60 ? `${seconds}s` : `${seconds / 60} min`}
                  </button>
                ))}
              </div>
              <input id="video-duration" className="studio-input" type="number" min={5}
                max={MAX_DURATION_SECONDS} step={1} value={duration}
                onChange={e => setDuration(Number(e.target.value))} />
              <p className="mt-2 text-xs leading-relaxed text-[#969db7]">
                Full-length mode generates a developed script, more scenes and longer narration.
                3-minute videos use more free-tier AI calls and render time; your provider quotas still apply.
              </p>
            </div>
            <div>
              <label htmlFor="narration-voice-mode" className="mb-2 block text-sm font-medium text-[#e0e2f1]">
                Narration source
              </label>
              <select id="narration-voice-mode" className="studio-input" value={voiceMode}
                onChange={event => { setVoiceMode(event.target.value as VoiceMode); setVoiceId(undefined); }}>
                {language === "English" && <option value="auto">AI English narrator</option>}
                <option value="recorded">My own recorded voice</option>
                {cloneReady && <option value="cloned">My AI voice (licensed model)</option>}
              </select>
              {voiceMode === "auto" && <select aria-label="AI narrator" className="studio-input mt-2"
                value={voiceId ?? ""} onChange={event => setVoiceId(event.target.value || undefined)}>
                <option value="">Auto-select voice</option>
                {voices.map(voice => <option key={voice.voice_id} value={voice.voice_id}>
                  {voice.voice_id} ({voice.gender ?? "unspecified"})
                </option>)}
              </select>}
              {voiceMode === "cloned" && <div className="mt-2">
                <label htmlFor="personal-voice-select" className="text-xs text-[#a5abc4]">Saved profile for this language</label>
                <select id="personal-voice-select" className="studio-input mt-2" value={voiceProfileId}
                  onChange={event => setVoiceProfileId(event.target.value)}>
                  <option value="">Choose my voice</option>
                  {voiceProfiles.filter(p => p.language === language).map(profile => (
                    <option key={profile.id} value={profile.id}>{profile.name}</option>
                  ))}
                </select>
                <p className="mt-2 text-xs text-amber-200">
                  Cloning uses a separately hosted licensed inference service and may have infrastructure costs.
                </p>
              </div>}
              {voiceMode === "recorded" && <p className="mt-2 text-xs leading-relaxed text-[#a5aaca]">
                The first render is a silent storyboard. After generation, record or upload
                your own narration for each scene and click Re-render edits. This uses your
                real voice, not an AI clone, and adds no TTS calls.
              </p>}
            </div>
          </div>

          <label className="block text-sm font-medium">Captions on exported video
            <select className="studio-input mt-2" value={captionStyle}
              onChange={e => setCaptionStyle(e.target.value as "none" | "classic" | "bold")}>
              <option value="none">No captions (clean MP4)</option>
              <option value="classic">Classic subtitles</option>
              <option value="bold">Bold subtitles</option>
            </select>
          </label>
          <p className="text-xs text-[#959bb5]">
            Select only your own or authorized recordings. The recorded-voice option stores
            your private audio and never clones your identity; disclose AI narration where used.
          </p>
          <VoiceProfileStudio language={language} profiles={voiceProfiles}
            onRefresh={refreshVoiceProfiles} />
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
