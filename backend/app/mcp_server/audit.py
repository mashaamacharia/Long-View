"""Every tool call is logged to tool_calls (input, output, error)."""
import functools
from typing import Any, Callable

from app.db.models import ToolCall
from app.db.session import SessionLocal


def audited(tool_name: str, approval_required: bool = False) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            error, output = None, None
            try:
                output = fn(*args, **kwargs)
                return output
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                raise
            finally:
                with SessionLocal() as db:
                    db.add(
                        ToolCall(
                            run_id=kwargs.get("run_id"),
                            tool_name=tool_name,
                            tool_input={k: v for k, v in kwargs.items()},
                            tool_output=output if isinstance(output, dict) else None,
                            error=error,
                            approval_required=approval_required,
                        )
                    )
                    db.commit()

        return wrapper

    return decorator
