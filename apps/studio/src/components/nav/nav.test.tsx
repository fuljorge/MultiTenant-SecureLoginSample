import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MeOut } from "@cap/api-client";

import { CurrentUserProvider } from "@/lib/auth/current-user";

import { MainNav } from "./main-nav";
import { RequirePermission } from "./require-permission";

vi.mock("next/navigation", () => ({ usePathname: () => "/admin/usuarios/123" }));

// Permissões como /me devolve para cada perfil (matriz em identity/permissions.py).
const ADMINISTRATOR = ["users:read", "users:manage", "audit:read", "agents:read"];
const SUPER_ADMIN = [
  "organizations:manage",
  "organization_admins:manage",
  "super_admins:manage",
  "security:manage",
  "billing:read:all",
  "billing:manage:all",
  "audit:read:installation",
];
const BUSINESS_ANALYST = ["agents:read", "conversations:read", "conversations:review"];

function links() {
  return screen.queryAllByRole("link").map((link) => link.textContent);
}

function me(permissions: string[]): MeOut {
  return { permissions } as MeOut;
}

describe("MainNav", () => {
  it("mostra Usuários ao Administrador, sem a segurança da instalação", () => {
    render(<MainNav permissions={ADMINISTRATOR} />);
    expect(links()).toEqual(["Usuários", "Auditoria"]);
  });

  it("mostra só as áreas da instalação ao Super Administrador", () => {
    render(<MainNav permissions={SUPER_ADMIN} />);
    expect(links()).toEqual(["Organizações", "Super Administradores", "Segurança", "Auditoria"]);
  });

  it("não mostra a administração ao Business Analyst", () => {
    render(<MainNav permissions={BUSINESS_ANALYST} />);
    expect(links()).toEqual([]);
  });

  it("marca a área atual", () => {
    render(<MainNav permissions={[...ADMINISTRATOR, "security:manage"]} />);
    expect(screen.getByRole("link", { name: "Usuários" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Segurança" })).not.toHaveAttribute("aria-current");
  });
});

describe("RequirePermission", () => {
  function renderGate(permissions: string[]) {
    render(
      <CurrentUserProvider me={me(permissions)}>
        <RequirePermission permission="users:read">
          <p>Lista de usuários</p>
        </RequirePermission>
      </CurrentUserProvider>,
    );
  }

  it("exibe a tela para quem tem a permissão", () => {
    renderGate(ADMINISTRATOR);
    expect(screen.getByText("Lista de usuários")).toBeInTheDocument();
  });

  it("não mostra os usuários das organizações ao Super Administrador", () => {
    renderGate(SUPER_ADMIN);
    expect(screen.queryByText("Lista de usuários")).not.toBeInTheDocument();
  });

  it("explica a falta de permissão em vez de exibir a tela", () => {
    renderGate(BUSINESS_ANALYST);
    expect(screen.queryByText("Lista de usuários")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sem permissão" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar ao início" })).toHaveAttribute("href", "/");
  });
});
