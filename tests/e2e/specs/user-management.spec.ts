/**
 * US3 — Gestão de usuários pelo Administrador (T049): convida, a pessoa ativa, o
 * Administrador muda o perfil e desativa, e a pessoa perde o acesso.
 */
import { expect, test } from "@playwright/test";

import { extractCode, extractLink, waitForEmail } from "../support/mailpit";
import { ageLogin, seedPerson, type Person } from "../support/people";
import { loginWith } from "../support/session";

test("administrador convida, muda o perfil e desativa; a pessoa perde o acesso", async ({
  page,
  browser,
}) => {
  test.setTimeout(180_000);
  const admin: Person = seedPerson("administrator");
  await loginWith(page, admin.email, admin.password);

  // Convite
  const name = `Convidada ${Date.now() % 100000}`;
  const email = `e2e-${Date.now()}@exemplo.com.br`;
  await page.getByRole("link", { name: "Usuários" }).click();
  await page.getByRole("button", { name: "Convidar pessoa" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Nome", { exact: true }).fill(name);
  await dialog.getByLabel("E-mail", { exact: true }).fill(email);
  await dialog.getByRole("combobox", { name: "Perfil" }).click();
  await page.getByRole("option", { name: "Supervisor", exact: true }).click();
  const inviteSince = new Date(Date.now() - 1000);
  await page.getByRole("button", { name: "Enviar convite" }).click();
  await expect(page.getByRole("status")).toContainText(`Convite enviado para ${email}`);
  await page.getByRole("button", { name: "Fechar" }).click();

  // A pessoa ativa a conta e entra
  const invitee = await browser.newPage();
  const activation = extractLink(await waitForEmail(email, inviteSince));
  await invitee.goto(activation);
  await invitee.getByRole("link", { name: /continuar/i }).click();
  const password = `Senha-Convidada-${Date.now()}`;
  await invitee.locator("#password-new").fill(password);
  await invitee.locator("#password-confirm").fill(password);
  await invitee.getByRole("button", { name: "Enviar" }).click();
  await invitee.getByRole("link", { name: "Voltar para o SecureLogin" }).click();
  await loginWith(invitee, email, password);
  await expect(invitee.getByRole("link", { name: "Usuários" })).toHaveCount(0);

  // O Administrador muda o perfil
  await page.reload();
  await page.getByLabel("Buscar por nome ou e-mail").fill(email);
  // Espera a busca filtrar: clicar durante a troca das linhas acerta outra pessoa.
  await expect(page.getByRole("table").first().getByRole("row")).toHaveCount(2);
  await page.getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await page
    .getByRole("combobox", { name: /^Perfil em / })
    .first()
    .click();
  await page.getByRole("option", { name: "Agent Designer", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Perfil alterado");

  // E desativa: ação sensível com o login de mais de 15 min pede senha e código (RF-031)
  ageLogin(admin.email);
  await page.getByRole("button", { name: "Desativar" }).click();
  await expect(page).toHaveURL(/\/idp\/realms\/cap\//);
  // A tela já traz o e-mail fixo e pede a senha (e depois o código).
  await expect(
    page.getByText("Por segurança, confirme sua identidade para continuar."),
  ).toBeVisible();
  const reauthSince = new Date();
  await page.getByLabel("Senha", { exact: true }).fill(admin.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.locator("#emailCode").fill(extractCode(await waitForEmail(admin.email, reauthSince)));
  await page.locator('input[name="login"]').click();
  await expect(page.getByRole("status").first()).toContainText("Identidade confirmada");
  await expect(page).not.toHaveURL(/reautenticado/);
  await page.getByRole("button", { name: "Desativar" }).click();
  await expect(page.getByRole("status").last()).toContainText("Pessoa desativada.");

  // A sessão da pessoa acabou e o login é recusado com a mensagem genérica
  await invitee.reload();
  await expect(invitee).toHaveURL(/\/idp\/realms\/cap\//);
  await invitee.getByLabel("E-mail").fill(email);
  await invitee.getByLabel("Senha", { exact: true }).fill(password);
  await invitee.getByRole("button", { name: "Entrar" }).click();
  await expect(invitee.getByText("E-mail ou senha inválidos.")).toBeVisible();
  await invitee.close();
});
