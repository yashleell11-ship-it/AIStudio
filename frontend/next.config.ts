import type { NextConfig } from "next";

// In-network address of the backend the /api/* rewrite proxies to. In Docker
// this is the private `backend` service; in local dev it's the dev backend.
const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (.next/standalone/server.js) for the
  // production Docker image.
  output: "standalone",

  // Same-origin API: the browser calls /api/*, and Next proxies it to the
  // backend server-side. This keeps the backend off the public edge (only the
  // frontend is exposed) and sidesteps CORS entirely. The backend serves its
  // routes at the root, so /api/sources -> {backend}/sources and, critically,
  // /api/health -> {backend}/health (the health contract deploy.sh + Caddy probe).
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_INTERNAL_URL}/:path*`,
      },
    ];
  },

  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "127.0.0.1",
        port: "8000",
        pathname: "/**",
      },
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
        pathname: "/**",
      },
    ],
  },
};

export default nextConfig;
