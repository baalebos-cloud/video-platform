"use client";

import { FormEvent, useEffect, useState } from "react";
import { DashboardShell } from "@/components/dashboard/Shell";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { useAuth } from "@/hooks/useAuth";
import { apiRequest, ApiError } from "@/lib/api/client";

interface Account {
  id: string;
  email: string;
  status: string;
  balance: string;
  currency: string;
}
interface Usage {
  period_days: number;
  recorded_outputs: number;
  breakdown: Array<{ provider: string; model: string; type: string; outputs: number }>;
  metric_note: string;
}
interface AdjustmentResult {
  request_id: string;
  applied: boolean;
  balance: string;
  currency: string;
}

export default function AdministrationPage() {
  const { user, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [account, setAccount] = useState<Account | null>(null);
  const [lookupBusy, setLookupBusy] = useState(false);
  const [amount, setAmount] = useState("10");
  const [reason, setReason] = useState("");
  const [adjustBusy, setAdjustBusy] = useState(false);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.is_admin) return;
    let active = true;
    setUsage(null);
    setUsageError(null);
    apiRequest<Usage>(`/admin/usage?days=${days}`)
      .then(result => { if (active) setUsage(result); })
      .catch(() => { if (active) setUsageError("Unable to load provider output report."); });
    return () => { active = false; };
  }, [user?.is_admin, days]);

  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLookupBusy(true);
    setAccount(null);
    setError(null);
    setFeedback(null);
    try {
      setAccount(await apiRequest<Account>(`/admin/users/lookup?email=${encodeURIComponent(email.trim())}`));
      setRequestId(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Account lookup failed.");
    } finally { setLookupBusy(false); }
  }

  async function adjust(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!account) return;
    setAdjustBusy(true);
    setError(null);
    setFeedback(null);
    const id = requestId || crypto.randomUUID();
    setRequestId(id);
    try {
      const result = await apiRequest<AdjustmentResult>("/admin/credits/adjust", {
        method: "POST",
        body: {
          user_id: account.id,
          amount: Number(amount),
          reason: reason.trim(),
          request_id: id,
        },
      });
      setAccount({ ...account, balance: result.balance });
      setFeedback(result.applied
        ? "Credit adjustment recorded with an audit entry."
        : "This request was already applied; no second adjustment was made.");
      setRequestId(null);
    } catch (cause) {
      // Preserve request ID: safe retry without granting a second adjustment.
      setError(cause instanceof ApiError ? cause.message : "Adjustment could not be confirmed; retry with the same inputs.");
    } finally { setAdjustBusy(false); }
  }

  return <DashboardShell>
    <div className="mb-8">
      <p className="studio-eyebrow mb-2">Restricted operations</p>
      <h1 className="text-3xl font-bold text-white">Administration</h1>
      <p className="mt-2 text-sm text-[#a4a8be]">
        Account usage credits and recorded AI media outputs. Not a payment settlement dashboard.
      </p>
    </div>
    {loading ? <p className="text-sm text-[#a8acc3]">Checking permissions…</p>
      : !user?.is_admin ? <div role="alert" className="studio-surface p-6 text-sm text-rose-300">
        You do not have administrator access.
      </div> : <>
      <div className="grid gap-6 xl:grid-cols-2">
        <section className="studio-surface p-6">
          <div className="mb-5 flex items-center gap-3">
            <StudioIcon name="wallet" className="text-[#bea9ff]" />
            <h2 className="text-lg font-semibold">Manage user credits</h2>
          </div>
          <form onSubmit={lookup} className="flex flex-wrap items-end gap-3">
            <label className="min-w-[220px] flex-1 text-xs font-semibold text-[#b3b7cf]">
              Look up account by email
              <input type="email" value={email} required onChange={e => setEmail(e.target.value)}
                className="studio-input mt-2" placeholder="creator@example.com" />
            </label>
            <button type="submit" disabled={lookupBusy} className="studio-button-secondary">
              <StudioIcon name="search" size={16} /> {lookupBusy ? "Searching…" : "Find account"}
            </button>
          </form>

          {account && <div className="mt-6 rounded-xl border border-white/10 bg-[#10121e] p-4">
            <div className="flex flex-wrap justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">{account.email}</p>
                <p className="mt-1 text-xs capitalize text-[#9ca0b9]">Status: {account.status}</p>
              </div>
              <div className="text-right">
                <p className="text-xs text-[#9ca0b9]">Available credits</p>
                <p className="text-xl font-semibold">{Number(account.balance).toLocaleString()} {account.currency}</p>
              </div>
            </div>
            <form onSubmit={adjust} className="mt-6 space-y-4 border-t border-white/10 pt-5">
              <label className="block text-xs font-semibold text-[#b4b8cf]">
                Adjustment in CRD (negative removes credits)
                <input type="number" min={-1000} max={1000} required value={amount}
                  onChange={e => { setAmount(e.target.value); setRequestId(null); }}
                  className="studio-input mt-2" />
              </label>
              <label className="block text-xs font-semibold text-[#b4b8cf]">
                Reason for change (12 characters minimum)
                <textarea rows={3} minLength={12} maxLength={300} required value={reason}
                  onChange={e => { setReason(e.target.value); setRequestId(null); }}
                  className="studio-input mt-2" placeholder="Explain the authorized adjustment…" />
              </label>
              <p className="text-xs text-[#9ca0b8]">
                Every successful adjustment creates a credit-ledger entry and administrator audit record.
                You cannot adjust your own account.
              </p>
              <button type="submit"
                disabled={adjustBusy || !Number.isInteger(Number(amount)) || Number(amount) === 0 || reason.trim().length < 12}
                className="studio-button">
                <StudioIcon name="check" size={16} /> {adjustBusy ? "Submitting…" : "Apply adjustment"}
              </button>
            </form>
          </div>}
        </section>

        <section className="studio-surface p-6">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="studio-eyebrow mb-1">AI media activity</p>
              <h2 className="text-lg font-semibold">Provider output reporting</h2>
            </div>
            <label className="text-xs text-[#aab0c8]">Period
              <select value={days} onChange={e => setDays(Number(e.target.value))}
                className="studio-input mt-2">
                <option value={7}>7 days</option><option value={30}>30 days</option>
                <option value={90}>90 days</option>
              </select>
            </label>
          </div>
          {usageError && <p role="alert" className="text-sm text-rose-300">{usageError}</p>}
          {usage ? <>
            <div className="mb-5 rounded-xl bg-violet-400/10 p-5">
              <p className="text-xs text-[#adb1c8]">Saved AI media outputs</p>
              <p className="mt-2 text-3xl font-bold">{usage.recorded_outputs.toLocaleString()}</p>
            </div>
            <div className="max-h-[360px] overflow-x-auto">
              <table className="w-full min-w-[410px] text-left text-xs">
                <thead className="text-[#a9abc2]"><tr>
                  {["Provider", "Model", "Media", "Outputs"].map(name =>
                    <th key={name} className="border-b border-white/10 px-2 py-3">{name}</th>)}
                </tr></thead>
                <tbody className="divide-y divide-white/[0.07]">
                  {usage.breakdown.map((row, i) => <tr key={i}>
                    <td className="px-2 py-3">{row.provider}</td>
                    <td className="px-2 py-3">{row.model}</td>
                    <td className="px-2 py-3 capitalize">{row.type}</td>
                    <td className="px-2 py-3">{row.outputs}</td>
                  </tr>)}
                  {!usage.breakdown.length && <tr><td colSpan={4} className="py-8 text-center text-[#989eb9]">
                    No saved provider media in this period.
                  </td></tr>}
                </tbody>
              </table>
            </div>
            <p className="mt-4 text-xs leading-relaxed text-[#9298b1]">{usage.metric_note}</p>
          </> : !usageError && <p className="text-sm text-[#9298b1]">Loading recorded outputs…</p>}
        </section>
      </div>
      {feedback && <p role="status" className="mt-6 rounded-xl bg-emerald-500/10 p-4 text-sm text-emerald-300">{feedback}</p>}
      {error && <p role="alert" className="mt-6 rounded-xl bg-rose-500/10 p-4 text-sm text-rose-300">{error}</p>}
    </>}
  </DashboardShell>;
}
