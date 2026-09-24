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
  estimated_remaining_seconds?: number | null;
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
