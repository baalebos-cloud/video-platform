"use client";

import { useEffect, useState } from "react";
import { DashboardShell } from "@/components/dashboard/Shell";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { apiRequest } from "@/lib/api/client";

interface CreditEntry {
  id: string;
  type: string;
  amount: number;
  currency: string;
  reference_type?: string | null;
  created_at: string;
}
interface Usage {
  recorded_outputs: number;
  breakdown: Array<{ provider: string; model: string; type: string; outputs: number }>;
  metric_note: string;
}

export default function BillingPage() {
  const [balance, setBalance] = useState<number | null>(null);
  const [currency, setCurrency] = useState("CRD");
  const [history, setHistory] = useState<CreditEntry[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiRequest<{ balance: number; currency: string }>("/billing/credits"),
      apiRequest<CreditEntry[]>("/billing/credits/history"),
      apiRequest<Usage>("/billing/usage?days=30"),
    ]).then(([credits, entries, media]) => {
      if (!active) return;
      setBalance(credits.balance);
      setCurrency(credits.currency);
      setHistory(entries);
      setUsage(media);
    }).catch(() => {
      if (active) setError("We could not load your credit and usage details. Refresh the page.");
    });
    return () => { active = false; };
  }, []);

  return <DashboardShell>
    <div className="mb-8">
      <p className="studio-eyebrow mb-2">Your account</p>
      <h1 className="text-3xl font-bold text-white">Credits & usage</h1>
      <p className="mt-2 text-sm text-[#a4a8be]">Track internal usage credits and saved AI media assets.</p>
    </div>
    {error && <p role="alert" className="mb-5 rounded-xl border border-rose-400/20 bg-rose-500/10 p-4 text-sm text-rose-300">{error}</p>}
    <div className="mb-7 grid gap-4 lg:grid-cols-2">
      <section className="studio-surface relative overflow-hidden p-6">
        <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-violet-500/15 blur-3xl" />
        <span className="mb-5 inline-flex rounded-xl bg-violet-500/15 p-3 text-[#c8b7ff]"><StudioIcon name="wallet" size={24} /></span>
        <p className="text-sm text-[#aeb2c7]">Available usage credits</p>
        <p className="mt-2 text-4xl font-bold text-white">{balance === null ? "—" : balance.toLocaleString()} <span className="text-lg font-medium text-[#aba4cd]">{currency}</span></p>
        <p className="mt-5 text-xs leading-relaxed text-[#9398b3]">
          CRD is an internal video-creation credit, not a USD balance. There is no online credit checkout at this time.
        </p>
      </section>
      <section className="studio-surface p-6">
        <span className="mb-5 inline-flex rounded-xl bg-sky-500/15 p-3 text-sky-300"><StudioIcon name="film" size={24} /></span>
        <p className="text-sm text-[#aeb2c7]">Recorded AI media outputs · 30 days</p>
        <p className="mt-2 text-4xl font-bold text-white">{usage ? usage.recorded_outputs.toLocaleString() : "—"}</p>
        <p className="mt-5 text-xs leading-relaxed text-[#9398b3]">
          Counts saved voice and image assets. Actual provider call counts and dollar spending may differ.
        </p>
      </section>
    </div>
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <section className="studio-surface overflow-hidden">
        <div className="border-b border-white/10 p-5">
          <p className="studio-eyebrow mb-1">Account history</p>
          <h2 className="text-lg font-semibold">Credit activity</h2>
        </div>
        <div className="max-h-[520px] overflow-y-auto">
          {history.length ? <ul className="divide-y divide-white/[0.07]">
            {history.map(item => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 text-sm">
              <div>
                <p className="font-semibold capitalize text-[#e5e4f2]">{item.type.replace(/_/g, " ")}</p>
                <p className="mt-1 text-xs text-[#9499b2]">{item.reference_type?.replace(/_/g, " ") || "Account activity"} · {new Date(item.created_at).toLocaleString()}</p>
              </div>
              <span className={`font-semibold ${item.amount >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                {item.amount > 0 ? "+" : ""}{item.amount} {item.currency}
              </span>
            </li>)}
          </ul> : <p className="px-5 py-12 text-center text-sm text-[#9297b0]">No credit activity recorded yet.</p>}
        </div>
      </section>
      <section className="studio-surface p-5">
        <p className="studio-eyebrow mb-1">Media report</p>
        <h2 className="mb-5 text-lg font-semibold">Provider breakdown</h2>
        {usage?.breakdown.length ? <div className="space-y-3">
          {usage.breakdown.map((item, index) => <div key={index}
            className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.07] bg-[#111320] p-3">
            <div>
              <p className="text-sm font-semibold text-white">{item.provider} · {item.type}</p>
              <p className="mt-1 text-xs text-[#959ab3]">{item.model}</p>
            </div>
            <p className="text-lg font-semibold text-[#c9b9ff]">{item.outputs}</p>
          </div>)}
        </div> : <p className="py-9 text-center text-sm text-[#9398b1]">No saved AI media in the last 30 days.</p>}
        <p className="mt-5 text-xs leading-relaxed text-[#9398b1]">{usage?.metric_note || "Usage reporting is based on stored media, not provider invoices."}</p>
      </section>
    </div>
  </DashboardShell>;
}
