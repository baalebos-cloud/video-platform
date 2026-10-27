"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, apiRequest } from "@/lib/api/client";

export type VoiceProfile = {
  id: string;
  name: string;
  language: string;
  duration_seconds: number;
  status: "reference_saved";
  created_at: string | null;
};

const MAX_BYTES = 3 * 1024 * 1024;

export function VoiceProfileStudio({
  language, profiles, onRefresh,
}: {
  language: string;
  profiles: VoiceProfile[];
  onRefresh: () => Promise<void>;
}) {
  const [name, setName] = useState("My voice");
  const [confirmed, setConfirmed] = useState(false);
  const [audio, setAudio] = useState<File | Blob | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [active, setActive] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const parts = useRef<Blob[]>([]);

  useEffect(() => {
    if (!audio) { setPreview(null); return; }
    const url = URL.createObjectURL(audio);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [audio]);

  useEffect(() => () => {
    if (recorder.current?.state === "recording") recorder.current.stop();
    stream.current?.getTracks().forEach(track => track.stop());
  }, []);

  async function record() {
    if (!confirmed) return;
    setError(null); setMessage(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Microphone recording is not supported here. Upload a voice recording instead.");
      return;
    }
    try {
      const track = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = track;
      const preferred = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"]
        .find(type => MediaRecorder.isTypeSupported(type));
      const instance = preferred ? new MediaRecorder(track, {mimeType: preferred}) : new MediaRecorder(track);
      recorder.current = instance;
      parts.current = [];
      instance.ondataavailable = event => { if (event.data.size) parts.current.push(event.data); };
      instance.onstop = () => {
        const blob = new Blob(parts.current, {type: instance.mimeType || "audio/webm"});
        parts.current = [];
        stream.current?.getTracks().forEach(t => t.stop());
        stream.current = null;
        setActive(false);
        if (blob.size > MAX_BYTES) setError("Reference audio exceeds 3 MB.");
        else if (blob.size) setAudio(blob);
      };
      instance.onerror = () => setError("Microphone recording failed. Try another recording.");
      instance.start(250);
      setAudio(null);
      setActive(true);
    } catch {
      stream.current?.getTracks().forEach(t => t.stop());
      setError("Microphone permission was denied or unavailable.");
    }
  }

  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  async function enroll() {
    if (!audio || !confirmed || !name.trim() || saving) return;
    setError(null); setMessage(null); setSaving(true);
    try {
      if (audio.size > MAX_BYTES) throw new Error("Maximum voice reference size is 3 MB.");
      const response = await fetch("/api/gateway/voice-profiles", {
        method: "POST", credentials: "same-origin",
        headers: {
          "Content-Type": audio.type || "audio/webm",
          "X-Voice-Consent": "self",
          "X-Voice-Name": name.trim(),
          "X-Voice-Language": language,
        },
        body: audio,
      });
      if (!response.ok) {
        const message = await response.json().catch(() => null);
        throw new Error(typeof message?.detail === "string" ? message.detail :
          `Reference save failed (HTTP ${response.status})`);
      }
      setAudio(null);
      setMessage("Reference saved privately. This is not a cloned voice until licensed inference is connected.");
      await onRefresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save reference audio.");
    } finally { setSaving(false); }
  }

  async function remove(id: string, title: string) {
    if (!window.confirm(`Permanently delete voice reference "${title}"? This cannot be undone.`)) return;
    setError(null); setMessage(null);
    try {
      await apiRequest(`/voice-profiles/${id}`, {method: "DELETE"});
      setMessage("Voice reference deleted from your profile and private storage.");
      await onRefresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to delete reference.");
    }
  }

  return <section className="rounded-xl border border-violet-400/20 bg-violet-500/5 p-4">
    <h3 className="text-sm font-semibold text-white">My voice profiles</h3>
    <p className="mt-2 text-xs leading-relaxed text-[#aab0c7]">
      Record or upload 5-30 seconds of your own voice. The reference stays private.
      Saving a profile does not automatically enable voice cloning or spend on an AI API.
    </p>
    <div className="mt-3 space-y-2">
      {profiles.filter(p => p.language === language).map(p => (
        <div key={p.id} className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-[#10121d] p-3">
          <div className="min-w-0 text-xs">
            <p className="truncate font-medium text-white">{p.name}</p>
            <p className="mt-1 text-[#a1a8c0]">{p.language} · {p.duration_seconds.toFixed(1)}s · Private reference</p>
          </div>
          <button type="button" onClick={() => void remove(p.id, p.name)}
            className="rounded-md border border-rose-300/20 px-2 py-1.5 text-xs text-rose-200 hover:bg-rose-500/10">
            Delete
          </button>
        </div>
      ))}
    </div>
    {profiles.length >= 3 ? <p className="mt-3 text-xs text-[#a5abc4]">
      Three profiles saved. Delete one to enroll another.
    </p> : <div className="mt-4 space-y-3">
      <label htmlFor="voice-profile-name" className="block text-xs text-[#c6cadc]">Profile name</label>
      <input id="voice-profile-name" className="studio-input" maxLength={60} value={name}
        onChange={event => setName(event.target.value)} />
      <label className="flex items-start gap-2 text-xs text-[#bfc4d7]">
        <input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}
          className="mt-1 accent-violet-400" />
        This is my own voice. I consent to its private storage and potential use for synthetic narration
        only after an approved model is configured.
      </label>
      <div className="flex flex-wrap gap-2">
        {active ? <button type="button" className="studio-button-secondary text-xs" onClick={stop}>Stop recording</button> :
          <button type="button" className="studio-button-secondary text-xs" disabled={!confirmed || saving}
            onClick={() => void record()}>Record reference</button>}
        <label className={`studio-button-secondary cursor-pointer text-xs ${confirmed ? "" : "opacity-40"}`}>
          Upload reference
          <input type="file" className="sr-only" disabled={!confirmed || saving || active}
            accept="audio/wav,audio/mpeg,audio/webm,audio/mp4,audio/ogg,.wav,.mp3,.m4a,.webm,.ogg"
            onChange={event => {
              const file = event.target.files?.[0];
              if (file) {
                if (file.size > MAX_BYTES) setError("Audio exceeds 3 MB.");
                else { setAudio(file); setError(null); }
              }
              event.target.value = "";
            }} />
        </label>
      </div>
      {active && <p role="status" className="text-xs text-amber-200">Recording. Speak naturally, then stop after 5–30 seconds.</p>}
      {preview && <div className="space-y-2">
        <audio controls src={preview} className="h-9 w-full" />
        <button type="button" className="studio-button w-full" disabled={saving || !confirmed}
          onClick={() => void enroll()}>{saving ? "Saving…" : "Save private voice reference"}</button>
        <button type="button" onClick={() => setAudio(null)} className="text-xs text-violet-300">
          Discard and retake
        </button>
      </div>}
    </div>}
    {message && <p role="status" className="mt-3 text-xs text-emerald-300">{message}</p>}
    {error && <p role="alert" className="mt-3 text-xs text-rose-300">{error}</p>}
  </section>;
}
