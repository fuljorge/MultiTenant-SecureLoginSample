"""Logs estruturados em JSON com redação de dados sensíveis (T016).

Constituição, Princípios V e X: senhas, códigos, tokens, links de uso único, e-mails e
IPs não aparecem nos logs técnicos. A redação é aplicada à mensagem final e a todos os
campos extras; campos cujo nome indica dado sensível são substituídos por inteiro.
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDIGIDO]"

# Palavras que, no nome de um campo (separadas por "_", "-" ou "."), indicam valor que
# nunca é registrado. Comparação por palavra: "membership_id" e "status_code" passam.
_SENSITIVE_WORDS = {
    "password",
    "passwd",
    "senha",
    "secret",
    "token",
    "authorization",
    "cookie",
    "session",
    "sid",
    "email",
    "ip",
    "link",
    "url",
    "otp",
    "code",
    "codigo",
    "agent",
}
# Campos que contêm uma palavra sensível mas são seguros e úteis no log.
_SAFE_KEYS = {"status_code", "error_code", "http_status_code"}


def is_sensitive_key(key: str) -> bool:
    key = key.lower()
    if key in _SAFE_KEYS:
        return False
    return any(word in _SENSITIVE_WORDS for word in re.split(r"[_\-.]", key))


# Padrões procurados dentro de textos livres, na ordem em que são aplicados.
_TEXT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Links: o caminho e a consulta podem carregar tokens de uso único.
    (re.compile(r"https?://[^\s\"'<>]+"), "[LINK]"),
    (re.compile(r"(?i)\bbearer\s+\S+"), "Bearer " + REDACTED),
    (re.compile(r"\beyJ[\w-]+\.[\w-]+(?:\.[\w-]+)?"), "[TOKEN]"),
    (
        re.compile(r"(?i)\b(password|senha|secret|token|code|codigo)(\s*[=:]\s*)\S+"),
        r"\1\2" + REDACTED,
    ),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[E-MAIL]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
    (
        re.compile(
            # IPv6 completo (8 grupos) ou abreviado com "::". Horários como 12:00:00 não casam.
            r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
            r"|(?:\b[0-9a-fA-F]{1,4}:){1,6}:(?:[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4})*)?"
            r"|(?<![\w:])::(?:[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4})*)?"
        ),
        "[IP]",
    ),
]

# Atributos padrão do LogRecord, que não são campos extras.
_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


def redact_text(text: str) -> str:
    for pattern, replacement in _TEXT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(key: str, value: Any) -> Any:
    if is_sensitive_key(key):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(key, v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = redact_value(key, value)
        if record.exc_info:
            entry["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Logs de acesso do servidor web trazem IP e URL; a telemetria cobre esse papel.
    logging.getLogger("uvicorn.access").disabled = True
