/**
 * US4 — Matriz de perfis (T057, T083; RF-014, RF-028): cada perfil vê só as suas áreas, a
 * tela explica a falta de permissão e a API recusa a chamada direta com 403. O Super
 * Administrador vê só as áreas da instalação.
 */
import { expect, test } from "@playwright/test";

import { seedPerson, seedSuperAdmin } from "../support/people";
import { loginWith } from "../support/session";

test("Business Analyst não vê a administração e a API recusa a chamada direta", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const analyst = seedPerson("business_analyst");
  await loginWith(page, analyst.email, analyst.password);

  const nav = page.getByRole("navigation", { name: "Principal" });
  await expect(nav.getByRole("link")).toHaveCount(0);

  await page.goto("/admin/usuarios");
  await expect(page.getByRole("heading", { name: "Sem permissão" })).toBeVisible();
  await expect(page.getByLabel("Buscar por nome ou e-mail")).toHaveCount(0);

  for (const url of ["/api/v1/users", "/api/v1/security-settings"]) {
    const response = await page.request.get(url);
    expect(response.status(), url).toBe(403);
  }
});

test("Administrador vê Usuários, mas não a segurança da instalação", async ({ page }) => {
  test.setTimeout(120_000);
  const admin = seedPerson("administrator");
  await loginWith(page, admin.email, admin.password);

  const nav = page.getByRole("navigation", { name: "Principal" });
  await expect(nav.getByRole("link", { name: "Usuários" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Segurança" })).toHaveCount(0);

  await page.goto("/admin/seguranca");
  await expect(page.getByRole("heading", { name: "Sem permissão" })).toBeVisible();
  expect((await page.request.get("/api/v1/security-settings")).status()).toBe(403);
});

test("Super Administrador vê só as áreas da instalação e nenhum usuário das organizações", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const superAdmin = seedSuperAdmin();
  await loginWith(page, superAdmin.email, superAdmin.password);

  const nav = page.getByRole("navigation", { name: "Principal" });
  await expect(nav.getByRole("link")).toHaveText([
    "Organizações",
    "Super Administradores",
    "Segurança",
    "Auditoria",
  ]);
  await expect(page.getByRole("button", { name: "Menu da conta" })).toContainText(
    "Super Administrador",
  );

  await page.goto("/admin/usuarios");
  await expect(page.getByRole("heading", { name: "Sem permissão" })).toBeVisible();
  expect((await page.request.get("/api/v1/users")).status()).toBe(403);
  expect((await page.request.get("/api/v1/security-settings")).status()).toBe(200);
});
