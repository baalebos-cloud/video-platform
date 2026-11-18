// Media (scene images, narration audio, thumbnails) is served through
// time-limited signed URLs the backend hands out from /assets/{id} — see
// frontend/hooks/useSignedMedia.ts — rendered with plain <img>/<audio>/
// <video> tags, not next/image. The storage host varies by deployment
// (MinIO locally, R2/Neon Storage/S3 in production), so img-src/media-src
// below allow https: generally rather than one hardcoded host; narrowing
// further would mean re-deploying this config every time STORAGE_ENDPOINT
// changes. next/image itself is unused, so remotePatterns stays empty.
// The local Docker Compose stack's default STORAGE_PUBLIC_BASE_URL is
// http://localhost:9000 (plain http, not the frontend's own origin), so
// dev additionally allows http:/localhost: or scene media would 404 under
// this policy in the documented local setup; production never serves
// media over plain http.
// blob: is required in media-src: PersonalNarrationPanel/VoiceProfileStudio
// create local audio previews with URL.createObjectURL before anything is
// uploaded, and 'self' alone does not cover the blob: scheme.
// script-src needs 'unsafe-inline': Next.js 14 App Router's own hydration
// bootstrap (the inline `self.__next_f.push(...)` flight-data scripts)
// is itself an inline script with no nonce/hash wiring in this app, so a
// strict 'self'-only policy breaks client-side hydration everywhere, not
// just in development. A nonce-based CSP (via Next.js middleware) would
// be the stronger option but is a separate, bigger change than this pass.
const IS_DEV = process.env.NODE_ENV !== "production";
const CSP = [
  "default-src 'self'",
  IS_DEV ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'" : "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  IS_DEV ? "img-src 'self' https: http: data:" : "img-src 'self' https: data:",
  IS_DEV ? "media-src 'self' https: http: blob:" : "media-src 'self' https: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // microphone stays available (Personal Narration / Voice Profile Studio
  // record audio via getUserMedia); everything else this app doesn't use.
  { key: "Permissions-Policy", value: "camera=(), geolocation=(), payment=(), microphone=(self)" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  async headers() {
    return [
      { source: "/:path*", headers: SECURITY_HEADERS },
      // Stricter than the global policy: no caching of reset-password links.
      { source: "/reset-password", headers: [{ key: "Referrer-Policy", value: "no-referrer" }] },
    ];
  },
  reactStrictMode: true,
  output: "standalone",
  images: {
    remotePatterns: [],
  },
};

export default nextConfig;
