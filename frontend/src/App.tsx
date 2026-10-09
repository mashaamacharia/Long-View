import { useEffect, useState } from "react";
import { api } from "./api/client";

type Learner = { id: string; full_name: string; grade_level: string | null };

export default function App() {
  const [learners, setLearners] = useState<Learner[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Learner[]>("/learners").then(setLearners).catch((e) => setError(String(e)));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 720, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>LongView</h1>
      <p>Profile, don't label. Evidence-backed patterns for teacher review.</p>
      {error && <p style={{ color: "crimson" }}>API error: {error}</p>}
      <ul>
        {learners.map((l) => (
          <li key={l.id}>
            {l.full_name} ({l.id}) {l.grade_level}
          </li>
        ))}
      </ul>
    </main>
  );
}
