import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Check, ClipboardCheck, FileText, Loader2, MessageCircleQuestion, RefreshCw, X,
} from "lucide-react";
import { api, post } from "../api/client";
import Sidebar from "../components/Sidebar";
import type { Decision, ReviewDetail, ReviewListItem } from "../types";

const TEACHER_ID = "MK"; // demo has no login; the sidebar teacher is Mr. Kamau

function ReviewCard({ review, onOpen }: { review: ReviewListItem; onOpen: () => void }) {
  const p = review.pattern;
  return (
    <button type="button" className="review-card" onClick={onOpen}>
      <div className="review-card-top">
        <span className={`review-badge ${p.evidence_strength}`}>{p.evidence_strength}</span>
        <span className="review-learner">{review.learner.full_name} · {review.learner.id}</span>
        <span className="review-date">{review.created_at ? new Date(review.created_at).toLocaleDateString() : ""}</span>
      </div>
      <p className="review-statement">{p.statement}</p>
      <div className="review-meta">
        <span>{p.kind}{p.subtype ? ` · ${p.subtype}` : ""}</span>
        {p.subject && <span>{p.subject}{p.skill ? ` · ${p.skill.replace(/_/g, " ")}` : ""}</span>}
        <span>{p.n_terms} terms</span>
        <span className={`review-status ${review.status}`}>{review.status.replace("_", " ")}</span>
      </div>
    </button>
  );
}

function EvidenceList({ records, observations }: { records: NonNullable<ReviewDetail["evidence"]["records"]>; observations: NonNullable<ReviewDetail["evidence"]["observations"]> }) {
  return (
    <div className="evidence-columns">
      <section>
        <h4>Records <span>{records.length}</span></h4>
        <div className="evidence-scroll">
          <table>
            <thead><tr><th>Term</th><th>Type</th><th>Title</th><th>Score</th></tr></thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.record_id}>
                  <td>{r.term}</td>
                  <td>{r.kind}</td>
                  <td>{r.title ?? "—"}</td>
                  <td>{r.pct === null ? "—" : `${r.pct}%`}{r.late ? " (late)" : ""}</td>
                </tr>
              ))}
              {!records.length && <tr><td colSpan={4}>No records cited.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h4>Teacher notes <span>{observations.length}</span></h4>
        <div className="evidence-scroll">
          {observations.map((o, i) => (
            <div className="evidence-note" key={i}>
              <span>{String(o.term ?? "")}</span>
              <p>{String(o.text ?? "")}</p>
            </div>
          ))}
          {!observations.length && <p className="sample-note">No notes cited.</p>}
        </div>
      </section>
    </div>
  );
}

export default function ReviewsPage() {
  const { reviewId } = useParams();
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState("pending");
  const [reviews, setReviews] = useState<ReviewListItem[]>([]);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(() => {
    api<ReviewListItem[]>(`/reviews?status=${statusFilter}`).then(setReviews).catch((e) => setError(String(e.message ?? e)));
  }, [statusFilter]);

  useEffect(() => { loadList(); }, [loadList]);

  useEffect(() => {
    if (reviewId) {
      api<ReviewDetail>(`/reviews/${reviewId}`).then(setDetail).catch((e) => setError(String(e.message ?? e)));
    } else {
      setDetail(null);
      setComment("");
    }
  }, [reviewId]);

  const decide = async (decision: Decision) => {
    if (!detail) return;
    setBusy(decision);
    setError(null);
    try {
      await post(`/reviews/${detail.review_id}/decision`, { teacher_id: TEACHER_ID, decision, comment: comment.trim() || null });
      setDetail(null);
      navigate("/reviews");
      loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content reviews-main">
        {detail ? (
          <>
            <button className="back-link" onClick={() => navigate("/reviews")}>
              <ArrowLeft size={18} /> Back to reviews
            </button>
            <div className="review-detail-head">
              <p className="eyebrow">TEACHER REVIEW</p>
              <h1>{detail.learner.full_name} · {detail.learner.id}</h1>
              <p>{detail.reason}</p>
              <div className="review-meta">
                <span className={`review-badge ${detail.pattern.evidence_strength}`}>{detail.pattern.evidence_strength} evidence</span>
                <span>{detail.pattern.kind}{detail.pattern.subtype ? ` · ${detail.pattern.subtype}` : ""}</span>
                <span>{detail.pattern.n_terms} terms</span>
                {detail.run_id && <span>run {detail.run_id}</span>}
              </div>
            </div>

            <div className="review-detail-grid">
              <section className="panel">
                <div className="panel-heading">
                  <div><h2>The finding</h2><p>What the agent proposes — not yet written to any profile</p></div>
                  <FileText size={18} className="heading-icon" />
                </div>
                <p className="result-summary">{detail.pattern.statement}</p>
                {detail.decisions.length > 0 && (
                  <div className="decision-history">
                    <h3>Decision history</h3>
                    {detail.decisions.map((d) => (
                      <p key={d.approval_id}>
                        <strong>{d.decision}</strong> by {d.teacher_id} · {d.decided_at ? new Date(d.decided_at).toLocaleString() : ""}
                        {d.comment ? ` — “${d.comment}”` : ""}
                      </p>
                    ))}
                  </div>
                )}
                <div className="decision-actions">
                  <label htmlFor="decision-comment">Comment <span>Optional</span>
                    <textarea id="decision-comment" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500}
                      placeholder="Context for the decision…" disabled={detail.status !== "pending"} />
                  </label>
                  <div className="decision-buttons">
                    <button className="decision approve" disabled={detail.status !== "pending" || busy !== null} onClick={() => decide("approved")}>
                      {busy === "approved" ? <Loader2 className="spin" size={14} /> : <Check size={14} />} Approve
                    </button>
                    <button className="decision reject" disabled={detail.status !== "pending" || busy !== null} onClick={() => decide("rejected")}>
                      {busy === "rejected" ? <Loader2 className="spin" size={14} /> : <X size={14} />} Reject
                    </button>
                    <button className="decision more" disabled={detail.status !== "pending" || busy !== null} onClick={() => decide("more_evidence")}>
                      {busy === "more_evidence" ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />} More evidence
                    </button>
                  </div>
                </div>
              </section>

              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Evidence</h2>
                    <p>The exact records and notes behind the finding — unredacted for review</p>
                  </div>
                  <ClipboardCheck size={18} className="heading-icon" />
                </div>
                <EvidenceList records={detail.evidence.records ?? []} observations={detail.evidence.observations ?? []} />
              </section>
            </div>
          </>
        ) : (
          <>
            <header className="reviews-header">
              <div>
                <p className="eyebrow">TEACHER REVIEWS</p>
                <h1>Findings waiting on you</h1>
                <p>Approve to write a finding to the learner&apos;s profile, reject to close it, or send it back for more evidence.</p>
              </div>
              <label className="directory-filter">
                <span className="sr-only">Filter by status</span>
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                  {["pending", "approved", "rejected", "more_evidence", "all"].map((s) => (
                    <option key={s} value={s}>{s === "more_evidence" ? "More evidence" : s[0].toUpperCase() + s.slice(1)}</option>
                  ))}
                </select>
              </label>
            </header>
            {error && <div className="ask-banner error" role="alert">{error}</div>}
            <div className="review-list">
              {reviews.map((r) => (
                <ReviewCard key={r.review_id} review={r} onOpen={() => navigate(`/reviews/${r.review_id}`)} />
              ))}
              {!reviews.length && !error && (
                <div className="placeholder-panel">
                  <div className="placeholder-icon"><ClipboardCheck /></div>
                  <h2>Nothing here</h2>
                  <p>{statusFilter === "pending" ? "No findings are waiting for a decision. Run “Ask the AI” on a learner to surface one." : `No reviews with status “${statusFilter}”.`}</p>
                  <button className="primary-button" onClick={() => navigate("/students")}>Go to Students</button>
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
