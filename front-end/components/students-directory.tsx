'use client'

import { useMemo, useState } from 'react'
import { ChevronRight, Search, SlidersHorizontal } from 'lucide-react'
import { useRouter } from 'next/navigation'

export type DirectoryStudent = {
  id: string
  name: string
  className: string
  age: number
  lastUpdated: string
}

export const directoryStudents: DirectoryStudent[] = [
  { id: 'STU001', name: 'Amina Okello', className: '4A', age: 9, lastUpdated: '2 days ago' },
  { id: 'STU002', name: 'Brian Otieno', className: '4A', age: 10, lastUpdated: '1 day ago' },
  { id: 'STU003', name: 'Caroline Njeri', className: '4B', age: 9, lastUpdated: '3 days ago' },
  { id: 'STU004', name: 'David Mwangi', className: '4A', age: 10, lastUpdated: '5 days ago' },
  { id: 'STU005', name: 'Evelyn Wanjiku', className: '4B', age: 9, lastUpdated: '1 day ago' },
  { id: 'STU006', name: 'Faith Achieng', className: '4A', age: 10, lastUpdated: '4 days ago' },
  { id: 'STU007', name: 'George Odhiambo', className: '5A', age: 11, lastUpdated: '2 days ago' },
  { id: 'STU008', name: 'Helen Wairimu', className: '4B', age: 9, lastUpdated: '6 days ago' },
  { id: 'STU009', name: 'Ian Kamau', className: '5A', age: 11, lastUpdated: 'Today' },
  { id: 'STU010', name: 'Joy Wambui', className: '4A', age: 10, lastUpdated: '3 days ago' },
  { id: 'STU011', name: 'Kevin Kiptoo', className: '5A', age: 11, lastUpdated: '4 days ago' },
  { id: 'STU012', name: 'Lucy Atieno', className: '4B', age: 9, lastUpdated: '1 day ago' },
]

const avatarPalette = ['blue', 'green', 'amber', 'coral', 'purple', 'teal']
const initials = (name: string) => name.split(' ').filter(Boolean).slice(0, 2).map((word) => word[0]).join('').toUpperCase()
const avatarTone = (student: DirectoryStudent) => avatarPalette[student.id.split('').reduce((sum, char) => sum + char.charCodeAt(0), 0) % avatarPalette.length]

function StudentAvatar({ student }: { student: DirectoryStudent }) {
  return <span className={`directory-avatar ${avatarTone(student)}`} aria-hidden="true">{initials(student.name)}</span>
}

export default function StudentsDirectory() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [classFilter, setClassFilter] = useState('All Classes')
  const filtered = useMemo(() => directoryStudents.filter((student) => {
    const matchesQuery = `${student.name} ${student.id}`.toLowerCase().includes(query.toLowerCase())
    return matchesQuery && (classFilter === 'All Classes' || student.className === classFilter)
  }), [query, classFilter])

  return <div className="directory-shell">
    <div className="directory-main">
      <header className="directory-header">
        <div><p className="eyebrow">LEARNER DIRECTORY</p><h1>Students</h1><p>Manage and explore your learners</p></div>
        <div className="directory-controls"><label className="directory-search"><Search aria-hidden="true" /><span className="sr-only">Search students</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name or ID..." /></label><label className="directory-filter"><SlidersHorizontal aria-hidden="true" /><span className="sr-only">Filter by class</span><select value={classFilter} onChange={(event) => setClassFilter(event.target.value)}><option>All Classes</option><option>4A</option><option>4B</option><option>5A</option></select></label></div>
      </header>
      <div className="directory-table-wrap">
        <table className="directory-table"><thead><tr><th>Name</th><th>Student ID</th><th>Class</th><th>Age</th><th>Last Updated</th><th><span className="sr-only">Open profile</span></th></tr></thead><tbody>
          {filtered.map((student) => <tr key={student.id} onClick={() => router.push(`/students/${student.id}`)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') router.push(`/students/${student.id}`) }}><td><div className="directory-name"><StudentAvatar student={student} /><strong>{student.name}</strong></div></td><td>{student.id}</td><td>{student.className}</td><td>{student.age}</td><td>{student.lastUpdated}</td><td><ChevronRight className="directory-chevron" aria-hidden="true" /></td></tr>)}
        </tbody></table>
        {!filtered.length && <div className="directory-empty"><Search aria-hidden="true" /><strong>No students found</strong><span>Try another name, student ID, or class.</span><button onClick={() => { setQuery(''); setClassFilter('All Classes') }}>Clear filters</button></div>}
      </div>
    </div>
  </div>
}

export function getStudentById(id: string) {
  return directoryStudents.find((student) => student.id.toLowerCase() === id.toLowerCase()) ?? directoryStudents[0]
}
