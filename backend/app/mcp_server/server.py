"""learner-intelligence-mcp: our MCP server. Run: python -m app.mcp_server.server"""
from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.mcp_server.audit import audited
from app.mcp_server.tools import (
    detect_patterns as _detect,
    flag_for_teacher_review as _flag,
    get_evidence as _evidence,
    get_learner_timeline as _timeline,
    update_learner_profile as _update,
)

mcp = FastMCP("learner-intelligence", host=settings.mcp_host, port=settings.mcp_port)


@mcp.tool()
@audited("get_learner_timeline")
def get_learner_timeline(learner_id: str, subject: str | None = None, run_id: str | None = None) -> dict:
    """Get a learner's term-ordered records and teacher observations."""
    return _timeline.get_learner_timeline(learner_id, subject)


@mcp.tool()
@audited("detect_patterns")
def detect_patterns(learner_id: str, subject: str | None = None, run_id: str | None = None) -> dict:
    """Detect evidence-backed patterns across terms (deterministic; may return 'insufficient data')."""
    return _detect.detect_patterns(learner_id, subject)


@mcp.tool()
@audited("get_evidence")
def get_evidence(pattern_id: str, run_id: str | None = None) -> dict:
    """Get the underlying evidence for a detected pattern."""
    return _evidence.get_evidence(pattern_id)


@mcp.tool()
@audited("flag_for_teacher_review")
def flag_for_teacher_review(learner_id: str, pattern_id: str, reason: str, run_id: str | None = None) -> dict:
    """Send a pattern to the teacher for review."""
    return _flag.flag_for_teacher_review(learner_id, pattern_id, reason)


@mcp.tool()
@audited("update_learner_profile", approval_required=True)
def update_learner_profile(learner_id: str, pattern_id: str, summary: str,
                           approval_id: str | None = None, run_id: str | None = None) -> dict:
    """Update the learner profile. Requires a valid teacher approval_id."""
    return _update.update_learner_profile(learner_id, pattern_id, summary, approval_id)


if __name__ == "__main__":
    mcp.run(transport=settings.mcp_transport)
