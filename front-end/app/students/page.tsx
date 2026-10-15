'use client'

import StudentsDirectory from '@/components/students-directory'
import { AppSidebar } from '@/components/student-profile'

export default function StudentsPage() {
  return <div className="app-shell"><AppSidebar onUpdate={() => {}} /><StudentsDirectory /></div>
}
