/**
 * US6 — Auditoria de acessos (T070; RF-022, RF-023): o Administrador encontra o próprio
 * login filtrando por evento e exporta o resultado em CSV.
 */
import { expect, test } from "@playwright/test";

import { seedPerson } from "../support/people";
import { loginWith } from "../support/session";

test("Administrador encontra o login e exporta a auditoria", async ({ page }) => {
  test.setTimeout(120_000);
  const admin = seedPerson("administrator");
  await loginWith(page, admin.email, admin.password);

  await page.getByRole("link", { name: "Auditoria" }).click();
  await expect(page.getByRole("heading", { name: "Auditoria" })).toBeVisible({ timeout: 20_000 });
  // O login chega pelo worker que importa os eventos do Keycloak (a cada 5 s).
  await expect(async () => {
    await page.reload();
    await page.getByRole("combobox", { name: "Filtrar por evento" }).click();
    await page.getByRole("option", { name: "Login", exact: true }).click();
    await page.getByLabel("Pessoa: nome ou e-mail").fill(admin.email);
    await expect(page.getByRole("row", { name: new RegExp(admin.name) }).first()).toBeVisible({
      timeout: 3_000,
    });
  }).toPass({ timeout: 45_000 });

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar CSV" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^auditoria-.*\.csv$/);
});
