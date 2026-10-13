"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { StudioIcon, StudioIconName } from "@/components/ui/StudioIcon";

const MAIN_NAV: { href: string; label: string; icon: StudioIconName }[] = [
  { href: "/dashboard", label: "Overview", icon: "dashboard" },
  { href: "/dashboard/analytics", label: "Analytics", icon: "chart" },
  { href: "/dashboard/billing", label: "Credits & billing", icon: "wallet" },
  { href: "/dashboard/settings", label: "Settings", icon: "settings" },
];

export function DashboardShell({ children, wide = false }: {
  children: React.ReactNode; wide?: boolean;
}) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return <div className="flex min-h-screen items-center justify-center bg-[#0b0d16] text-sm text-[#9ea3ba]">Loading your workspace…</div>;
  }

  const nav = (
    <nav aria-label="Main navigation" className="space-y-1.5">
      {MAIN_NAV.map((item) => {
        const active = item.href === "/dashboard"
          ? pathname === "/dashboard" || pathname.startsWith("/dashboard/projects")
          : pathname === item.href;
        return (
          <Link key={item.href} href={item.href} onClick={() => setMobileNavOpen(false)}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-3 rounded-xl px-3.5 py-3 text-sm font-medium transition ${active
              ? "bg-violet-500/15 text-[#c7b3ff] ring-1 ring-violet-400/10"
              : "text-[#989cb5] hover:bg-white/5 hover:text-white"}`}>
            <StudioIcon name={item.icon} size={19} />{item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="flex min-h-screen bg-[#0b0d16] text-[#ecedf7]">
      <aside className="sticky top-0 hidden h-screen w-[246px] shrink-0 flex-col border-r border-white/[0.07] bg-[#11131f] px-4 py-7 lg:flex">
        <Link href="/dashboard" className="mb-12 flex items-center gap-3 px-2">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-lg shadow-violet-600/20">
            <StudioIcon name="sparkles" size={22} />
          </span>
          <span><strong className="block text-[15px] tracking-wide">BAALEBOS</strong>
            <small className="block text-[10px] font-semibold uppercase tracking-[0.25em] text-[#8f95b1]">Creator Studio</small>
          </span>
        </Link>
        <p className="mb-3 px-3 text-[10px] font-bold uppercase tracking-[0.22em] text-[#626982]">Workspace</p>
        {nav}
        <div className="mt-auto rounded-xl border border-violet-400/10 bg-gradient-to-br from-violet-500/10 to-fuchsia-500/5 p-4">
          <StudioIcon name="sparkles" size={20} className="mb-2 text-[#c4a9ff]" />
          <p className="mb-1 text-sm font-semibold">Create something great</p>
          <p className="text-xs leading-relaxed text-[#a4a8bd]">Make the next video your best one yet.</p>
        </div>
        <button type="button" onClick={logout}
          className="mt-5 flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-[#969bb4] hover:bg-white/5 hover:text-white">
          <StudioIcon name="logout" size={17} /> Sign out
        </button>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex h-[72px] items-center justify-between border-b border-white/[0.07] bg-[#0e101b]/95 px-4 backdrop-blur-xl sm:px-8">
          <div className="flex items-center gap-3">
            <button type="button" className="rounded-lg p-2 text-white hover:bg-white/10 lg:hidden"
              aria-label="Toggle navigation" aria-expanded={mobileNavOpen}
              onClick={() => setMobileNavOpen(v => !v)}>
              <StudioIcon name="menu" />
            </button>
            <Link href="/dashboard" className="text-xs font-semibold uppercase tracking-[0.18em] text-[#a5a9c0] lg:text-sm">
              Creative workspace
            </Link>
            <span className="hidden text-[#545a70] sm:block">/</span>
            <span className="hidden text-sm font-medium text-white sm:block">{pathname.includes("studio") ? "Editor" : "Dashboard"}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden max-w-[200px] truncate text-xs text-[#9197b0] sm:block">{user.email}</span>
            <span className="flex h-9 w-9 items-center justify-center rounded-full border border-violet-400/30 bg-violet-500/20 text-sm font-semibold text-[#d6c9ff]">
              {(user.full_name || user.email).charAt(0).toUpperCase()}
            </span>
          </div>
        </header>
        {mobileNavOpen && <div className="sticky top-[72px] z-20 border-b border-white/10 bg-[#11131f] p-4 lg:hidden">
          {nav}
          <button type="button" onClick={logout} className="mt-3 flex items-center gap-2 px-3 py-2 text-sm text-[#a9aec5]">
            <StudioIcon name="logout" size={17} /> Sign out
          </button>
        </div>}
        <main className={`mx-auto w-full ${wide ? "max-w-[1760px]" : "max-w-[1480px]"} px-4 py-7 sm:px-7 sm:py-9 lg:px-10`}>
          {children}
        </main>
      </div>
    </div>
  );
}
