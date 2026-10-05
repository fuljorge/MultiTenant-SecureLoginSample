import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LoginErrorPage from "./page";

async function renderWith(motivo?: string) {
  render(await LoginErrorPage({ searchParams: Promise.resolve({ motivo }) }));
}

describe("LoginErrorPage", () => {
  it("explica o motivo recebido", async () => {
    await renderWith("expirado");
    expect(screen.getByRole("alert")).toHaveTextContent("A tentativa de login expirou");
  });

  it("usa mensagem genérica para motivo desconhecido", async () => {
    await renderWith("qualquer-coisa");
    expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível concluir o login");
  });

  it("oferece tentar de novo pelo login do BFF", async () => {
    await renderWith("falha");
    expect(screen.getByRole("link", { name: "Tentar de novo" })).toHaveAttribute(
      "href",
      "/api/v1/auth/login",
    );
  });
});
