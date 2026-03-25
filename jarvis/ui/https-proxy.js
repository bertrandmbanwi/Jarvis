/**
 * JARVIS HTTPS Proxy
 *
 * Terminates TLS using Tailscale-provisioned certs and proxies to the
 * plain HTTP Next.js dev server. Handles both regular HTTP requests and
 * WebSocket upgrades (needed for Next.js HMR/hot reload).
 *
 * Usage:
 *   JARVIS_TLS_CERT=cert.pem JARVIS_TLS_KEY=key.pem \
 *     node https-proxy.js [listen_port] [target_port]
 *
 * Defaults: listens on 3000 (HTTPS), proxies to 3001 (HTTP).
 */
const https = require("https");
const http = require("http");
const fs = require("fs");
const net = require("net");

const CERT_PATH = process.env.JARVIS_TLS_CERT;
const KEY_PATH = process.env.JARVIS_TLS_KEY;
const LISTEN_PORT = parseInt(process.argv[2] || "3000", 10);
const TARGET_PORT = parseInt(process.argv[3] || "3001", 10);

if (!CERT_PATH || !KEY_PATH) {
  console.error("Error: JARVIS_TLS_CERT and JARVIS_TLS_KEY must be set.");
  process.exit(1);
}

const tlsOptions = {
  key: fs.readFileSync(KEY_PATH),
  cert: fs.readFileSync(CERT_PATH),
};

// HTTPS server for regular requests
const server = https.createServer(tlsOptions, (clientReq, clientRes) => {
  const proxyReq = http.request(
    {
      hostname: "127.0.0.1",
      port: TARGET_PORT,
      path: clientReq.url,
      method: clientReq.method,
      headers: clientReq.headers,
    },
    (proxyRes) => {
      clientRes.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(clientRes);
    }
  );

  proxyReq.on("error", (err) => {
    console.error(`Proxy error: ${err.message}`);
    if (!clientRes.headersSent) {
      clientRes.writeHead(502);
    }
    clientRes.end("Bad Gateway");
  });

  clientReq.pipe(proxyReq);
});

// Handle WebSocket upgrades (Next.js HMR needs this)
server.on("upgrade", (req, socket, head) => {
  const proxySocket = net.connect(TARGET_PORT, "127.0.0.1", () => {
    // Reconstruct the raw HTTP upgrade request
    let rawRequest = `${req.method} ${req.url} HTTP/1.1\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      rawRequest += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
    }
    rawRequest += "\r\n";

    proxySocket.write(rawRequest);
    if (head && head.length > 0) {
      proxySocket.write(head);
    }

    // Bidirectional pipe
    socket.pipe(proxySocket);
    proxySocket.pipe(socket);
  });

  proxySocket.on("error", () => socket.destroy());
  socket.on("error", () => proxySocket.destroy());
});

server.listen(LISTEN_PORT, "0.0.0.0", () => {
  console.log(
    `HTTPS proxy: https://0.0.0.0:${LISTEN_PORT} -> http://localhost:${TARGET_PORT}`
  );
});
