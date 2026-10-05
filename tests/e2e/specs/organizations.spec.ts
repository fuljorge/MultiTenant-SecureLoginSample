/**
 * US5 — Gestão de organizações pelo Super Administrador (T062; RF-018, RF-019, RF-025 a
 * RF-028): convite de organização de ponta a ponta, Super Administrador sem acesso aos
 * usuários, suspensão que derruba o acesso e troca de organização pelo seletor.
 */
import { expect, test } from "@playwright/test";

import { extractLink, waitForEmail } from "../support/mailpit";
import { seedPersonInTwoOrganizations, seedSuperAdmin } from "../support/people";
import { loginWith } from "../support/session";

test("Super Administrador convida organização, o responsável ativa e a suspensão derruba o acesso", async ({
  page,
  browser,
}) => {
  test.setTimeout(180_000);
  const superAdmin = seedSuperAdmin();
  await loginWith(page, superAdmin.email, superAdmin.password);

  // Convite da organização
  const orgName = `Cliente ${Date.now() % 1000000}`;
  const email = `e2e-org-${Date.now()}@exemplo.com.br`;
  await page.getByRole("link", { name: "Organizações" }).click();
  await page.getByRole("button", { name: "Convidar organização" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Nome da organização").fill(orgName);
  await dialog.getByLabel("Nome do responsável").fill("Responsável E2E");
  await dialog.getByLabel("E-mail do responsável").fill(email);
  const since = new Date(Date.now() - 1000);
  await dialog.getByRole("button", { name: "Enviar convite" }).click();
  await expect(dialog.getByRole("status")).toContainText(`Convite enviado para ${email}`);
  await dialog.getByRole("button", { name: "Fechar" }).click();
  await page.getByLabel("Buscar por organização ou Administrador").fill(orgName);
  await expect(page.getByRole("row", { name: new RegExp(orgName) })).toContainText("Pendente");

  // O responsável ativa a conta e entra como Administrador
  const admin = await browser.newPage();
  await admin.goto(extractLink(await waitForEmail(email, since)));
  await admin.getByRole("link", { name: /continuar/i }).click();
  const password = `Senha-Org-${Date.now()}`;
  await admin.locator("#password-new").fill(password);
  await admin.locator("#password-confirm").fill(password);
  await admin.getByRole("button", { name: "Enviar" }).click();
  await admin.getByRole("link", { name: "Voltar para o SecureLogin" }).click();
  await loginWith(admin, email, password);
  await expect(admin.getByRole("button", { name: "Menu da conta" })).toContainText(orgName);
  await expect(admin.getByRole("link", { name: "Usuários" })).toBeVisible();

  // O Super Administrador vê a organização ativa e o Administrador, não os usuários
  await page.reload();
  await page.getByLabel("Buscar por organização ou Administrador").fill(orgName);
  // Espera a busca filtrar: clicar durante a troca das linhas acerta outra organização.
  await expect(page.getByRole("row")).toHaveCount(2);
  await page.getByRole("link", { name: orgName }).click();
  // Primeira visita à rota: o servidor de desenvolvimento ainda compila a página.
  await expect(page.getByRole("heading", { name: orgName })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Ativa", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: email })).toBeVisible();
  expect((await page.request.get("/api/v1/users")).status()).toBe(403);

  // Suspensão: o Administrador perde o acesso
  await page.getByRole("button", { name: "Suspender" }).click();
  await expect(page.getByRole("status")).toContainText("Organização suspensa");
  await admin.reload();
  await expect(admin).toHaveURL(/\/idp\/realms\/cap\/|\/entrar\/erro/);
  await admin.close();
});

test("pessoa com duas organizações troca pelo seletor e vê o perfil da ativa", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const person = seedPersonInTwoOrganizations("administrator", "business_analyst");
  await loginWith(page, person.email, person.password);

  const switcher = page.getByRole("combobox", { name: "Organização ativa" });
  await expect(switcher).toBeVisible();
  const before = await page.getByRole("button", { name: "Menu da conta" }).textContent();
  const hadUsers = (await page.getByRole("link", { name: "Usuários" }).count()) > 0;

  const current = ((await switcher.textContent()) ?? "").split("·")[0].trim();
  await switcher.click();
  const options = page.getByRole("option");
  await expect(options).toHaveCount(2);
  await options.filter({ hasNotText: current }).click();

  await expect(page.getByRole("heading", { name: /^Olá, / })).toBeVisible();
  await expect(page.getByRole("button", { name: "Menu da conta" })).not.toHaveText(before ?? "");
  // Um perfil é Administrador e o outro Business Analyst: o menu Usuários muda.
  await expect(page.getByRole("link", { name: "Usuários" })).toHaveCount(hadUsers ? 0 : 1);
});
