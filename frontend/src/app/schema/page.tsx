"use client"
import { useState } from "react"
import Navbar from "@/components/Navbar"
import Link from "next/link"

const ROLES = [
  { id:"data_engineer",  label:"Data Engineer",  icon:"⚡" },
  { id:"sde",            label:"SDE",             icon:"🏗" },
  { id:"data_analyst",   label:"Data Analyst",    icon:"📊" },
  { id:"mle",            label:"MLE",             icon:"🤖" },
  { id:"data_scientist", label:"Data Scientist",  icon:"🔬" },
]

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function SchemaAnalyzer() {
  const [url, setUrl]         = useState("")
  const [key, setKey]         = useState("")
  const [role, setRole]       = useState("data_engineer")
  const [problem, setProblem] = useState("")
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState<any>(null)
  const [error, setError]     = useState("")

  const DOMAIN_TAG: Record<string,string> = {
    schema_quality:"var(--purple)", pipeline:"var(--blue)",
    performance:"var(--orange)", security:"var(--red)",
  }
  const SEV_COLOR: Record<string,string> = {
    critical:"var(--red)",high:"var(--orange)",medium:"var(--yellow)",low:"var(--green)"
  }

  async function analyze() {
    if (!url || !key) return
    setLoading(true); setResult(null); setError("")
    let full = ""
    try {
      const res = await fetch(API + "/analyze/schema", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ supabase_url: url, supabase_key: key, role, problem }),
      })
      if (!res.ok) {
        const err = await res.json()
        setError(err.detail || "Failed to connect to Supabase")
        setLoading(false); return
      }
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        full += dec.decode(value)
      }
      const match = full.match(/\{[\s\S]*\}/)
      if (match) setResult(JSON.parse(match[0]))
      else setError("Could not parse response")
    } catch(e: any) { setError(e.message) }
    setLoading(false)
  }

  return (
    <>
      <Navbar />
      <main style={{maxWidth:680,margin:"0 auto",padding:"32px 16px 80px"}}>
        <div style={{marginBottom:28}}>
          <Link href="/app" style={{fontSize:12,color:"var(--text-3)",textDecoration:"none",display:"inline-flex",alignItems:"center",gap:4,marginBottom:16}}>
            ← Back to app
          </Link>
          <h1 style={{fontSize:20,fontWeight:600,color:"var(--text-1)",letterSpacing:-0.5}}>
            🗄 Supabase schema analyzer
          </h1>
          <p style={{fontSize:13,color:"var(--text-3)",marginTop:4}}>
            Connect your Supabase project and get an AI-powered schema quality analysis
          </p>
        </div>

        {/* Warning */}
        <div style={{padding:"12px 16px",borderRadius:"var(--radius-md)",background:"var(--yellow-dim)",
          border:"1px solid rgba(251,191,36,0.2)",marginBottom:24}}>
          <p style={{fontSize:12,color:"var(--yellow)",lineHeight:1.6}}>
            ⚠ Use your <strong>anon key</strong> (not service role key) for read-only analysis.
            Never share your service role key with any external tool.
          </p>
        </div>

        {/* Connection */}
        <div className="card" style={{marginBottom:16}}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",marginBottom:14}}>
            Supabase connection
          </p>
          <div style={{display:"flex",flexDirection:"column",gap:10}}>
            <div>
              <label style={{fontSize:12,color:"var(--text-2)",display:"block",marginBottom:6}}>Project URL</label>
              <input className="input" value={url} onChange={e=>setUrl(e.target.value)}
                placeholder="https://your-project.supabase.co" />
            </div>
            <div>
              <label style={{fontSize:12,color:"var(--text-2)",display:"block",marginBottom:6}}>Anon key</label>
              <input className="input" value={key} onChange={e=>setKey(e.target.value)}
                type="password" placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." />
            </div>
          </div>
        </div>

        {/* Role */}
        <div style={{marginBottom:16}}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",marginBottom:10}}>Your role</p>
          <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:6}}>
            {ROLES.map(r=>(
              <button key={r.id} onClick={()=>setRole(r.id)}
                className={"card card-hover "+(role===r.id?"card-active":"")}
                style={{padding:"10px 6px",textAlign:"center",cursor:"pointer",
                  background:role===r.id?"var(--brand-dim)":"var(--bg-surface)",
                  border:`1px solid ${role===r.id?"var(--border-brand)":"var(--border-1)"}`}}>
                <div style={{fontSize:16,marginBottom:4}}>{r.icon}</div>
                <div style={{fontSize:11,fontWeight:500,color:role===r.id?"var(--text-brand)":"var(--text-2)"}}>{r.label}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Problem */}
        <div style={{marginBottom:20}}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",marginBottom:10}}>
            Specific concern (optional)
          </p>
          <textarea className="input" value={problem} onChange={e=>setProblem(e.target.value)}
            rows={2} placeholder="e.g. Missing indexes, RLS not enabled, nullable columns causing issues..." />
        </div>

        <button className="btn btn-primary btn-lg" onClick={analyze}
          disabled={!url||!key||loading} style={{width:"100%"}}>
          {loading ? <><span className="spinner"/>Analyzing schema…</> : "Analyze schema →"}
        </button>

        {error && (
          <div style={{marginTop:16,padding:"12px 16px",borderRadius:"var(--radius-md)",
            background:"var(--red-dim)",border:"1px solid rgba(248,113,113,0.2)"}}>
            <p style={{fontSize:13,color:"var(--red)"}}>{error}</p>
          </div>
        )}

        {loading && (
          <div className="card fade-up" style={{marginTop:16}}>
            <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:16}}>
              <div className="loading-dots">
                <span style={{background:"var(--purple)"}}/><span style={{background:"var(--purple)"}}/><span style={{background:"var(--purple)"}}/>
              </div>
              <span style={{fontSize:13,color:"var(--text-2)"}}>Fetching and analyzing schema…</span>
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:8}}>
              <div className="shimmer" style={{height:10,width:"70%"}} />
              <div className="shimmer" style={{height:10,width:"50%"}} />
              <div className="shimmer" style={{height:10,width:"60%"}} />
            </div>
          </div>
        )}

        {result && !loading && (
          <div className="card fade-up" style={{marginTop:16}}>
            <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:14,flexWrap:"wrap"}}>
              <span className="badge" style={{background:"var(--purple-dim)",color:"var(--purple)",borderColor:"rgba(167,139,250,0.2)"}}>
                schema quality
              </span>
              <span style={{fontSize:11,fontWeight:600,textTransform:"uppercase",
                color:SEV_COLOR[result.severity]||"var(--text-2)"}}>
                {result.severity}
              </span>
              <span style={{marginLeft:"auto",fontSize:11,color:"var(--text-3)"}}>
                {Math.round((result.confidence||0)*100)}% confidence
              </span>
            </div>
            <p style={{fontSize:13,color:"var(--text-2)",lineHeight:1.65,marginBottom:16}}>{result.summary}</p>
            {result.symptoms?.length>0 && (
              <div style={{marginBottom:14}}>
                <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)",marginBottom:8}}>Issues detected</p>
                <div style={{display:"flex",flexDirection:"column",gap:6}}>
                  {result.symptoms.map((s:string,i:number)=>(
                    <div key={i} style={{display:"flex",gap:8}}>
                      <span style={{color:"var(--text-brand)",flexShrink:0}}>→</span>
                      <span style={{fontSize:13,color:"var(--text-2)"}}>{s}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {result.affected_areas?.length>0 && (
              <div style={{marginBottom:16}}>
                <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)",marginBottom:8}}>Affected tables</p>
                <div style={{display:"flex",flexWrap:"wrap",gap:6}}>
                  {result.affected_areas.map((a:string,i:number)=>(
                    <span key={i} className="badge" style={{background:"var(--bg-elevated)",color:"var(--text-2)",borderColor:"var(--border-1)"}}>{a}</span>
                  ))}
                </div>
              </div>
            )}
            <div className="divider" />
            <p style={{fontSize:12,color:"var(--text-3)"}}>
              For deeper analysis, go to the{" "}
              <Link href="/app" style={{color:"var(--text-brand)"}}>main app</Link>{" "}
              and paste your schema definition as code.
            </p>
          </div>
        )}
      </main>
    </>
  )
}
