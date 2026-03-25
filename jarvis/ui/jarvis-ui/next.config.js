/** @type {import('next').NextConfig} */
const nextConfig = {
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
        destination: "http://127.0.0.1:8741/:path*",
      },
      {
        // WebSocket endpoint: the Next.js dev server proxies upgrade
        // requests through rewrites, so this handles ws:// connections too.
        source: "/jarvis-ws",
        destination: "http://127.0.0.1:8741/ws",
      },
    ];
  },
};

module.exports = nextConfig;
