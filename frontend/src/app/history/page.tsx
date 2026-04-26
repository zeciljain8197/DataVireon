"use client"
import Navbar from "@/components/Navbar"
import { useState, useEffect } from "react"
import { supabase } from "@/lib/supabase"
import Link from "next/link"

const DOMAIN_COLORS: Record<string,string> = {
  pipeline:       "bg-blue-900 text-blue-200",
  schema_quality: "bg-purple-900 text-purple-200",
  performance:    "bg-orange-900 text-orange-200",
  model_health:   "bg-pink-900 text-pink-200",
  security:       "bg-red-900 text-red-200",
  code_quality:   "bg-green-900 text-green-200",
  environment:    "bg-yellow-900 text-yellow-200",
  testing:        "bg-teal-900 text-teal-200",
}

const SEVERITY_COLORS: Record<string,string> = {
  critical: "text-red-400",
  high:     "text-orange-400",
  medium:   "text-yellow-400",
  low:      "text-green-400",
}

export default function History() {
  const [sessions, setSessions]     = useState<any[]>([])
  const [loading, setLoading]       = useState(true)
  const [userId, setUserId]         = useState<string | null>(null)
  const [selected, setSelected]     = useState<any>(null)
  const [steps, setSteps]           = useState<any[]>([])
  const [stepsLoading, setStepsLoading] = useState(false)

  useEffect(() => {
    supabase.auth.getUser().then(async ({ data }) => {
      if (!data.user) { setLoading(false); return }
      setUserId(data.user.id)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/sessions/${data.user.id}`)
      const json = await res.json()
      setSessions(json.sessions || [])
      setLoading(false)
    })
  }, [])

  async function openSession(session: any) {
    setSelected(session)
    setStepsLoading(true)
    setSteps([])
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/session/${session.id}/steps`)
    const json = await res.json()
    setSteps(json.steps || [])
    setStepsLoading(false)
  }

  if (loading) return (
    <>
    <Navbar />
    <main className="max-w-4xl mx-auto px-4 py-10">
      <div className="space-y-3">
        {[1,2,3].map(i => (
          <div key={i} className="h-20 bg-gray-900 rounded-xl animate-pulse" />
        ))}
      </div>
    </main>
    </>
  )

  if (!userId) return (
    <>
    <Navbar />
    <main className="max-w-4xl mx-auto px-4 py-10">
      <div className="text-center py-20">
        <p className="text-gray-400 mb-4">Sign in to view your session history</p>
        <Link href="/app" className="text-indigo-400 hover:text-indigo-300 text-sm">← Back to home</Link>
      </div>
    </main>
    </>
  )

  if (selected) return (
    <>
    <Navbar />
    <main className="max-w-4xl mx-auto px-4 py-10">
      <button onClick={() => { setSelected(null); setSteps([]) }}
        className="text-sm text-gray-500 hover:text-gray-300 mb-6 flex items-center gap-2 transition-all">
        ← Back to history
      </button>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-6">
        <div className="flex items-center gap-3 mb-3">
          {selected.domain && (
            <span className={"text-xs px-2 py-0.5 rounded font-medium " + (DOMAIN_COLORS[selected.domain] || "bg-gray-800 text-gray-300")}>
              {selected.domain.replace("_"," ")}
            </span>
          )}
          {selected.diagnostic_report?.severity && (
            <span className={"text-xs font-semibold uppercase " + (SEVERITY_COLORS[selected.diagnostic_report.severity] || "text-gray-400")}>
              {selected.diagnostic_report.severity}
            </span>
          )}
          <span className="text-xs text-gray-600 capitalize ml-auto">{selected.role?.replace("_"," ")}</span>
        </div>
        <p className="text-white font-medium mb-2">{selected.problem_statement}</p>
        {selected.diagnostic_report?.summary && (
          <p className="text-gray-400 text-sm leading-relaxed mb-4">{selected.diagnostic_report.summary}</p>
        )}
        {selected.diagnostic_report?.symptoms?.length > 0 && (
          <div className="mb-4">
            <p className="text-xs text-gray-600 uppercase tracking-widest mb-2">Symptoms</p>
            <ul className="space-y-1">
              {selected.diagnostic_report.symptoms.map((s: string, i: number) => (
                <li key={i} className="text-sm text-gray-300 flex gap-2">
                  <span className="text-indigo-400">—</span>{s}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex items-center gap-3 pt-3 border-t border-gray-800">
          <span className="text-xs text-gray-600">
            {new Date(selected.created_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })}
          </span>
          <span className={"text-xs px-2 py-0.5 rounded ml-auto " + (selected.status === "completed" ? "bg-green-900 text-green-300" : "bg-gray-800 text-gray-400")}>
            {selected.status}
          </span>
        </div>
      </div>

      <div>
        <p className="text-xs uppercase tracking-widest text-gray-500 mb-3">Resolution steps</p>
        {stepsLoading ? (
          <div className="space-y-2">
            {[1,2].map(i => <div key={i} className="h-16 bg-gray-900 rounded-lg animate-pulse" />)}
          </div>
        ) : steps.length === 0 ? (
          <div className="text-center py-10 border border-gray-800 rounded-xl">
            <p className="text-gray-600 text-sm">No resolution steps recorded</p>
          </div>
        ) : (
          <div className="space-y-3">
            {steps.map((s: any, i: number) => (
              <div key={i} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-xs text-gray-600">Step {s.step_number}</span>
                  <span className={"text-xs font-medium px-2 py-0.5 rounded " + (
                    s.user_decision === "approved" ? "bg-green-900 text-green-300" :
                    s.user_decision === "rejected" ? "bg-gray-800 text-gray-400" :
                    "bg-indigo-900 text-indigo-300"
                  )}>
                    {s.user_decision}
                  </span>
                </div>
                <p className="text-gray-300 text-sm mb-3">{s.ai_explanation}</p>
                {s.proposed_diff && (
                  <pre className="bg-gray-950 border border-gray-800 rounded-lg p-3 text-xs font-mono text-green-300 overflow-x-auto whitespace-pre-wrap">
                    {s.proposed_diff}
                  </pre>
                )}
                {s.override_prompt && (
                  <p className="text-xs text-indigo-400 mt-2">Override: {s.override_prompt}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-6">
        <Link href="/app"
          className="w-full block text-center py-2.5 rounded-lg border border-gray-700 text-gray-400 hover:border-indigo-500 hover:text-indigo-400 text-sm font-medium transition-all">
          Start new session →
        </Link>
      </div>
    </main>
    </>
  )

  return (
    <>
    <Navbar />
    <main className="max-w-4xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-white">Session history</h1>
          <p className="text-gray-500 text-sm mt-1">{sessions.length} sessions saved</p>
        </div>
        <Link href="/app"
          className="text-sm px-4 py-2 rounded-lg border border-gray-700 text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-all">
          + New session
        </Link>
      </div>

      {sessions.length === 0 ? (
        <div className="text-center py-20 border border-gray-800 rounded-xl">
          <p className="text-gray-500 mb-4">No sessions yet</p>
          <Link href="/app" className="text-indigo-400 hover:text-indigo-300 text-sm">Start your first diagnostic →</Link>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map((s: any) => (
            <button key={s.id} onClick={() => openSession(s)}
              className="w-full bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-600 transition-all text-left">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    {s.domain && (
                      <span className={"text-xs px-2 py-0.5 rounded font-medium " + (DOMAIN_COLORS[s.domain] || "bg-gray-800 text-gray-300")}>
                        {s.domain.replace("_"," ")}
                      </span>
                    )}
                    {s.diagnostic_report?.severity && (
                      <span className={"text-xs font-medium uppercase " + (SEVERITY_COLORS[s.diagnostic_report.severity] || "text-gray-400")}>
                        {s.diagnostic_report.severity}
                      </span>
                    )}
                    <span className="text-xs text-gray-600 capitalize">{s.role?.replace("_"," ")}</span>
                  </div>
                  <p className="text-gray-200 text-sm font-medium truncate">{s.problem_statement}</p>
                  {s.diagnostic_report?.summary && (
                    <p className="text-gray-500 text-xs mt-1 line-clamp-2">{s.diagnostic_report.summary}</p>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-xs text-gray-600">
                    {new Date(s.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </p>
                  <span className={"text-xs mt-1 inline-block px-2 py-0.5 rounded " + (s.status === "completed" ? "bg-green-900 text-green-300" : "bg-gray-800 text-gray-400")}>
                    {s.status}
                  </span>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </main>
    </>
  )
}
