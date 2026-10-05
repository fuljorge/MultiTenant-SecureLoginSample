/**
 * US1 — Login com segundo fator por e-mail (T034).
 *
 * Fora do E2E (cobertos em outros níveis): código expirado e reenvio (validade de 10 min e
 * intervalo de 5 min; testes da extensão e do realm) e inatividade de 30 min (T028, com
 * relógio simulado).
 */
import { expect, test, type Page } from "@playwright/test";

import { extractCode, extractLink, waitForEmail } from "../support/mailpit";
import { seedPerson, type Person } from "../support/people";

const GENERIC_ERROR = "E-mail ou senha inválidos.";

async function submitPassword(page: Page, email: string, password: string) {
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}

async function login(page: Page, person: Person) {
  await page.goto("/");
  const since = new Date();
  await submitPassword(page, person.email, person.password);
  const code = extractCode(await waitForEmail(person.email, since));
  await page.locator("#emailCode").fill(code);
  await page.locator('input[name="login"]').click();
  await expect(page.getByRole("heading", { name: `Olá, ${person.name}` })).toBeVisible();
}

test("login com senha e código do e-mail abre o Studio", async ({ page }) => {
  const person = seedPerson();

  await login(page, person);

  await expect(page).toHaveURL(/localhost:3000\/$/);
});

test("senha incorreta mostra mensagem genérica e não pede código", async ({ page }) => {
  const person = seedPerson();
  await page.goto("/");

  await submitPassword(page, person.email, "senha-errada-123");

  await expect(page.getByText(GENERIC_ERROR)).toBeVisible();
  await expect(page.locator("#emailCode")).toHaveCount(0);
});

test("e-mail inexistente recebe a mesma mensagem", async ({ page }) => {
  await page.goto("/");

  await submitPassword(page, `ninguem-${Date.now()}@exemplo.com.br`, "senha-errada-123");

  await expect(page.getByText(GENERIC_ERROR)).toBeVisible();
});

test("código incorreto mantém a tela de código", async ({ page }) => {
  const person = seedPerson();
  await page.goto("/");
  await submitPassword(page, person.email, person.password);

  await page.locator("#emailCode").fill("000000");
  await page.locator('input[name="login"]').click();

  await expect(page.locator("#emailCode")).toBeVisible();
  await expect(page).toHaveURL(/\/idp\/realms\/cap\//);
});

test("cinco senhas erradas bloqueiam a conta temporariamente", async ({ page }) => {
  const person = seedPerson();
  await page.goto("/");
  for (let attempt = 0; attempt < 5; attempt++) {
    await submitPassword(page, person.email, `errada-${attempt}`);
    // Abaixo de 1 s entre falhas o Keycloak aplica outra proteção (login rápido).
    await page.waitForTimeout(1200);
  }

  await submitPassword(page, person.email, person.password);

  await expect(page.locator("#emailCode")).toHaveCount(0);
  await expect(page.getByText(GENERIC_ERROR)).toBeVisible();
});

test("sair encerra a sessão", async ({ page }) => {
  const person = seedPerson();
  await login(page, person);

  await page.getByRole("button", { name: "Menu da conta" }).click();
  await page.getByRole("menuitem", { name: "Sair" }).click();

  await expect(page).toHaveURL(/\/idp\/realms\/cap\//);
  await expect(page.getByLabel("E-mail")).toBeVisible();
});

test("recuperação de senha avisa por e-mail e encerra as sessões", async ({ page, browser }) => {
  // Fluxo longo: login, e-mail de recuperação, nova senha e importação do evento pelo worker.
  test.setTimeout(120_000);
  const person = seedPerson();
  await login(page, person);

  const other = await browser.newPage();
  await other.goto("/");
  await other.getByRole("link", { name: "Esqueceu sua senha?" }).click();
  const since = new Date();
  await other.getByLabel(/e-?mail/i).fill(person.email);
  await other.getByRole("button", { name: /enviar/i }).click();
  const resetLink = extractLink(await waitForEmail(person.email, since));
  await other.goto(resetLink);
  const newPassword = `Nova-Senha-${Date.now()}`;
  const noticeSince = new Date();
  await other.locator("#password-new").fill(newPassword);
  await other.locator("#password-confirm").fill(newPassword);
  await other.getByRole("button", { name: "Enviar" }).click();

  const notice = await waitForEmail(person.email, noticeSince);
  expect(notice.Text).toContain("foi alterada");
  // O worker encerra as sessões do Studio ao importar o evento de troca de senha.
  await expect(async () => {
    await page.reload();
    await expect(page).toHaveURL(/\/idp\/realms\/cap\//);
  }).toPass({ timeout: 20_000 });
  await other.close();
});
