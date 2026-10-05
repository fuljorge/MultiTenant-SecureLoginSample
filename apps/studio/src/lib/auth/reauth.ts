import { ApiError } from "@cap/api-client";

/** Marca na URL de retorno: a pessoa acabou de confirmar a identidade (RF-031). */
export const REAUTH_FLAG = "reautenticado";

/** Resposta da API para ação sensível com login antigo (`401`, `code: reauth_required`). */
export function isReauthRequired(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 401) return false;
  const body = error.body as { code?: unknown } | undefined;
  return body?.code === "reauth_required";
}

/** Nova autenticação (senha e código) que volta para a mesma tela, com a marca. */
export function reauthUrl(location: { pathname: string; search: string }): string {
  const params = new URLSearchParams(location.search);
  params.set(REAUTH_FLAG, "1");
  const returnTo = `${location.pathname}?${params.toString()}`;
  return `/api/v1/auth/login?reauth=1&return_to=${encodeURIComponent(returnTo)}`;
}

export function redirectToReauth(): void {
  // Navegação completa: a autenticação acontece nas telas do Keycloak.
  window.location.assign(reauthUrl(window.location));
}

/** Lê e remove a marca da URL; verdadeiro se a pessoa voltou da nova autenticação. */
export function consumeReauthFlag(): boolean {
  const url = new URL(window.location.href);
  if (!url.searchParams.has(REAUTH_FLAG)) return false;
  url.searchParams.delete(REAUTH_FLAG);
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  return true;
}
