"""Publisher module for TAF events.

This package exposes publishers that handle event delivery to various outputs,
such as console, Redis, Kafka, and RabbitMQ.
"""

from .base_publisher import BasePublisher
from .composite_publisher import CompositePublisher
from .console_publisher import ConsolePublisher
from .events import ContentType, Event, EventModel, EventType
from .kafka_publisher import KafkaPublisher
from .otel_publisher import OtelPublisher, setup_tracing
from .publish import publish_event
from .rabbitmq_publisher import RabbitMQPublisher
from .redis_publisher import RedisPublisher


__all__ = [
    "BasePublisher",
    "CompositePublisher",
    "ConsolePublisher",
    "ContentType",
    "Event",
    "EventModel",
    "EventType",
    "KafkaPublisher",
    "OtelPublisher",
    "RabbitMQPublisher",
    "RedisPublisher",
    "publish_event",
    "setup_tracing",
]
