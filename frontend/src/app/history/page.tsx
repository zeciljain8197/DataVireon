"use client"
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
  const [sessions, setSessions]   = useState<any[]>([])
  const [loading, setLoading]     = useState(true)
  const [userId, setUserId]       = useState<string | null>(null)

  useEffect(() => {
    supabase.auth.getUser().then(async ({ data }) => {
      if (!data.user) { setLoading(false); return }
      setUserId(data.user.id)
      const res = await fetch(`http://localhost:8000/sessions/${data.user.id}`)
      const json = await res.json()
      setSessions(json.sessions || [])
      setLoading(false)
    })
  }, [])

  if (loading) return (
    <main className="max-w-4xl mx-auto px-4 py-10">
      <div className="space-y-3">
        {[1,2,3].map(i => (
          <div key={i} className="h-20 bg-gray-900 rounded-xl animate-pulse" />
        ))}
      </div>
    </main>
  )

  if (!userId) return (
    <main className="max-w-4xl mx-auto px-4 py-10">
      <div className="text-center py-20">
        <p className="text-gray-400 mb-4">Sign in to view your session history</p>
        <Link href="/" className="text-indigo-400 hover:text-indigo-300 text-sm">← Back to home</Link>
      </div>
    </main>
  )

  return (
    <main className="max-w-4xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-white">Session history</h1>
          <p className="text-gray-500 text-sm mt-1">{sessions.length} sessions saved</p>
        </div>
        <Link href="/"
          className="text-sm px-4 py-2 rounded-lg border border-gray-700 text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-all">
          + New session
        </Link>
      </div>

      {sessions.length === 0 ? (
        <div className="text-center py-20 border border-gray-800 rounded-xl">
          <p className="text-gray-500 mb-4">No sessions yet</p>
          <Link href="/" className="text-indigo-400 hover:text-indigo-300 text-sm">Start your first diagnostic →</Link>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map((s: any) => (
            <div key={s.id} className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition-all">
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
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
