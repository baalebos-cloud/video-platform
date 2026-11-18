// Media (scene images, narration audio, thumbnails) is served through
// time-limited signed URLs the backend hands out from /assets/{id} — see
// frontend/hooks/useSignedMedia.ts — rendered with plain <img>/<audio>/
// <video> tags, not next/image. The storage host varies by deployment
// (MinIO locally, R2/Neon Storage/S3 in production), so img-src/media-src
// below allow https: generally rather than one hardcoded host; narrowing
// further would mean re-deploying this config every time STORAGE_ENDPOINT
// changes. next/image itself is unused, so remotePatterns stays empty.
// Next.js dev mode (HMR, React Refresh) needs 'unsafe-eval'; production
// App Router output does not, so keep the strict policy for what's actually
// served to users and only loosen script-src under `next dev`.
const IS_DEV = process.env.NODE_ENV !== "production";
const CSP = [
  "default-src 'self'",
  IS_DEV ? "script-src 'self' 'unsafe-eval'" : "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' https: data:",
  "media-src 'self' https:",
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
