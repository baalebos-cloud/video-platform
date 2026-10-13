export interface User {
  id: string;
  email: string;
  full_name: string | null;
  status: string;
}

export interface Project {
  id: string;
  name: string;
  niche: string | null;
  brand_context: Record<string, unknown>;
  description: string | null;
}

export type VideoStatus =
  | "draft"
  | "queued"
  | "planning"
  | "scripting"
  | "storyboarding"
  | "generating_assets"
  | "rendering"
  | "ready"
  | "failed"
  | "cancelled";

export interface VideoStatusResponse {
  video_id: string;
  status: VideoStatus;
  progress: number;
  current_stage: string | null;
  error_message?: string | null;
  estimated_remaining_seconds?: number | null;
  output_asset_id?: string | null;
  thumbnail_asset_id?: string | null;
  project_id?: string | null;
  topic?: string | null;
  platform?: string | null;
  language?: string | null;
  duration_seconds?: number | null;
  needs_rerender?: boolean;
}

export interface ProjectVideo {
  id: string;
  topic: string;
  status: VideoStatus;
  progress: number;
  platform: string;
  language: string;
  duration_seconds: number;
  output_asset_id: string | null;
  thumbnail_asset_id: string | null;
  created_at: string;
}

export interface ProjectVideoPage {
  items: ProjectVideo[];
  total: number;
  limit: number;
  offset: number;
}

export interface StoryboardScene {
  id: string;
  sequence: number;
  narration: string;
  visual_prompt: string;
  duration_seconds: number;
  visual_asset_id: string | null;
  on_screen_text: string | null;
}

export interface GenerateVideoResponse {
  video_id: string;
  status: string;
  job_id: string;
  message: string;
}

export interface Voice {
  voice_id: string;
  locale: string;
  gender: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}


export interface CreatorVideo {
  id: string;
  project_id: string;
  topic: string;
  status: VideoStatus;
  progress: number;
  platform: string;
  duration_seconds: number;
  thumbnail_asset_id: string | null;
  created_at: string;
}

export interface CreatorOverview {
  stats: {
    projects: number;
    total_videos: number;
    ready_videos: number;
    published_posts: number;
    views: number;
    likes: number;
    shares: number;
    comments: number;
  };
  projects: Array<{ id: string; name: string; niche: string | null }>;
  recent_videos: CreatorVideo[];
  platforms: Array<{
    platform: string; posts: number; views: number; likes: number;
    shares: number; comments: number;
  }>;
  trend: Array<{ date: string; views: number; engagement: number }>;
  trend_description: string;
}

export type CaptionStyle = "classic" | "bold" | "social" | "minimal";

export interface CaptionScene {
  scene_id: string;
  sequence: number;
  text: string;
  original_text: string;
  start_seconds: number;
  end_seconds: number;
}

export interface CaptionTrack {
  video_id: string;
  style: CaptionStyle;
  needs_rerender: boolean;
  scenes: CaptionScene[];
  timing_note: string;
}
