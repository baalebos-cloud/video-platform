"use client";
import {useCallback, useEffect, useState} from "react";
import Link from "next/link";
import {DashboardShell} from "@/components/dashboard/Shell";
import {apiRequest, ApiError} from "@/lib/api/client";
import type {CreatorOverview} from "@/types";
type Account = {id:string;platform:string;external_id:string};
type Entry = {id:string;video_id:string;platform:string;status:string;external_post_id:string|null;created_at:string};

export default function PublishingPage() {
  const [accounts,setAccounts] = useState<Account[]>([]);
  const [history,setHistory] = useState<Entry[]>([]);
  const [videos,setVideos] = useState<CreatorOverview["recent_videos"]>([]);
  const [selectedAccount,setSelectedAccount] = useState("");
  const [videoId,setVideoId] = useState("");
  const [title,setTitle] = useState("");
  const [description,setDescription] = useState("");
  const [consent,setConsent] = useState(false);
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState("");
  const [error,setError] = useState("");

  const load = useCallback(async () => {
    const [connected, posts, overview] = await Promise.all([
      apiRequest<{items:Account[]}>("/publishing/accounts"),
      apiRequest<{items:Entry[]}>("/publishing/history"),
      apiRequest<CreatorOverview>("/creator/overview"),
    ]);
    setAccounts(connected.items);
    setHistory(posts.items);
    setVideos(overview.recent_videos.filter(v=>v.status==="ready"));
  }, []);
  useEffect(()=>{load().catch(()=>setError("Unable to load publishing accounts."));},[load]);
  const account = accounts.find(a=>a.id===selectedAccount);
  const selected = videos.find(v=>v.id===videoId);

  async function connect(platform:string) {
    setBusy(true); setError("");
    try {
      const data = await apiRequest<{authorization_url:string}>(
        `/publishing/connections/${platform}/start`, {method:"POST"});
      window.location.assign(data.authorization_url);
    } catch(e) {setError(e instanceof ApiError?e.message:"Unable to begin authorization");setBusy(false);}
  }
  async function unlink(id:string) {
    if (!window.confirm("Disconnect this publishing account?")) return;
    setBusy(true);setError("");
    try {
      await apiRequest(`/publishing/accounts/${id}`,{method:"DELETE"});
      setSelectedAccount(""); await load();
    } catch(e) {setError(e instanceof ApiError?e.message:"Cannot disconnect");}
    finally {setBusy(false);}
  }
  async function publish() {
    if (!account || !selected || !consent) return;
    setBusy(true);setError("");setMessage("");
    try {
      await apiRequest(`/publishing/${account.platform}`,{method:"POST",
        body:{video_id:selected.id,publishing_account_id:account.id,title,description,hashtags:[]}});
      setMessage(account.platform==="youtube" ?
        "Private YouTube upload queued. Verify it in YouTube Studio before making it public." :
        "TikTok inbox upload queued. Open TikTok to review and finish posting.");
      setConsent(false); await load();
    } catch(e) {setError(e instanceof ApiError?e.message:"Publishing request failed");}
    finally {setBusy(false);}
  }
  return <DashboardShell>
    <h1 className="mb-2 text-3xl font-bold text-white">Publishing</h1>
    <p className="mb-6 text-sm text-[#a4a8be]">
      Connect accounts, review your own videos and explicitly approve every upload.
      YouTube uploads are private. TikTok uploads require completion inside TikTok.
    </p>
    <section className="studio-surface mb-6 p-6">
      <h2 className="mb-4 text-lg font-semibold">Connected channels</h2>
      <div className="mb-4 flex flex-wrap gap-3">
        <button className="studio-button-secondary" type="button" disabled={busy}
          onClick={()=>void connect("youtube")}>Connect YouTube</button>
        <button className="studio-button-secondary" type="button" disabled={busy}
          onClick={()=>void connect("tiktok")}>Connect TikTok</button>
      </div>
      <div className="space-y-2">
        {accounts.map(a=><div key={a.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/10 p-3">
          <span className="text-sm capitalize">{a.platform} · {a.external_id}</span>
          <button className="text-xs text-rose-300 underline" disabled={busy}
            onClick={()=>void unlink(a.id)}>Disconnect</button>
        </div>)}
        {!accounts.length&&<p className="text-sm text-[#9fa5bd]">No connected publishing channels yet.</p>}
      </div>
    </section>
    <section className="studio-surface mb-6 p-6">
      <h2 className="mb-4 text-lg font-semibold">Upload a rendered video</h2>
      <div className="grid max-w-2xl gap-4">
        <label className="text-sm">Connected account
          <select className="studio-input mt-1" value={selectedAccount} onChange={e=>setSelectedAccount(e.target.value)}>
            <option value="">Select channel</option>
            {accounts.map(a=><option key={a.id} value={a.id}>{a.platform} · {a.external_id}</option>)}
          </select>
        </label>
        <label className="text-sm">Ready video
          <select className="studio-input mt-1" value={videoId} onChange={e=>{
            setVideoId(e.target.value);
            setTitle(videos.find(v=>v.id===e.target.value)?.topic ?? "");
          }}>
            <option value="">Select a finished video</option>
            {videos.map(v=><option key={v.id} value={v.id}>{v.topic}</option>)}
          </select>
        </label>
        <label className="text-sm">Title
          <input className="studio-input mt-1" required maxLength={100} value={title}
            onChange={e=>setTitle(e.target.value)}/>
        </label>
        <label className="text-sm">Description
          <textarea className="studio-input mt-1" maxLength={5000} rows={3} value={description}
            onChange={e=>setDescription(e.target.value)}/>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>
          I own or have permission to publish this video. I authorize this specific upload.
        </label>
        <button className="studio-button w-fit" type="button"
          disabled={busy || !account || !selected || !title.trim() || !consent}
          onClick={()=>void publish()}>{busy?"Working…":"Authorize upload"}</button>
        <p className="text-xs text-[#a4a8be]">YouTube defaults to private.
          TikTok receives an upload in the creator inbox, not a public post.
          External platform approval and quotas apply.</p>
      </div>
    </section>
    <section className="studio-surface p-6">
      <h2 className="mb-4 text-lg font-semibold">Recent publishing activity</h2>
      {history.map(post=><div className="border-b border-white/10 py-3 text-sm" key={post.id}>
        <span className="capitalize">{post.platform}</span> · {post.status==="ready"&&post.platform==="tiktok"?
          "Awaiting final action in TikTok":post.status}
        {" · "}<Link className="text-violet-300 underline" href={`/studio/video/${post.video_id}`}>View video</Link>
      </div>)}
      {!history.length&&<p className="text-sm text-[#9fa5bd]">No uploads recorded yet.</p>}
    </section>
    {message&&<p role="status" className="mt-4 text-sm text-emerald-300">{message}</p>}
    {error&&<p role="alert" className="mt-4 text-sm text-rose-300">{error}</p>}
  </DashboardShell>;
}
