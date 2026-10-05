import { defineConfig, devices } from "@playwright/test";

// URL do Studio. Em CI, o job E2E sobe o ambiente completo e define STUDIO_URL.
const baseURL = process.env.STUDIO_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./specs",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    locale: "pt-BR",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    // Layout responsivo (§29.2); Chromium para não depender do WebKit no CI.
    { name: "celular", use: { ...devices["Pixel 7"] } },
  ],
  // Sem STUDIO_URL, sobe o Studio local para os testes.
  webServer: process.env.STUDIO_URL
    ? undefined
    : {
        command: "corepack pnpm --filter studio dev",
        url: baseURL,
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
