import { defineConfig, devices } from "@playwright/test";

// Medição das metas de desempenho (RNF-007; T075). Fora da suíte E2E: roda sob demanda,
// em sequência, contra o ambiente local ou de homologação.
//   corepack pnpm --filter e2e exec playwright test --config playwright.perf.config.ts
export default defineConfig({
  testDir: "./perf",
  workers: 1,
  timeout: 30 * 60_000,
  reporter: "list",
  use: {
    baseURL: process.env.STUDIO_URL ?? "http://localhost:3000",
    locale: "pt-BR",
    ...devices["Desktop Chrome"],
  },
});
