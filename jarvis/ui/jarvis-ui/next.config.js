/** @type {import('next').NextConfig} */
const path = require("path");
const apiPort = process.env.JARVIS_API_PORT || process.env.API_PORT || "8741";

const nextConfig = {
  outputFileTracingRoot: path.join(__dirname),
  // Transpile Three.js for SSR compatibility
  transpilePackages: ["three"],
  // Disable SSR for the entire app since it's a local client-side UI
  // that connects to a local JARVIS server via WebSocket
  reactStrictMode: true,

  // Allow cross-origin requests from Cloudflare Tunnel domains.
  // Suppresses the "Cross origin request detected" dev warning.
  allowedDevOrigins: ["*.trycloudflare.com"],

  // Proxy API and WebSocket requests to the JARVIS Python backend.
  // This lets the entire app work through a single port/URL, which is
  // essential for Cloudflare Tunnel (only one origin per quick tunnel).
  // When accessed locally, the UI can still talk to port 8741 directly,
  // but when accessed via tunnel, it routes through these rewrites.
  async rewrites() {
    return [
      {
        source: "/jarvis-api/:path*",
        destination: `http://127.0.0.1:${apiPort}/:path*`,
      },
      {
        // Compatibility for older browser bundles that queried auth directly.
        source: "/auth/:path*",
        destination: `http://127.0.0.1:${apiPort}/auth/:path*`,
      },
      {
        // WebSocket endpoint: the Next.js dev server proxies upgrade
        // requests through rewrites, so this handles ws:// connections too.
        source: "/jarvis-ws",
        destination: `http://127.0.0.1:${apiPort}/ws`,
      },
    ];
  },
};

module.exports = nextConfig;
