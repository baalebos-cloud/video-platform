"use client";

import { Card } from "@/components/ui/Card";
import { DashboardShell } from "@/components/dashboard/Shell";
import { useAuth } from "@/hooks/useAuth";

export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <DashboardShell>
      <h1 className="mb-6 text-2xl font-semibold">Settings</h1>
      <Card className="max-w-md">
        <dl className="flex flex-col gap-3 text-sm">
          <div>
            <dt className="text-slate-500">Email</dt>
            <dd className="font-medium text-slate-900">{user?.email}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Full name</dt>
            <dd className="font-medium text-slate-900">{user?.full_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Account status</dt>
            <dd className="font-medium capitalize text-slate-900">{user?.status}</dd>
          </div>
        </dl>
      </Card>
    </DashboardShell>
  );
}
