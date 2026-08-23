import pytest
import alcyoneus.storage


def test_storage_lazy_exports():
    assert alcyoneus.storage.make_agent_memory_tool is not None
    assert alcyoneus.storage.make_user_memory_tool is not None
    assert alcyoneus.storage.memory_tool is not None

    with pytest.raises(AttributeError):
        _ = alcyoneus.storage.invalid_attribute_name_xxx
