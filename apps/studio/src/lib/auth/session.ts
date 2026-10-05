"use client";

import { useEffect } from "react";

import { ApiError, useMe, type MeOut } from "@cap/api-client";

/** Endereço que inicia o login no BFF e volta para `returnTo` depois. */
export function loginUrl(returnTo: string): string {
  return `/api/v1/auth/login?return_to=${encodeURIComponent(returnTo)}`;
}

export type SessionState =
  { status: "loading" } | { status: "authenticated"; me: MeOut } | { status: "error" };

/**
 * Sessão da pessoa logada. Sem sessão (401), redireciona para o login e volta para a
 * página atual. As permissões servem só para exibir a interface: quem decide é a API.
 */
export function useSession(): SessionState {
  const query = useMe();
  const unauthorized = query.error instanceof ApiError && query.error.status === 401;

  useEffect(() => {
    if (unauthorized) {
      window.location.assign(loginUrl(window.location.pathname + window.location.search));
    }
  }, [unauthorized]);

  if (query.data) return { status: "authenticated", me: query.data };
  if (query.isPending || unauthorized) return { status: "loading" };
  return { status: "error" };
}

export function activeOrganizationName(me: MeOut): string | undefined {
  return me.organizations.find((o) => o.id === me.active_organization_id)?.name;
}

/** Onde a pessoa atua: a organização ativa ou, para o Super Administrador, a instalação. */
export function scopeLabel(me: MeOut): string | undefined {
  return me.kind === "super_admin" ? "Super Administrador" : activeOrganizationName(me);
}
