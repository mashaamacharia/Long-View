import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Brain, Check, CircleAlert, Loader2, Send, Square, TriangleAlert, Wrench, ClipboardCheck, FileText,
} from "lucide-react";
import { api, followRun, post } from "../api/client";
import Sidebar from "../components/Sidebar";
import type { AgentEvent, Learner, RunSummary } from "../types";

const KIND_STYLE: Record<string, { icon: typeof Brain; tone: string }> = {
  node: { icon: Brain, tone: "node" },
  llm: { icon: Brain, tone: "llm" },
  tool: { icon: Wrench, tone: "tool" },
  forced: { icon: Square, tone: "forced" },
  rejected: { icon: TriangleAlert, tone: "rejected" },
  interrupt: { icon: ClipboardCheck, tone: "interrupt" },
  resume: { icon: ArrowLeft, tone: "resume" },
  error: { icon: CircleAlert, tone: "error" },
  final: { icon: Check, tone: "final" },
};

export default function AskPage() {
  const { learnerId = "" } = useParams();
  const navigate = useNavigate();
  const [learner, setLearner] = useState<Learner | null>(null);
  const [request, setRequest] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [state, setState] = useState<string>("idle");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [result, setResult] = useState<RunSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeStream = useRef<(() => void) | null>(null);
  const pollTimer = useRef<number | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api<Learner>(`/learners/${learnerId}`).then(setLearner).catch(() => {});
    return () => {
      closeStream.current?.();
      if (pollTimer.current) window.clearInterval(pollTimer.current);
    };
  }, [learnerId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [events.length]);

  const finish = async (id: string) => {
    closeStream.current?.();
    if (pollTimer.current) window.clearInterval(pollTimer.current);
    closeStream.current = null;
    pollTimer.current = null;
    try {
      const run = await api<RunSummary>(`/runs/${id}`);
      setResult(run);
      setState(run.state);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState("failed");
    }
  };

  const start = async () => {
    const trimmed = request.trim();
    if (trimmed.length < 3 || !learnerId) return;
    setError(null);
    setResult(null);
    setEvents([]);
    setState("queued");
    try {
      const started = await post<{ run_id: string; state: string }>("/runs", { learner_id: learnerId, request: trimmed });
      setRunId(started.run_id);
      setState(started.state);
      closeStream.current = followRun(started.run_id, {
        onEvent: (e) => setEvents((current) => (current.some((x) => x.seq === e.seq) ? current : [...current, e])),
        onEnd: () => finish(started.run_id),
        onError: (m) => { setError(m); finish(started.run_id); },
      });
      // The stream stays open while a run waits for a teacher; poll to surface that state.
      pollTimer.current = window.setInterval(async () => {
        try {
          const run = await api<RunSummary>(`/runs/${started.run_id}`);
          setState(run.state);
        } catch { /* transient */ }
      }, 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState("failed");
    }
  };

  const streaming = ["queued", "running"].includes(state);
  const waiting = state === "waiting_for_teacher";

  return (
    <div className="app-shell">
      <Sidebar learnerId={learnerId} />
      <main className="main-content ask-main">
        <button className="back-link" onClick={() => navigate(`/students/${learnerId}`)}>
          <ArrowLeft size={18} /> Back to {learner?.full_name ?? "profile"}
        </button>
        <div className="ask-header">
          <p className="eyebrow">ASK THE AI</p>
          <h1>What would you like to understand about {learner?.full_name ?? "this learner"}?</h1>
          <p>Runs the evidence-driven agent over the learner&apos;s records, notes and documents. Every finding stays a proposal until you approve it.</p>
        </div>

        <form className="ask-composer" onSubmit={(e) => { e.preventDefault(); start(); }}>
          <textarea
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            rows={3}
            placeholder="e.g. Look at Amina's mathematics results over the last three terms — is anything drifting?"
            disabled={streaming || waiting}
          />
          <button type="submit" className="ask-submit" disabled={streaming || waiting || request.trim().length < 3}>
            {streaming ? <Loader2 className="spin" size={15} /> : <Send size={15} />}
            {streaming ? "Working…" : waiting ? "Waiting for review" : "Run analysis"}
          </button>
        </form>

        {error && <div className="ask-banner error" role="alert"><CircleAlert size={15} /> {error}</div>}
        {waiting && (
          <div className="ask-banner waiting" role="status">
            <ClipboardCheck size={15} />
            <span>The agent paused for your decision on a proposed finding.</span>
            <button onClick={() => navigate("/reviews")}>Open Reviews</button>
          </div>
        )}
        {state === "completed" && result && (
          <div className="ask-banner ok" role="status"><Check size={15} /> Run completed{result.review_ids?.length ? ` · ${result.review_ids.length} finding(s) awaiting review` : ""}</div>
        )}

        {events.length > 0 && (
          <section className="panel stream-panel" aria-label="Run progress">
            <div className="panel-heading">
              <div>
                <h2>{streaming ? "Working…" : "What the agent did"}</h2>
                <p>{events.length} step{events.length === 1 ? "" : "s"}{runId ? ` · ${runId}` : ""}</p>
              </div>
            </div>
            <ol className="stream-list">
              {events.map((e) => {
                const style = KIND_STYLE[e.kind] ?? KIND_STYLE.node;
                const Icon = style.icon;
                return (
                  <li key={e.seq} className={`stream-item ${style.tone}`}>
                    <span className="stream-icon"><Icon size={13} /></span>
                    <div>
                      <strong>{e.title}</strong>
                      {e.detail && typeof e.detail.tool === "string" && (
                        <code className="stream-tool">{e.detail.tool}</code>
                      )}
                      {typeof e.detail?.note === "string" && <p>{e.detail.note}</p>}
                    </div>
                  </li>
                );
              })}
            </ol>
            <div ref={bottomRef} />
          </section>
        )}

        {result?.result && (
          <section className="panel result-panel" aria-label="Run result">
            {result.result.error ? (
              <div className="ask-banner error"><CircleAlert size={15} /> {result.result.error}</div>
            ) : (
              <>
                <div className="panel-heading">
                  <div>
                    <h2>Summary</h2>
                    <p>
                      {result.result.llm?.available === false
                        ? "Deterministic analysis (no model call)"
                        : `${result.result.llm?.provider ?? ""}/${result.result.llm?.model ?? ""} · ${result.result.llm?.calls ?? 0} model call(s)`}
                    </p>
                  </div>
                  <FileText size={18} className="heading-icon" />
                </div>
                <p className="result-summary">{result.result.summary}</p>

                {!!result.result.findings?.length && (
                  <div className="result-block">
                    <h3>Proposed findings</h3>
                    {result.result.findings!.map((f, i) => (
                      <div className="result-finding" key={f.pattern_id ?? i}>
                        <p>{f.statement ?? JSON.stringify(f)}</p>
                        {f.pattern_id && <code>{f.pattern_id}</code>}
                      </div>
                    ))}
                  </div>
                )}

                {!!result.result.fallbacks?.length && (
                  <div className="result-block">
                    <h3>Fallbacks used</h3>
                    <ul className="result-fallbacks">
                      {result.result.fallbacks!.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </div>
                )}
              </>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
