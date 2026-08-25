import logging
import sys
from pythonjsonlogger import jsonlogger
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def setup_observability(app: FastAPI, service_name: str = "agentic-commerce"):
    # 1. Setup JSON Logging
    logHandler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    logHandler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    root_logger.addHandler(logHandler)
    # The log level is managed by config.py, but we ensure the handlers are json formatted.
    
    # 2. Setup OpenTelemetry
    resource = Resource(attributes={
        ResourceAttributes.SERVICE_NAME: service_name
    })
    
    provider = TracerProvider(resource=resource)
    # For demonstration, we export to console. In a real environment, use OTLPSpanExporter
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    logging.info("Observability setup complete: JSON logging & OpenTelemetry enabled")
