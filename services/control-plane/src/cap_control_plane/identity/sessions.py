"""Sessões do BFF no Valkey (T029; RF-006, RNF-005, research R3).

- O cookie leva um `sid` aleatório de 256 bits; o Valkey só guarda o SHA-256 dele.
- Os tokens do Keycloak ficam cifrados pelo OpenBao Transit.
- A validade é renovada a cada uso até `idle_seconds` de inatividade e nunca passa de
  `max_seconds` desde a criação.
- Índices por usuário e por sessão do Keycloak permitem encerrar todas as sessões de uma
  pessoa (desativação, troca de senha) ou as ligadas a um logout do Keycloak.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass

import redis

from cap_control_plane.core.secrets import TransitCipher


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def partial_ip(source_ip: str | None) -> str | None:
    """IP parcial para exibição (RNF-002): o endereço completo não é guardado."""
    if not source_ip:
        return None
    try:
        address = ipaddress.ip_address(source_ip)
    except ValueError:
        return None
    if address.version == 4:
        return ".".join([*source_ip.split(".")[:3], "x"])
    groups = address.exploded.split(":")[:4]
    return ":".join(groups) + "::x"


@dataclass(frozen=True)
class CreatedSession:
    sid: str
    csrf_token: str


@dataclass
class SessionData:
    user_id: uuid.UUID
    keycloak_sid: str
    organization_id: uuid.UUID | None
    csrf_hash: str
    tokens_ciphertext: str
    created_at: float
    last_seen_at: float
    user_agent: str | None
    source_ip_partial: str | None
    # Quando a pessoa digitou senha e código (claim auth_time; RF-031). Sessões antigas,
    # sem o valor, contam como login antigo.
    auth_time: float = 0.0
    key_hash: str = ""

    def to_json(self) -> str:
        data = asdict(self)
        data.pop("key_hash")
        data["user_id"] = str(self.user_id)
        data["organization_id"] = str(self.organization_id) if self.organization_id else None
        return json.dumps(data)

    @classmethod
    def from_json(cls, raw: bytes | str, key_hash: str) -> SessionData:
        data = json.loads(raw)
        data["user_id"] = uuid.UUID(data["user_id"])
        org = data["organization_id"]
        data["organization_id"] = uuid.UUID(org) if org else None
        return cls(**data, key_hash=key_hash)


@dataclass(frozen=True)
class SessionSummary:
    """O que o usuário vê em "Minhas sessões" (US1; GET /me/sessions)."""

    public_id: str
    created_at: float
    last_seen_at: float
    user_agent: str | None
    source_ip_partial: str | None


class SessionStore:
    def __init__(
        self,
        client: redis.Redis,
        cipher: TransitCipher,
        *,
        idle_seconds: int,
        max_seconds: int,
        clock: Callable[[], float] = time.time,
        key_prefix: str = "cap",
        limits: Callable[[], tuple[int, int]] | None = None,
    ) -> None:
        """`limits` (opcional) devolve (inatividade, máximo) vigentes, ex.: da configuração
        de segurança da instalação; sem ele, valem `idle_seconds` e `max_seconds`."""
        self._redis = client
        self._cipher = cipher
        self._limits = limits or (lambda: (idle_seconds, max_seconds))
        self._clock = clock
        self.key_prefix = key_prefix

    @property
    def _idle(self) -> int:
        return self._limits()[0]

    @property
    def _max(self) -> int:
        return self._limits()[1]

    # Chaves -----------------------------------------------------------------------------

    def session_key(self, sid: str) -> str:
        return self._key_for_hash(_sha256(sid))

    def _key_for_hash(self, key_hash: str) -> str:
        return f"{self.key_prefix}:sess:{key_hash}"

    def _user_key(self, user_id: uuid.UUID) -> str:
        return f"{self.key_prefix}:user-sess:{user_id}"

    def _keycloak_key(self, keycloak_sid: str) -> str:
        return f"{self.key_prefix}:kc-sess:{keycloak_sid}"

    @staticmethod
    def public_id(sid: str) -> str:
        """Identificador exibido ao usuário; não permite reconstruir o `sid`."""
        return _sha256(sid)[:16]

    # Ciclo de vida ----------------------------------------------------------------------

    def create(
        self,
        *,
        user_id: uuid.UUID,
        keycloak_sid: str,
        organization_id: uuid.UUID | None,
        tokens: dict[str, str],
        user_agent: str | None,
        source_ip: str | None,
        auth_time: float,
    ) -> CreatedSession:
        sid = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        now = self._clock()
        key_hash = _sha256(sid)
        session = SessionData(
            user_id=user_id,
            keycloak_sid=keycloak_sid,
            organization_id=organization_id,
            csrf_hash=_sha256(csrf_token),
            tokens_ciphertext=self._cipher.encrypt(json.dumps(tokens)),
            created_at=now,
            last_seen_at=now,
            user_agent=user_agent,
            source_ip_partial=partial_ip(source_ip),
            auth_time=auth_time,
            key_hash=key_hash,
        )
        pipe = self._redis.pipeline()
        pipe.set(self._key_for_hash(key_hash), session.to_json(), ex=self._idle)
        pipe.sadd(self._user_key(user_id), key_hash)
        pipe.expire(self._user_key(user_id), self._max)
        pipe.sadd(self._keycloak_key(keycloak_sid), key_hash)
        pipe.expire(self._keycloak_key(keycloak_sid), self._max)
        pipe.execute()
        return CreatedSession(sid=sid, csrf_token=csrf_token)

    def get(self, sid: str) -> SessionData | None:
        """Lê a sessão e renova a inatividade, respeitando o limite absoluto."""
        return self._load(_sha256(sid), touch=True)

    def _load(self, key_hash: str, *, touch: bool) -> SessionData | None:
        raw = self._redis.get(self._key_for_hash(key_hash))
        if raw is None:
            return None
        session = SessionData.from_json(raw, key_hash)
        now = self._clock()
        remaining = session.created_at + self._max - now
        if remaining <= 0:
            self._delete(session)
            return None
        if touch:
            session.last_seen_at = now
            ttl = int(min(self._idle, remaining))
            self._redis.set(self._key_for_hash(key_hash), session.to_json(), ex=max(ttl, 1))
        return session

    def save(self, session: SessionData) -> None:
        """Grava mudanças (organização ativa, tokens renovados) mantendo o TTL atual."""
        key = self._key_for_hash(session.key_hash)
        self._redis.set(key, session.to_json(), keepttl=True, xx=True)

    def tokens(self, session: SessionData) -> dict[str, str]:
        return dict(json.loads(self._cipher.decrypt(session.tokens_ciphertext)))

    def replace_tokens(self, session: SessionData, tokens: dict[str, str]) -> None:
        session.tokens_ciphertext = self._cipher.encrypt(json.dumps(tokens))
        self.save(session)

    @staticmethod
    def csrf_matches(session: SessionData, token: str | None) -> bool:
        if not token:
            return False
        return hmac.compare_digest(session.csrf_hash, _sha256(token))

    # Encerramento -----------------------------------------------------------------------

    def delete(self, sid: str) -> None:
        session = self._load(_sha256(sid), touch=False)
        if session:
            self._delete(session)

    def _delete(self, session: SessionData) -> None:
        pipe = self._redis.pipeline()
        pipe.delete(self._key_for_hash(session.key_hash))
        pipe.srem(self._user_key(session.user_id), session.key_hash)
        pipe.srem(self._keycloak_key(session.keycloak_sid), session.key_hash)
        pipe.execute()

    def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        """Encerra todas as sessões da pessoa (RF-005, RF-011). Devolve quantas existiam."""
        count = 0
        for key_hash in self._members(self._user_key(user_id)):
            session = self._load(key_hash, touch=False)
            if session:
                self._delete(session)
                count += 1
        self._redis.delete(self._user_key(user_id))
        return count

    def delete_for_user_in_organization(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> int:
        """Encerra só as sessões da pessoa com essa organização ativa (plano §4.4)."""
        count = 0
        for key_hash in self._members(self._user_key(user_id)):
            session = self._load(key_hash, touch=False)
            if session and session.organization_id == organization_id:
                self._delete(session)
                count += 1
        return count

    def delete_by_keycloak_sid(self, keycloak_sid: str) -> None:
        """Back-channel logout: encerra as sessões ligadas à sessão do Keycloak."""
        for key_hash in self._members(self._keycloak_key(keycloak_sid)):
            session = self._load(key_hash, touch=False)
            if session:
                self._delete(session)
        self._redis.delete(self._keycloak_key(keycloak_sid))

    def list_for_user(self, user_id: uuid.UUID) -> list[SessionSummary]:
        summaries = []
        for key_hash in self._members(self._user_key(user_id)):
            session = self._load(key_hash, touch=False)
            if session:
                summaries.append(
                    SessionSummary(
                        public_id=key_hash[:16],
                        created_at=session.created_at,
                        last_seen_at=session.last_seen_at,
                        user_agent=session.user_agent,
                        source_ip_partial=session.source_ip_partial,
                    )
                )
        return sorted(summaries, key=lambda s: s.last_seen_at, reverse=True)

    def delete_by_public_id(self, user_id: uuid.UUID, public_id: str) -> bool:
        """Encerra uma sessão da própria pessoa (RF-006). Falso se não for dela."""
        for key_hash in self._members(self._user_key(user_id)):
            if key_hash.startswith(public_id):
                session = self._load(key_hash, touch=False)
                if session and session.user_id == user_id:
                    self._delete(session)
                    return True
        return False

    def _members(self, key: str) -> list[str]:
        return [m.decode() for m in self._redis.smembers(key)]  # type: ignore[union-attr]
