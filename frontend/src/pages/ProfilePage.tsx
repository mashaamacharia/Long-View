import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, BookOpen, Check, ChevronRight, CircleHelp, FilePlus2,
  HelpCircle, Lightbulb, Sparkles, Star, TrendingUp, TriangleAlert, Users, X,
} from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import Sidebar from "../components/Sidebar";
import RecordModal from "../components/RecordModal";
import type { Learner, LearnerRecord, Observation, PatternSummary, ProfileEntry, RecordsFeed } from "../types";

const pct = (r: LearnerRecord): number | null =>
  r.score === null ? null : r.max_score && r.max_score !== 100 ? (r.score / r.max_score) * 100 : r.score;
const yearOf = (r: LearnerRecord) => r.term.slice(0, 4);
const initialsOf = (name: string) => name.split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

function yearlyAverages(records: LearnerRecord[], filter?: (r: LearnerRecord) => boolean) {
  const buckets = new Map<string, number[]>();
  for (const r of records) {
    if (filter && !filter(r)) continue;
    const p = pct(r);
    if (p === null) continue;
    const y = yearOf(r);
    buckets.set(y, [...(buckets.get(y) ?? []), p]);
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([year, scores]) => ({ year, score: Math.round(scores.reduce((s, v) => s + v, 0) / scores.length) }));
}

const HIGHLIGHTS = [
  { icon: Star, tone: "green" },
  { icon: TriangleAlert, tone: "amber" },
  { icon: TrendingUp, tone: "purple" },
  { icon: Lightbulb, tone: "blue" },
];

function KeyHighlights({ entries, learnerName }: { entries: ProfileEntry[]; learnerName: string }) {
  return (
    <section className="panel highlights-panel">
      <div className="panel-heading">
        <div>
          <h2>Key Highlights</h2>
          <p>Teacher-approved findings from {learnerName}&apos;s learning journey</p>
        </div>
        <Sparkles size={18} className="heading-icon" />
      </div>
      {entries.length ? (
        <div className="highlight-list">
          {entries.map((entry, i) => {
            const meta = HIGHLIGHTS[i % HIGHLIGHTS.length];
            const Icon = meta.icon;
            return (
              <div className={`highlight-card ${meta.tone === "blue" ? "purple" : meta.tone}`} key={entry.change_id}>
                <div className="highlight-icon"><Icon size={18} /></div>
                <div>
                  <h3>{entry.pattern.subject ? `${entry.pattern.subject}${entry.pattern.skill ? ` · ${entry.pattern.skill.replace(/_/g, " ")}` : ""}` : entry.pattern.kind}</h3>
                  <p>{entry.summary}</p>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="highlight-list">
          <div className="highlight-card purple">
            <div className="highlight-icon"><Sparkles size={18} /></div>
            <div>
              <h3>No approved findings yet</h3>
              <p>When an agent run surfaces a pattern and a teacher approves it in Reviews, it appears here.</p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function PerformanceOverTime({ records }: { records: LearnerRecord[] }) {
  const yearly = useMemo(() => yearlyAverages(records), [records]);
  const latest = yearly[yearly.length - 1];
  const first = yearly[0];
  const change = latest && first && yearly.length > 1 ? latest.score - first.score : null;
  return (
    <section className="panel performance-panel">
      <div className="panel-heading performance-heading">
        <div>
          <h2>Performance Over Time</h2>
          <p>Average score across recorded academic years</p>
        </div>
      </div>
      {latest ? (
        <>
          <div className="sample-summary">
            <div><span>Latest recorded average</span><strong>{latest.score}%</strong></div>
            {change !== null && (
              <div className="summary-change">
                <Check size={14} /> {change >= 0 ? "+" : ""}{change} percentage points <small>since {first.year}</small>
              </div>
            )}
          </div>
          <div className="chart-wrap" aria-label={`Line chart showing average scores from ${first.year} to ${latest.year}`}>
            <ResponsiveContainer width="100%" height={196}>
              <LineChart data={yearly} margin={{ top: 12, right: 8, left: -24, bottom: 0 }}>
                <CartesianGrid stroke="#E8EEF5" vertical={false} />
                <XAxis dataKey="year" axisLine={false} tickLine={false} tick={{ fill: "#718096", fontSize: 11 }} />
                <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} axisLine={false} tickLine={false} tick={{ fill: "#718096", fontSize: 10 }} tickFormatter={(v) => `${v}%`} />
                <Tooltip contentStyle={{ border: "1px solid #E2EAF3", borderRadius: 8, boxShadow: "0 4px 14px rgba(16,43,78,.08)", fontSize: 12 }} formatter={(v) => [`${v}%`, "Average score"]} labelFormatter={(l) => `Academic year ${l}`} />
                <Line type="monotone" dataKey="score" stroke="#2878E5" strokeWidth={2.5} dot={{ r: 4, fill: "#fff", stroke: "#2878E5", strokeWidth: 2 }} activeDot={{ r: 5, fill: "#2878E5", stroke: "#fff", strokeWidth: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <p className="sample-note">No scored records yet for this learner.</p>
      )}
    </section>
  );
}

function QuickActions({ learnerId, onUpdate }: { learnerId: string; onUpdate: () => void }) {
  const navigate = useNavigate();
  const actions = [
    { title: "Update Student Record", description: "Add an assessment result or teacher observation.", button: "Add Record", icon: FilePlus2, action: onUpdate },
    { title: "Ask the AI", description: "Explore strengths, difficulties, and progress using the learner's history.", button: "Ask a Question", icon: HelpCircle, action: () => navigate(`/students/${learnerId}/ask`) },
  ];
  return (
    <section className="panel quick-panel">
      <div className="panel-heading"><div><h2>Quick Actions</h2><p>Continue building this learner&apos;s fuller picture</p></div></div>
      <div className="action-list">
        {actions.map(({ title, description, button, icon: Icon, action }) => (
          <div className="action-item" key={title}>
            <div className="action-icon"><Icon size={18} /></div>
            <div className="action-copy">
              <h3>{title}</h3>
              <p>{description}</p>
              <button onClick={action}>{button}<ArrowLeft size={14} className="arrow-right" /></button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SubjectSparkline({ points }: { points: { year: string; score: number }[] }) {
  const path = points
    .map((p, i) => {
      const x = 34 + i * 86;
      const y = 58 - p.score * 0.42;
      return `${i === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
  return (
    <svg className="subject-sparkline" viewBox="0 0 206 78" role="img" aria-label={`Yearly averages: ${points.map((p) => `${p.year} ${p.score}%`).join(", ")}`}>
      <line x1="34" y1="8" x2="34" y2="66" className="sparkline-guide" />
      <line x1="120" y1="8" x2="120" y2="66" className="sparkline-guide" />
      <line x1="206" y1="8" x2="206" y2="66" className="sparkline-guide" />
      {path && <path d={path} className="sparkline-path" />}
      {points.map((p, i) => {
        const x = 34 + i * 86;
        const y = 58 - p.score * 0.42;
        return (
          <g key={p.year}>
            <text x={x} y={Math.max(10, y - 8)} textAnchor="middle" className="sparkline-label">{p.score}%</text>
            <circle cx={x} cy={y} r="3.5" className="sparkline-dot" />
          </g>
        );
      })}
    </svg>
  );
}

const subjectIcons: Record<string, typeof BookOpen> = {
  Mathematics: Users, English: BookOpen, Science: Lightbulb,
};

function SubjectDetailModal({
  subject, records, observations, onClose,
}: {
  subject: string;
  records: LearnerRecord[];
  observations: Observation[];
  onClose: () => void;
}) {
  const subjectRecords = records.filter((r) => r.subject === subject);
  const yearly = yearlyAverages(subjectRecords);
  const years = yearly.map((y) => y.year).reverse();
  const [year, setYear] = useState(years[0] ?? "");
  const Icon = subjectIcons[subject] ?? BookOpen;
  const yearRecords = subjectRecords.filter((r) => yearOf(r) === year);
  const average = yearly.find((y) => y.year === year)?.score ?? null;

  const termScores = ["1", "2", "3"]
    .map((t) => {
      const inTerm = yearRecords.filter((r) => r.term.endsWith(`-T${t}`));
      const scores = inTerm.map(pct).filter((p): p is number => p !== null);
      return scores.length ? { term: `Term ${t}`, score: Math.round(scores.reduce((s, v) => s + v, 0) / scores.length), n: scores.length } : null;
    })
    .filter((x): x is { term: string; score: number; n: number } => x !== null);
  const improvement = termScores.length > 1 ? termScores[termScores.length - 1].score - termScores[0].score : null;
  const yearTerms = new Set(yearRecords.map((r) => r.term));
  const yearObservations = observations.filter((o) => o.subject === subject && yearTerms.has(o.term));

  return (
    <div className="subject-modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <section className="subject-modal" role="dialog" aria-modal="true" aria-labelledby="subject-modal-title">
        <header className="subject-modal-header">
          <div>
            <button className="modal-back-link" onClick={onClose}><ArrowLeft data-icon="inline-start" /> Back to profile</button>
            <div className="modal-subject-identity">
              <div className="modal-subject-icon"><Icon /></div>
              <div>
                <h2 id="subject-modal-title">{subject}</h2>
                <p>Performance and insights for this subject</p>
              </div>
            </div>
          </div>
          <div className="modal-header-actions">
            <label>Academic Year
              <select value={year} onChange={(e) => setYear(e.target.value)}>
                {years.map((y) => <option key={y}>{y}</option>)}
              </select>
            </label>
            <button className="modal-close" aria-label="Close subject details" onClick={onClose}><X /></button>
          </div>
        </header>
        <div className="subject-summary-card">
          <div className="score-gauge-wrap">
            <div className="score-gauge" style={{ "--score-angle": `${(average ?? 0) * 3.6}deg` } as React.CSSProperties}>
              <strong>{average === null ? "—" : `${average}%`}</strong>
            </div>
            <div><b>Average Score</b><span>Selected academic year</span></div>
          </div>
          <div className="improvement-stat">
            <span className={improvement !== null && improvement >= 0 ? "positive" : "neutral"}>
              {improvement === null ? "—" : `${improvement >= 0 ? "↑ +" : "↓ "}${Math.abs(improvement)}%`}
            </span>
            <b>{improvement === null ? "Not enough term data" : "Change across terms"}</b>
          </div>
          <div className="term-chart">
            <div className="chart-title">Term performance</div>
            {termScores.length ? (
              <table className="term-table">
                <thead><tr><th>Term</th><th>Average</th><th>Records</th></tr></thead>
                <tbody>
                  {termScores.map((t) => <tr key={t.term}><td>{t.term}</td><td><strong>{t.score}%</strong></td><td>{t.n}</td></tr>)}
                </tbody>
              </table>
            ) : <p className="sample-note">No scored records in {year}.</p>}
          </div>
        </div>
        <div className="subject-detail-grid">
          <section className="subject-detail-card">
            <h3>Recorded assessments</h3>
            <div className="subject-detail-scroll">
              <table>
                <thead><tr><th>Term</th><th>Type</th><th>Title</th><th>Score</th></tr></thead>
                <tbody>
                  {yearRecords.slice(0, 30).map((r) => (
                    <tr key={r.id}>
                      <td>{r.term}</td>
                      <td>{r.kind}</td>
                      <td>{r.title ?? r.skill ?? "—"}</td>
                      <td>{pct(r) === null ? "—" : <strong>{Math.round(pct(r)!)}%</strong>}</td>
                    </tr>
                  ))}
                  {!yearRecords.length && <tr><td colSpan={4}>No records this year.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
          <section className="subject-detail-card observations-card">
            <h3>Teacher Observations</h3>
            {yearObservations.length ? (
              <div className="observation-list">
                {yearObservations.map((o) => (
                  <div className="observation-item" key={o.id}>
                    <span>{o.term}</span>
                    <p>{o.text}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-observations">
                <CircleHelp />
                <p>No teacher observations recorded for this subject in {year}.</p>
              </div>
            )}
          </section>
        </div>
      </section>
    </div>
  );
}

type Tab = "Overview" | "Subjects";

export default function ProfilePage() {
  const { learnerId = "" } = useParams();
  const navigate = useNavigate();
  const [learner, setLearner] = useState<Learner | null>(null);
  const [feed, setFeed] = useState<RecordsFeed>({ records: [], observations: [] });
  const [entries, setEntries] = useState<ProfileEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [recordOpen, setRecordOpen] = useState(false);
  const [selectedSubject, setSelectedSubject] = useState<string | null>(null);

  const reload = useCallback(() => {
    api<Learner>(`/learners/${learnerId}`).then(setLearner).catch((e) => setError(String(e.message ?? e)));
    api<RecordsFeed>(`/learners/${learnerId}/records`).then(setFeed).catch(() => {});
    api<ProfileEntry[]>(`/learners/${learnerId}/profile`).then(setEntries).catch(() => setEntries([]));
  }, [learnerId]);

  useEffect(() => { setTab("Overview"); reload(); }, [reload]);

  const subjects = useMemo(() => {
    const map = new Map<string, LearnerRecord[]>();
    for (const r of feed.records) map.set(r.subject, [...(map.get(r.subject) ?? []), r]);
    return [...map.entries()].map(([name, records]) => ({ name, records, yearly: yearlyAverages(records) }));
  }, [feed.records]);

  if (error) {
    return (
      <div className="app-shell">
        <Sidebar />
        <main className="main-content">
          <div className="placeholder-panel">
            <div className="placeholder-icon"><TriangleAlert /></div>
            <h2>Could not load this learner</h2>
            <p>{error}</p>
            <button className="primary-button" onClick={() => navigate("/students")}>Back to Students</button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar learnerId={learnerId} onUpdate={() => setRecordOpen(true)} />
      <main className="main-content">
        <button className="back-link" onClick={() => navigate("/students")}>
          <ArrowLeft size={18} /> Back to Students
        </button>
        <div className="identity-row">
          <div className="student-identity">
            <div className="student-avatar">{learner ? initialsOf(learner.full_name) : "…"}</div>
            <div>
              <h1>{learner?.full_name ?? "Loading…"}</h1>
              <div className="student-meta">
                <span>Learner ID: {learnerId}</span>
                {learner?.grade_level && <><i /><span>Grade: {learner.grade_level}</span></>}
                <i />
                <span>{feed.records.length} records</span>
              </div>
            </div>
          </div>
        </div>
        <div className="profile-tabs" role="tablist" aria-label="Learner profile sections">
          {(["Overview", "Subjects"] as Tab[]).map((item) => (
            <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? "selected" : ""} onClick={() => setTab(item)}>
              {item}
            </button>
          ))}
        </div>
        {tab === "Overview" ? (
          <div className="overview-grid">
            <KeyHighlights entries={entries} learnerName={learner?.full_name ?? "this learner"} />
            <div className="right-column">
              <PerformanceOverTime records={feed.records} />
              <QuickActions learnerId={learnerId} onUpdate={() => setRecordOpen(true)} />
            </div>
          </div>
        ) : (
          <section className="subjects-section" aria-labelledby="subjects-heading">
            <div className="subjects-heading">
              <div><p id="subjects-heading">Explore academic performance across recorded years.</p></div>
              <span>{subjects.length} subjects recorded</span>
            </div>
            <div className="panel subjects-panel">
              <div className="panel-heading">
                <div><h2 className="!text-15">Performance by subject</h2><p className="font-medium">Annual average across academic years</p></div>
              </div>
              <div className="subject-list">
                {subjects.map(({ name, records, yearly }) => {
                  return (
                    <button type="button" className="subject-row" key={name} onClick={() => setSelectedSubject(name)}>
                      <div className="subject-info">
                        <strong>{name}</strong>
                        <span className="font-medium">{records.length} records · {yearly.length} {yearly.length === 1 ? "year" : "years"}</span>
                      </div>
                      <SubjectSparkline points={yearly.slice(-3)} />
                      <ChevronRight className="subject-chevron" aria-hidden="true" />
                    </button>
                  );
                })}
                {!subjects.length && <div className="directory-empty"><strong>No records yet</strong><span>Use “Add / Update Record” to enter the first assessment.</span></div>}
              </div>
            </div>
            {selectedSubject && (
              <SubjectDetailModal
                subject={selectedSubject}
                records={feed.records}
                observations={feed.observations}
                onClose={() => setSelectedSubject(null)}
              />
            )}
          </section>
        )}
        {recordOpen && (
          <RecordModal
            learnerId={learnerId}
            subjects={subjects.map((s) => s.name)}
            onClose={() => setRecordOpen(false)}
            onSaved={() => { setRecordOpen(false); reload(); }}
          />
        )}
      </main>
    </div>
  );
}
