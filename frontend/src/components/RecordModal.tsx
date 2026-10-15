import { useState } from "react";
import { X } from "lucide-react";
import { post } from "../api/client";
import type { LearnerRecord, RecordInput } from "../types";

const KINDS: { value: RecordInput["kind"]; label: string }[] = [
  { value: "quiz", label: "Quiz / CAT" },
  { value: "assignment", label: "Assignment" },
  { value: "project", label: "Project" },
  { value: "attendance", label: "Attendance" },
];
const SUBJECTS = ["Mathematics", "English", "Science", "Social Studies", "Creative Arts"];
const YEARS = ["2026", "2025", "2024", "2023"];

export default function RecordModal({
  learnerId,
  subjects,
  onClose,
  onSaved,
}: {
  learnerId: string;
  subjects: string[];
  onClose: () => void;
  onSaved: (record: LearnerRecord) => void;
}) {
  const [form, setForm] = useState({ subject: "", kind: "", score: "", year: "", term: "", date: "", notes: "" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const hasChanges = Object.values(form).some(Boolean);
  const requestClose = () => { if (!hasChanges || window.confirm("Discard your unsaved changes?")) onClose(); };
  const update = (field: keyof typeof form, value: string) => { setForm((c) => ({ ...c, [field]: value })); setError(""); };

  const subjectOptions = Array.from(new Set([...SUBJECTS, ...subjects]));

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const required = [
      ["subject", form.subject],
      ["assessment type", form.kind],
      ["term", form.year || form.term],
      ["date", form.date],
    ].find(([, value]) => !value);
    if (required) { setError(`Please complete the ${required[0]} field.`); return; }
    if (form.score) {
      const score = Number(form.score);
      if (!Number.isFinite(score) || score < 0 || score > 100) {
        setError("Score must be a number between 0 and 100.");
        return;
      }
    }
    setSaving(true);
    try {
      const body: RecordInput = {
        term: `${form.year}-T${form.term.slice(-1)}`,
        kind: form.kind as RecordInput["kind"],
        subject: form.subject,
        score: form.score ? Number(form.score) : null,
        recorded_on: form.date || null,
        notes: form.notes.trim() || null,
      };
      const created = await post<LearnerRecord>(`/learners/${learnerId}/records`, body);
      onSaved(created);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Saving failed.");
      setSaving(false);
    }
  };

  return (
    <div className="record-modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) requestClose(); }}>
      <section className="record-modal" role="dialog" aria-modal="true" aria-labelledby="record-modal-title">
        <header className="record-modal-header">
          <div>
            <h2 id="record-modal-title">Update Student Record</h2>
            <p>Record assessment results and add teacher observations to the learner&apos;s profile.</p>
          </div>
          <button className="modal-close" aria-label="Close update student record" onClick={requestClose}><X /></button>
        </header>
        <form onSubmit={save} noValidate>
          <div className="record-form-grid">
            <label>Subject
              <select value={form.subject} onChange={(e) => update("subject", e.target.value)}>
                <option value="">Select a subject</option>
                {subjectOptions.map((s) => <option key={s}>{s}</option>)}
              </select>
            </label>
            <label>Assessment Type
              <select value={form.kind} onChange={(e) => update("kind", e.target.value)}>
                <option value="">Select assessment type</option>
                {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
              </select>
            </label>
            <label>Score <span className="record-field-note">Optional</span>
              <input type="number" min="0" max="100" step="any" placeholder="Enter score" value={form.score} onChange={(e) => update("score", e.target.value)} />
            </label>
            <label>Term
              <span className="record-term-row">
                <select value={form.year} onChange={(e) => update("year", e.target.value)} aria-label="Academic year">
                  <option value="">Year</option>
                  {YEARS.map((y) => <option key={y}>{y}</option>)}
                </select>
                <select value={form.term} onChange={(e) => update("term", e.target.value)} aria-label="Term">
                  <option value="">Term</option>
                  {["Term 1", "Term 2", "Term 3"].map((t) => <option key={t}>{t}</option>)}
                </select>
              </span>
            </label>
            <label>Date
              <input type="date" value={form.date} onChange={(e) => update("date", e.target.value)} />
            </label>
            <label className="record-notes">Notes <span>Optional</span>
              <textarea
                rows={4}
                placeholder="Add observations about the learner's performance, strengths, or areas needing support…"
                value={form.notes}
                onChange={(e) => update("notes", e.target.value)}
              />
            </label>
          </div>
          {error && <p className="record-form-error" role="alert">{error}</p>}
          <footer className="record-modal-footer">
            <button type="button" className="record-cancel" onClick={requestClose}>Cancel</button>
            <button type="submit" className="record-save" disabled={saving}>{saving ? "Saving…" : "Save Record"}</button>
          </footer>
        </form>
      </section>
    </div>
  );
}
