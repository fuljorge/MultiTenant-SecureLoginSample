# Infraestrutura

## Ambiente local

```sh
uv run python infra/compose/init_env.py          # gera infra/compose/.env (credenciais locais)
docker compose -f infra/compose/docker-compose.yml up -d
```

| Serviço | Endereço | Observação |
|---|---|---|
| PostgreSQL 17 | `127.0.0.1:5432` | Bancos `cap` (Control Plane) e `keycloak`. Use `127.0.0.1`, não `localhost`: no Windows o driver trava tentando IPv6 |
| Valkey | `127.0.0.1:6379` | Sessões do BFF |
| OpenBao (dev) | `http://127.0.0.1:8200` | Transit com a chave `cap-session` |
| Keycloak | `http://localhost:8080/idp` | Realm `cap`, aplicado pelo serviço `keycloak-config` |
| Mailpit | `http://localhost:8025` | Todos os e-mails enviados ficam aqui |

Primeiro acesso: o provisionamento cria só o **Super Administrador** inicial, que convida as
organizações pela plataforma (spec 001, §4.8). Localmente:

```sh
cd services/control-plane
CAP_ENV_FILE=../../infra/compose/.env.control-plane uv run cap-admin bootstrap-super-admin \
  --email voce@exemplo.com.br --name "Seu Nome"   # o link de ativação chega no Mailpit
```

## Imagens (T073)

Contexto de build é a raiz do repositório; o `.dockerignore` deixa de fora `.env*`,
`DevNotes.MD` e artefatos locais.

```sh
docker build -f services/control-plane/Dockerfile -t cap-control-plane .   # API, cap-worker, cap-admin, alembic
docker build -f apps/studio/Dockerfile -t cap-studio .                     # Next.js standalone
docker build -t cap-keycloak infra/keycloak
```

O CI constrói as três e roda o Trivy: falha com vulnerabilidade alta ou crítica que tenha
correção, salvo mitigação registrada em `.trivyignore.yaml` (justificativa, caminho e data
de validade). O job E2E usa essas mesmas imagens e varre os logs com
`infra/ci/scan_logs_for_secrets.py` (CS-007).

## Keycloak

- `keycloak/Dockerfile`: imagem fixada por digest; extensão de código por e-mail compilada
  a partir de commit fixado com o patch do achado A15; lista de senhas vazadas com checksum.
  Detalhes e procedência em `keycloak/providers.lock`.
- `keycloak/realm/cap-realm.yaml`: configuração do realm (keycloak-config-cli). A
  substituição de variáveis do keycloak-config-cli vale até em comentários.
- `keycloak/themes/cap/`: telas de login e e-mails em PT-BR com a identidade da marca.

## Alerta de tentativa de alterar o Audit Trail

`audit.audit_event` só aceita inserções (specs/001-identity-access, data-model.md). Qualquer
`UPDATE`, `DELETE` ou `TRUNCATE` é recusado:

- pelo papel da aplicação (`cap_app`), por falta de privilégio: `permission denied for table
  audit_event`;
- por qualquer papel, inclusive o dono, pelo trigger `audit_event_no_change`:
  `audit.audit_event é append-only: <operação> recusado`.

O PostgreSQL registra os dois erros e o comando no log do servidor (configuração padrão:
`log_min_messages = warning` e `log_min_error_statement = error`). A observabilidade da
instalação deve coletar esse log e gerar alerta, e o evento `audit.tamper_attempt`, quando
encontrar uma das mensagens acima com a tabela `audit_event`. Até a coleta existir, a
tentativa fica no log do container `postgres`:

```sh
docker compose -f infra/compose/docker-compose.yml logs postgres | grep -E "append-only|permission denied for table audit_event"
```

## Pontos de implantação (produção)

- **IP de origem nos eventos do Keycloak:** atrás de proxy/ingress, configure
  `KC_PROXY_HEADERS=xforwarded` (ou `forwarded`) e confie só no proxy da instalação. Sem
  isso, o Audit Trail registra o IP do proxy, não o do usuário (no ambiente local aparece o
  gateway do Docker, ex.: `172.18.0.1`).
- **Importação de eventos:** o processo `cap-worker` precisa estar sempre em execução. A
  observabilidade deve alertar na mensagem de log `Importação de eventos do Keycloak parada`
  (cursor sem avançar há mais de 5 minutos; os eventos ficam 7 dias no Keycloak).
