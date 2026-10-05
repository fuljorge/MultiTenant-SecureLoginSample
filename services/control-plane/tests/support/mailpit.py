"""Leitura dos e-mails capturados pelo Mailpit."""

from __future__ import annotations

import re
import time
from datetime import datetime

import httpx


def wait_for_email(mailpit_url: str, to: str, since: datetime, timeout_s: float = 60) -> str:
    """Retorna o texto do e-mail mais recente para `to` recebido depois de `since`."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = httpx.get(f"{mailpit_url}/api/v1/search", params={"query": f"to:{to}"})
        response.raise_for_status()
        messages = [
            m
            for m in response.json()["messages"]
            if datetime.fromisoformat(m["Created"].replace("Z", "+00:00")) >= since
        ]
        if messages:
            latest = max(messages, key=lambda m: m["Created"])
            body = httpx.get(f"{mailpit_url}/api/v1/message/{latest['ID']}")
            body.raise_for_status()
            return str(body.json()["Text"])
        time.sleep(0.5)
    raise TimeoutError(f"Nenhum e-mail para {to} em {timeout_s} s")


def extract_code(text: str) -> str:
    match = re.search(r"\b(\d{6})\b", text)
    if match is None:
        raise ValueError("Código de 6 dígitos não encontrado no e-mail")
    return match.group(1)
