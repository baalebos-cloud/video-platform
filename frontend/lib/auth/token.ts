/** Legacy localStorage tokens are no longer used; erase on module load for migration.
 * Session credentials are now server-only HttpOnly cookies.
 */
if (typeof window !== "undefined") {
  window.localStorage.removeItem("ai_video_platform_access_token");
}
