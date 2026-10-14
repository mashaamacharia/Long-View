"""Tool access for the agent: two MCP servers behind one validated router.

Safety boundary (all enforced here, in code, not in the prompt):
  * the external filesystem server also exposes write_file / edit_file / move_file; only the read-only
    allowlist below is ever reachable
  * learner_id and run_id are injected by the runtime and hidden from the model's tool schemas, so the
    model cannot target another learner or forge an audit identity
  * approval_id is only ever supplied by the runtime from a teacher's decision
  * document paths are confined to the current learner's folder
  * every model-proposed call is validated against the run's own state before it executes
"""
from __future__ import annotations

import json
import logging
import posixpath
import shlex
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator

from app.config import settings

log = logging.getLogger(__name__)

OURS_RUNTIME = {"get_learner_timeline", "detect_patterns", "get_evidence", "flag_for_teacher_review", "update_learner_profile"}
EXTERNAL_RUNTIME = {"list_directory", "read_text_file"}          # read-only; the server's write tools are unreachable
LLM_OURS = {"get_evidence", "detect_patterns"}                   # what the model may choose between
LLM_EXTERNAL = {"list_directory", "read_text_file"}
MODEL_FACING = LLM_OURS | LLM_EXTERNAL                           # the only tools a model-proposed call may ever reach
HIDDEN_PARAMS = {"run_id", "learner_id", "approval_id", "head", "tail"}


class ToolError(Exception):
    pass


def _text(res: Any) -> str:
    return "".join(getattr(c, "text", "") for c in getattr(res, "content", []) or [])


class ToolRouter:
    def __init__(self, ours: Any, external: Any | None, *, run_id: str, learner_id: str, docs_root: str):
        self.ours, self.external = ours, external
        self.run_id, self.learner_id = run_id, learner_id
        self.docs_root = docs_root.rstrip("/")
        self.external_error: str | None = None
        self._tools: dict[str, Any] = {}
        self._ours_names: set[str] = set()
        self._external_names: set[str] = set()

    async def load(self) -> "ToolRouter":
        for t in (await self.ours.list_tools()).tools:
            if t.name in OURS_RUNTIME:
                self._tools[t.name] = t
                self._ours_names.add(t.name)
        if self.external is not None:
            for t in (await self.external.list_tools()).tools:
                if t.name in EXTERNAL_RUNTIME:
                    self._tools[t.name] = t
                    self._external_names.add(t.name)
        return self

    @property
    def has_external(self) -> bool:
        return self.external is not None and self._external_names >= EXTERNAL_RUNTIME

    @property
    def learner_docs_dir(self) -> str:
        return posixpath.join(self.docs_root, self.learner_id)

    # ----- paths -----
    def check_doc_path(self, path: Any, *, directory: bool = False) -> str:
        if not isinstance(path, str) or not path.strip():
            raise ToolError("path is required")
        d = self.learner_docs_dir
        p = posixpath.normpath(path if path.startswith("/") else posixpath.join(d, path))
        if directory:
            if p != d:
                raise ToolError(f"only this learner's folder may be listed: {d}")
        elif not (p.startswith(d + "/") and p.lower().endswith((".md", ".txt"))):
            raise ToolError(f"only .md/.txt files inside {d} may be read")
        return p

    # ----- runtime-trusted calls -----
    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(args or {})
        try:
            if name in self._ours_names:
                props = (self._tools[name].inputSchema or {}).get("properties", {})
                if "learner_id" in props:
                    args["learner_id"] = self.learner_id      # forced, never taken from the model
                if "run_id" in props:
                    args["run_id"] = self.run_id
                session, external = self.ours, False
            elif name in self._external_names and self.external is not None:
                args = {"path": self.check_doc_path(args.get("path"), directory=(name == "list_directory"))}
                session, external = self.external, True
            else:
                raise ToolError(f"tool not available: {name}")
        except ToolError as exc:
            return {"ok": False, "error": str(exc), "rejected": True}
        try:
            res = await session.call_tool(name, args)
        except Exception as exc:  # noqa: BLE001  (CancelledError is a BaseException and still propagates)
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        text = _text(res)
        if getattr(res, "isError", False):
            return {"ok": False, "error": text[:400] or "tool error"}
        if external:
            return {"ok": True, "text": text}
        try:
            parsed = json.loads(text)
        except ValueError:
            return {"ok": False, "error": f"unparseable tool output: {text[:120]}"}
        return parsed if isinstance(parsed, dict) else {"ok": True, "result": parsed}

    # ----- what the model sees -----
    def llm_specs(self, names: set[str]) -> list[dict[str, Any]]:
        specs = []
        for n in sorted(names & MODEL_FACING & set(self._tools)):   # the router enforces this, not its callers
            t = self._tools[n]
            schema = json.loads(json.dumps(t.inputSchema or {}))
            props = {k: v for k, v in schema.get("properties", {}).items() if k not in HIDDEN_PARAMS}
            for v in props.values():
                v.pop("title", None)
            if n == "list_directory" and "path" in props:
                props["path"]["description"] = f"Use exactly: {self.learner_docs_dir}"
            if n == "read_text_file" and "path" in props:
                props["path"]["description"] = f"A .md file inside {self.learner_docs_dir}"
            desc = " ".join((t.description or "").split())[:220]
            specs.append({"type": "function", "function": {
                "name": n, "description": desc,
                "parameters": {"type": "object", "properties": props,
                               "required": [r for r in schema.get("required", []) if r in props]}}})
        return specs

    def check_llm_call(self, name: str, args: Any, *, allowed: set[str], pattern_ids: list[str],
                       subjects: list[str]) -> tuple[dict[str, Any] | None, str | None]:
        """Validate a model-proposed call. Returns (clean_args, None) or (None, reason)."""
        if name not in allowed or name not in MODEL_FACING:
            return None, f"'{name}' is not an available tool. Available: {', '.join(sorted(allowed & MODEL_FACING))}"
        if not isinstance(args, dict):
            return None, "arguments must be an object"
        if name == "get_evidence":
            pid = args.get("pattern_id")
            if pid not in pattern_ids:
                return None, f"unknown pattern_id. Valid ids: {', '.join(pattern_ids)}"
            try:
                n = max(1, min(int(args.get("max_records", 12)), 50))
            except (TypeError, ValueError):
                n = 12
            return {"pattern_id": pid, "max_records": n}, None
        if name == "detect_patterns":
            subj = args.get("subject")
            if subj in (None, ""):
                return {}, None
            match = next((s for s in subjects if isinstance(subj, str) and s.lower() == subj.lower()), None)
            return ({"subject": match}, None) if match else (None, f"unknown subject. Valid: {', '.join(subjects)}")
        try:
            if name == "list_directory":
                return {"path": self.check_doc_path(args.get("path") or self.learner_docs_dir, directory=True)}, None
            if name == "read_text_file":
                return {"path": self.check_doc_path(args.get("path"))}, None
        except ToolError as exc:
            return None, str(exc)
        return None, f"unsupported tool: {name}"


@asynccontextmanager
async def open_router(run_id: str, learner_id: str, *, learner_url: str | None = None, docs_dir: str | None = None,
                      docs_command: str | None = None, docs_args: str | None = None) -> AsyncIterator[ToolRouter]:
    """Connect to our MCP server (streamable HTTP) and, if it can start, the external filesystem server (stdio)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    url = learner_url or settings.learner_mcp_url
    root = docs_dir or settings.docs_dir
    cmd = docs_command or settings.docs_mcp_command
    extra = shlex.split(docs_args if docs_args is not None else settings.docs_mcp_args)
    async with AsyncExitStack() as stack:
        read, write, *_ = await stack.enter_async_context(streamablehttp_client(url))
        ours = await stack.enter_async_context(ClientSession(read, write))
        await ours.initialize()
        ext_stack, external, ext_error = AsyncExitStack(), None, None
        try:
            r, w = await ext_stack.enter_async_context(stdio_client(StdioServerParameters(command=cmd, args=[*extra, root])))
            external = await ext_stack.enter_async_context(ClientSession(r, w))
            await external.initialize()
        except Exception as exc:  # noqa: BLE001  the run continues without documents
            ext_error = f"{type(exc).__name__}: {exc}"
            log.warning("external documents server unavailable: %s", ext_error)
            external = None
            try:
                await ext_stack.aclose()
            except Exception:  # noqa: BLE001
                pass
        try:
            router = ToolRouter(ours, external, run_id=run_id, learner_id=learner_id, docs_root=root)
            router.external_error = ext_error
            yield await router.load()
        finally:
            await ext_stack.aclose()
