import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  async rewrites() {
    const api = process.env.WDS_API_URL ?? "http://127.0.0.1:18741";
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};
export default nextConfig;
