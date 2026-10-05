"""Exporta o OpenAPI do Control Plane (fonte do cliente TypeScript, T041).

Uso: `uv run python -m cap_control_plane.openapi packages/api-client/openapi.json`
Grava em UTF-8 direto no arquivo (a saída padrão do Windows não é UTF-8).
"""

import json
import sys
from pathlib import Path

from cap_control_plane.main import create_app


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m cap_control_plane.openapi <arquivo de saída>")
    schema = create_app().openapi()
    text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    Path(sys.argv[1]).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
