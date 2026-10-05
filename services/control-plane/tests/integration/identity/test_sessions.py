"""Sessões do BFF no Valkey (T028; RF-006, RNF-005, research R3)."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator

import pytest
import redis

from cap_control_plane.core.secrets import TransitCipher
from cap_control_plane.core.settings import Settings
from cap_control_plane.identity.sessions import SessionStore

TOKENS = {"access_token": "acesso-123", "refresh_token": "renovacao-456", "id_token": "id-789"}


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def valkey(settings: Settings) -> Iterator[redis.Redis]:
    client = redis.Redis.from_url(settings.valkey_url.get_secret_value())
    yield client
    client.close()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(settings: Settings, valkey: redis.Redis, clock: Clock) -> SessionStore:
    return SessionStore(
        valkey,
        TransitCipher(settings),
        idle_seconds=1800,
        max_seconds=43200,
        clock=clock,
        key_prefix=f"test-{uuid.uuid4().hex[:8]}",
    )


def _create(store: SessionStore, user_id: uuid.UUID | None = None, kc_sid: str = "kc-1") -> str:
    created = store.create(
        user_id=user_id or uuid.uuid4(),
        keycloak_sid=kc_sid,
        organization_id=uuid.uuid4(),
        tokens=TOKENS,
        user_agent="pytest",
        source_ip="203.0.113.45",
        auth_time=1_000_000.0,
    )
    return created.sid


def test_cria_e_le_sessao(store: SessionStore) -> None:
    user_id = uuid.uuid4()
    created = store.create(
        user_id=user_id,
        keycloak_sid="kc-1",
        organization_id=None,
        tokens=TOKENS,
        user_agent="pytest",
        source_ip="203.0.113.45",
        auth_time=1_000_000.0,
    )

    session = store.get(created.sid)

    assert session is not None
    assert session.user_id == user_id
    assert store.tokens(session) == TOKENS
    assert store.csrf_matches(session, created.csrf_token)
    assert not store.csrf_matches(session, "outro")


def test_valkey_guarda_hash_do_sid_e_tokens_cifrados(
    store: SessionStore, valkey: redis.Redis
) -> None:
    sid = _create(store)

    keys = [k.decode() for k in valkey.scan_iter(f"{store.key_prefix}:sess:*")]
    raw = b"".join(valkey.get(k) or b"" for k in keys).decode()

    assert keys == [f"{store.key_prefix}:sess:{hashlib.sha256(sid.encode()).hexdigest()}"]
    assert sid not in raw
    for token in TOKENS.values():
        assert token not in raw
    assert "203.0.113.45" not in raw


def test_expira_por_inatividade(store: SessionStore, valkey: redis.Redis) -> None:
    sid = _create(store)

    ttl = valkey.ttl(store.session_key(sid))

    assert 1790 <= ttl <= 1800


def test_uso_renova_a_inatividade_sem_passar_do_limite_de_12h(
    store: SessionStore, valkey: redis.Redis, clock: Clock
) -> None:
    sid = _create(store)

    clock.now += 43200 - 600  # faltam 10 min para o limite absoluto
    assert store.get(sid) is not None
    ttl = valkey.ttl(store.session_key(sid))

    assert 590 <= ttl <= 600


def test_sessao_acima_de_12h_e_recusada_e_apagada(
    store: SessionStore, valkey: redis.Redis, clock: Clock
) -> None:
    sid = _create(store)

    clock.now += 43200 + 1

    assert store.get(sid) is None
    assert valkey.exists(store.session_key(sid)) == 0


def test_encerra_todas_as_sessoes_do_usuario(store: SessionStore) -> None:
    user_id = uuid.uuid4()
    sids = [_create(store, user_id) for _ in range(3)]
    other = _create(store)

    assert store.delete_all_for_user(user_id) == 3

    assert all(store.get(sid) is None for sid in sids)
    assert store.get(other) is not None


def test_encerra_pela_sessao_do_keycloak(store: SessionStore) -> None:
    sid = _create(store, kc_sid="kc-abc")
    other = _create(store, kc_sid="kc-xyz")

    store.delete_by_keycloak_sid("kc-abc")

    assert store.get(sid) is None
    assert store.get(other) is not None


def test_lista_e_encerra_uma_sessao_pelo_id_publico(store: SessionStore) -> None:
    user_id = uuid.uuid4()
    keep, drop = _create(store, user_id), _create(store, user_id)

    listed = store.list_for_user(user_id)
    public_ids = {s.public_id for s in listed}
    drop_public = next(s.public_id for s in listed if s.public_id != store.public_id(keep))

    assert len(listed) == 2
    assert all(s.source_ip_partial == "203.0.113.x" for s in listed)
    assert keep not in public_ids
    assert store.delete_by_public_id(user_id, drop_public)
    assert store.get(drop) is None
    assert store.get(keep) is not None


def test_nao_encerra_sessao_de_outro_usuario_pelo_id_publico(store: SessionStore) -> None:
    owner, intruder = uuid.uuid4(), uuid.uuid4()
    sid = _create(store, owner)

    assert not store.delete_by_public_id(intruder, store.public_id(sid))
    assert store.get(sid) is not None
