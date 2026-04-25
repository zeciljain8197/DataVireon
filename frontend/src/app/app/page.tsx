"use client"
import Navbar from "@/components/Navbar"
import { useState, useEffect, useRef } from "react"
import { supabase } from "@/lib/supabase"

const ROLES = [
  { id: "data_engineer",  label: "Data Engineer",  desc: "Pipelines, ETL, orchestration" },
  { id: "sde",            label: "SDE",             desc: "APIs, architecture, code quality" },
  { id: "data_analyst",   label: "Data Analyst",    desc: "SQL, BI, reporting" },
  { id: "mle",            label: "MLE",             desc: "ML pipelines, model health" },
  { id: "data_scientist", label: "Data Scientist",  desc: "Stats, experimentation, EDA" },
]

const MODES = [
  { id: "automatic", label: "Fully automatic", desc: "AI applies all fixes end-to-end" },
  { id: "semi_auto", label: "Semi-automatic",  desc: "Step checkpoints, you choose" },
  { id: "advisory",  label: "Advisory only",   desc: "Recommendations, you act" },
]

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

const API = "http://localhost:8000"

export default function Home() {
  const [role, setRole]               = useState("")
  const [mode, setMode]               = useState("semi_auto")
  const [activeResult, setActiveResult] = useState<"semi"|"auto"|"advisory"|null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [requestCount, setRequestCount] = useState(0)
  const [codebase, setCodebase]       = useState("")
  const [problem, setProblem]         = useState("")
  const [loading, setLoading]         = useState(false)
  const [diagnostic, setDiagnostic]   = useState<any>(null)
  const [rawStream, setRawStream]     = useState("")
  const [step, setStep]               = useState<any>(null)
  const [stepNum, setStepNum]         = useState(1)
  const [prevSteps, setPrevSteps]     = useState<any[]>([])
  const [override, setOverride]       = useState("")
  const [stepLoading, setStepLoading] = useState(false)
  const [userId, setUserId]           = useState<string | null>(null)
  const [sessionId, setSessionId]     = useState<string | null>(null)
  const [runbook, setRunbook]           = useState("")
  const [runbookLoading, setRunbookLoading] = useState(false)
  const [repoUrl, setRepoUrl]           = useState("")
  const [repoFiles, setRepoFiles]       = useState<any[]>([])
  const [repoLoading, setRepoLoading]   = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [repoOwner, setRepoOwner]       = useState("")
  const [showRepo, setShowRepo]         = useState(false)
  const [advisory, setAdvisory]         = useState<any>(null)
  const [advisoryLoading, setAdvisoryLoading] = useState(false)
  const [autoResult, setAutoResult]     = useState<any>(null)
  const [autoLoading, setAutoLoading]   = useState(false)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setUserId(data.user?.id ?? null)
      console.log("Auth user ID:", data.user?.id)
    })
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      setUserId(session?.user?.id ?? null)
      console.log("Auth state changed, user ID:", session?.user?.id)
    })
    return () => subscription.unsubscribe()
  }, [])

  async function runDiagnostic() {
    if (!role || !codebase.trim() || !problem.trim()) return
    setLoading(true)
    setRawStream("")
    setDiagnostic(null)
    setStep(null)
    setPrevSteps([])
    setStepNum(1)
    setSessionId(null)
    let full = ""
    try {
      const res = await fetch(API + "/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codebase, role, problem, user_id: userId }),
        signal: abortRef.current?.signal,
      })
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        full += dec.decode(value)
        setRawStream(full)
      }
      const match = full.match(/\{[\s\S]*\}/)
      if (match) {
        const diag = JSON.parse(match[0])
        setRawStream("")
        setActiveResult(null)
        setStep(null)
        setAutoResult(null)
        setAdvisory(null)
        setPrevSteps([])
        setStepNum(1)
        setRunbook("")
        setRequestCount(c => c + 1)
        setDiagnostic(diag)
        if (userId) {
          const saved = await fetch(API + "/session/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              user_id: userId,
              role,
              problem,
              domain: diag.domain,
              resolution_mode: mode,
              diagnostic_report: diag,
            }),
          })
          const savedData = await saved.json()
          setSessionId(savedData.session_id)
        }
      }
    } catch(e) { console.error(e) }
    setLoading(false)
  }

  async function runStep(currentNum?: number, currentPrev?: any[]) {
    setStepLoading(true)
    setStep(null)
    setRawStream("")
    const num  = currentNum  ?? stepNum
    const prev = currentPrev ?? prevSteps
    let full = ""
    try {
      const res = await fetch(API + "/resolve/step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId ?? "local-session",
          codebase, role, problem,
          diagnostic: JSON.stringify(diagnostic),
          mode,
          step_number: num,
          previous_steps: prev,
          override_prompt: override || null,
          user_id: userId,
        }),
      })
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        full += dec.decode(value)
        setRawStream(full)
      }
      const match = full.match(/\{[\s\S]*\}/)
      if (match) {
        setStep(JSON.parse(match[0]))
        setActiveResult("semi")
      }
    } catch(e) { console.error(e) }
    setStepLoading(false)
    setOverride("")
  }

  async function saveStep(decision: string, currentStep: any, num: number) {
    if (!sessionId || !currentStep) return
    await fetch(API + "/session/step/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        step_number: num,
        ai_explanation: currentStep.explanation,
        proposed_diff: currentStep.diff,
        user_decision: decision,
        override_prompt: override || null,
      }),
    })
  }

  function approveStep() {
    if (!step) return
    saveStep("approved", step, stepNum)
    const newPrev = [...prevSteps, { step_number: stepNum, explanation: step.explanation, decision: "approved" }]
    setPrevSteps(newPrev)
    const newNum = stepNum + 1
    setStepNum(newNum)
    setStep(null)
    if (!step.is_final) runStep(newNum, newPrev)
  }

  function rejectStep() {
    if (!step) return
    saveStep("rejected", step, stepNum)
    const newPrev = [...prevSteps, { step_number: stepNum, explanation: step.explanation, decision: "rejected" }]
    setPrevSteps(newPrev)
    setStep(null)
    setRawStream("")
  }

  function resetAll() {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setLoading(false)
    setStepLoading(false)
    setAutoLoading(false)
    setAdvisoryLoading(false)
    setRunbookLoading(false)
    setDiagnostic(null)
    setStep(null)
    setAutoResult(null)
    setAdvisory(null)
    setPrevSteps([])
    setStepNum(1)
    setOverride("")
    setRunbook("")
    setRawStream("")
    setSessionId(null)
    setActiveResult(null)
    setCodebase("")
    setProblem("")
    setRole("")
  }

  async function runAuto() {
    setAutoLoading(true)
    setAutoResult(null)
    let full = ""
    try {
      const res = await fetch("http://localhost:8000/resolve/auto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          codebase, role, problem,
          diagnostic,
          user_id: userId,
          session_id: sessionId,
        }),
      })
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        full += dec.decode(value)
        setRawStream(full)
      }
      const match = full.match(/\{[\s\S]*\}/)
      if (match) {
        setAutoResult(JSON.parse(match[0]))
        setActiveResult("auto")
      }
    } catch(e) { console.error(e) }
    setAutoLoading(false)
    setRawStream("")
  }

  async function runAdvisory() {
    setAdvisoryLoading(true)
    setAdvisory(null)
    let full = ""
    try {
      const res = await fetch("http://localhost:8000/advisory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codebase, role, problem, diagnostic }),
      })
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        full += dec.decode(value)
      }
      const match = full.match(/\{[\s\S]*\}/)
      if (match) {
        setAdvisory(JSON.parse(match[0]))
        setActiveResult("advisory")
      }
    } catch(e) { console.error(e) }
    setAdvisoryLoading(false)
  }

  async function fetchRepo() {
    if (!repoUrl.trim()) return
    setRepoLoading(true)
    setRepoFiles([])
    setSelectedFiles([])
    try {
      const res = await fetch("http://localhost:8000/github/tree", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl }),
      })
      const data = await res.json()
      if (data.files) {
        setRepoFiles(data.files)
        setRepoOwner(data.owner + "/" + data.repo)
      }
    } catch(e) { console.error(e) }
    setRepoLoading(false)
  }

  async function loadSelectedFiles() {
    if (!selectedFiles.length) return
    setRepoLoading(true)
    try {
      const res = await fetch("http://localhost:8000/github/contents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl, file_paths: selectedFiles }),
      })
      const data = await res.json()
      if (data.combined) {
        setCodebase(data.combined)
        setShowRepo(false)
      }
    } catch(e) { console.error(e) }
    setRepoLoading(false)
  }

  function toggleFile(path: string) {
    setSelectedFiles(prev =>
      prev.includes(path) ? prev.filter(p => p !== path) : [...prev, path]
    )
  }

  async function generateRunbook() {
    setRunbookLoading(true)
    setRunbook("")
    let full = ""
    try {
      const res = await fetch("http://localhost:8000/runbook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, problem, diagnostic, steps: prevSteps }),
      })
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        full += dec.decode(value)
        setRunbook(full)
      }
    } catch(e) { console.error(e) }
    setRunbookLoading(false)
  }


  return (
    <>
    <Navbar />
    <main className="max-w-4xl mx-auto px-4 py-10">
      <section className="mb-8">
        <p className="text-xs uppercase tracking-widest text-gray-500 mb-3">Select your role</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
          {ROLES.map(r => (
            <button key={r.id} onClick={() => setRole(r.id)}
              className={"p-3 rounded-lg border text-left transition-all " + (role === r.id
                ? "border-indigo-500 bg-indigo-950 text-white"
                : "border-gray-800 bg-gray-900 text-gray-400 hover:border-gray-600")}>
              <div className="text-sm font-medium">{r.label}</div>
              <div className="text-xs mt-0.5 opacity-60">{r.desc}</div>
            </button>
          ))}
        </div>
      </section>

      <section className="mb-6">
        <p className="text-xs uppercase tracking-widest text-gray-500 mb-3">Code source</p>
        <div className="flex gap-2 mb-3">
          <button onClick={() => setShowRepo(false)}
            className={"px-3 py-1.5 rounded-lg text-xs font-medium border transition-all " + (!showRepo ? "border-indigo-500 bg-indigo-950 text-white" : "border-gray-700 text-gray-500 hover:border-gray-600")}>
            Paste code
          </button>
          <button onClick={() => setShowRepo(true)}
            className={"px-3 py-1.5 rounded-lg text-xs font-medium border transition-all " + (showRepo ? "border-indigo-500 bg-indigo-950 text-white" : "border-gray-700 text-gray-500 hover:border-gray-600")}>
            Connect GitHub repo
          </button>
        </div>

        {showRepo && (
          <div className="mb-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex gap-2 mb-4">
              <input value={repoUrl} onChange={e => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-500" />
              <button onClick={fetchRepo} disabled={repoLoading || !repoUrl}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium transition-all">
                {repoLoading ? "Loading..." : "Browse"}
              </button>
            </div>

            {repoFiles.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs text-gray-500">{repoOwner} — {repoFiles.length} files — {selectedFiles.length} selected</p>
                  <button onClick={loadSelectedFiles} disabled={!selectedFiles.length || repoLoading}
                    className="text-xs px-3 py-1.5 rounded-lg bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white font-medium transition-all">
                    Load selected →
                  </button>
                </div>
                <div className="max-h-64 overflow-y-auto space-y-1">
                  {repoFiles.map((f: any) => (
                    <button key={f.path} onClick={() => toggleFile(f.path)}
                      className={"w-full text-left px-3 py-1.5 rounded-lg text-xs font-mono transition-all flex items-center justify-between " + (selectedFiles.includes(f.path) ? "bg-indigo-950 text-indigo-300 border border-indigo-700" : "text-gray-400 hover:bg-gray-800")}>
                      <span className="truncate">{f.path}</span>
                      <span className="text-gray-600 ml-2 flex-shrink-0">{f.type}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="mb-6">
        <p className="text-xs uppercase tracking-widest text-gray-500 mb-3">Paste your code or describe your setup</p>
        <textarea value={codebase} onChange={e => setCodebase(e.target.value)}
          rows={8} placeholder="Paste code, config, SQL, pipeline definition..."
          className="w-full bg-gray-900 border border-gray-800 rounded-lg p-4 text-sm font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none" />
      </section>

      <section className="mb-6">
        <p className="text-xs uppercase tracking-widest text-gray-500 mb-3">Describe the problem</p>
        <textarea value={problem} onChange={e => setProblem(e.target.value)}
          rows={3} placeholder="What is going wrong? Include any error messages..."
          className="w-full bg-gray-900 border border-gray-800 rounded-lg p-4 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none" />
      </section>

      <div className="flex gap-2">
        <button onClick={runDiagnostic} disabled={!role || !codebase || !problem || loading}
          className="flex-1 py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium transition-all text-sm">
          {loading ? "Analyzing..." : "Run diagnostic"}
        </button>
        {(loading || stepLoading || autoLoading || advisoryLoading || diagnostic) && (
          <button onClick={resetAll}
            className="px-4 py-3 rounded-lg border border-gray-700 text-gray-400 hover:border-red-700 hover:text-red-400 transition-all text-sm font-medium whitespace-nowrap">
            {(loading || stepLoading || autoLoading || advisoryLoading) ? "✕ Cancel" : "↺ Reset"}
          </button>
        )}
      </div>

      {requestCount > 0 && (
        <div className="mt-3 flex items-center justify-end gap-2">
          <span className="text-xs text-gray-600">{requestCount} diagnostic{requestCount !== 1 ? "s" : ""} run this session</span>
          <span className={"text-xs px-2 py-0.5 rounded " + (requestCount >= 8 ? "bg-orange-900 text-orange-300" : "bg-gray-800 text-gray-500")}>
            {10 - requestCount > 0 ? `${10 - requestCount} remaining` : "limit reached"}
          </span>
        </div>
      )}

      {loading && (
        <div className="mt-6 bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
            <div className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse delay-75" />
            <div className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse delay-150" />
            <span className="text-sm text-gray-400 ml-1">Analyzing your codebase...</span>
          </div>
          <div className="space-y-2">
            <div className="h-3 bg-gray-800 rounded animate-pulse w-3/4" />
            <div className="h-3 bg-gray-800 rounded animate-pulse w-1/2" />
            <div className="h-3 bg-gray-800 rounded animate-pulse w-2/3" />
          </div>
        </div>
      )}

      {diagnostic && !loading && (
        <div className="mt-8 bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <span className={"text-xs px-2 py-1 rounded font-medium " + (DOMAIN_COLORS[diagnostic.domain] || "bg-gray-800 text-gray-300")}>
              {diagnostic.domain?.replace("_"," ")}
            </span>
            <span className={"text-sm font-semibold uppercase " + (SEVERITY_COLORS[diagnostic.severity] || "text-gray-400")}>
              {diagnostic.severity}
            </span>
            <span className="ml-auto text-xs text-gray-500">{Math.round((diagnostic.confidence || 0) * 100)}% confidence</span>
          </div>
          <p className="text-gray-200 text-sm leading-relaxed mb-4">{diagnostic.summary}</p>
          {diagnostic.symptoms?.length > 0 && (
            <div className="mb-4">
              <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Symptoms detected</p>
              <ul className="space-y-1">
                {diagnostic.symptoms.map((s: string, i: number) => (
                  <li key={i} className="text-sm text-gray-300 flex gap-2"><span className="text-indigo-400">—</span>{s}</li>
                ))}
              </ul>
            </div>
          )}
          {diagnostic.affected_areas?.length > 0 && (
            <div className="mb-6">
              <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Affected areas</p>
              <div className="flex flex-wrap gap-2">
                {diagnostic.affected_areas.map((a: string, i: number) => (
                  <span key={i} className="text-xs bg-gray-800 text-gray-300 px-2 py-1 rounded">{a}</span>
                ))}
              </div>
            </div>
          )}
          {sessionId && (
            <p className="text-xs text-gray-600 mb-4">Session saved — ID: {sessionId.slice(0,8)}...</p>
          )}

          <div className="border-t border-gray-800 pt-5 mt-2">
            <p className="text-xs uppercase tracking-widest text-gray-500 mb-3">How do you want to resolve this?</p>
            <div className="grid grid-cols-3 gap-2 mb-4">
              {[
                { id: "automatic", label: "Fully automatic", desc: "AI applies all fixes" },
                { id: "semi_auto", label: "Semi-automatic",  desc: "Step checkpoints, you choose" },
                { id: "advisory",  label: "Advisory only",   desc: "Recommendations, you act" },
              ].map(m => (
                <button key={m.id} onClick={() => {
                  if (abortRef.current) { abortRef.current.abort(); abortRef.current = null }
                  setMode(m.id)
                  setActiveResult(null)
                  setStep(null)
                  setAutoResult(null)
                  setAdvisory(null)
                  setPrevSteps([])
                  setStepNum(1)
                  setRunbook("")
                  setStepLoading(false)
                  setAutoLoading(false)
                  setAdvisoryLoading(false)
                }}
                  className={"p-3 rounded-lg border text-left transition-all " + (mode === m.id
                    ? "border-indigo-500 bg-indigo-950 text-white"
                    : "border-gray-800 bg-gray-900 text-gray-400 hover:border-gray-600")}>
                  <div className="text-sm font-medium">{m.label}</div>
                  <div className="text-xs mt-0.5 opacity-60">{m.desc}</div>
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-600 mb-4">
              {mode === "advisory"
                ? "Receive a prioritised list of recommendations with severity, effort, and exact action steps. No code will be changed."
                : mode === "automatic"
                ? "AI applies every fix at once and returns a fully patched codebase ready to copy."
                : "Walk through fixes one step at a time. Approve, reject, or override each change before moving to the next."}
            </p>
            <div className="flex gap-2">
              {mode === "advisory" ? (
                <button onClick={runAdvisory} disabled={advisoryLoading}
                  className="flex-1 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium transition-all">
                  {advisoryLoading ? "Generating recommendations..." : "Get recommendations →"}
                </button>
              ) : mode === "automatic" ? (
                <button onClick={runAuto} disabled={autoLoading}
                  className="flex-1 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium transition-all">
                  {autoLoading ? "Applying all fixes..." : "Apply all fixes automatically →"}
                </button>
              ) : (
                <button onClick={() => runStep()} disabled={stepLoading}
                  className="flex-1 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium transition-all">
                  {stepLoading ? "Generating fix..." : "Start resolution →"}
                </button>
              )}
              {(advisoryLoading || autoLoading || stepLoading || activeResult) && (
                <button onClick={() => {
                  if (abortRef.current) { abortRef.current.abort(); abortRef.current = null }
                  setStepLoading(false)
                  setAutoLoading(false)
                  setAdvisoryLoading(false)
                  if (activeResult) {
                    setActiveResult(null)
                    setStep(null)
                    setAutoResult(null)
                    setAdvisory(null)
                    setPrevSteps([])
                    setStepNum(1)
                    setRunbook("")
                  }
                }}
                  className="px-4 py-2.5 rounded-lg border border-gray-700 text-gray-400 hover:border-red-700 hover:text-red-400 transition-all text-sm font-medium whitespace-nowrap">
                  {(advisoryLoading || autoLoading || stepLoading) ? "✕ Cancel" : "↺ Clear"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {advisoryLoading && (
        <div className="mt-6 bg-gray-900 border border-gray-800 rounded-lg p-4 text-sm text-gray-400 animate-pulse">
          Generating recommendations...
        </div>
      )}

      {advisory && !advisoryLoading && activeResult === "advisory" && (
        <div className="mt-6 bg-gray-900 border border-gray-800 rounded-xl p-6">
          <p className="text-xs uppercase tracking-widest text-gray-500 mb-2">Advisory report</p>
          <p className="text-gray-300 text-sm leading-relaxed mb-6">{advisory.summary}</p>

          {advisory.quick_wins?.length > 0 && (
            <div className="mb-6 bg-green-950 border border-green-900 rounded-lg p-4">
              <p className="text-xs text-green-400 uppercase tracking-widest mb-2">Quick wins</p>
              <ul className="space-y-1">
                {advisory.quick_wins.map((w: string, i: number) => (
                  <li key={i} className="text-sm text-green-300 flex gap-2">
                    <span>⚡</span>{w}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="space-y-4">
            {advisory.recommendations?.map((r: any, i: number) => (
              <div key={i} className="border border-gray-800 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded">#{r.priority}</span>
                  <span className={"text-xs font-medium uppercase " + (
                    r.severity === "critical" ? "text-red-400" :
                    r.severity === "high" ? "text-orange-400" :
                    r.severity === "medium" ? "text-yellow-400" : "text-green-400"
                  )}>{r.severity}</span>
                  <span className="text-xs text-gray-500 ml-auto">effort: {r.effort}</span>
                </div>
                <p className="text-white text-sm font-medium mb-2">{r.title}</p>
                <p className="text-gray-400 text-sm leading-relaxed mb-3">{r.explanation}</p>
                <div className="bg-gray-950 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1">Action</p>
                  <p className="text-sm text-indigo-300">{r.action}</p>
                </div>
                <button onClick={() => navigator.clipboard.writeText(r.action)}
                  className="text-xs text-gray-600 hover:text-gray-400 mt-2 transition-all">
                  Copy action
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {autoLoading && (
        <div className="mt-6 bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse delay-75" />
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse delay-150" />
            <span className="text-sm text-gray-400 ml-1">Applying all fixes automatically...</span>
          </div>
          <div className="space-y-2">
            <div className="h-3 bg-gray-800 rounded animate-pulse w-full" />
            <div className="h-3 bg-gray-800 rounded animate-pulse w-4/5" />
            <div className="h-3 bg-gray-800 rounded animate-pulse w-2/3" />
            <div className="h-3 bg-gray-800 rounded animate-pulse w-3/4" />
          </div>
        </div>
      )}

      {autoResult && !autoLoading && activeResult === "auto" && (
        <div className="mt-6 bg-gray-900 border border-gray-800 rounded-xl p-6">
          <p className="text-xs uppercase tracking-widest text-gray-500 mb-2">Automatic fix applied</p>
          <p className="text-gray-300 text-sm leading-relaxed mb-6">{autoResult.summary}</p>

          {autoResult.warnings?.length > 0 && (
            <div className="mb-6 bg-yellow-950 border border-yellow-900 rounded-lg p-4">
              <p className="text-xs text-yellow-400 uppercase tracking-widest mb-2">Verify these</p>
              <ul className="space-y-1">
                {autoResult.warnings.map((w: string, i: number) => (
                  <li key={i} className="text-sm text-yellow-300 flex gap-2"><span>⚠</span>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {autoResult.fixes?.map((f: any, i: number) => (
            <div key={i} className="mb-4 border border-gray-800 rounded-xl p-4">
              <p className="text-white text-sm font-medium mb-2">{f.title}</p>
              <p className="text-gray-400 text-sm mb-3">{f.explanation}</p>
              {f.fixed && (
                <pre className="bg-gray-950 border border-gray-800 rounded-lg p-3 text-xs font-mono text-green-300 overflow-x-auto whitespace-pre-wrap">
                  {f.fixed}
                </pre>
              )}
            </div>
          ))}

          {autoResult.patched_codebase && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-gray-500 uppercase tracking-widest">Patched codebase</p>
                <button onClick={() => navigator.clipboard.writeText(autoResult.patched_codebase)}
                  className="text-xs text-gray-500 hover:text-gray-300 transition-all">
                  Copy all
                </button>
              </div>
              <pre className="bg-gray-950 border border-gray-800 rounded-lg p-4 text-xs font-mono text-green-300 overflow-x-auto whitespace-pre-wrap max-h-96">
                {autoResult.patched_codebase}
              </pre>
            </div>
          )}
        </div>
      )}

      {stepLoading && (
        <div className="mt-6 bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center gap-3 mb-5">
            <div className="flex gap-1">
              <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{animationDelay:"0ms"}} />
              <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{animationDelay:"150ms"}} />
              <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{animationDelay:"300ms"}} />
            </div>
            <span className="text-sm text-gray-300 font-medium">Generating fix for step {stepNum}...</span>
          </div>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 rounded-full border-2 border-purple-500 border-t-transparent animate-spin flex-shrink-0" />
              <div className="h-3 bg-gray-800 rounded animate-pulse flex-1" />
            </div>
            <div className="h-3 bg-gray-800 rounded animate-pulse w-4/5 ml-7" />
            <div className="h-3 bg-gray-800 rounded animate-pulse w-3/5 ml-7" />
            <div className="h-24 bg-gray-800 rounded animate-pulse w-full mt-2" />
            <div className="flex gap-2 mt-4">
              <div className="h-9 bg-gray-800 rounded-lg animate-pulse flex-1" />
              <div className="h-9 bg-gray-800 rounded-lg animate-pulse flex-1" />
              <div className="h-9 bg-gray-800 rounded-lg animate-pulse flex-1" />
            </div>
          </div>
        </div>
      )}

      {step && !stepLoading && activeResult === "semi" && (
        <div className="mt-6 bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-gray-500">Step {stepNum}</span>
            {step.is_final && <span className="text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded">Final step</span>}
          </div>
          <h3 className="text-white font-medium mb-3">{step.step_title}</h3>
          <p className="text-gray-300 text-sm leading-relaxed mb-4">{step.explanation}</p>
          {step.diff && (
            <pre className="bg-gray-950 border border-gray-800 rounded-lg p-4 text-xs font-mono text-green-300 overflow-x-auto whitespace-pre-wrap mb-4">
              {step.diff}
            </pre>
          )}
          <input value={override} onChange={e => setOverride(e.target.value)}
            placeholder="Optional: give specific instructions before approving..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-500 mb-3" />
          <div className="flex gap-2">
            <button onClick={approveStep}
              className="flex-1 py-2 rounded-lg bg-green-700 hover:bg-green-600 text-white text-sm font-medium transition-all">
              Approve
            </button>
            <button onClick={rejectStep}
              className="flex-1 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-white text-sm font-medium transition-all">
              Reject
            </button>
            <button onClick={() => runStep()}
              className="flex-1 py-2 rounded-lg bg-indigo-700 hover:bg-indigo-600 text-white text-sm font-medium transition-all">
              Override + retry
            </button>
          </div>
        </div>
      )}

      {prevSteps.length > 0 && activeResult === "semi" && (
        <div className="mt-6 mb-10">
          <p className="text-xs uppercase tracking-widest text-gray-500 mb-3">Resolution trail</p>
          <div className="space-y-2">
            {prevSteps.map((s,i) => (
              <div key={i} className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2">
                <span className="text-xs text-gray-500">Step {s.step_number}</span>
                <span className="text-sm text-gray-300 flex-1">{s.explanation}</span>
                <span className={"text-xs font-medium " + (s.decision==="approved" ? "text-green-400" : "text-gray-500")}>
                  {s.decision}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
    </>
  )
}
