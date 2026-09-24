/**
 * Access-token storage. Uses localStorage for simplicity; move to an
 * httpOnly cookie set by a Next.js route handler before shipping this
 * to production (see docs/security.md).
 */
const TOKEN_KEY = "ai_video_platform_access_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}
