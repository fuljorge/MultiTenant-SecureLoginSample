import { expect, test } from "@playwright/test";

test("página pública de erro de login usa o tema da marca", async ({ page }) => {
  await page.goto("/entrar/erro?motivo=expirado");

  await expect(page.getByRole("heading", { name: "Não foi possível entrar" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "pt-BR");
});
