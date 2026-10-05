"""Processo de tarefas em segundo plano do Control Plane (`cap-worker`).

- Importação dos eventos do Keycloak para o Audit Trail, a cada 5 s (research R4).
- Expurgo diário de IP e navegador antigos do Audit Trail (T069; RNF-002).
"""

import logging
import time

from cap_control_plane.audit.keycloak_ingestor import KeycloakEventIngestor
from cap_control_plane.audit.purge import purge_origins
from cap_control_plane.core.logging import configure_logging
from cap_control_plane.core.settings import get_settings
from cap_control_plane.services import Services

logger = logging.getLogger(__name__)

POLL_SECONDS = 5.0
PURGE_EVERY_SECONDS = 24 * 60 * 60


def main() -> None:
    configure_logging()
    services = Services.from_settings(get_settings())
    ingestor = KeycloakEventIngestor(services)
    last_purge = 0.0
    while True:
        ingestor.tick()
        if time.monotonic() - last_purge >= PURGE_EVERY_SECONDS or not last_purge:
            try:
                purge_origins(services)
            except Exception:
                logger.exception("Falha no expurgo da origem dos eventos de auditoria")
            last_purge = time.monotonic()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
