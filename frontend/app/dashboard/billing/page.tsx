"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { DashboardShell } from "@/components/dashboard/Shell";
import { apiRequest } from "@/lib/api/client";

interface CreditEntry {
  id: string;
  type: string;
  amount: number;
  currency: string;
  created_at: string;
}

export default function BillingPage() {
  const [balance, setBalance] = useState<number | null>(null);
  const [currency, setCurrency] = useState("CRD");
  const [history, setHistory] = useState<CreditEntry[]>([]);

  useEffect(() => {
    apiRequest<{ balance: number; currency: string }>("/billing/credits").then((d) => {setBalance(d.balance);setCurrency(d.currency);});
    apiRequest<CreditEntry[]>("/billing/credits/history").then(setHistory);
  }, []);

  return (
    <DashboardShell>
      <h1 className="mb-6 text-2xl font-semibold">Billing</h1>

      <Card className="mb-6 max-w-md">
        <p className="text-sm text-slate-500">Available usage credits ({currency}, not USD)</p>
        <p className="mt-1 text-3xl font-semibold">{balance === null ? "..." : balance.toFixed(0)}</p>
        <p className="mt-2 text-xs text-slate-500">Credits are charged for generation and refunded if a generation job fails. No payment checkout is enabled yet.</p>
      </Card>

      <Card className="max-w-2xl">
        <h2 className="mb-4 text-sm font-semibold text-slate-700">Recent activity</h2>
        {history.length === 0 ? (
          <p className="text-sm text-slate-400">No ledger entries yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {history.map((entry) => (
              <li key={entry.id} className="flex items-center justify-between py-2 text-sm">
                <span className="capitalize text-slate-700">{entry.type}</span>
                <span className="text-slate-500">
                  {entry.amount} {entry.currency}
                </span>
                <span className="text-slate-400">{new Date(entry.created_at).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </DashboardShell>
  );
}
