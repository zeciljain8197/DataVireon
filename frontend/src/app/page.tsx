"use client"
import Link from "next/link"
import { useState, useEffect } from "react"
import { supabase, signInWithGitHub } from "@/lib/supabase"

const ROLES = [
  { id: "data_engineer",  label: "Data Engineer",  color: "text-blue-400",   bg: "bg-blue-900/30 border-blue-800" },
  { id: "sde",            label: "SDE",             color: "text-purple-400", bg: "bg-purple-900/30 border-purple-800" },
  { id: "data_analyst",   label: "Data Analyst",    color: "text-teal-400",   bg: "bg-teal-900/30 border-teal-800" },
  { id: "mle",            label: "MLE",             color: "text-pink-400",   bg: "bg-pink-900/30 border-pink-800" },
  { id: "data_scientist", label: "Data Scientist",  color: "text-amber-400",  bg: "bg-amber-900/30 border-amber-800" },
]

const FEATURES = [
  {
    icon: "⚡",
    title: "Role-aware diagnosis",
    desc: "DataVireon understands your exact role. A Data Engineer gets pipeline and schema analysis. An MLE gets model drift and serving skew detection. Same codebase, completely different lens."
  },
  {
    icon: "🔬",
    title: "40 expert skill modules",
    desc: "Every role x domain combination has a deeply engineered expert prompt — from Airflow DAG failures to CUDA memory issues to SQL cartesian joins. Not generic AI advice."
  },
  {
    icon: "🔀",
    title: "Three resolution modes",
    desc: "Let AI fix everything automatically, walk through changes step by step with full approval control, or get a prioritised advisory report with no code changes."
  },
  {
    icon: "🐙",
    title: "GitHub repo integration",
    desc: "Connect any GitHub repo and browse files directly. Select the files you want analyzed — no copy-pasting entire codebases."
  },
  {
    icon: "📋",
    title: "Incident runbooks",
    desc: "Every resolved session generates a production-ready incident runbook in markdown. Ready to paste into Notion, Confluence, or your internal wiki."
  },
  {
    icon: "🕓",
    title: "Session history",
    desc: "Every diagnostic and resolution step is saved. Resume where you left off, review past fixes, or share sessions with your team."
  },
]

const DOMAINS = [
  { label: "Pipeline debugger",    color: "bg-blue-900 text-blue-200" },
  { label: "Schema & quality",     color: "bg-purple-900 text-purple-200" },
  { label: "Performance & cost",   color: "bg-orange-900 text-orange-200" },
  { label: "Model health",         color: "bg-pink-900 text-pink-200" },
  { label: "Security & compliance",color: "bg-red-900 text-red-200" },
  { label: "Code quality",         color: "bg-green-900 text-green-200" },
  { label: "Env & infra",          color: "bg-yellow-900 text-yellow-200" },
  { label: "Testing & CI/CD",      color: "bg-teal-900 text-teal-200" },
]

const STEPS = [
  { num: "01", title: "Select your role", desc: "Tell DataVireon whether you are a Data Engineer, SDE, MLE, Data Analyst, or Data Scientist. Everything adapts to your context." },
  { num: "02", title: "Add your code", desc: "Paste a snippet, upload files, or connect your GitHub repo and browse files directly." },
  { num: "03", title: "Describe the problem", desc: "Explain what is going wrong. Include error messages, symptoms, or just describe the unexpected behavior." },
  { num: "04", title: "Run diagnostic", desc: "DataVireon analyzes your code through the lens of your role, classifies the problem domain, and generates a structured diagnostic report." },
  { num: "05", title: "Choose your resolution mode", desc: "Automatic, semi-automatic with step approval, or advisory recommendations only. You decide how much control you want." },
  { num: "06", title: "Get your fix", desc: "Receive patched code, a step-by-step resolution trail, and a production-ready incident runbook. All saved to your session history." },
]

export default function Landing() {
  const [activeRole, setActiveRole] = useState(0)
  const [user, setUser] = useState<any>(null)

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveRole(r => (r + 1) % ROLES.length)
    }, 2000)
    supabase.auth.getUser().then(({ data }) => setUser(data.user))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      setUser(session?.user ?? null)
    })
    return () => { clearInterval(interval); subscription.unsubscribe() }
  }, [])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">

      {/* Nav */}
      <nav className="border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-white font-semibold text-lg tracking-tight">DataVireon</span>
          <span className="text-xs text-gray-500 border border-gray-700 px-2 py-0.5 rounded-full">beta</span>
        </div>
        <div className="flex items-center gap-4">
          {user ? (
            <Link href="/app"
              className="text-sm px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-all">
              Go to app →
            </Link>
          ) : (
            <button onClick={signInWithGitHub}
              className="text-sm px-4 py-2 rounded-lg bg-white text-gray-900 font-medium hover:bg-gray-100 transition-all flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
              </svg>
              Sign in with GitHub
            </button>
          )}
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-5xl mx-auto px-6 pt-24 pb-20 text-center">
        <div className="inline-flex items-center gap-2 bg-indigo-950 border border-indigo-800 rounded-full px-4 py-1.5 text-xs text-indigo-300 mb-8">
          <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse" />
          AI-powered problem resolution for data and engineering teams
        </div>
        <h1 className="text-5xl sm:text-6xl font-semibold tracking-tight text-white mb-6 leading-tight">
          Fix data and engineering<br />
          problems <span className="text-indigo-400">10x faster</span>
        </h1>
        <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-10 leading-relaxed">
          DataVireon diagnoses your codebase through the lens of your exact role,
          then walks you through production-grade fixes — step by step or all at once.
        </p>
        <div className="flex items-center justify-center gap-4 flex-wrap">
          {user ? (
            <Link href="/app"
              className="px-8 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-all text-sm">
              Go to app →
            </Link>
          ) : (
            <button onClick={signInWithGitHub}
              className="px-8 py-3.5 rounded-xl bg-white text-gray-900 hover:bg-gray-100 font-medium transition-all text-sm flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
              </svg>
              Sign in with GitHub
            </button>
          )}
          <a href="#how-it-works"
            className="px-8 py-3.5 rounded-xl border border-gray-700 text-gray-300 hover:border-gray-500 hover:text-white font-medium transition-all text-sm">
            See how it works ↓
          </a>
        </div>

        {/* Role pills rotating */}
        <div className="flex items-center justify-center gap-2 mt-12 flex-wrap">
          <span className="text-sm text-gray-500">Built for</span>
          {ROLES.map((r, i) => (
            <span key={r.id}
              className={"text-xs px-3 py-1.5 rounded-full border transition-all duration-500 " + (i === activeRole
                ? r.bg + " " + r.color + " border-opacity-100"
                : "border-gray-800 text-gray-600")}>
              {r.label}
            </span>
          ))}
        </div>
      </section>

      {/* Domain modules */}
      <section className="border-y border-gray-800 bg-gray-900/50 py-8">
        <div className="max-w-5xl mx-auto px-6">
          <p className="text-xs uppercase tracking-widest text-gray-500 mb-4 text-center">8 specialised problem domains</p>
          <div className="flex flex-wrap gap-2 justify-center">
            {DOMAINS.map(d => (
              <span key={d.label} className={"text-xs px-3 py-1.5 rounded-full font-medium " + d.color}>
                {d.label}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-5xl mx-auto px-6 py-24">
        <p className="text-xs uppercase tracking-widest text-gray-500 mb-3 text-center">Why DataVireon</p>
        <h2 className="text-3xl font-semibold text-white text-center mb-16">
          Not a chatbot. A resolution platform.
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map(f => (
            <div key={f.title} className="bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition-all">
              <div className="text-2xl mb-4">{f.icon}</div>
              <h3 className="text-white font-medium mb-2">{f.title}</h3>
              <p className="text-gray-400 text-sm leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-gray-800 bg-gray-900/30 py-24">
        <div className="max-w-4xl mx-auto px-6" id="how-it-works">
          <p className="text-xs uppercase tracking-widest text-gray-500 mb-3 text-center">How it works</p>
          <h2 className="text-3xl font-semibold text-white text-center mb-16">From problem to fix in minutes</h2>
          <div className="space-y-6">
            {STEPS.map(s => (
              <div key={s.num} className="flex gap-6 items-start">
                <span className="text-3xl font-bold text-gray-800 flex-shrink-0 w-12">{s.num}</span>
                <div className="pt-1">
                  <h3 className="text-white font-medium mb-1">{s.title}</h3>
                  <p className="text-gray-400 text-sm leading-relaxed">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Resolution modes */}
      <section className="max-w-5xl mx-auto px-6 py-24">
        <p className="text-xs uppercase tracking-widest text-gray-500 mb-3 text-center">Resolution modes</p>
        <h2 className="text-3xl font-semibold text-white text-center mb-16">You choose how much control you want</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="text-xs text-green-400 font-medium uppercase tracking-widest mb-3">Fully automatic</div>
            <h3 className="text-white font-medium mb-3">AI fixes everything</h3>
            <p className="text-gray-400 text-sm leading-relaxed">
              DataVireon analyzes all issues and applies every fix at once.
              Returns a fully patched codebase ready to copy or commit.
              Best for well-understood, isolated problems.
            </p>
          </div>
          <div className="bg-gray-900 border border-indigo-800 rounded-xl p-6 relative">
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 text-xs bg-indigo-600 text-white px-3 py-1 rounded-full">Recommended</div>
            <div className="text-xs text-indigo-400 font-medium uppercase tracking-widest mb-3">Semi-automatic</div>
            <h3 className="text-white font-medium mb-3">Step-by-step with approval</h3>
            <p className="text-gray-400 text-sm leading-relaxed">
              Walk through each fix with full visibility. Approve, reject, or
              override with your own instructions at every checkpoint.
              Best for production systems and learning.
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="text-xs text-amber-400 font-medium uppercase tracking-widest mb-3">Advisory only</div>
            <h3 className="text-white font-medium mb-3">Recommendations, you act</h3>
            <p className="text-gray-400 text-sm leading-relaxed">
              Get a prioritised list of issues with severity, effort estimates,
              and exact action steps. No code changes made.
              Best for audits, code reviews, and planning.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-gray-800 bg-gray-900/50 py-24">
        <div className="max-w-2xl mx-auto px-6 text-center">
          <h2 className="text-3xl font-semibold text-white mb-4">Ready to fix your first issue?</h2>
          <p className="text-gray-400 mb-8">Free to use. No credit card required. Sign in with GitHub and start in seconds.</p>
          <Link href="/"
            className="inline-block px-10 py-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-all text-sm">
            Open DataVireon →
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-800 px-6 py-8">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-gray-500 text-sm font-medium">DataVireon</span>
            <span className="text-xs text-gray-700 border border-gray-800 px-2 py-0.5 rounded-full">beta</span>
          </div>
          <div className="flex gap-4">
            <Link href="/app" className="text-xs text-gray-600 hover:text-gray-400 transition-all">Launch app</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
