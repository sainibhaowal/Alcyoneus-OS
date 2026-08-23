import pytest
from unittest.mock import AsyncMock, MagicMock
from alcyoneus.runtime.publisher.publish import _publish_event_task, publish_event
from alcyoneus.runtime.publisher.events import EventModel
from alcyoneus.runtime.publisher.base_publisher import BasePublisher
from alcyoneus.utils.background_task_manager import BackgroundTaskManager


@pytest.mark.asyncio
async def test_publish_event_task_success():
    event = MagicMock(spec=EventModel)
    publisher = AsyncMock(spec=BasePublisher)
    
    await _publish_event_task(event, publisher)
    
    publisher.publish.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_publish_event_task_failure():
    event = MagicMock(spec=EventModel)
    publisher = AsyncMock(spec=BasePublisher)
    publisher.publish.side_effect = RuntimeError("publish boom")
    
    await _publish_event_task(event, publisher)
    
    publisher.publish.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_publish_event_task_no_publisher():
    event = MagicMock(spec=EventModel)
    await _publish_event_task(event, None)


def test_publish_event():
    event = MagicMock(spec=EventModel)
    publisher = MagicMock(spec=BasePublisher)
    task_manager = MagicMock(spec=BackgroundTaskManager)
    
    publish_event(event, publisher, task_manager)
    task_manager.create_task.assert_called_once()
