import Link from "next/link";
import { Button } from "@/components/ui/Button";

export default function LandingPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col items-center justify-center gap-8 px-6 text-center">
      <span className="rounded-full bg-brand-100 px-3 py-1 text-xs font-semibold text-brand-700">
        AI Video Creator &amp; Monetization Platform
      </span>
      <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
        Turn one idea into a<br className="hidden sm:block" /> polished, multilingual video
      </h1>
      <p className="max-w-2xl text-lg text-slate-600">
        AI-assisted scripting, voice, visual generation, editing and publishing —
        production-grade pipeline, server-side AI orchestration, and a clear
        path from a single topic to a ready-to-publish short-form video.
      </p>
      <div className="flex gap-3">
        <Link href="/signup">
          <Button className="px-6 py-3 text-base">Start creating</Button>
        </Link>
        <Link href="/login">
          <Button variant="secondary" className="px-6 py-3 text-base">
            Sign in
          </Button>
        </Link>
      </div>
      <dl className="mt-12 grid grid-cols-1 gap-6 text-left sm:grid-cols-3">
        <div>
          <dt className="font-semibold text-slate-900">Idea to video</dt>
          <dd className="text-sm text-slate-600">Topic, language and platform in — script, voice, scenes and captions out.</dd>
        </div>
        <div>
          <dt className="font-semibold text-slate-900">Provider-agnostic</dt>
          <dd className="text-sm text-slate-600">Swap AI providers without touching product code.</dd>
        </div>
        <div>
          <dt className="font-semibold text-slate-900">Built for teams</dt>
          <dd className="text-sm text-slate-600">Projects, jobs, credits and publishing from day one.</dd>
        </div>
      </dl>
    </main>
  );
}
