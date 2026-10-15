'use client'

import { FormEvent, useState } from 'react'
import Image from 'next/image'
import { BookOpen, Eye, EyeOff, LockKeyhole } from 'lucide-react'
import { useRouter } from 'next/navigation'

function LongViewLogo() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex size-10 items-center justify-center rounded-xl bg-[#102B4E] text-white shadow-sm">
        <BookOpen aria-hidden="true" className="size-5" strokeWidth={1.8} />
      </div>
      <div className="flex flex-col gap-0.5">
        <span className="text-[18px] font-semibold tracking-[-0.02em] text-[#102B4E]">The Long View</span>
        <span className="text-[11px] font-medium text-[#2878E5]">Every learner. A fuller picture.</span>
      </div>
    </div>
  )
}

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const router=useRouter()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')

    if (!email.trim() || !email.includes('@')) {
      setError('Enter a valid school email address.')
      return
    }
    if (!password) {
      setError('Enter your password to continue.')
      return
    }

    setIsSubmitting(true)
    window.setTimeout(() => {
      setIsSubmitting(false)
      router.push('/students')
      // setError('Sign-in is not configured for this preview yet. Connect your authentication provider to continue.')
    }, 500)
  }

  return (
    <main className="min-h-svh bg-white text-[#172B4D] lg:grid lg:grid-cols-[45%_55%]">
      <section className="relative flex min-h-[500px] flex-col overflow-hidden bg-[#EDF5FC] px-7 py-8 sm:px-10 lg:min-h-svh lg:px-12 lg:py-10" aria-labelledby="welcome-heading">
        <LongViewLogo />
        <div className="relative z-10 mt-14 max-w-[330px] sm:mt-20 lg:mt-[17vh]">
          <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#2878E5]">Learner intelligence for educators</p>
          <h1 id="welcome-heading" className="max-w-[310px] text-[32px] font-bold leading-[1.08] tracking-[-0.04em] text-[#102B4E] sm:text-[38px] lg:text-[34px]">Better decisions.<br />Brighter futures.</h1>
          <p className="mt-5 max-w-[310px] text-[14px] leading-6 text-[#718096]">An AI-powered learner profile that helps teachers understand each student&apos;s journey over time.</p>
        </div>
        <div className="pointer-events-none mt-auto flex justify-center pt-10 lg:absolute lg:inset-x-0 lg:bottom-0 lg:pt-0">
          <Image src="/long-view-welcome.png" alt="A teacher helping a student with schoolwork" width={760} height={520} priority className="h-auto w-full max-w-[560px] object-contain object-bottom lg:max-h-[44vh] lg:w-[115%] lg:max-w-none" />
        </div>
      </section>

      <section className="flex min-h-[560px] items-center justify-center border-l border-[#E2EAF3] bg-white px-6 py-12 sm:px-10 lg:min-h-svh lg:px-12">
        <div className="w-full max-w-[390px]">
          <div className="mb-8">
            <h2 className="text-[28px] font-semibold tracking-[-0.03em] text-[#102B4E]">Welcome back</h2>
            <p className="mt-2 text-[14px] text-[#718096]">Sign in to access learner profiles and insights.</p>
          </div>

          <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5" aria-describedby={error ? 'login-error' : notice ? 'login-notice' : undefined}>
            <div className="flex flex-col gap-2">
              <label htmlFor="email" className="text-[13px] font-semibold text-[#172B4D]">Email address</label>
              <input id="email" name="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@school.org" className="h-11 rounded-md border border-[#E2EAF3] bg-white px-3 text-[14px] outline-none transition placeholder:text-[#A0AEC0] focus:border-[#2878E5] focus:ring-4 focus:ring-[#2878E5]/10" />
            </div>
            <div className="flex flex-col gap-2">
              <label htmlFor="password" className="text-[13px] font-semibold text-[#172B4D]">Password</label>
              <div className="relative">
                <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" className="h-11 w-full rounded-md border border-[#E2EAF3] bg-white px-3 pr-11 text-[14px] outline-none transition placeholder:text-[#A0AEC0] focus:border-[#2878E5] focus:ring-4 focus:ring-[#2878E5]/10" />
                <button type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? 'Hide password' : 'Show password'} className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center rounded-r-md text-[#718096] transition hover:text-[#2878E5] focus:outline-none focus:ring-2 focus:ring-inset focus:ring-[#2878E5]">
                  {showPassword ? <EyeOff aria-hidden="true" className="size-[17px]" /> : <Eye aria-hidden="true" className="size-[17px]" />}
                </button>
              </div>
            </div>

            {error ? <p id="login-error" role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-[12px] leading-5 text-red-700">{error}</p> : null}
            {notice ? <p id="login-notice" role="status" className="rounded-md border border-[#BFE8D8] bg-[#F0FBF6] px-3 py-2.5 text-[12px] leading-5 text-[#16704F]">{notice}</p> : null}

            <button type="submit" disabled={isSubmitting} className="h-11 rounded-md bg-[#2878E5] px-4 text-[14px] font-semibold text-white transition hover:bg-[#245DA8] focus:outline-none focus:ring-4 focus:ring-[#2878E5]/20 disabled:cursor-not-allowed disabled:opacity-60">{isSubmitting ? 'Signing in…' : 'Log in'}</button>
            <button type="button" onClick={() => setNotice('Password recovery will be available once authentication is connected.')} className="-mt-1 self-center text-[12px] font-medium text-[#2878E5] underline-offset-4 hover:underline focus:outline-none focus:ring-2 focus:ring-[#2878E5]">Forgot password?</button>
          </form>

          <div className="mt-12 flex items-center justify-center gap-2 text-[11px] text-[#718096]"><LockKeyhole aria-hidden="true" className="size-3.5" /> Secure access to your learner profiles</div>
        </div>
      </section>
    </main>
  )
}
