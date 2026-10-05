import { expect, type Page } from "@playwright/test";

import { extractCode, waitForEmail } from "./mailpit";

/** Login completo pelas telas do Keycloak: senha e código enviado por e-mail. */
export async function loginWith(page: Page, email: string, password: string) {
  await page.goto("/");
  const since = new Date();
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  const code = extractCode(await waitForEmail(email, since));
  await page.locator("#emailCode").fill(code);
  await page.locator('input[name="login"]').click();
  await expect(page.getByRole("heading", { name: /^Olá, / })).toBeVisible();
}
