"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { apiRequest, ApiError } from "@/lib/api/client";

export default function ResetPasswordPage() {
  const [token, setToken] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [sent, setSent] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("token");
    setToken(code);
    // Do not leave the recovery credential in browser history or future
    // referrer URLs; only retain it in memory for the current page instance.
    if (code) window.history.replaceState(null, "", "/reset-password");
    setLoaded(true);
  }, []);

  async function requestLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiRequest("/auth/password-reset/request", {
        method: "POST", body: { email }, auth: false,
      });
      setSent(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to request a reset link.");
    } finally { setBusy(false); }
  }

  async function completeReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    if (password !== confirm) { setError("Passwords must match."); return; }
    setBusy(true);
    setError(null);
    try {
      await apiRequest("/auth/password-reset/confirm", {
        method: "POST", body: { token, new_password: password }, auth: false,
      });
      setCompleted(true);
      setToken(null);
      setPassword("");
      setConfirm("");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Unable to reset password.");
    } finally { setBusy(false); }
  }

  return <main className="flex min-h-screen items-center justify-center px-6">
    <Card className="w-full max-w-md">
      <h1 className="mb-3 text-xl font-semibold">Account recovery</h1>
      {!loaded ? <p className="text-sm text-slate-500">Loading…</p> : completed ? <>
        <p className="text-sm text-slate-700">Your password was changed. All previous sessions were signed out.</p>
        <Link href="/login" className="mt-5 inline-block text-sm font-semibold text-brand-600 hover:underline">
          Return to sign in
        </Link>
      </> : token ? <>
        <p className="mb-6 text-sm text-slate-600">Choose a new password with at least 12 characters.</p>
        <form onSubmit={completeReset} className="flex flex-col gap-4">
          <Input label="New password" type="password" minLength={12} maxLength={72}
            autoComplete="new-password" required value={password}
            onChange={event => setPassword(event.target.value)} />
          <Input label="Confirm password" type="password" minLength={12} maxLength={72}
            autoComplete="new-password" required value={confirm}
            onChange={event => setConfirm(event.target.value)} />
          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
          <Button type="submit" loading={busy} className="w-full">Reset password</Button>
        </form>
      </> : sent ? <>
        <p role="status" className="text-sm text-slate-700">
          If an account exists for that email address, a reset link will be emailed.
          Check your inbox and spam folder.
        </p>
        <Link href="/login" className="mt-5 inline-block text-sm font-semibold text-brand-600 hover:underline">
          Return to sign in
        </Link>
      </> : <>
        <p className="mb-6 text-sm text-slate-600">
          Enter your account email to request a one-time password reset link.
        </p>
        <form onSubmit={requestLink} className="flex flex-col gap-4">
          <Input label="Email" type="email" required value={email} autoComplete="email"
            onChange={event => setEmail(event.target.value)} />
          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
          <Button type="submit" loading={busy} className="w-full">Send reset link</Button>
        </form>
        <Link href="/login" className="mt-5 inline-block text-sm text-brand-600 hover:underline">
          Return to sign in
        </Link>
      </>}
    </Card>
  </main>;
}
