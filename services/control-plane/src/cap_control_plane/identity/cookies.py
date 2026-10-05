"""Cookies do BFF (research R3; RNF-005).

- Sessão: `__Host-` (só HTTPS, sem Domain, Path=/), HttpOnly, SameSite=Lax.
- CSRF: legível pelo Studio, que o devolve no cabeçalho `X-CSRF-Token` (double submit).
- Login: liga a tentativa de login ao navegador que a iniciou (contra CSRF no login).
"""

from fastapi import Response

SESSION_COOKIE = "__Host-cap_session"
CSRF_COOKIE = "__Host-cap_csrf"
LOGIN_COOKIE = "__Host-cap_login"
CSRF_HEADER = "X-CSRF-Token"


def set_cookie(
    response: Response, name: str, value: str, *, http_only: bool, max_age: int | None = None
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=http_only,
        samesite="lax",
    )


def clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")
