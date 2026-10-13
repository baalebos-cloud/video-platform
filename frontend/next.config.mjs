/** @type {import('next').NextConfig} */
const nextConfig = {
  async headers() {
    return [{ source: "/reset-password", headers: [{ key: "Referrer-Policy", value: "no-referrer" }] }];
  },
  reactStrictMode: true,
  output: "standalone",
  images: {
    remotePatterns: [{ protocol: "https", hostname: "**" }],
  },
};

export default nextConfig;
