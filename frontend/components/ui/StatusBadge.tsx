const STATUS_STYLES: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  queued: "bg-blue-100 text-blue-700",
  planning: "bg-blue-100 text-blue-700",
  scripting: "bg-blue-100 text-blue-700",
  storyboarding: "bg-blue-100 text-blue-700",
  generating_assets: "bg-amber-100 text-amber-700",
  rendering: "bg-amber-100 text-amber-700",
  ready: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-slate-100 text-slate-500",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${style}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
