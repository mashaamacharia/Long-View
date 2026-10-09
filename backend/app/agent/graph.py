"""LangGraph skeleton. Nodes are stubs; wire in MCP tool calls + the LLM provider.

Flow: understand -> timeline -> patterns -> evidence -> sufficiency
      sufficiency --insufficient--> gather more evidence (loop, capped) / write "insufficient" summary
      sufficiency --sufficient----> teacher_review (interrupt) -> approved: update_profile -> summary
                                                              -> rejected: summary
                                                              -> more_evidence: back to evidence
"""
from langgraph.graph import END, StateGraph

from app.agent.state import AgentState

MAX_LOOPS = 2


def understand_request(state: AgentState) -> AgentState:
    return state


def fetch_timeline(state: AgentState) -> AgentState:
    return state  # TODO: MCP get_learner_timeline


def detect_patterns(state: AgentState) -> AgentState:
    return state  # TODO: MCP detect_patterns


def gather_evidence(state: AgentState) -> AgentState:
    return {**state, "loops": state.get("loops", 0) + 1}  # TODO: MCP get_evidence (+ external docs MCP)


def check_sufficiency(state: AgentState) -> AgentState:
    return {**state, "sufficient": state.get("sufficient", False)}


def teacher_review(state: AgentState) -> AgentState:
    return state  # TODO: flag_for_teacher_review + interrupt until the teacher decides


def update_profile(state: AgentState) -> AgentState:
    return state  # TODO: MCP update_learner_profile(approval_id=...)


def write_summary(state: AgentState) -> AgentState:
    return state  # TODO: LLM writes teacher-readable summary with evidence citations


def after_sufficiency(state: AgentState) -> str:
    if state.get("sufficient"):
        return "teacher_review"
    return "gather_evidence" if state.get("loops", 0) < MAX_LOOPS else "write_summary"


def after_review(state: AgentState) -> str:
    return {"approved": "update_profile", "more_evidence": "gather_evidence"}.get(
        state.get("decision") or "", "write_summary"
    )


def build_graph():
    g = StateGraph(AgentState)
    for name, fn in [
        ("understand_request", understand_request), ("fetch_timeline", fetch_timeline),
        ("detect_patterns", detect_patterns), ("gather_evidence", gather_evidence),
        ("check_sufficiency", check_sufficiency), ("teacher_review", teacher_review),
        ("update_profile", update_profile), ("write_summary", write_summary),
    ]:
        g.add_node(name, fn)

    g.set_entry_point("understand_request")
    g.add_edge("understand_request", "fetch_timeline")
    g.add_edge("fetch_timeline", "detect_patterns")
    g.add_edge("detect_patterns", "gather_evidence")
    g.add_edge("gather_evidence", "check_sufficiency")
    g.add_conditional_edges("check_sufficiency", after_sufficiency)
    g.add_conditional_edges("teacher_review", after_review)
    g.add_edge("update_profile", "write_summary")
    g.add_edge("write_summary", END)
    return g.compile()  # TODO: add checkpointer + interrupt_before=["teacher_review"]
