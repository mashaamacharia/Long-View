"""Smoke test: can the configured Ollama model emit a valid tool call? Run: make check-llm"""
import json
import sys
import time

import httpx

from app.config import settings

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_learner_timeline",
        "description": "Get a learner's records across terms",
        "parameters": {
            "type": "object",
            "properties": {
                "learner_id": {"type": "string"},
                "subject": {"type": "string"},
            },
            "required": ["learner_id"],
        },
    },
}]


def main() -> int:
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "tools": TOOLS,
        "messages": [{"role": "user", "content": "Show me the timeline for learner L1042 in mathematics."}],
        "options": {"num_ctx": 8192, "temperature": 0.2},
    }
    t0 = time.time()
    r = httpx.post(f"{settings.ollama_base_url}/api/chat", json=payload, timeout=600)
    r.raise_for_status()
    msg = r.json()["message"]
    calls = msg.get("tool_calls") or []
    print(f"model={settings.ollama_model} latency={time.time() - t0:.1f}s")
    if not calls:
        print("FAIL: no tool call produced. Content:", msg.get("content"))
        return 1
    print("tool call:", json.dumps(calls[0], indent=2))
    args = calls[0]["function"]["arguments"]
    ok = calls[0]["function"]["name"] == "get_learner_timeline" and args.get("learner_id") == "L1042"
    print("PASS" if ok else "FAIL: wrong tool/arguments")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
