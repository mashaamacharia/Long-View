"""Every tool call is logged to tool_calls (input, output, error). Auditing never breaks a tool."""
from __future__ import annotations

import functools
import inspect
import json
import logging
from typing import Any, Callable

from app.db.models import AgentRun, ToolCall
from app.db.session import SessionLocal

log = logging.getLogger(__name__)


def _jsonable(x: Any) -> Any:
    return json.loads(json.dumps(x, default=str))


def _record(tool_name: str, approval_required: bool, inputs: dict[str, Any], output: Any, error: str | None) -> None:
    try:
        if error is None and isinstance(output, dict) and output.get("ok") is False:
            error = str(output.get("error", "tool reported ok=false"))  # refusals are audit-worthy too
        with SessionLocal() as db:
            run_id = inputs.get("run_id")
            if run_id and db.get(AgentRun, run_id) is None:
                run_id = None  # an unknown run id must not violate the foreign key and lose the audit row
            db.add(ToolCall(
                run_id=run_id,
                tool_name=tool_name,
                tool_input=_jsonable(inputs),
                tool_output=_jsonable(output) if isinstance(output, dict) else None,
                error=error,
                approval_required=approval_required,
            ))
            db.commit()
    except Exception:  # noqa: BLE001
        log.exception("failed to write audit row for %s", tool_name)


def audited(tool_name: str, approval_required: bool = False) -> Callable:
    def decorator(fn: Callable) -> Callable:
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                inputs = dict(sig.bind_partial(*args, **kwargs).arguments)
            except TypeError:
                inputs = dict(kwargs)
            output, error = None, None
            try:
                output = fn(*args, **kwargs)
                return output
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                _record(tool_name, approval_required, inputs, output, error)

        return wrapper

    return decorator
