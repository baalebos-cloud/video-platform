import { Suspense } from "react";
import { DashboardShell } from "@/components/dashboard/Shell";
import NewVideoForm from "./NewVideoForm";

export default function NewVideoPage() {
  return (
    <Suspense
      fallback={
        <DashboardShell>
          <p className="text-sm text-slate-500">Loading...</p>
        </DashboardShell>
      }
    >
      <NewVideoForm />
    </Suspense>
  );
}
