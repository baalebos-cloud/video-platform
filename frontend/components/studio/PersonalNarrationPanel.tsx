"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { useSignedMedia } from "@/hooks/useSignedMedia";
import type { StoryboardScene } from "@/types";

const MAX_AUDIO_BYTES = 3 * 1024 * 1024;

export function PersonalNarrationPanel({ videoId, scene, canEdit, onUpdated }: {
  videoId: string;
  scene: StoryboardScene;
  canEdit: boolean;
  onUpdated: () => Promise<void>;
}) {
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const mediaStream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const [consent, setConsent] = useState(false);
  const [recording, setRecording] = useState(false);
  const [audio, setAudio] = useState<Blob | File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const { url: storedVoiceUrl } = useSignedMedia(scene.audio_state === "recorded" ? scene.audio_asset_id : null);

  useEffect(() => {
    if (!audio) { setPreviewUrl(null); return; }
    const url = URL.createObjectURL(audio);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [audio]);

  useEffect(() => {
    return () => {
      if (mediaRecorder.current?.state === "recording") mediaRecorder.current.stop();
      mediaStream.current?.getTracks().forEach(track => track.stop());
    };
  }, [scene.id]);

  async function startRecording() {
    setError(null);
    setMessage(null);
    if (!consent) { setError("Confirm that you own this voice or have permission to use it."); return; }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Browser microphone recording is unavailable. Upload an audio file instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      mediaStream.current = stream;
      const preferredTypes = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg"];
      const format = preferredTypes.find(type => MediaRecorder.isTypeSupported(type));
      const recorder = format ? new MediaRecorder(stream, {mimeType: format}) : new MediaRecorder(stream);
      mediaRecorder.current = recorder;
      chunks.current = [];
      recorder.ondataavailable = event => { if (event.data.size) chunks.current.push(event.data); };
      recorder.onstop = () => {
        const result = new Blob(chunks.current, {type: recorder.mimeType || format || "audio/webm"});
        chunks.current = [];
        mediaStream.current?.getTracks().forEach(track => track.stop());
        mediaStream.current = null;
        setRecording(false);
        if (result.size > MAX_AUDIO_BYTES) {
          setError("Recording is over 3 MB. Make a shorter or more compressed recording.");
        } else if (result.size > 0) setAudio(result);
      };
      recorder.onerror = () => setError("Microphone recording failed. Try uploading an audio file.");
      recorder.start(250);
      setAudio(null);
      setRecording(true);
    } catch {
      mediaStream.current?.getTracks().forEach(track => track.stop());
      mediaStream.current = null;
      setError("Microphone permission was denied or the microphone is unavailable.");
    }
  }

  function stopRecording() {
    if (mediaRecorder.current?.state === "recording") mediaRecorder.current.stop();
  }

  async function submitAudio() {
    if (!audio || !canEdit || !consent) return;
    if (audio.size > MAX_AUDIO_BYTES) {
      setError("Audio recording must be under 3 MB.");
      return;
    }
    setError(null);
    setMessage(null);
    setUploading(true);
    try {
      const response = await fetch(
        `/api/gateway/videos/${videoId}/storyboard/scenes/${scene.id}/narration`,
        {
          method: "POST",
          headers: {"Content-Type": audio.type || "audio/webm"},
          body: audio,
          credentials: "same-origin",
        },
      );
      if (!response.ok) {
        let detail = `Voice upload failed (HTTP ${response.status}).`;
        try {
          const data: {detail?: string; message?: string} = await response.json();
          detail = data.detail || data.message || detail;
        } catch { /* leave safe status message */ }
        throw new ApiError(response.status, detail);
      }
      await onUpdated();
      setAudio(null);
      setMessage("Your real voice was saved privately for this scene. Re-render the video to hear it.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to save your narration.");
    } finally {
      setUploading(false);
    }
  }

  return <section aria-label="Record your narration" className="mt-4 space-y-3 rounded-xl border border-violet-400/20 bg-violet-500/5 p-3">
    <p className="text-xs font-semibold text-white">Your voice for this scene</p>
    <p className="text-[11px] leading-relaxed text-[#a5abc3]">
      Read the scene script above in the selected language. Keep the audio
      within {scene.duration_seconds.toFixed(1)} seconds. This records your actual
      voice, not an AI clone, and does not incur TTS calls.
    </p>
    <span className="block text-[11px] text-[#c9c6e6]">
      Narration: {scene.audio_state === "recorded" ? "Your recording saved" :
        scene.audio_state === "pending" ? "Awaiting your recording (silent)" : "AI-generated voice"}
    </span>
    {scene.audio_state === "recorded" && storedVoiceUrl && <>
      <label className="text-[11px] text-[#afb5d0]">Saved narration</label>
      <audio className="h-9 w-full" controls src={storedVoiceUrl} preload="none"/>
    </>}
    <label className="flex items-start gap-2 text-[11px] leading-relaxed text-[#b7bed7]">
      <input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)}
        className="mt-0.5 accent-violet-400"/>
      I am recording my own voice, or I have the speaker's permission to use this recording.
    </label>
    <div className="flex flex-wrap gap-2">
      {recording ? <button type="button" onClick={stopRecording}
        className="studio-button-secondary text-xs">Stop recording</button>
        : <button type="button" disabled={!canEdit || !consent || uploading}
          onClick={() => void startRecording()} className="studio-button-secondary text-xs">
          Record microphone
        </button>}
      <label className={`studio-button-secondary cursor-pointer text-xs ${!canEdit || !consent ? "opacity-40" : ""}`}>
        Upload audio
        <input type="file" accept="audio/wav,audio/mpeg,audio/mp3,audio/webm,audio/mp4,audio/ogg,.wav,.mp3,.m4a,.webm,.ogg"
          className="sr-only" disabled={!canEdit || !consent || uploading || recording}
          onChange={event => {
            const file = event.target.files?.[0];
            if (!file) return;
            setError(null);
            setMessage(null);
            if (file.size > MAX_AUDIO_BYTES) {
              setError("Maximum audio upload size is 3 MB.");
              setAudio(null);
            } else setAudio(file);
            event.target.value = "";
          }}/>
      </label>
    </div>
    {recording && <p role="status" className="text-xs text-amber-200">Microphone recording is active…</p>}
    {previewUrl && !recording && <>
      <label className="text-[11px] text-[#a9afc7]">Review new recording</label>
      <audio className="h-9 w-full" controls src={previewUrl}/>
      <button type="button" disabled={!canEdit || !consent || uploading} onClick={() => void submitAudio()}
        className="studio-button w-full text-xs">{uploading ? "Saving…" : "Save narration for scene"}</button>
    </>}
    {message && <p role="status" className="text-xs text-emerald-300">{message}</p>}
    {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
  </section>;
}
