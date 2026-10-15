export type Learner = { id: string; full_name: string; grade_level: string | null }

export type LearnerRecord = {
  id: number
  term: string
  kind: string
  subject: string
  skill: string | null
  title: string | null
  score: number | null
  max_score: number | null
  recorded_on: string | null
  submitted_late: boolean
  notes: string | null
}

export type Observation = {
  id: number
  term: string
  subject: string | null
  skill: string | null
  sentiment: string | null
  text: string
  teacher_id: string
  recorded_on: string | null
}

export type RecordsFeed = { records: LearnerRecord[]; observations: Observation[] }

export type RecordInput = {
  term: string
  kind: 'quiz' | 'assignment' | 'project' | 'attendance'
  subject: string
  score?: number | null
  recorded_on?: string | null
  notes?: string | null
}

export type PatternSummary = {
  pattern_id: string
  kind: string
  subtype: string | null
  subject: string | null
  skill: string | null
  statement: string
  evidence_strength: string
  n_terms: number
  status: string
}

export type ProfileEntry = {
  change_id: number
  applied_at: string
  summary: string
  approval_id: string
  pattern: PatternSummary
}

export type ReviewListItem = {
  review_id: number
  status: string
  reason: string
  created_at: string
  learner: { id: string; full_name: string }
  pattern: PatternSummary
}

export type EvidenceRecord = {
  record_id: number
  term: string
  kind: string
  title: string | null
  pct: number | null
  score: number | null
  max_score: number | null
  late: boolean
  source: string | null
}

export type EvidenceObservation = {
  term: string
  text: string
  [key: string]: unknown
}

export type ReviewDetail = {
  review_id: number
  status: string
  reason: string
  run_id: string | null
  created_at: string
  learner: { id: string; full_name: string; grade_level: string | null }
  pattern: PatternSummary & Record<string, unknown>
  evidence: {
    records?: EvidenceRecord[]
    observations?: EvidenceObservation[]
    attendance?: { term: string; pct: number | null }[]
    documents?: { document_ref: string; note: string | null }[]
    [key: string]: unknown
  }
  decisions: {
    approval_id: string
    teacher_id: string
    decision: string
    comment: string | null
    decided_at: string
  }[]
}

export type Decision = 'approved' | 'rejected' | 'more_evidence'

export type RunSummary = {
  run_id: string
  state: string
  request: string
  learner_id: string
  learner_name: string | null
  llm: { provider: string | null; model: string | null }
  started_at: string | null
  finished_at: string | null
  result?: RunResult | null
  review_ids?: number[]
}

export type RunResult = {
  summary?: string
  summary_source?: string
  findings?: { pattern_id?: string; statement?: string; [key: string]: unknown }[]
  fallbacks?: string[]
  documents_consulted?: unknown[]
  profile_changes?: unknown[]
  checked?: { subject?: string; skill?: string; result?: string; [key: string]: unknown }[]
  data_quality?: Record<string, unknown>
  llm?: { provider?: string; model?: string; calls?: number; seconds?: number; available?: boolean }
  rounds?: number
  error?: string
}

export type AgentEvent = {
  seq: number
  kind: string
  node: string | null
  title: string
  detail: Record<string, unknown> | null
  created_at: string | null
}
