"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { useSignedMedia } from "@/hooks/useSignedMedia";
import type { StoryboardScene } from "@/types";

const MAX_AUDIO_BYTES = 3 * 1024 * 1024;
const MAX_SCENE_SECONDS = 60;
const time = (value: number) => `${Math.floor(value / 60)}:${Math.floor(value % 60).toString().padStart(2, "0")}`;

export function PersonalNarrationPanel({ videoId, scene, canEdit, onUpdated }: {
  videoId: string;
  scene: StoryboardScene;
  canEdit: boolean;
  onUpdated: () => Promise<void>;
}) {
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const audioContext = useRef<AudioContext | null>(null);
  const clock = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAt = useRef(0);
  const chunks = useRef<Blob[]>([]);
  const [consent, setConsent] = useState(false);
  const [recording, setRecording] = useState(false);
  const [secondsElapsed, setSecondsElapsed] = useState(0);
  const [micLevel, setMicLevel] = useState(0);
  const [audio, setAudio] = useState<Blob | File | null>(null);
  const [audioLength, setAudioLength] = useState(0);
  const [trimStart, setTrimStart] = useState(0);
  const [trimEnd, setTrimEnd] = useState(0);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const { url: storedVoiceUrl } = useSignedMedia(scene.audio_state === "recorded" ? scene.audio_asset_id : null);

  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  function cleanup() {
    if (clock.current) clearInterval(clock.current);
    clock.current = null;
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    void audioContext.current?.close().catch(() => undefined);
    audioContext.current = null;
  }

  useEffect(() => {
    setAudio(null);
    setAudioLength(0);
    setTrimStart(0);
    setTrimEnd(0);
    setConsent(false);
    setMessage(null);
    setError(null);
    return () => {
      if (recorder.current?.state === "recording") recorder.current.stop();
      if (clock.current) clearInterval(clock.current);
      stream.current?.getTracks().forEach(track => track.stop());
      void audioContext.current?.close().catch(() => undefined);
    };
  }, [scene.id]);

  useEffect(() => {
    if (!audio) { setPreviewUrl(null); return; }
    const url = URL.createObjectURL(audio);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [audio]);

  async function startRecording() {
    setError(null);
    setMessage(null);
    if (!consent) { setError("Confirm you have the right to use the recording."); return; }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Microphone recording is unavailable. Upload a WAV, MP3, M4A or WebM instead.");
      return;
    }
    try {
      const input = await navigator.mediaDevices.getUserMedia({ audio: {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      } });
      stream.current = input;
      const formats = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg"];
      const format = formats.find(type => MediaRecorder.isTypeSupported(type));
      const instance = format ? new MediaRecorder(input, { mimeType: format }) : new MediaRecorder(input);
      recorder.current = instance;
      chunks.current = [];
      instance.ondataavailable = event => { if (event.data.size) chunks.current.push(event.data); };
      instance.onstop = () => {
        const file = new Blob(chunks.current, { type: instance.mimeType || format || "audio/webm" });
        chunks.current = [];
        cleanup();
        setRecording(false);
        if (file.size > MAX_AUDIO_BYTES) setError("Recording exceeds 3 MB. Use a shorter recording.");
        else if (file.size > 0) setAudio(file);
      };
      instance.onerror = () => { cleanup(); setRecording(false); setError("Recording failed. Try another take."); };
      try {
        const context = new AudioContext();
        audioContext.current = context;
        const source = context.createMediaStreamSource(input);
        const analyser = context.createAnalyser();
        analyser.fftSize = 512;
        source.connect(analyser);
        const levels = new Uint8Array(analyser.frequencyBinCount);
        startedAt.current = Date.now();
        clock.current = setInterval(() => {
          const elapsed = (Date.now() - startedAt.current) / 1000;
          setSecondsElapsed(elapsed);
          analyser.getByteFrequencyData(levels);
          setMicLevel(Math.min(100, Math.round(levels.reduce((sum, n) => sum + n, 0) / levels.length)));
          if (elapsed >= Math.min(MAX_SCENE_SECONDS, scene.duration_seconds)) {
            if (instance.state === "recording") instance.stop();
          }
        }, 180);
      } catch {
        // Recording continues even if AudioContext visual metering is blocked.
        startedAt.current = Date.now();
        clock.current = setInterval(() => {
          const elapsed = (Date.now() - startedAt.current) / 1000;
          setSecondsElapsed(elapsed);
          if (elapsed >= Math.min(MAX_SCENE_SECONDS, scene.duration_seconds)
              && instance.state === "recording") instance.stop();
        }, 250);
      }
      setAudio(null);
      setAudioLength(0);
      setTrimStart(0);
      setTrimEnd(0);
      setSecondsElapsed(0);
      instance.start(250);
      setRecording(true);
    } catch {
      cleanup();
      setError("Microphone permission was denied or the microphone is unavailable.");
    }
  }

  const validTrim = audioLength > 0 && Number.isFinite(trimStart) && Number.isFinite(trimEnd)
    && trimStart >= 0 && trimEnd <= audioLength + 0.1
    && trimEnd - trimStart >= 0.4
    && trimEnd - trimStart <= scene.duration_seconds + 0.25;

  async function save() {
    if (!audio || !consent || !canEdit || !validTrim) return;
    if (audio.size > MAX_AUDIO_BYTES) { setError("Recording is too large."); return; }
    setError(null);
    setMessage(null);
    setUploading(true);
    try {
      const response = await fetch(
        `/api/gateway/videos/${videoId}/storyboard/scenes/${scene.id}/narration`,
        {
          method: "POST", credentials: "same-origin",
          headers: {
            "Content-Type": audio.type || "audio/webm",
            "X-Voice-Consent": "confirmed",
            "X-Trim-Start": String(trimStart),
            "X-Trim-End": String(trimEnd),
          },
          body: audio,
        },
      );
      if (!response.ok) {
        let detail = `Voice upload failed (HTTP ${response.status}).`;
        try {
          const result: { detail?: string; message?: string } = await response.json();
          detail = result.detail || result.message || detail;
        } catch { /* Preserve HTTP status */ }
        throw new ApiError(response.status, detail);
      }
      await onUpdated();
      setAudio(null);
      setMessage("Narration saved. Re-render the project to update its audio.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save narration.");
    } finally {
      setUploading(false);
    }
  }

  return <section aria-label="Personal narration recording studio" className="mt-4 space-y-3 rounded-xl border border-violet-400/20 bg-violet-500/5 p-3">
    <p className="text-xs font-semibold text-white">Record your voice</p>
    <p className="text-[11px] leading-relaxed text-[#a5abc3]">
      Read the script above. Target {time(scene.duration_seconds)} per scene.
      Retake or trim the recording before saving. No voice-cloning call is made here.
    </p>
    <p className="text-[11px] text-[#c9c6e6]">
      {scene.audio_state === "recorded" ? "Saved recording" :
        scene.audio_state === "pending" ? "Recording required" : "Generated narrator currently attached"}
    </p>
    {scene.audio_state === "recorded" && storedVoiceUrl &&
      <audio aria-label="Saved voice" className="h-9 w-full" controls src={storedVoiceUrl} preload="none"/>}
    <label className="flex items-start gap-2 text-[11px] leading-relaxed text-[#b7bed7]">
      <input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)}
        className="mt-0.5 accent-violet-400"/>
      This is my voice, or I have the speaker&apos;s explicit permission.
    </label>
    <div className="flex flex-wrap gap-2">
      {recording ?
        <button type="button" onClick={stop} className="studio-button-secondary text-xs">Stop take</button> :
        <button type="button" disabled={!canEdit || !consent || uploading}
          onClick={() => void startRecording()} className="studio-button-secondary text-xs">
          {audio ? "Retake" : "Record microphone"}
        </button>}
      <label className={`studio-button-secondary cursor-pointer text-xs ${!canEdit || !consent ? "opacity-40" : ""}`}>
        Upload audio
        <input type="file" className="sr-only"
          accept="audio/wav,audio/mpeg,audio/mp3,audio/webm,audio/mp4,audio/ogg,.wav,.mp3,.m4a,.webm,.ogg"
          disabled={!canEdit || !consent || uploading || recording}
          onChange={event => {
            const file = event.target.files?.[0];
            if (!file) return;
            setError(null); setMessage(null);
            if (file.size > MAX_AUDIO_BYTES) {
              setError("Maximum audio size is 3 MB."); setAudio(null);
            } else { setAudio(file); setAudioLength(0); setTrimStart(0); setTrimEnd(0); }
            event.target.value = "";
          }}/>
      </label>
    </div>
    {recording && <div role="status" className="space-y-1">
      <div className="flex justify-between text-xs text-amber-200">
        <span>Recording · {time(secondsElapsed)}</span><span>{time(scene.duration_seconds)}</span>
      </div>
      <div aria-label="Microphone level" className="h-2 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-violet-400 transition-all" style={{width:`${micLevel}%`}}/>
      </div>
      <div className="h-1 rounded-full bg-white/10">
        <div className="h-1 rounded-full bg-amber-400" style={{
          width:`${Math.min(100, secondsElapsed / scene.duration_seconds * 100)}%`,
        }}/>
      </div>
    </div>}
    {previewUrl && !recording && <>
      <label className="block text-[11px] text-[#a9afc7]">Listen to this take before saving</label>
      <audio className="h-9 w-full" controls src={previewUrl}
        onLoadedMetadata={event => {
          const length = event.currentTarget.duration;
          if (!Number.isFinite(length) || length <= 0) {
            setError("Unable to determine recording length. Try a different format.");
            return;
          }
          setAudioLength(length);
          setTrimStart(0);
          setTrimEnd(Math.min(length, scene.duration_seconds));
        }} />
      <div className="grid grid-cols-2 gap-2">
        <label className="text-[11px] text-[#c4c8df]">Start (seconds)
          <input aria-label="Trim start seconds" className="studio-input mt-1" type="number" step="0.1"
            min={0} max={audioLength} value={trimStart}
            onChange={event => setTrimStart(Number(event.target.value))}/>
        </label>
        <label className="text-[11px] text-[#c4c8df]">End (seconds)
          <input aria-label="Trim end seconds" className="studio-input mt-1" type="number" step="0.1"
            min={0.4} max={audioLength} value={trimEnd}
            onChange={event => setTrimEnd(Number(event.target.value))}/>
        </label>
      </div>
      <p className="text-[11px] text-[#a9afc7]">Selected: {Math.max(0, trimEnd - trimStart).toFixed(1)}s
        · Clip limit: {scene.duration_seconds.toFixed(1)}s</p>
      {!validTrim && <p role="alert" className="text-xs text-amber-200">
        Choose a valid selection of at least 0.4s no longer than this scene.
      </p>}
      <button type="button" className="studio-button w-full text-xs"
        disabled={!canEdit || !consent || uploading || !validTrim} onClick={() => void save()}>
        {uploading ? "Saving…" : scene.audio_state === "recorded" ? "Replace saved take" : "Save narration"}
      </button>
    </>}
    {message && <p role="status" className="text-xs text-emerald-300">{message}</p>}
    {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
  </section>;
}
