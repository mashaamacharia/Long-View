'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  ArrowLeft,
  BarChart3,
  BookOpen,
  Brain,
  ChevronDown,
  CircleHelp,
  Lightbulb,
  X,
  Check,
  ChevronRight,
  FilePlus2,
  GraduationCap,
  HelpCircle,
  MessageCircleQuestion,
  Settings,
  Sparkles,
  Star,
  TrendingUp,
  TriangleAlert,
  Users,
} from 'lucide-react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const studentRecords = [
  { name: 'Amina Okello', initials: 'AO', id: 'STU001', className: '4A', age: 9 },
  { name: 'Brian Otieno', initials: 'BO', id: 'STU002', className: '4A', age: 10 },
  { name: 'Caroline Njeri', initials: 'CN', id: 'STU003', className: '4B', age: 9 },
  { name: 'David Mwangi', initials: 'DM', id: 'STU004', className: '4A', age: 10 },
  { name: 'Evelyn Wanjiku', initials: 'EW', id: 'STU005', className: '4B', age: 9 },
  { name: 'Faith Achieng', initials: 'FA', id: 'STU006', className: '4A', age: 10 },
  { name: 'George Odhiambo', initials: 'GO', id: 'STU007', className: '5A', age: 11 },
  { name: 'Helen Wairimu', initials: 'HW', id: 'STU008', className: '4B', age: 9 },
  { name: 'Ian Kamau', initials: 'IK', id: 'STU009', className: '5A', age: 11 },
  { name: 'Joy Wambui', initials: 'JW', id: 'STU010', className: '4A', age: 10 },
  { name: 'Kevin Kiptoo', initials: 'KK', id: 'STU011', className: '5A', age: 11 },
  { name: 'Lucy Atieno', initials: 'LA', id: 'STU012', className: '4B', age: 9 },
] as const

let student = studentRecords[0]
const highlights = [
  { title: 'Key Strengths', description: 'Practical science, creativity, class participation', icon: Star, tone: 'green' },
  { title: 'Areas to Watch', description: 'Reading comprehension, consistent homework', icon: TriangleAlert, tone: 'amber' },
  { title: 'Progress', description: 'Improving in mathematics and social studies', icon: TrendingUp, tone: 'purple' },
] as const
const performance = [
  { year: '2022', score: 58 },
  { year: '2023', score: 64 },
  { year: '2024', score: 69 },
  { year: '2025', score: 76 },
]

type Tab = 'Overview' | 'Subjects' | 'Timeline' | 'Update'

export function AppSidebar({ onUpdate }: { onUpdate: () => void }) {
  const router = useRouter()
  const nav = [
    { label: 'Students', icon: Users, action: () => router.push('/students') },
    { label: 'Add / Update Record', icon: FilePlus2, action: onUpdate },
    { label: 'Ask the AI', icon: MessageCircleQuestion, action: () => router.push('/students/amina-okello/ask') },
  ]
  return (
    <aside className="sidebar-shell">
      <div>
        <div className="brand-block">
          <div className="brand-mark"><BookOpen size={20} /></div>
          <div><div className="brand-name">The Long View</div>
          <div className="brand-tagline">Every learner. A fuller picture.</div>
        </div>
        </div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {nav.map(({ label, icon: Icon, action }, index) => (
            <button key={label} className={`sidebar-nav-item ${index === 0 ? 'active' : ''}`} onClick={action}>
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
            </button>
          ))}
        </nav>
      </div>
      <div className="sidebar-bottom">
        <button className="sidebar-nav-item"><Settings size={17} strokeWidth={1.8} /><span>Settings</span></button>
        <div className="teacher-profile"><div className="teacher-avatar">MK</div><div><div className="teacher-name">Mr. Kamau</div><div className="teacher-role">Teacher</div></div></div>
      </div>
    </aside>
  )
}

function StudentIdentity() {
  const router = useRouter()
  return <>
    <button className="back-link" onClick={() => router.push('/students')}>
      <ArrowLeft size={18} /> Back to Students</button>
    <div className="identity-row">
      <div className="student-identity"><div className="student-avatar">{student.initials}</div>
      <div><h1>{student.name}</h1>
      <div className="student-meta"><span>Student ID: {student.id}</span><i /><span>Class: {student.className}</span><i /><span>Age: {student.age}</span></div></div></div>
      <div className="updated"><span className="status-dot" /> <span>Last updated</span><strong>2 days ago</strong></div>
    </div>
  </>
}

function ProfileTabs({ tab, setTab }: { tab: Tab; setTab: (tab: Tab) => void }) {
  return <div className="profile-tabs" role="tablist" aria-label="Student profile sections">{(['Overview', 'Subjects',] as Tab[]).map((item) => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? 'selected' : ''} onClick={() => setTab(item)}>{item}</button>)}</div>
}

function HighlightCard({ item }: { item: (typeof highlights)[number] }) {
  const Icon = item.icon
  return <div className={`highlight-card ${item.tone}`}>
    <div className="highlight-icon">
      <Icon size={18} />
    </div>
    <div>
      <h3>{item.title}</h3>
      <p>{item.description}</p>
    </div></div>
}

function KeyHighlights() {
  return <section className="panel highlights-panel">
    <div className="panel-heading">
      <div>
        <h2>Key Highlights</h2>
        <p>What stands out in Amina&apos;s learning journey</p>
      </div>
      <Sparkles size={18} className="heading-icon" />
      </div>
      <div className="highlight-list">{highlights.map((item) => <HighlightCard key={item.title} item={item} />)}</div></section>
}

function AcademicPerformanceChart() {
  return <div className="chart-wrap" aria-label="Line chart showing average scores from 2022 to 2025"><ResponsiveContainer width="100%" height={196}><LineChart data={performance} margin={{ top: 12, right: 8, left: -24, bottom: 0 }}><CartesianGrid stroke="#E8EEF5" vertical={false} /><XAxis dataKey="year" axisLine={false} tickLine={false} tick={{ fill: '#718096', fontSize: 11 }} /><YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} axisLine={false} tickLine={false} tick={{ fill: '#718096', fontSize: 10 }} tickFormatter={(value) => `${value}%`} /><Tooltip contentStyle={{ border: '1px solid #E2EAF3', borderRadius: 8, boxShadow: '0 4px 14px rgba(16,43,78,.08)', fontSize: 12 }} formatter={(value) => [`${value}%`, 'Average score']} labelFormatter={(label) => `Academic year ${label}`} /><Line type="monotone" dataKey="score" stroke="#2878E5" strokeWidth={2.5} dot={{ r: 4, fill: '#fff', stroke: '#2878E5', strokeWidth: 2 }} activeDot={{ r: 5, fill: '#2878E5', stroke: '#fff', strokeWidth: 2 }} /></LineChart></ResponsiveContainer></div>
}

function PerformanceOverTime() {
  return <section className="panel performance-panel"><div className="panel-heading performance-heading"><div><h2>Performance Over Time</h2><p>Academic performance across recorded years</p></div><select aria-label="Academic period" defaultValue="all"><option value="all">All years</option><option value="recent">Recent years</option></select></div><div className="sample-summary"><div><span>Latest recorded average</span><strong>76%</strong></div><div className="summary-change"><Check size={14} /> +18 percentage points <small>since 2022</small></div></div><AcademicPerformanceChart /><p className="sample-note">Illustrative sample data, not actual results for Amina.</p></section>
}

function QuickActions({ onUpdate }: { onUpdate: () => void }) {
  const router = useRouter()
  const actions = [
    { title: 'Update Student Record', description: 'Add an assessment result or teacher observation.', button: 'Add Record', icon: FilePlus2, action: onUpdate },
    { title: 'Ask the AI', description: "Explore strengths, difficulties, and progress using the learner's history.", button: 'Ask a Question', icon: HelpCircle, action: () => router.push('/students/amina-okello/ask') },
  ]
  return <section className="panel quick-panel"><div className="panel-heading"><div><h2>Quick Actions</h2><p>Continue building Amina&apos;s fuller picture</p></div></div><div className="action-list">{actions.map(({ title, description, button, icon: Icon, action }) => <div className="action-item" key={title}><div className="action-icon"><Icon size={18} /></div><div className="action-copy"><h3>{title}</h3><p>{description}</p><button onClick={action}>{button}<ArrowLeft size={14} className="arrow-right" /></button></div></div>)}</div></section>
}

function UpdateRecordModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ subject: '', assessment: '', score: '', term: '', date: '', notes: '' })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const hasChanges = Object.values(form).some(Boolean)
  const requestClose = () => { if (!hasChanges || window.confirm('Discard your unsaved changes?')) onClose() }
  const update = (field: keyof typeof form, value: string) => { setForm((current) => ({ ...current, [field]: value })); setError('') }
  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    const required = [['subject', form.subject], ['assessment type', form.assessment], ['score', form.score], ['term', form.term], ['date', form.date]].find(([, value]) => !value)
    if (required) { setError(`Please complete the ${required[0]} field.`); return }
    const score = Number(form.score)
    if (!Number.isFinite(score) || score < 0 || score > 100) { setError('Score must be a number between 0 and 100.'); return }
    setSaving(true)
    await new Promise((resolve) => setTimeout(resolve, 450))
    setSaving(false)
    onClose()
  }
  return <div className="record-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) requestClose() }}>
    <section className="record-modal" role="dialog" aria-modal="true" aria-labelledby="record-modal-title">
      <header className="record-modal-header"><div><h2 id="record-modal-title">Update Student Record</h2><p>Record assessment results and add teacher observations to the learner&apos;s profile.</p></div><button className="modal-close" aria-label="Close update student record" onClick={requestClose}><X /></button></header>
      <form onSubmit={save} noValidate><div className="record-form-grid">
        <label>Subject<select value={form.subject} onChange={(event) => update('subject', event.target.value)}><option value="">Select a subject</option>{subjectPerformance.map(({ name }) => <option key={name}>{name}</option>)}</select></label>
        <label>Assessment Type<select value={form.assessment} onChange={(event) => update('assessment', event.target.value)}><option value="">Select assessment type</option>{['Exam', 'CAT', 'RAT'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Score<input type="number" min="0" max="100" step="any" placeholder="Enter score" value={form.score} onChange={(event) => update('score', event.target.value)} /></label>
        <label>Term<select value={form.term} onChange={(event) => update('term', event.target.value)}><option value="">Select term</option>{['Term 1', 'Term 2', 'Term 3'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Date<input type="date" value={form.date} onChange={(event) => update('date', event.target.value)} /></label>
        <label className="record-notes">Notes <span>Optional</span><textarea rows={4} placeholder="Add observations about the learner&apos;s performance, strengths, or areas needing support…" value={form.notes} onChange={(event) => update('notes', event.target.value)} /></label>
      </div>{error && <p className="record-form-error" role="alert">{error}</p>}<footer className="record-modal-footer"><button type="button" className="record-cancel" onClick={requestClose}>Cancel</button><button type="submit" className="record-save" disabled={saving}>{saving ? 'Saving…' : 'Save Record'}</button></footer></form>
    </section>
  </div>
} 

const subjectPerformance = [
  { name: 'Mathematics', scores: [58, 64, 69] },
  { name: 'English', scores: [62, 59, 66] },
  { name: 'Science', scores: [70, 74, 81] },
  { name: 'Social Studies', scores: [60, 65, 68] },
  { name: 'Creative Arts', scores: [78, 82, 80] },
] as const

function SubjectSparkline({ scores }: { scores: readonly number[] }) {
  const points = scores.map((score, index) => ({ x: 34 + index * 86, y: 58 - score * 0.42, score }))
  const path = `M ${points[0].x} ${points[0].y} C ${points[0].x + 28} ${points[0].y}, ${points[1].x - 28} ${points[1].y}, ${points[1].x} ${points[1].y} S ${points[2].x - 28} ${points[2].y}, ${points[2].x} ${points[2].y}`
  return <svg className="subject-sparkline" viewBox="0 0 206 78" role="img" aria-label={`Annual averages: ${scores.join('%, ')}%`}>
    <line x1="34" y1="8" x2="34" y2="66" className="sparkline-guide" />
    <line x1="120" y1="8" x2="120" y2="66" className="sparkline-guide" />
    <line x1="206" y1="8" x2="206" y2="66" className="sparkline-guide" />
    <path d={path} className="sparkline-path" />
    {points.map((point) => <g key={`${point.x}-${point.score}`}><text x={point.x} y={Math.max(10, point.y - 8)} textAnchor="middle" className="sparkline-label">{point.score}%</text><circle cx={point.x} cy={point.y} r="3.5" className="sparkline-dot" /></g>)}
  </svg>
}

type SubjectName = (typeof subjectPerformance)[number]['name']

const subjectIcons = { Mathematics: Brain, English: BookOpen, Science: Lightbulb, 'Social Studies': Users, 'Creative Arts': Star } as const

function SubjectDetailModal({ subject, onClose }: { subject: SubjectName; onClose: () => void }) {
  const subjectData = subjectPerformance.find((item) => item.name === subject) ?? subjectPerformance[0]
  const years = ['2024', '2023', '2022']
  const [year, setYear] = useState(years[0])
  const Icon = subjectIcons[subject]
  const yearIndex = Number(year) - 2022
  const score = subjectData.scores[yearIndex] ?? null
  const termScores = subjectData.scores.map((value, index) => ({ term: `Term ${index + 1}`, score: Math.max(0, value - 4 + index * 2) })).slice(0, 3)
  const average = score === null ? null : score
  const previous = termScores[0]?.score
  const latest = termScores[termScores.length - 1]?.score
  const improvement = previous && latest ? latest - previous : null
  const points = termScores.map((item, index) => `${24 + index * 110},${132 - item.score * 0.92}`).join(' ')

  return <div className="subject-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="subject-modal" role="dialog" aria-modal="true" aria-labelledby="subject-modal-title">
      <header className="subject-modal-header">
        <div><button className="modal-back-link" onClick={onClose}><ArrowLeft data-icon="inline-start" /> Back to {student.name}</button><div className="modal-subject-identity"><div className="modal-subject-icon"><Icon /></div><div><h2 id="subject-modal-title">{subject}</h2><p>Performance and insights for this subject</p></div></div></div>
        <div className="modal-header-actions"><label>Academic Year<select value={year} onChange={(event) => setYear(event.target.value)}>{years.map((item) => <option key={item}>{item}</option>)}</select></label><button className="modal-close" aria-label="Close subject details" onClick={onClose}><X /></button></div>
      </header>
      <div className="subject-summary-card"><div className="score-gauge-wrap"><div className="score-gauge" style={{ '--score-angle': `${(average ?? 0) * 3.6}deg` } as React.CSSProperties}><strong>{average === null ? '—' : `${average}%`}</strong></div><div><b>Average Score</b><span>Selected academic year</span></div></div><div className="improvement-stat"><span className={improvement !== null && improvement >= 0 ? 'positive' : 'neutral'}>{improvement === null ? '—' : `${improvement >= 0 ? '↑ +' : '↓ '}${Math.abs(improvement)}%`}</span><b>{improvement === null ? 'Not enough data' : 'Improvement since Term 1'}</b></div><div className="term-chart"><div className="chart-title">Term performance</div><svg viewBox="0 0 268 160" role="img" aria-label={`${subject} scores by term`}><line x1="24" y1="132" x2="244" y2="132" className="detail-chart-axis" /><line x1="24" y1="40" x2="244" y2="40" className="detail-chart-grid" /><polyline points={points} className="detail-chart-line" />{termScores.map((item, index) => <g key={item.term}><circle cx={24 + index * 110} cy={132 - item.score * 0.92} r="4" className="detail-chart-dot" /><text x={24 + index * 110} y="151" textAnchor="middle">{item.term}</text></g>)}</svg></div></div>
      <div className="subject-detail-grid"><section className="subject-detail-card"><h3>Term Breakdown</h3><table><thead><tr><th>Term</th><th>Score</th><th>Notes</th></tr></thead><tbody>{termScores.map((item) => <tr key={item.term}><td>{item.term}</td><td><strong>{item.score}%</strong></td><td>—</td></tr>)}</tbody></table></section><section className="subject-detail-card observations-card"><h3>Teacher Observations</h3><div className="empty-observations"><CircleHelp /><p>No teacher observations recorded for this year.</p></div></section></div>
    </section>
  </div>
}

function SubjectsTab() {
  const [selectedSubject, setSelectedSubject] = useState<SubjectName | null>(null)
  return <section className="subjects-section" aria-labelledby="subjects-heading">
    <div className="subjects-heading">
      <div><p>Explore academic performance across recorded years.</p></div><span>Academic years: 2022–2024</span></div>
    <div className="panel subjects-panel"><div className="panel-heading"><div><h2 className='!text-15'>Performance by subject</h2><p className='font-medium'>Annual average across academic years</p></div></div>
    <div className="subject-years" aria-hidden="true"><span /><span>2022</span><span>2023</span><span>2024</span><span /></div>
    <div className="subject-list">{subjectPerformance.map(({ name, scores }) => <button type="button" className="subject-row" key={name} onClick={() => setSelectedSubject(name)}>
      <div className="subject-info"><strong>{name}</strong>
      <span className='font-medium'>3 years recorded</span></div>
      <SubjectSparkline scores={scores} /><ChevronRight className="subject-chevron" aria-hidden="true" /></button>)}</div></div>
    {selectedSubject && <SubjectDetailModal subject={selectedSubject} onClose={() => setSelectedSubject(null)} />}
  </section>
}

function Placeholder({ tab }: { tab: Exclude<Tab, 'Overview' | 'Subjects'> }) {
  const copy = { Timeline: ['Learning timeline', 'A chronological history of assessments, observations, and milestones will appear here.'], Update: ['Update student record', 'Add an assessment result or teacher observation for Amina Okello.'] }[tab]
  return <section className="placeholder-panel"><div className="placeholder-icon"><BarChart3 size={22} /></div><h2>{copy[0]}</h2><p>{copy[1]}</p><button className="primary-button">Continue with Amina Okello</button></section>
}

export default function StudentProfile({ studentId }: { studentId?: string }) {
  student = studentRecords.find((record) => record.id.toLowerCase() === studentId?.toLowerCase()) ?? studentRecords[0]
  const [tab, setTab] = useState<Tab>('Overview')
  const [recordOpen, setRecordOpen] = useState(false)
  return <div className="app-shell">
    <AppSidebar onUpdate={() => setRecordOpen(true)} />
      <main className="main-content">
        <StudentIdentity />
        <ProfileTabs tab={tab} setTab={setTab} />{tab === 'Overview' ? <div className="overview-grid">
          <KeyHighlights />
          <div className="right-column">
            <PerformanceOverTime />
            <QuickActions onUpdate={() => setRecordOpen(true)} />
          </div>
         </div> : 
         tab === 'Subjects' ? <SubjectsTab /> : 
         <Placeholder tab={tab} />}
      </main>{recordOpen && <UpdateRecordModal onClose={() => setRecordOpen(false)} />}</div>
}
