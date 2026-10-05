"""Instrumentação OpenTelemetry (constituição, Princípio VII).

Exportadores são configurados pelo ambiente padrão do OpenTelemetry (`OTEL_*`) quando
a observabilidade da instalação existir; sem eles, os spans não saem do processo.
"""

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def setup_telemetry(app: FastAPI, service_name: str) -> None:
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    trace.set_tracer_provider(provider)
    # Rotas de saúde não geram spans; parâmetros de consulta não são registrados.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz")
