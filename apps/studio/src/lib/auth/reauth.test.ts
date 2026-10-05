import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@cap/api-client";

import { consumeReauthFlag, isReauthRequired, reauthUrl, redirectToReauth } from "./reauth";

describe("reautenticação recente (RF-031)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("reconhece só o 401 com code reauth_required", () => {
    expect(isReauthRequired(new ApiError(401, { code: "reauth_required" }))).toBe(true);
    expect(isReauthRequired(new ApiError(401, { detail: "Sessão expirada" }))).toBe(false);
    expect(isReauthRequired(new ApiError(403, { code: "reauth_required" }))).toBe(false);
    expect(isReauthRequired(new Error("rede"))).toBe(false);
  });

  it("volta para a tela atual, preservando a consulta, com a marca", () => {
    const url = reauthUrl({ pathname: "/admin/usuarios/123", search: "?aba=sessoes" });

    expect(url.startsWith("/api/v1/auth/login?reauth=1&return_to=")).toBe(true);
    const returnTo = decodeURIComponent(url.split("return_to=")[1]);
    expect(returnTo).toBe("/admin/usuarios/123?aba=sessoes&reautenticado=1");
  });

  it("leva o navegador à nova autenticação", () => {
    const assign = vi.fn();
    vi.spyOn(window, "location", "get").mockReturnValue({
      ...window.location,
      pathname: "/admin/seguranca",
      search: "",
      assign,
    });

    redirectToReauth();

    expect(assign).toHaveBeenCalledWith(
      `/api/v1/auth/login?reauth=1&return_to=${encodeURIComponent("/admin/seguranca?reautenticado=1")}`,
    );
  });

  it("consome a marca da URL uma vez", () => {
    window.history.replaceState(null, "", "/admin/usuarios?q=ana&reautenticado=1");

    expect(consumeReauthFlag()).toBe(true);
    expect(window.location.pathname + window.location.search).toBe("/admin/usuarios?q=ana");
    expect(consumeReauthFlag()).toBe(false);
  });
});
