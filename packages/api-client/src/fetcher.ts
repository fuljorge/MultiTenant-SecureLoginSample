/**
 * Fetch usado pelo cliente gerado (orval).
 *
 * - Mesmo domínio do Studio: o cookie de sessão (HttpOnly) vai automaticamente.
 * - Requisições que alteram estado levam o cabeçalho anti-CSRF, lido do cookie
 *   `__Host-cap_csrf` (double submit; research R3).
 */
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const CSRF_COOKIE = "__Host-cap_csrf";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`HTTP ${status}`);
  }
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

/** Download de arquivo gerado pela API (ex.: CSV da auditoria), com o mesmo CSRF. */
export async function capDownload(url: string, options: RequestInit = {}): Promise<Blob> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, text ? JSON.parse(text) : undefined);
  }
  return response.blob();
}

export async function capFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  const text = await response.text();
  const body = text ? JSON.parse(text) : undefined;
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}
