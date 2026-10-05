/** US2 — Primeiro acesso pelo link de boas-vindas ou convite (T043). */
import { expect, test } from "@playwright/test";

import { extractCode, extractLink, waitForEmail } from "../support/mailpit";
import { seedInvitedPerson } from "../support/people";

test("link de ativação define a senha e o primeiro login abre o Studio", async ({ page }) => {
  test.setTimeout(90_000);
  const person = seedInvitedPerson();
  const invitation = await waitForEmail(person.email, new Date(Date.now() - 60_000));
  expect(invitation.Text).toContain("Você recebeu acesso ao SecureLogin");
  const link = extractLink(invitation);

  await page.goto(link);
  // Página intermediária do Keycloak: evita que leitores de e-mail que abrem links sozinhos
  // consumam o link de uso único.
  await page.getByRole("link", { name: /continuar/i }).click();
  // Indicador de força (RF-032): orienta enquanto a pessoa digita.
  const strength = page.locator("#password-new-strength");
  await page.locator("#password-new").fill("curta1");
  await expect(strength).toHaveText("Força da senha: Fraca (mínimo de 12 caracteres)");
  await page.locator("#password-new").fill("Céu-Lilás-7q!Rv2M-Pântano");
  await expect(strength).toHaveText("Força da senha: Forte");
  const password = `Senha-Inicial-${Date.now()}`;
  await page.locator("#password-new").fill(password);
  await page.locator("#password-confirm").fill(password);
  await page.getByRole("button", { name: "Enviar" }).click();

  // O Keycloak confirma e oferece voltar ao Studio, que inicia o login com senha e código.
  await expect(page.getByText("Sua senha foi definida.")).toBeVisible();
  await page.getByRole("link", { name: "Voltar para o SecureLogin" }).click();
  const since = new Date();
  await page.getByLabel("E-mail").fill(person.email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  const code = extractCode(await waitForEmail(person.email, since));
  await page.locator("#emailCode").fill(code);
  await page.locator('input[name="login"]').click();

  await expect(page.getByRole("heading", { name: `Olá, ${person.name}` })).toBeVisible();

  // O link é de uso único: abrir de novo não permite definir outra senha.
  await page.goto(link);
  await expect(page.getByRole("link", { name: /continuar/i })).toHaveCount(0);
  await expect(page.locator("#password-new")).toHaveCount(0);
});
