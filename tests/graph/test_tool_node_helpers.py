from pathlib import Path

from alcyoneus.core.graph.tool_node._helpers import (
    _as_bool,
    _extract_block_meta,
    _safe_serialize,
)


class _ResourceDump:
    def model_dump(self):
        return {
            "type": "resource",
            "resource": {"uri": Path("/tmp/data.json"), "mime": "application/json"},
        }


class _NoJsonNoDump:
    def __repr__(self):
        return "<non-json>"


class _NonSerializableNoDump:
    def __init__(self):
        self.value = {1, 2, 3}


def test_safe_serialize_handles_dict_and_scalar_values():
    assert _safe_serialize({"a": 1}) == {"a": 1}
    assert _safe_serialize("text") == {"content": "text"}


def test_safe_serialize_uses_model_dump_and_normalizes_resource_uri():
    result = _safe_serialize(_ResourceDump())
    assert result["type"] == "resource"
    assert result["resource"]["uri"] == "/tmp/data.json"


def test_safe_serialize_falls_back_to_string_when_not_serializable():
    result = _safe_serialize(_NonSerializableNoDump())
    assert result["type"] == "fallback"
    assert "content" in result


def test_as_bool_handles_native_and_string_values():
    truthy = {"true", "1", "yes"}
    assert _as_bool(True, truthy) is True
    assert _as_bool(False, truthy) is False
    assert _as_bool("YES", truthy) is True
    assert _as_bool("no", truthy) is False


def test_extract_block_meta_prefers_explicit_error_and_strips_meta_keys():
    is_error, cleaned = _extract_block_meta(
        {"is_error": "yes", "status": "ok", "payload": 1, "success": True}
    )
    assert is_error is True
    assert cleaned == {"payload": 1}


def test_extract_block_meta_uses_success_flag_when_error_not_present():
    is_error, cleaned = _extract_block_meta({"success": "false", "x": 1})
    assert is_error is True
    assert cleaned == {"x": 1}


def test_extract_block_meta_marks_failure_status_as_error():
    is_error, cleaned = _extract_block_meta({"status": "failed", "value": "v"})
    assert is_error is True
    assert cleaned == {"value": "v"}


def test_extract_block_meta_defaults_to_non_error_without_status_fields():
    is_error, cleaned = _extract_block_meta({"answer": 42})
    assert is_error is False
    assert cleaned == {"answer": 42}
