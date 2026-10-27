"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "@/lib/api/client";

export type VoiceProfile = {
  id: string; name: string; language: string;
  duration_seconds: number; status: "reference_saved";
};
export type VoiceCapabilities = {
  personal_recordings: boolean; reference_profiles: boolean;
  automatic_cloning: boolean; languages: string[]; notice: string;
};

export function VoiceProfiles({ language, selectedId, onSelect, onReady }: {
  language: string; selectedId: string; onSelect: (value: string) => void;
  onReady: (available: boolean) => void;
}) {
  const [capabilities, setCapabilities] = useState<VoiceCapabilities | null>(null);
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [name, setName] = useState("My voice");
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [cap, items] = await Promise.all([
      apiRequest<VoiceCapabilities>("/voice-profiles/capabilities"),
      apiRequest<VoiceProfile[]>("/voice-profiles"),
    ]);
    setCapabilities(cap);
    setProfiles(items);
    onReady(cap.automatic_cloning);
  }, [onReady]);

  useEffect(() => {
    void refresh().catch(() => setError("Unable to load your private voice profiles."));
  }, [refresh]);

  async function enroll() {
    if (!file || !consent || busy) return;
    setBusy(true); setError(null); setStatus(null);
    try {
      if (file.size > 3 * 1024 * 1024) throw new Error("Reference audio must be under 3 MB.");
      const response = await fetch("/api/gateway/voice-profiles", {
        method: "POST", credentials: "same-origin",
        headers: {
          "Content-Type": file.type || "audio/wav",
          "X-Voice-Consent": "confirmed", "X-Clone-Consent": "confirmed",
          "X-Voice-Name": name, "X-Voice-Language": language,
        },
        body: file,
      });
      if (!response.ok) {
        const details = await response.json().catch(() => ({})) as {detail?: string};
        throw new Error(details.detail || `Enrollment failed (HTTP ${response.status}).`);
      }
      const saved = await response.json() as VoiceProfile;
      setFile(null); setConsent(false); setStatus("Private reference saved. You can revoke it below.");
      await refresh();
      onSelect(saved.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save reference audio.");
    } finally { setBusy(false); }
  }

  async function revoke(id: string) {
    if (!window.confirm("Delete this voice reference? This cannot be undone.")) return;
    setBusy(true); setError(null); setStatus(null);
    try {
      await apiRequest(`/voice-profiles/${id}`, {method:"DELETE"});
      if (id === selectedId) onSelect("");
      await refresh();
      setStatus("Reference revoked and deletion requested.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete profile.");
    } finally { setBusy(false); }
  }

  return <section aria-label="My AI voice profiles" className="space-y-3 rounded-xl border border-violet-400/20 bg-violet-500/5 p-4">
    <div>
      <p className="text-sm font-semibold text-white">My AI Voice: reference library</p>
      <p className="mt-1 text-xs leading-relaxed text-[#a7abc4]">
        Save a clear 5–20 second reference once. This is not a generated voice model.
        Automatic synthesis works only after a licensed multilingual voice service is configured.
      </p>
    </div>
    <p role="status" className={`text-xs ${capabilities?.automatic_cloning ? "text-emerald-300" : "text-amber-200"}`}>
      {capabilities?.notice || "Checking AI voice provider…"}
    </p>
    {profiles.length > 0 && <div className="space-y-2">
      {profiles.map(profile => <div key={profile.id}
        className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/15 p-2">
        <label className="min-w-0 flex-1 text-xs text-[#e4e2ee]">
          <input type="radio" className="mr-2 accent-violet-400"
            checked={selectedId === profile.id}
            disabled={busy || !capabilities?.automatic_cloning || profile.language !== language}
            onChange={() => onSelect(profile.id)}/>
          {profile.name}
          <span className="block pl-5 text-[11px] text-[#9a9eb9]">
            {profile.language} · {profile.duration_seconds}s · Private reference
          </span>
        </label>
        <button type="button" disabled={busy} onClick={() => void revoke(profile.id)}
          className="rounded-md border border-rose-400/25 px-2 py-1 text-xs text-rose-200 hover:bg-rose-500/10">
          Delete
        </button>
      </div>)}
    </div>}
    <label className="block text-xs text-[#d2d5e2]">
      Reference name
      <input className="studio-input mt-1" maxLength={60} value={name}
        onChange={event => setName(event.target.value)}/>
    </label>
    <label className="block text-xs text-[#d2d5e2]">
      Reference audio, 5–20 seconds (WAV, MP3, WebM, M4A)
      <input className="mt-2 block w-full text-xs" type="file"
        accept="audio/wav,audio/mpeg,audio/webm,audio/mp4,audio/ogg,.wav,.mp3,.m4a,.webm"
        onChange={event => setFile(event.target.files?.[0] ?? null)}/>
    </label>
    <label className="flex items-start gap-2 text-xs leading-relaxed text-[#bfc3d8]">
      <input className="mt-1 accent-violet-400" type="checkbox" checked={consent}
        onChange={event => setConsent(event.target.checked)}/>
      This is my own voice and I explicitly consent to storing this reference
      for future synthetic narration. I can revoke it at any time.
    </label>
    <button type="button" className="studio-button-secondary text-xs"
      disabled={!file || !consent || busy || !name.trim()}
      onClick={() => void enroll()}>{busy ? "Saving…" : "Save private voice reference"}</button>
    {status && <p role="status" className="text-xs text-emerald-300">{status}</p>}
    {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
  </section>;
}
