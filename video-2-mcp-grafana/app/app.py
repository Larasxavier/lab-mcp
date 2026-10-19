"""
checkout-service
Aplicacao de demonstracao para o lab de observabilidade + MCP.

Simula um fluxo simples de checkout com uma etapa interna de
processamento de pagamento. De proposito, uma fracao das requisicoes
sofre latencia alta e outra fracao falha, para dar ao agente de IA
algo real para investigar (metricas mostram o sintoma, logs mostram
o erro, traces mostram onde o tempo foi gasto).
"""

import logging
import os
import random
import time

from flask import Flask, jsonify

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

try:
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
except ImportError:  # nome do modulo mudou entre versoes da SDK
    from opentelemetry.exporter.otlp.proto.grpc.log_exporter import OTLPLogExporter

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "checkout-service")
OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm.observability.svc.cluster.local:4317")

resource = Resource.create({"service.name": SERVICE_NAME})

# --- traces ---
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(SERVICE_NAME)

# --- metrics ---
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True),
    export_interval_millis=5000,
)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(SERVICE_NAME)

checkout_counter = meter.create_counter(
    "checkout_requests_total", description="Total de requisicoes de checkout"
)
payment_duration_histogram = meter.create_histogram(
    "payment_processing_duration_seconds", description="Duracao da etapa de pagamento"
)

# --- logs correlacionados com trace_id/span_id, exportados de verdade via OTLP ---
# ate aqui so formatavamos o log com trace_id/span_id pro stdout (kubectl logs).
# faltava o LoggerProvider de verdade, sem ele nada chegava no Loki, mesmo
# com metricas e traces funcionando normalmente.
LoggingInstrumentor().instrument(set_logging_format=True)

logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)
otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(message)s",
)
logger = logging.getLogger(SERVICE_NAME)
logger.addHandler(otel_handler)

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)


def process_payment():
    """Etapa interna que simula a chamada a um provedor de pagamento externo."""
    with tracer.start_as_current_span("payment-processing") as span:
        start = time.time()

        # ~20% das vezes o "provedor de pagamento" fica lento de proposito
        is_slow = random.random() < 0.20
        # ~10% das vezes o pagamento falha de proposito
        is_failure = random.random() < 0.10

        base_latency = random.uniform(0.05, 0.15)
        if is_slow:
            base_latency += random.uniform(1.5, 3.0)
        time.sleep(base_latency)

        duration = time.time() - start
        payment_duration_histogram.record(duration, {"slow": str(is_slow)})
        span.set_attribute("payment.slow", is_slow)
        span.set_attribute("payment.duration_seconds", duration)

        if is_failure:
            span.set_attribute("payment.status", "failed")
            logger.error("falha ao processar pagamento no provedor externo (timeout simulado)")
            raise RuntimeError("payment provider timeout")

        span.set_attribute("payment.status", "success")
        logger.info("pagamento processado com sucesso em %.2fs", duration)
        return duration


@app.route("/checkout", methods=["GET"])
def checkout():
    checkout_counter.add(1, {"endpoint": "/checkout"})
    logger.info("nova requisicao de checkout recebida")
    try:
        duration = process_payment()
        return jsonify(status="ok", payment_duration_seconds=round(duration, 3))
    except RuntimeError as exc:
        logger.error("checkout falhou: %s", exc)
        return jsonify(status="error", reason=str(exc)), 500


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify(status="healthy")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
