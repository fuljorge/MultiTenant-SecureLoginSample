import path from "node:path";

import type { NextConfig } from "next";

// O Studio e a API ficam no mesmo domínio (cookies __Host-; plano §4.9). Em produção o
// ingress encaminha /api ao Control Plane; no desenvolvimento, este rewrite faz o papel.
const controlPlaneUrl = process.env.CAP_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Imagem enxuta (apps/studio/Dockerfile): só o necessário para `node server.js`.
  output: "standalone",
  // Monorepo: o rastreamento de dependências parte da raiz (packages/api-client).
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  async rewrites() {
    return {
      beforeFiles: [{ source: "/api/:path*", destination: `${controlPlaneUrl}/api/:path*` }],
      afterFiles: [],
      fallback: [],
    };
  },
};

export default nextConfig;
