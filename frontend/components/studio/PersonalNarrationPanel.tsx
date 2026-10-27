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
  const activeSceneId = useRef(scene.id);
  activeSceneId.current = scene.id;
  const [consent, setConsent] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordedSeconds, setRecordedSeconds] = useState(0);
  const [microphoneLevel, setMicrophoneLevel] = useState<number | null>(null);
  const [sourceSeconds, setSourceSeconds] = useState<number | null>(null);
  const [trimStart, setTrimStart] = useState(0);
  const [trimEnd, setTrimEnd] = useState(0);
  const [audio, setAudio] = useState<Blob | File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const { url: storedVoiceUrl } = useSignedMedia(scene.audio_state === "recorded" ? scene.audio_asset_id : null);

  useEffect(() => {
    if (!recording) return;
    const started = Date.now();
    const interval = window.setInterval(() => {
      const elapsed = (Date.now() - started) / 1000;
      setRecordedSeconds(elapsed);
      if (elapsed >= scene.duration_seconds && mediaRecorder.current?.state === "recording") {
        mediaRecorder.current.stop();
      }
    }, 200);
    return () => window.clearInterval(interval);
  }, [recording, scene.duration_seconds]);

  useEffect(() => {
    // Read the existing microphone stream locally. The level never leaves
    // the browser and no additional audio is saved or transmitted.
    if (!recording || !mediaStream.current) {
      return;
    }
    const Context = window.AudioContext;
    if (!Context) return;
    let context: AudioContext | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;
    try {
      context = new Context();
      const source = context.createMediaStreamSource(mediaStream.current);
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      const readings = new Uint8Array(analyser.frequencyBinCount);
      timer = setInterval(() => {
        analyser.getByteFrequencyData(readings);
        // A relative mic activity indicator, not a calibrated decibel meter.
        const mean = readings.reduce((sum, level) => sum + level, 0) / readings.length;
        setMicrophoneLevel(Math.min(100, Math.round(mean / 128 * 100)));
      }, 180);
    } catch {
      // Microphone recording still works when web audio metering is blocked.
      void context?.close().catch(() => undefined);
      return;
    }
    const activeContext = context;
    return () => {
      if (timer) clearInterval(timer);
      void activeContext?.close().catch(() => undefined);
      setMicrophoneLevel(null);
    };
  }, [recording]);

  useEffect(() => {
    if (!audio) { setPreviewUrl(null); return; }
    const url = URL.createObjectURL(audio);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [audio]);

  useEffect(() => {
    setAudio(null);
    setSourceSeconds(null);
    setTrimStart(0);
    setTrimEnd(0);
    setError(null);
    setMessage(null);
    setConsent(false);
  }, [scene.id]);

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
      const recordingSceneId = scene.id;
      recorder.onstop = () => {
        if (activeSceneId.current !== recordingSceneId) {
          chunks.current = [];
          stream.getTracks().forEach(track => track.stop());
          setRecording(false);
          return;
        }
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
      setRecordedSeconds(0);
      setSourceSeconds(null);
      setTrimStart(0);
      setTrimEnd(0);
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
    if (sourceSeconds !== null && (!Number.isFinite(sourceSeconds) ||
        trimEnd <= trimStart + 0.4 ||
        trimEnd - trimStart > scene.duration_seconds + 0.25)) {
      setError("Trim the recording to fit this scene before saving.");
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
          headers: {
            "Content-Type": audio.type || "audio/webm",
            "X-Voice-Consent": "confirmed",
            ...(sourceSeconds && Number.isFinite(sourceSeconds) ? {
              "X-Voice-Trim-Start": String(trimStart),
              "X-Voice-Trim-End": String(trimEnd || sourceSeconds),
            } : {}),
          },
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
      I am recording my own voice, or I have the speaker&apos;s permission to use this recording.
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
    {recording && <div role="status" className="text-xs text-amber-200">
      <div className="flex justify-between gap-3"><span>Recording microphone · {recordedSeconds.toFixed(1)}s</span>
        <span>Limit {scene.duration_seconds.toFixed(1)}s</span></div>
      {microphoneLevel !== null && <>
        <span className="mt-2 block text-[#b9c0da]">Microphone activity (relative level)</span>
        <div role="meter" aria-label="Live microphone activity"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={microphoneLevel}
          className="mt-1 h-2 overflow-hidden rounded-full bg-white/10">
          <div className="h-full bg-emerald-400 transition-[width]" style={{width: `${microphoneLevel}%`}} />
        </div>
      </>}
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/10">
        <div className="h-full bg-amber-400" style={{width: `${Math.min(100, recordedSeconds / scene.duration_seconds * 100)}%`}} />
      </div>
    </div>}
    {previewUrl && !recording && <>
      <label className="text-[11px] text-[#a9afc7]">Review new recording</label>
      <audio className="h-9 w-full" controls src={previewUrl} onLoadedMetadata={event => {
        const seconds = event.currentTarget.duration;
        if (Number.isFinite(seconds) && seconds > 0) {
          setSourceSeconds(seconds);
          setTrimStart(0);
          setTrimEnd(Math.min(seconds, scene.duration_seconds));
        }
      }}/>
      {sourceSeconds !== null && <div className="space-y-2 rounded-lg border border-white/10 p-3 text-xs">
        <p className="font-semibold text-white">Trim narration (non-destructive)</p>
        <label className="block text-[#b6bbd2]">Start: {trimStart.toFixed(1)}s
          <input className="w-full accent-violet-400" type="range" min={0} max={Math.max(0, sourceSeconds - 0.5)}
            step={0.1} value={trimStart}
            onChange={event => setTrimStart(Math.min(Number(event.target.value), trimEnd - 0.5))}/>
        </label>
        <label className="block text-[#b6bbd2]">End: {trimEnd.toFixed(1)}s
          <input className="w-full accent-violet-400" type="range" min={0.5} max={sourceSeconds}
            step={0.1} value={trimEnd}
            onChange={event => setTrimEnd(Math.max(Number(event.target.value), trimStart + 0.5))}/>
        </label>
        <p className={trimEnd - trimStart > scene.duration_seconds + 0.25
          ? "text-rose-300" : "text-emerald-300"}>
          Selected duration: {(trimEnd - trimStart).toFixed(1)}s /
          scene {scene.duration_seconds.toFixed(1)}s
        </p>
      </div>}
      <button type="button" onClick={() => {setAudio(null);setSourceSeconds(null);}}
        className="text-xs text-violet-300 hover:text-white">Discard and retake</button>
      <button type="button" disabled={!canEdit || !consent || uploading} onClick={() => void submitAudio()}
        className="studio-button w-full text-xs">{uploading ? "Saving…" : "Save narration for scene"}</button>
    </>}
    {message && <p role="status" className="text-xs text-emerald-300">{message}</p>}
    {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
  </section>;
}
