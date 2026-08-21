import logging


try:
    from injectq import Inject
except ImportError:

    class _DummyInject:
        def __getitem__(self, item):
            return None

    Inject = _DummyInject()


from alcyoneus.runtime.publisher.base_publisher import BasePublisher
from alcyoneus.runtime.publisher.events import EventModel
from alcyoneus.utils.background_task_manager import BackgroundTaskManager


logger = logging.getLogger("alcyoneus.publisher")


async def _publish_event_task(
    event: EventModel,
    publisher: BasePublisher | None,
) -> None:
    """Publish an event asynchronously if publisher is configured.

    Args:
        event: The event to publish.
        publisher: The publisher instance, or None.
    """
    if publisher:
        try:
            await publisher.publish(event)
            logger.debug("Published event: %s", event)
        except Exception as e:
            logger.error("Failed to publish event: %s", e)


def publish_event(
    event: EventModel,
    publisher: BasePublisher | None = Inject[BasePublisher] if Inject is not None else None,
    task_manager: BackgroundTaskManager | None = Inject[BackgroundTaskManager]
    if Inject is not None
    else None,
) -> None:
    """Publish an event asynchronously using the background task manager.

    Args:
        event: The event to publish.
        publisher: The publisher instance (injected).
        task_manager: The background task manager (injected).
    """
    # Store the task to prevent it from being garbage collected
    if task_manager is not None:
        task_manager.create_task(_publish_event_task(event, publisher))
