"""Envelhece o último login das sessões de uma pessoa, para testar o RF-031 sem esperar.

Só para o ambiente local e o CI (tests/e2e):
    uv run python -m tests.support.age_sessions --email pessoa@exemplo.com.br --minutes 20
"""

from __future__ import annotations

import argparse
import time

from sqlalchemy import text

from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.core.settings import get_settings
from cap_control_plane.services import Services


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--minutes", type=float, default=20)
    args = parser.parse_args()

    services = Services.from_settings(get_settings())
    with transaction(services.engine, DbContext.system()) as s:
        user_id = s.execute(
            text("SELECT id FROM identity.user_account WHERE email = :e"), {"e": args.email}
        ).scalar_one()
    store = services.sessions
    aged = 0
    for key_hash in store._members(store._user_key(user_id)):
        session = store._load(key_hash, touch=False)
        if session is not None:
            session.auth_time = time.time() - args.minutes * 60
            store.save(session)
            aged += 1
    print(aged)


if __name__ == "__main__":
    main()
