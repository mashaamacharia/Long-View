import StudentProfile from '@/components/student-profile'

export default async function StudentRoutes({ params }: { params: Promise<{ slug?: string[] }> }) {
  const routeParams = await params
  return <StudentProfile studentId={routeParams.slug?.[0]} />
}
