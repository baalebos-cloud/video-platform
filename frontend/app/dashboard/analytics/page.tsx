"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { DashboardShell } from "@/components/dashboard/Shell";
import { apiRequest } from "@/lib/api/client";

interface ChannelAnalytics {
  platform: string;
  status: string;
  views: number;
  likes: number;
  shares: number;
  comments: number;
}

export default function AnalyticsPage() {
  const [videoId, setVideoId] = useState("");
  const [channels, setChannels] = useState<ChannelAnalytics[] | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleLookup() {
    if (!videoId) return;
    setLoading(true);
    try {
      const data = await apiRequest<{ channels: ChannelAnalytics[] }>(`/analytics?video_id=${videoId}`);
      setChannels(data.channels);
    } finally {
      setLoading(false);
    }
  }

  return (
    <DashboardShell>
      <h1 className="mb-6 text-2xl font-semibold">Analytics</h1>
      <Card className="max-w-2xl">
        <div className="mb-4 flex items-end gap-3">
          <div className="flex-1">
            <Input label="Video ID" value={videoId} onChange={(e) => setVideoId(e.target.value)} />
          </div>
          <Button onClick={handleLookup} loading={loading}>
            Look up
          </Button>
        </div>

        {channels && (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="py-2">Platform</th>
                <th className="py-2">Status</th>
                <th className="py-2">Views</th>
                <th className="py-2">Likes</th>
                <th className="py-2">Shares</th>
                <th className="py-2">Comments</th>
              </tr>
            </thead>
            <tbody>
              {channels.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-slate-400">
                    No publishing activity for this video yet.
                  </td>
                </tr>
              ) : (
                channels.map((c) => (
                  <tr key={c.platform} className="border-b border-slate-100">
                    <td className="py-2 capitalize">{c.platform}</td>
                    <td className="py-2 capitalize">{c.status}</td>
                    <td className="py-2">{c.views}</td>
                    <td className="py-2">{c.likes}</td>
                    <td className="py-2">{c.shares}</td>
                    <td className="py-2">{c.comments}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </Card>
    </DashboardShell>
  );
}
