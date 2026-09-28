import { PHASE_DEVELOPMENT_SERVER } from "next/constants";
import type { NextConfig } from "next";

export default function config(phase: string): NextConfig {
  const nextConfig: NextConfig = {
    basePath: "/ui",
    trailingSlash: true,
    agentRules: false,
  };

  if (phase === PHASE_DEVELOPMENT_SERVER) {
    nextConfig.skipTrailingSlashRedirect = true;
    nextConfig.rewrites = async () => [
      { source: "/jobs", destination: "http://127.0.0.1:43187/jobs", basePath: false },
      { source: "/jobs/:path*", destination: "http://127.0.0.1:43187/jobs/:path*", basePath: false },
      { source: "/health", destination: "http://127.0.0.1:43187/health", basePath: false },
      { source: "/docs", destination: "http://127.0.0.1:43187/docs", basePath: false },
      { source: "/openapi.json", destination: "http://127.0.0.1:43187/openapi.json", basePath: false },
    ];
  } else {
    nextConfig.output = "export";
  }

  return nextConfig;
}
