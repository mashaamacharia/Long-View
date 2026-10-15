import { BookOpen, FilePlus2, MessageCircleQuestion, Settings, Users, ClipboardCheck } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

export default function Sidebar({ learnerId, onUpdate }: { learnerId?: string; onUpdate?: () => void }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const onStudents = pathname.startsWith("/students");
  const onReviews = pathname.startsWith("/reviews");

  const nav = [
    { label: "Students", icon: Users, active: onStudents, action: () => navigate("/students") },
    ...(onUpdate
      ? [{ label: "Add / Update Record", icon: FilePlus2, active: false, action: onUpdate }]
      : []),
    ...(learnerId
      ? [{ label: "Ask the AI", icon: MessageCircleQuestion, active: pathname.includes("/ask"), action: () => navigate(`/students/${learnerId}/ask`) }]
      : []),
    { label: "Teacher Reviews", icon: ClipboardCheck, active: onReviews, action: () => navigate("/reviews") },
  ];

  return (
    <aside className="sidebar-shell">
      <div>
        <div className="brand-block">
          <div className="brand-mark"><BookOpen size={20} /></div>
          <div>
            <div className="brand-name">The Long View</div>
            <div className="brand-tagline">Every learner. A fuller picture.</div>
          </div>
        </div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {nav.map(({ label, icon: Icon, active, action }) => (
            <button key={label} className={`sidebar-nav-item ${active ? "active" : ""}`} onClick={action}>
              <Icon size={17} strokeWidth={1.8} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </div>
      <div className="sidebar-bottom">
        <button className="sidebar-nav-item"><Settings size={17} strokeWidth={1.8} /><span>Settings</span></button>
        <div className="teacher-profile">
          <div className="teacher-avatar">MK</div>
          <div>
            <div className="teacher-name">Mr. Kamau</div>
            <div className="teacher-role">Teacher</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
