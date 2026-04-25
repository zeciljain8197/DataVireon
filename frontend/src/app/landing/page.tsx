"use client"
import Link from "next/link"
import { useState, useEffect } from "react"

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

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveRole(r => (r + 1) % ROLES.length)
    }, 2000)
    return () => clearInterval(interval)
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
          <Link href="/history" className="text-sm text-gray-400 hover:text-gray-200 transition-all">History</Link>
          <Link href="/"
            className="text-sm px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-all">
            Open app →
          </Link>
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
          <Link href="/"
            className="px-8 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-all text-sm">
            Start for free →
          </Link>
          <Link href="/history"
            className="px-8 py-3.5 rounded-xl border border-gray-700 text-gray-300 hover:border-gray-500 hover:text-white font-medium transition-all text-sm">
            View session history
          </Link>
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
        <div className="max-w-4xl mx-auto px-6">
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
          <p className="text-xs text-gray-700">Built for data and engineering teams</p>
        </div>
      </footer>
    </div>
  )
}
