"""Does the configured model work as the agent needs it to? Run on your machine: make check-agent-llm

Three checks, each mirroring one thing the agent asks of the model:
  1. choose a tool call from a STILL NEEDED list
  2. after a tool result, stop (no further tool call) when nothing is left
  3. write a summary from a fact sheet that passes the verifier (citations, no labels, no invented numbers)
A failing check is not fatal: the agent has a deterministic fallback for each. It tells you how often
you will see that fallback (the run's `fallbacks` list records every use).
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Callable

from app.agent import summary as summ
from app.agent.graph import INVESTIGATE_SYSTEM
from app.agent.llm import LLM, LLMError, get_llm

PID = "PAT-AB12CD34"
SPEC = [{"type": "function", "function": {
    "name": "get_evidence", "description": "Get the records and teacher notes behind a finding.",
    "parameters": {"type": "object", "properties": {"pattern_id": {"type": "string"}}, "required": ["pattern_id"]}}}]
FACTS = summ.Facts(
    text=("LEARNER: Test Learner (L0)\nTEACHER REQUEST: Look at English\nSUBJECT FOCUS: English\n"
          "DATA: 88 records over 11 terms (2023-T1 to 2026-T2); duplicates removed: 0; blank scores: 2; terms with no data inside the span: none.\n"
          f"[{PID}] kind=decline | English reading comprehension | evidence=high | terms=11\n"
          "  STATEMENT: English reading comprehension declined over 11 terms: term averages fell from about 70% to about 52% (-2.1 points per term).\n"
          "  RECORDS (33 in total, sample): R12 (2023-T1 quiz 71%), R99 (2026-T2 quiz 48%)\n"
          "  OBSERVATIONS: O5 (2025-T3, concern, T-017): \"Reading tasks now take most of the lesson.\"\n"
          "  REVIEW: sent to the teacher; waiting for their decision; nothing written to the profile"),
    allowed_ids={PID, "R12", "R99", "O5"}, pattern_ids=[PID])


async def check(llm: LLM, out: Callable[[str], None] = print) -> bool:
    ok = True

    def verdict(name: str, passed: bool, detail: str, secs: float) -> None:
        nonlocal ok
        ok = ok and passed
        out(f"{'PASS' if passed else 'FAIL'}  {name} ({secs:.0f}s)  {detail}")

    user = (f"Teacher request: Look at English\nLearner: Test Learner. Subject focus: English.\nCandidate findings (not conclusions):\n"
            f"- {PID} [decline, English/reading_comprehension, evidence high]: reading comprehension fell\nSTILL NEEDED:\n"
            f'- get_evidence(pattern_id="{PID}")')
    msgs = [{"role": "system", "content": INVESTIGATE_SYSTEM}, {"role": "user", "content": user}]
    try:
        r1 = await llm.chat(msgs, tools=SPEC)
        c = r1.tool_calls[0] if r1.tool_calls else None
        verdict("1 chooses the right tool call", bool(c and c.name == "get_evidence" and c.arguments.get("pattern_id") == PID),
                json.dumps({"name": c.name, "arguments": c.arguments}) if c else f"no tool call; said: {r1.content[:80]!r}", r1.seconds)

        msgs += [{"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "get_evidence", "arguments": {"pattern_id": PID}}]},
                 {"role": "tool", "tool_call_id": "c1", "name": "get_evidence",
                  "content": '{"ok":true,"records_total":33}\nNothing is left to retrieve. Reply DONE.'}]
        r2 = await llm.chat(msgs, tools=SPEC)
        verdict("2 stops when nothing is left", not r2.tool_calls, f"said: {r2.content[:60]!r}" if not r2.tool_calls
                else f"called {r2.tool_calls[0].name} again", r2.seconds)

        r3 = await llm.chat([{"role": "system", "content": summ.SYSTEM_PROMPT}, {"role": "user", "content": FACTS.text}], max_tokens=500)
        bad = summ.verify(r3.content, FACTS)
        verdict("3 writes a summary that passes the verifier", not bad, "; ".join(bad) if bad else "clean", r3.seconds)
        out(f"      draft: {r3.content.strip()[:400]}")
    except LLMError as exc:
        out(f"FAIL  model unreachable: {exc}")
        return False
    return ok


async def _main() -> int:
    llm = get_llm()
    print(f"checking {llm.provider}/{llm.model} (the first call may be slow while the model loads)\n")
    t0 = time.monotonic()
    good = await check(llm)
    print(f"\n{'all checks passed' if good else 'some checks failed; the agent will use its fallbacks for those steps'} "
          f"({time.monotonic() - t0:.0f}s)")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
