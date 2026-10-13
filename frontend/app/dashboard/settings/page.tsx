"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { DashboardShell } from "@/components/dashboard/Shell";
import { useAuth } from "@/hooks/useAuth";
import { apiRequest, ApiError } from "@/lib/api/client";


export default function SettingsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [revokePassword, setRevokePassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Array<{
    id: string; created_at: string; expires_at: string; current: boolean;
  }>>([]);
  const [sessionsError, setSessionsError] = useState("");
  useEffect(() => {
    let mounted = true;
    apiRequest<{sessions: typeof sessions}>("/auth/sessions")
      .then(data => {if(mounted) setSessions(data.sessions);})
      .catch(()=>{if(mounted) setSessionsError("Unable to load sessions.");});
    return () => {mounted = false;};
  }, []);

  async function revokeOne(id: string, isCurrent: boolean) {
    setError(null);
    try {
      await apiRequest(`/auth/sessions/${id}`, {method:"DELETE"});
      setSessions(previous=>previous.filter(row=>row.id!==id));
      if (isCurrent) exitToLogin();
    } catch(e) {
      setError(e instanceof ApiError ? e.message : "Unable to revoke session.");
    }
  }


  function exitToLogin() {
    router.replace("/login");
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setError("New passwords must match.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await apiRequest("/auth/password/change", {
        method: "POST", body: { current_password: currentPassword, new_password: newPassword },
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      exitToLogin();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Password change failed.");
    } finally { setBusy(false); }
  }

  async function revokeSessions(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiRequest("/auth/sessions/revoke-all", {
        method: "POST", body: { password: revokePassword },
      });
      setRevokePassword("");
      exitToLogin();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not revoke sessions.");
    } finally { setBusy(false); }
  }

  return <DashboardShell>
    <div className="mb-8">
      <p className="studio-eyebrow mb-2">Your account</p>
      <h1 className="text-3xl font-bold text-white">Account settings</h1>
      <p className="mt-2 text-sm text-[#a4a8be]">Manage your account and protect access to your videos.</p>
    </div>

    <section className="studio-surface mb-6 max-w-2xl p-6">
      <h2 className="mb-4 text-lg font-semibold">Profile</h2>
      <dl className="grid gap-4 text-sm sm:grid-cols-2">
        <div><dt className="text-[#979cb6]">Email</dt><dd className="mt-1 text-white">{user?.email || "—"}</dd></div>
        <div><dt className="text-[#979cb6]">Full name</dt><dd className="mt-1 text-white">{user?.full_name || "—"}</dd></div>
        <div><dt className="text-[#979cb6]">Status</dt><dd className="mt-1 capitalize text-white">{user?.status || "—"}</dd></div>
      </dl>
    </section>

    <section className="studio-surface mb-6 max-w-2xl p-6">
      <h2 className="text-lg font-semibold">Change password</h2>
      <p className="mt-2 text-sm text-[#a4a8be]">
        Changing your password signs out all devices. Sign in again using the new password.
      </p>
      <form onSubmit={changePassword} className="mt-5 space-y-4">
        <label className="block text-xs font-semibold text-[#b4b8cf]">Current password
          <input type="password" autoComplete="current-password" required
            value={currentPassword} onChange={e => setCurrentPassword(e.target.value)}
            className="studio-input mt-2" />
        </label>
        <label className="block text-xs font-semibold text-[#b4b8cf]">New password (12–72 characters)
          <input type="password" autoComplete="new-password" minLength={12} maxLength={72} required
            value={newPassword} onChange={e => setNewPassword(e.target.value)}
            className="studio-input mt-2" />
        </label>
        <label className="block text-xs font-semibold text-[#b4b8cf]">Confirm new password
          <input type="password" autoComplete="new-password" minLength={12} maxLength={72} required
            value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
            className="studio-input mt-2" />
        </label>
        <button type="submit" disabled={busy || !currentPassword || newPassword.length < 12 ||
          newPassword !== confirmPassword} className="studio-button">
          {busy ? "Saving…" : "Update password and sign out"}
        </button>
      </form>
    </section>

    <section className="studio-surface mb-6 max-w-2xl p-6">
      <h2 className="mb-2 text-lg font-semibold">Active sessions</h2>
      <p className="mb-4 text-sm text-[#a4a8be]">Review devices with an active refresh session and revoke access individually.</p>
      {sessionsError&&<p role="alert" className="text-xs text-rose-300">{sessionsError}</p>}
      <div className="space-y-3">
        {sessions.map(session=><div key={session.id} className="flex flex-wrap justify-between gap-3 rounded-xl border border-white/10 p-3">
          <div className="text-xs text-[#ccd0df]">
            <span className="font-semibold">{session.current ? "This device" : "Signed-in session"}</span>
            <div>Created {new Date(session.created_at).toLocaleString()}</div>
            <div>Expires {new Date(session.expires_at).toLocaleString()}</div>
          </div>
          <button type="button" className="studio-button-secondary"
            onClick={()=>void revokeOne(session.id,session.current)}>Revoke</button>
        </div>)}
        {!sessions.length&&!sessionsError&&<p className="text-xs text-[#8d93ac]">No listed sessions.</p>}
      </div>
    </section>

    <section className="studio-surface max-w-2xl p-6">
      <h2 className="text-lg font-semibold">Sign out everywhere</h2>
      <p className="mt-2 text-sm text-[#a4a8be]">
        Revoke all active sign-in tokens immediately. This includes the current browser.
      </p>
      <form onSubmit={revokeSessions} className="mt-5 space-y-4">
        <label className="block text-xs font-semibold text-[#b4b8cf]">Confirm your password
          <input type="password" autoComplete="current-password" required
            value={revokePassword} onChange={e => setRevokePassword(e.target.value)}
            className="studio-input mt-2" />
        </label>
        <button type="submit" disabled={busy || !revokePassword} className="studio-button-secondary">
          {busy ? "Revoking…" : "Sign out all devices"}
        </button>
      </form>
    </section>
    {error && <p role="alert" className="mt-6 text-sm text-rose-300">{error}</p>}
  </DashboardShell>;
}
