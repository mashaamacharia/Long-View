import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Search, SlidersHorizontal } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Learner } from "../types";

const avatarPalette = ["blue", "green", "amber", "coral", "purple", "teal"];
const initials = (name: string) =>
  name.split(" ").filter(Boolean).slice(0, 2).map((word) => word[0]).join("").toUpperCase();
const avatarTone = (id: string) =>
  avatarPalette[id.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0) % avatarPalette.length];

export default function DirectoryPage() {
  const navigate = useNavigate();
  const [learners, setLearners] = useState<Learner[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [gradeFilter, setGradeFilter] = useState("All Grades");

  useEffect(() => {
    api<Learner[]>("/learners").then(setLearners).catch((e) => setError(String(e.message ?? e)));
  }, []);

  const grades = useMemo(
    () => ["All Grades", ...Array.from(new Set(learners.map((l) => l.grade_level).filter(Boolean) as string[]))],
    [learners],
  );
  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return learners.filter((l) => {
      const matchesQuery = `${l.full_name} ${l.id}`.toLowerCase().includes(q);
      return matchesQuery && (gradeFilter === "All Grades" || l.grade_level === gradeFilter);
    });
  }, [learners, query, gradeFilter]);

  return (
    <div className="directory-shell">
      <div className="directory-main">
        <header className="directory-header">
          <div>
            <p className="eyebrow">LEARNER DIRECTORY</p>
            <h1>Students</h1>
            <p>Manage and explore your learners</p>
          </div>
          <div className="directory-controls">
            <label className="directory-search">
              <Search aria-hidden="true" />
              <span className="sr-only">Search students</span>
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name or ID..." />
            </label>
            <label className="directory-filter">
              <SlidersHorizontal aria-hidden="true" />
              <span className="sr-only">Filter by grade</span>
              <select value={gradeFilter} onChange={(e) => setGradeFilter(e.target.value)}>
                {grades.map((g) => <option key={g}>{g}</option>)}
              </select>
            </label>
          </div>
        </header>
        <div className="directory-table-wrap">
          {error && <div className="directory-empty"><strong>Could not reach the API</strong><span>{error}</span></div>}
          {!error && (
            <table className="directory-table">
              <thead>
                <tr><th>Name</th><th>Learner ID</th><th>Grade</th><th><span className="sr-only">Open profile</span></th></tr>
              </thead>
              <tbody>
                {filtered.map((learner) => (
                  <tr
                    key={learner.id}
                    onClick={() => navigate(`/students/${learner.id}`)}
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate(`/students/${learner.id}`); }}
                  >
                    <td>
                      <div className="directory-name">
                        <span className={`directory-avatar ${avatarTone(learner.id)}`} aria-hidden="true">
                          {initials(learner.full_name)}
                        </span>
                        <strong>{learner.full_name}</strong>
                      </div>
                    </td>
                    <td>{learner.id}</td>
                    <td>{learner.grade_level ?? "—"}</td>
                    <td><ChevronRight className="directory-chevron" aria-hidden="true" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!error && !filtered.length && (
            <div className="directory-empty">
              <Search aria-hidden="true" />
              <strong>No students found</strong>
              <span>Try another name, learner ID, or grade.</span>
              <button onClick={() => { setQuery(""); setGradeFilter("All Grades"); }}>Clear filters</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
