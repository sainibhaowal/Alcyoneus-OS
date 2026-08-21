"""Shared helper functions and constants for tool node executors."""

from __future__ import annotations

import json
import typing as t


_STATUS_OK: set[str] = {"completed", "success", "ok", "done", "true", "1"}
_STATUS_FAIL: set[str] = {"failed", "failure", "error", "false", "0"}
_ERROR_TRUE: set[str] = {"true", "1", "yes", "error", "failed", "failure"}


def _safe_serialize(obj: t.Any) -> dict[str, t.Any]:
    try:
        json.dumps(obj)
        return obj if isinstance(obj, dict) else {"content": obj}
    except (TypeError, OverflowError):
        if hasattr(obj, "model_dump"):
            dumped = obj.model_dump()  # type: ignore
            if isinstance(dumped, dict) and dumped.get("type") == "resource":
                resource = dumped.get("resource", {})
                if isinstance(resource, dict) and "uri" in resource:
                    resource["uri"] = str(resource["uri"])
                    dumped["resource"] = resource
            return dumped
        return {"content": str(obj), "type": "fallback"}


def _as_bool(val: t.Any, truthy_set: set[str]) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).lower() in truthy_set


def _extract_block_meta(
    data: dict[str, t.Any],
) -> tuple[bool, dict[str, t.Any]]:
    """Normalize arbitrary status/error keys; return (is_error, cleaned_data)."""
    data = dict(data)

    raw_status = data.pop("status", None)
    raw_is_error = data.pop("is_error", data.pop("error", None))
    raw_success = data.pop("success", None)

    if raw_is_error is not None:
        is_error = _as_bool(raw_is_error, _ERROR_TRUE)
    elif raw_success is not None:
        is_error = not _as_bool(raw_success, _STATUS_OK)
    else:
        is_error = False

    if raw_status is not None:
        s = str(raw_status).lower()
        if s in _STATUS_FAIL:
            is_error = True

    return is_error, data
