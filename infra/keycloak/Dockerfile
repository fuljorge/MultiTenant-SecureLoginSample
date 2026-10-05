# syntax=docker/dockerfile:1.10
# Keycloak da plataforma (specs/001-identity-access, plano §4.9).
# Artefatos fixados em providers.lock; o build falha se algum checksum ou commit divergir.

ARG KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:26.7.5@sha256:37dbaf6f0722c9ec246335f36e1ef8b2e6cb960f7c27e0d8c615121a3d475a85

# Extensão de código por e-mail compilada a partir do commit da tag v26.5.0 (fixado pelo
# hash, que garante o conteúdo) com o patch do achado A15 (patches/).
FROM maven:3.9-eclipse-temurin-21@sha256:99e61abcff91a9b1333463bd8451fb18495d6eba9250ac66a338b518f8278320 AS email-otp
ADD https://github.com/mesutpiskin/keycloak-2fa-email-authenticator.git#9da56443867332eb2d491f0a60544bf3c0c96d9d /src
COPY patches/ /patches/
WORKDIR /src
RUN git apply --verbose /patches/0001-limit-email-code-attempts.patch \
    && mvn -B -q package -Dkeycloak.version=26.7.5 \
    && cp target/keycloak-2fa-email-authenticator-*.jar /keycloak-2fa-email-authenticator.jar

FROM ${KEYCLOAK_IMAGE} AS builder

ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=true \
    KC_HTTP_RELATIVE_PATH=/idp

# Segundo fator por código no e-mail (research R1), compilado no estágio email-otp.
COPY --from=email-otp --chown=1000:0 --chmod=0644 /keycloak-2fa-email-authenticator.jar \
    /opt/keycloak/providers/keycloak-2fa-email-authenticator.jar

# Lista de senhas vazadas para a política "Password Blacklist" (research R5).
# O diretório é criado antes: um ADD --chmod também aplicaria 0644 ao diretório criado.
RUN mkdir -p /opt/keycloak/data/password-blacklists
ADD --chown=1000:0 --chmod=0644 \
    --checksum=sha256:e9a88f67aafe65496682dc374559ee714e978bee50314767494c3e37a18c9fc8 \
    https://raw.githubusercontent.com/danielmiessler/SecLists/15afcb8bac144abbec11d31ec3be394169b38bb1/Passwords/Common-Credentials/Pwdb_top-1000000.txt \
    /opt/keycloak/data/password-blacklists/pwdb-top-1000000.txt

# Tema da plataforma: telas de login e e-mails em PT-BR com a identidade da marca.
COPY --chown=1000:0 themes/cap /opt/keycloak/themes/cap

RUN /opt/keycloak/bin/kc.sh build

FROM ${KEYCLOAK_IMAGE}

COPY --from=builder /opt/keycloak/ /opt/keycloak/

# A extensão registra o e-mail do usuário em logs INFO; WARN reduz a exposição (research R1).
ENV KC_LOG_LEVEL=INFO,com.mesutpiskin:WARN

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
