# MultiTenant SecureLogin Sample

Exemplo de uma aplicação **multi-tenant** com login seguro, controle de acesso por perfil e
auditoria imutável. É um recorte, para portfólio, da camada de identidade de uma
plataforma maior. Foi construído com Spec-Driven Development: especificação, plano e
tarefas aprovados antes do código.

> **Licença: só para consulta.** Você pode ler e estudar o código. Copiar, usar ou
> redistribuir exige autorização. Detalhes em [LICENSE](LICENSE).

## O que o exemplo demonstra

- **Login direto com segundo fator** por código enviado ao e-mail (Keycloak), com:
  - bloqueio por tentativas, que conta senha **e** código;
  - recuperação de senha;
  - lista de senhas vazadas;
  - medidor de força da senha.
- **Sessão no padrão BFF.** Os tokens nunca chegam ao navegador:
  - cookies `__Host-`, `HttpOnly` e `SameSite`;
  - proteção contra CSRF por *double submit*;
  - inatividade de 30 min e duração máxima de 12 h;
  - *back-channel logout*.
- **Multi-tenant com RLS no PostgreSQL.** Cada transação define quem age e em qual
  organização, e nenhum papel do banco ignora as políticas.
- **Dois níveis de administração:**
  - um **Super Administrador** cria e suspende organizações sem enxergar nada dentro
    delas, o que é garantido pelo banco;
  - um **Administrador** gere as pessoas da própria organização.
- **Seis perfis fixos** aplicados em toda rota da API. Um teste estrutural reprova o CI se
  alguma rota não declarar a proteção.
- **Reautenticação recente** (senha e código) antes de ações sensíveis, quando o login
  tem mais de 15 minutos.
- **Audit Trail append-only com cadeia de hash.** Gatilho contra `UPDATE` e `DELETE`,
  consulta com filtros, exportação em CSV e expurgo de IP e navegador por retenção
  (LGPD).
- **Pedido de esquecimento** (LGPD): anonimiza a pessoa sem quebrar a auditoria.

## Arquitetura

```text
Navegador ──cookie de sessão──▶ Studio (Next.js) ──/api──▶ Control Plane (FastAPI)
                                                              │   ├── PostgreSQL 17 (RLS, auditoria)
     telas de login e código ◀── Keycloak (OIDC + PKCE) ◀────┘   ├── Valkey (sessões)
                                                                  ├── OpenBao (cifra dos tokens)
                                                                  └── SMTP (Mailpit no local)
```

| Pasta | Conteúdo |
|---|---|
| `services/control-plane/` | API FastAPI, migrações Alembic, CLI `cap-admin`, worker `cap-worker` |
| `apps/studio/` | Interface (Next.js 16, React 19, shadcn/ui, TanStack Query) |
| `packages/api-client/` | Cliente TypeScript gerado do OpenAPI (orval) |
| `infra/` | Docker Compose local, imagem e realm do Keycloak (tema, extensão de código por e-mail) |
| `tests/e2e/` | Playwright, desktop e celular |
| `specs/001-identity-access/` | Especificação, plano, tarefas, contratos e checklists (OWASP ASVS L2, desempenho) |

Os comentários e as specs citam a "constituição" e seções `§N` de uma referência de
produto. São documentos internos do projeto original e não estão incluídos aqui.

## Como rodar

Pré-requisitos: Python 3.12 com [uv](https://docs.astral.sh/uv/), Node 24 com `corepack`
e Docker. No Windows, use `127.0.0.1` (e não `localhost`) para o PostgreSQL e o Valkey.

```sh
uv sync && corepack pnpm install
uv run python infra/compose/init_env.py          # gera credenciais locais (.env, fora do Git)
docker compose -f infra/compose/docker-compose.yml up -d

cd services/control-plane
export CAP_ENV_FILE=../../infra/compose/.env.control-plane
(set -a; . $CAP_ENV_FILE; uv run alembic upgrade head)
uv run uvicorn cap_control_plane.main:run --factory --host 127.0.0.1 --port 8000
uv run cap-worker                                 # em outro terminal
uv run cap-admin bootstrap-super-admin --email voce@exemplo.com.br --name "Seu Nome"

cd ../../apps/studio && corepack pnpm dev        # http://localhost:3000
```

O link de ativação e os códigos de login chegam no Mailpit, em http://localhost:8025.

## Testes e qualidade

| O quê | Comando |
|---|---|
| Lint e tipos (Python) | `uv run ruff check services/` · `cd services/control-plane && uv run mypy` |
| Testes unitários e de contrato | `cd services/control-plane && uv run pytest -m "not integration"` |
| Testes de integração (serviços reais) | `cd services/control-plane && uv run pytest` |
| Lint, tipos e Vitest (TypeScript) | `corepack pnpm lint` · `corepack pnpm typecheck` · `corepack pnpm test` |
| E2E | `corepack pnpm e2e` |

O CI (`.github/workflows/ci.yml`) roda:
- lint, tipos e testes unitários de Python e TypeScript;
- a verificação de que o cliente gerado está em dia com o OpenAPI;
- gitleaks;
- Trivy no código e nas imagens;
- os E2E com as imagens do projeto, seguidos de uma varredura de segredos nos logs.

## Licença

Copyright © 2026 Fulvio Jorge da Silva. Todos os direitos reservados. Publicado só para
consulta, como exemplo de portfólio. Veja [LICENSE](LICENSE).

Os componentes de terceiros mantêm as próprias licenças, listadas nos manifestos de
dependências (`pyproject.toml`, `package.json` e `infra/keycloak/providers.lock`).
