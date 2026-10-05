import { defineConfig } from "orval";

// Cliente gerado a partir do OpenAPI do Control Plane (stack §3.1; plano §6).
// Nunca editar src/generated à mão: rode `pnpm --filter @cap/api-client generate`.
export default defineConfig({
  controlPlane: {
    input: "./openapi.json",
    output: {
      target: "./src/generated/api.ts",
      client: "react-query",
      httpClient: "fetch",
      mode: "single",
      override: {
        mutator: { path: "./src/fetcher.ts", name: "capFetch" },
        // Só o corpo de sucesso: o fetcher lança ApiError em qualquer resposta de erro.
        fetch: { includeHttpResponseReturnType: false },
      },
    },
  },
});
