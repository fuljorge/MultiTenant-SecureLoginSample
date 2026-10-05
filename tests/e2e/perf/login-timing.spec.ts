/**
 * RNF-007 (T075): p95 de cada etapa do login, da chegada do e-mail com o código e da troca
 * de organização, em N logins seguidos (padrão 50; PERF_LOGINS). O resultado vai para
 * test-results/perf-login.json e para a saída, para registro no PR.
 */
import { mkdirSync, writeFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { extractCode, waitForEmail } from "../support/mailpit";
import { seedPersonInTwoOrganizations } from "../support/people";

const LOGINS = Number(process.env.PERF_LOGINS ?? 50);

// Metas (ms). A chegada do e-mail é medida pelo horário de recebimento no Mailpit.
const TARGETS = {
  abrir_login: 2_000,
  senha: 2_000,
  codigo: 2_000,
  email_codigo: 60_000,
  troca_organizacao: 2_000,
} as const;
type Step = keyof typeof TARGETS;

function percentile(values: number[], p: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1)];
}

async function timed(action: () => Promise<unknown>): Promise<number> {
  const start = performance.now();
  await action();
  return performance.now() - start;
}

test("p95 do login, do e-mail com o código e da troca de organização", async ({ page }) => {
  const person = seedPersonInTwoOrganizations("administrator", "business_analyst");
  const samples: Record<Step, number[]> = {
    abrir_login: [],
    senha: [],
    codigo: [],
    email_codigo: [],
    troca_organizacao: [],
  };
  const home = (p: Page) => p.getByRole("heading", { name: /^Olá, / });

  // A primeira volta não conta: aquece páginas, conexões e caches.
  for (let i = -1; i < LOGINS; i++) {
    const record = (step: Step, ms: number) => {
      if (i >= 0) samples[step].push(ms);
    };
    await page.context().clearCookies();
    record(
      "abrir_login",
      await timed(async () => {
        await page.goto("/");
        await expect(page.getByLabel("E-mail")).toBeVisible();
      }),
    );
    await page.getByLabel("E-mail").fill(person.email);
    await page.getByLabel("Senha", { exact: true }).fill(person.password);
    const sentAt = Date.now();
    record(
      "senha",
      await timed(async () => {
        await page.getByRole("button", { name: "Entrar" }).click();
        await expect(page.locator("#emailCode")).toBeVisible();
      }),
    );
    const email = await waitForEmail(person.email, new Date(sentAt - 1_000));
    record("email_codigo", Math.max(0, new Date(email.Created).getTime() - sentAt));
    await page.locator("#emailCode").fill(extractCode(email));
    record(
      "codigo",
      await timed(async () => {
        await page.locator('input[name="login"]').click();
        await expect(home(page)).toBeVisible();
      }),
    );
    const switcher = page.getByRole("combobox", { name: "Organização ativa" });
    const current = ((await switcher.textContent()) ?? "").split("·")[0].trim();
    await switcher.click();
    record(
      "troca_organizacao",
      await timed(async () => {
        await page.getByRole("option").filter({ hasNotText: current }).click();
        await expect(switcher).not.toContainText(current);
        await expect(home(page)).toBeVisible();
      }),
    );
  }

  const report = Object.fromEntries(
    (Object.keys(TARGETS) as Step[]).map((step) => [
      step,
      {
        p50_ms: Math.round(percentile(samples[step], 50)),
        p95_ms: Math.round(percentile(samples[step], 95)),
        max_ms: Math.round(Math.max(...samples[step])),
        meta_ms: TARGETS[step],
      },
    ]),
  );
  mkdirSync("test-results", { recursive: true });
  writeFileSync(
    "test-results/perf-login.json",
    JSON.stringify({ logins: LOGINS, baseURL: test.info().project.use.baseURL, report }, null, 2),
  );
  console.table(report);

  for (const step of Object.keys(TARGETS) as Step[]) {
    expect
      .soft(report[step].p95_ms, `${step}: p95 acima da meta`)
      .toBeLessThanOrEqual(TARGETS[step]);
  }
});
