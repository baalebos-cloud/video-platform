"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { DashboardShell } from "@/components/dashboard/Shell";
import { StudioIcon } from "@/components/ui/StudioIcon";
import { apiRequest } from "@/lib/api/client";
import type { CreatorOverview } from "@/types";

function TrendGraph({ trend }: { trend: CreatorOverview["trend"] }) {
  const max = Math.max(1, ...trend.map(d => d.views));
  const { line, fill } = useMemo(() => {
    const points = trend.map((d, i) => ({
      x: 20 + (i / Math.max(1, trend.length - 1)) * 760,
      y: 194 - (d.views / max) * 166,
    }));
    const line = points.map(p => `${p.x},${p.y}`).join(" ");
    const fill = points.length ? `20,200 ${line} 780,200` : "";
    return { line, fill };
  }, [trend, max]);
  const anyViews = trend.some(row => row.views > 0);
  return <div className="relative">
    <svg role="img" aria-label="Recorded cumulative view snapshots by date" className="h-auto w-full" viewBox="0 0 800 220" preserveAspectRatio="xMidYMid meet">
      <defs><linearGradient id="viewsFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#986cf6" stopOpacity=".36" />
        <stop offset="1" stopColor="#986cf6" stopOpacity="0" />
      </linearGradient></defs>
      {[28,84,140,196].map(y => <line key={y} x1="20" x2="780" y1={y} y2={y} stroke="#333447" strokeDasharray="4 5" />)}
      {anyViews && <><polygon points={fill} fill="url(#viewsFill)" />
        <polyline points={line} fill="none" stroke="#b297ff" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" /></>}
      {!anyViews && <text x="400" y="112" textAnchor="middle" fill="#9298b3" fontSize="18">No recorded view data yet</text>}
    </svg>
    <div className="flex justify-between px-4 text-xs text-[#9398b2]">
      <span>{trend[0] ? new Date(trend[0].date + "T00:00:00").toLocaleDateString() : "—"}</span>
      <span>{trend[trend.length - 1] ? new Date(trend[trend.length - 1].date + "T00:00:00").toLocaleDateString() : "—"}</span>
    </div>
  </div>;
}

const cards = [
  { key: "views", title: "Recorded views", icon: "eye" },
  { key: "likes", title: "Likes", icon: "check" },
  { key: "shares", title: "Shares", icon: "arrow" },
  { key: "comments", title: "Comments", icon: "captions" },
] as const;

export default function AnalyticsPage() {
  const [data, setData] = useState<CreatorOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let mounted = true;
    apiRequest<CreatorOverview>("/creator/overview")
      .then(result => { if (mounted) setData(result); })
      .catch(() => { if (mounted) setError("Could not load analytics. Please refresh."); });
    return () => { mounted = false; };
  }, []);
  return <DashboardShell>
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="studio-eyebrow mb-2">Know your audience</p>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Analytics overview</h1>
        <p className="mt-2 text-sm text-[#9c9fba]">Real publishing snapshots for your connected channels.</p>
      </div>
      <Link href="/dashboard" className="studio-button-secondary">
        <StudioIcon name="back" size={16} /> Back to dashboard
      </Link>
    </div>
    {error && <p role="alert" className="mb-5 rounded-xl border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-200">{error}</p>}
    <div className="mb-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card, index) => (
        <div className="studio-stat" key={card.key}>
          <div className="mb-4 flex items-center justify-between">
            <span className="text-xs text-[#a0a4bd]">{card.title}</span>
            <span className={`rounded-xl p-2.5 ${index % 2 ? "bg-sky-400/10 text-sky-300" : "bg-violet-400/10 text-violet-300"}`}>
              <StudioIcon name={card.icon} />
            </span>
          </div>
          <strong className="text-3xl font-bold">{data ? data.stats[card.key].toLocaleString() : "—"}</strong>
        </div>
      ))}
    </div>
    <div className="mb-7 grid gap-5 xl:grid-cols-[minmax(0,1.8fr)_minmax(280px,1fr)]">
      <section className="studio-surface p-5 sm:p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div><p className="studio-eyebrow mb-1">Performance</p>
            <h2 className="text-lg font-semibold">Views over time</h2></div>
          <span className="rounded-lg bg-white/5 px-3 py-2 text-xs text-[#a9abc0]">Last 14 days</span>
        </div>
        {data ? <TrendGraph trend={data.trend} /> : <div className="h-60 animate-pulse rounded-xl bg-white/5" />}
        <p className="mt-4 text-xs leading-relaxed text-[#9196b1]">
          Recorded cumulative view snapshots for each date. These values are not daily new views.
        </p>
      </section>
      <section className="studio-surface p-5 sm:p-6">
        <p className="studio-eyebrow mb-1">Distribution</p>
        <h2 className="mb-5 text-lg font-semibold">Channel performance</h2>
        {data?.platforms.length ? <div className="space-y-5">
          {data.platforms.map(platform => {
            const share = data.stats.views > 0 ? platform.views / data.stats.views * 100 : 0;
            return <div key={platform.platform}>
              <div className="mb-2 flex justify-between text-sm">
                <span className="capitalize text-[#d8daed]">{platform.platform.replace(/_/g, " ")}</span>
                <span className="text-[#aeb2c6]">{platform.views.toLocaleString()} views</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500"
                  style={{ width: `${Math.max(0, Math.min(100, share))}%` }} />
              </div>
              <div className="mt-1 text-right text-[11px] text-[#8e93ae]">{platform.posts} published posts</div>
            </div>;
          })}
        </div> : <div className="flex h-48 flex-col items-center justify-center gap-2 text-center">
          <StudioIcon name="chart" size={32} className="text-violet-300" />
          <p className="text-sm font-medium">No published videos yet</p>
          <p className="text-xs text-[#9a9db6]">Performance appears here after publishing and data sync.</p>
        </div>}
      </section>
    </div>
    <section className="studio-surface overflow-hidden">
      <div className="border-b border-white/10 p-5 sm:p-6">
        <p className="studio-eyebrow mb-1">Breakdown</p>
        <h2 className="text-lg font-semibold">Platform details</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="bg-white/[0.025] text-xs text-[#9b9eb6]">
            <tr>{["Platform", "Published", "Views", "Likes", "Shares", "Comments"].map(col => (
              <th key={col} className="px-5 py-4 font-medium">{col}</th>
            ))}</tr>
          </thead>
          <tbody className="divide-y divide-white/[0.06]">
            {data?.platforms.map(row => <tr key={row.platform} className="text-[#daddf1]">
              <td className="px-5 py-4 font-semibold capitalize">{row.platform.replace(/_/g, " ")}</td>
              <td className="px-5 py-4">{row.posts.toLocaleString()}</td>
              <td className="px-5 py-4">{row.views.toLocaleString()}</td>
              <td className="px-5 py-4">{row.likes.toLocaleString()}</td>
              <td className="px-5 py-4">{row.shares.toLocaleString()}</td>
              <td className="px-5 py-4">{row.comments.toLocaleString()}</td>
            </tr>)}
            {data && !data.platforms.length && <tr><td colSpan={6} className="px-5 py-10 text-center text-[#9196b0]">No synchronized publishing records available.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  </DashboardShell>;
}
