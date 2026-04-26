"use client"
import { useState, useEffect, useRef } from "react"
import { supabase } from "@/lib/supabase"
import Navbar from "@/components/Navbar"

const ROLES = [
  { id:"data_engineer",  label:"Data Engineer",  desc:"Pipelines · ETL · Orchestration", icon:"⚡" },
  { id:"sde",            label:"SDE",             desc:"APIs · Architecture · Systems",    icon:"🏗" },
  { id:"data_analyst",   label:"Data Analyst",    desc:"SQL · BI · Reporting",             icon:"📊" },
  { id:"mle",            label:"MLE",             desc:"Models · Serving · Drift",         icon:"🤖" },
  { id:"data_scientist", label:"Data Scientist",  desc:"Stats · EDA · Experiments",        icon:"🔬" },
]

const MODES = [
  { id:"automatic", label:"Automatic",     desc:"AI applies all fixes at once",       icon:"⚡" },
  { id:"semi_auto", label:"Guided",        desc:"Step-by-step with your approval",    icon:"🎯" },
  { id:"advisory",  label:"Advisory",      desc:"Recommendations only, no changes",   icon:"📋" },
]

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

function TypingText({ text, speed=14 }: { text:string, speed?:number }) {
  const [out, setOut] = useState("")
  const [done, setDone] = useState(false)
  useEffect(() => {
    setOut(""); setDone(false)
    let i=0
    const t = setInterval(() => {
      if(i < text.length) { setOut(text.slice(0,++i)) }
      else { setDone(true); clearInterval(t) }
    }, speed)
    return () => clearInterval(t)
  }, [text])
  return <span>{out}{!done && <span className="cursor-blink" />}</span>
}

function Skel({ w="100%", h=12 }: { w?:string|number, h?:number }) {
  return <div className="shimmer" style={{width:w,height:h}} />
}

function LoadingCard({ color, label }: { color:string, label:string }) {
  return (
    <div className="card fade-up" style={{marginTop:16}}>
      <div className="flex items-center gap-3" style={{marginBottom:16}}>
        <div className="loading-dots">
          <span style={{background:color}} /><span style={{background:color}} /><span style={{background:color}} />
        </div>
        <span style={{fontSize:13,color:"var(--text-2)"}}>{label}</span>
      </div>
      <div style={{display:"flex",flexDirection:"column",gap:8}}>
        <Skel h={10} w="75%" /><Skel h={10} w="55%" /><Skel h={10} w="65%" />
      </div>
    </div>
  )
}

export default function App() {
  const [role,setRole]                   = useState("")
  const [mode,setMode]                   = useState("semi_auto")
  const [codebase,setCodebase]           = useState("")
  const [problem,setProblem]             = useState("")
  const [loading,setLoading]             = useState(false)
  const [diagnostic,setDiagnostic]       = useState<any>(null)
  const [step,setStep]                   = useState<any>(null)
  const [stepNum,setStepNum]             = useState(1)
  const [prevSteps,setPrevSteps]         = useState<any[]>([])
  const [override,setOverride]           = useState("")
  const [stepLoading,setStepLoading]     = useState(false)
  const [userId,setUserId]               = useState<string|null>(null)
  const [sessionId,setSessionId]         = useState<string|null>(null)
  const [runbook,setRunbook]             = useState("")
  const [runbookLoading,setRunbookLoading] = useState(false)
  const [repoUrl,setRepoUrl]             = useState("")
  const [repoFiles,setRepoFiles]         = useState<any[]>([])
  const [repoLoading,setRepoLoading]     = useState(false)
  const [selectedFiles,setSelectedFiles] = useState<string[]>([])
  const [repoOwner,setRepoOwner]         = useState("")
  const [showRepo,setShowRepo]           = useState(false)
  const [advisory,setAdvisory]           = useState<any>(null)
  const [advisoryLoading,setAdvisoryLoading] = useState(false)
  const [autoResult,setAutoResult]       = useState<any>(null)
  const [autoLoading,setAutoLoading]     = useState(false)
  const [activeResult,setActiveResult]   = useState<"semi"|"auto"|"advisory"|null>(null)
  const [reqCount,setReqCount]           = useState(0)
  const abortRef = useRef<AbortController|null>(null)

  useEffect(() => {
    supabase.auth.getUser().then(({data}) => setUserId(data.user?.id ?? null))
    const {data:{subscription}} = supabase.auth.onAuthStateChange((_,s) => setUserId(s?.user?.id ?? null))
    return () => subscription.unsubscribe()
  },[])

  useEffect(() => {
    const h = (e:KeyboardEvent) => {
      if((e.metaKey||e.ctrlKey) && e.key==="Enter") { e.preventDefault(); if(role&&codebase&&problem&&!loading) runDiagnostic() }
      if((e.metaKey||e.ctrlKey) && e.key==="k") { e.preventDefault(); resetAll() }
      if(e.key==="Escape") { if(abortRef.current){abortRef.current.abort();abortRef.current=null}; setLoading(false);setStepLoading(false);setAutoLoading(false);setAdvisoryLoading(false) }
    }
    window.addEventListener("keydown",h)
    return () => window.removeEventListener("keydown",h)
  },[role,codebase,problem,loading])

  function resetAll() {
    if(abortRef.current){abortRef.current.abort();abortRef.current=null}
    setLoading(false);setStepLoading(false);setAutoLoading(false);setAdvisoryLoading(false);setRunbookLoading(false)
    setDiagnostic(null);setStep(null);setAutoResult(null);setAdvisory(null)
    setPrevSteps([]);setStepNum(1);setOverride("");setRunbook("")
    setSessionId(null);setActiveResult(null);setCodebase("");setProblem("");setRole("")
  }

  function clearResult() {
    if(abortRef.current){abortRef.current.abort();abortRef.current=null}
    setStepLoading(false);setAutoLoading(false);setAdvisoryLoading(false)
    setActiveResult(null);setStep(null);setAutoResult(null);setAdvisory(null)
    setPrevSteps([]);setStepNum(1);setRunbook("")
  }

  async function stream(url:string, body:object, onDone:(text:string)=>void) {
    if(abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()
    let full=""
    const res = await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body),signal:abortRef.current.signal})
    const reader = res.body!.getReader(); const dec = new TextDecoder()
    while(true) { const {done,value}=await reader.read(); if(done) break; full+=dec.decode(value) }
    const m = full.match(/\{[\s\S]*\}/)
    if(m) onDone(m[0])
  }

  async function runDiagnostic() {
    if(!role||!codebase.trim()||!problem.trim()) return
    setLoading(true);setDiagnostic(null);setStep(null);setPrevSteps([]);setStepNum(1)
    setSessionId(null);setActiveResult(null);setAutoResult(null);setAdvisory(null);setRunbook("")
    try {
      await stream(API+"/analyze",{codebase,role,problem,user_id:userId},(json)=>{
        const diag=JSON.parse(json); setDiagnostic(diag); setReqCount(c=>c+1)
        if(userId) fetch(API+"/session/save",{method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({user_id:userId,role,problem,domain:diag.domain,resolution_mode:mode,diagnostic_report:diag})
        }).then(r=>r.json()).then(d=>setSessionId(d.session_id))
      })
    } catch(e:any){if(e.name!=="AbortError")console.error(e)}
    setLoading(false)
  }

  async function runStep(num?:number,prev?:any[]) {
    const n=num??stepNum, p=prev??prevSteps
    setStepLoading(true);setStep(null)
    try {
      await stream(API+"/resolve/step",{session_id:sessionId??"local",codebase,role,problem,
        diagnostic:JSON.stringify(diagnostic),mode,step_number:n,previous_steps:p,override_prompt:override||null,user_id:userId},
        (json)=>{setStep(JSON.parse(json));setActiveResult("semi")})
    } catch(e:any){if(e.name!=="AbortError")console.error(e)}
    setStepLoading(false);setOverride("")
  }

  async function runAuto() {
    setAutoLoading(true);setAutoResult(null)
    try {
      await stream(API+"/resolve/auto",{codebase,role,problem,diagnostic,user_id:userId,session_id:sessionId},
        (json)=>{setAutoResult(JSON.parse(json));setActiveResult("auto")})
    } catch(e:any){if(e.name!=="AbortError")console.error(e)}
    setAutoLoading(false)
  }

  async function runAdvisory() {
    setAdvisoryLoading(true);setAdvisory(null)
    try {
      await stream(API+"/advisory",{codebase,role,problem,diagnostic},
        (json)=>{setAdvisory(JSON.parse(json));setActiveResult("advisory")})
    } catch(e:any){if(e.name!=="AbortError")console.error(e)}
    setAdvisoryLoading(false)
  }

  async function saveStep(decision:string,s:any,n:number) {
    if(!sessionId||!s) return
    await fetch(API+"/session/step/save",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({session_id:sessionId,step_number:n,ai_explanation:s.explanation,proposed_diff:s.diff,user_decision:decision,override_prompt:override||null})})
  }

  function approve() {
    if(!step) return; saveStep("approved",step,stepNum)
    const np=[...prevSteps,{step_number:stepNum,explanation:step.explanation,decision:"approved"}]
    setPrevSteps(np); const nn=stepNum+1; setStepNum(nn); setStep(null)
    if(!step.is_final) runStep(nn,np)
  }
  function reject() {
    if(!step) return; saveStep("rejected",step,stepNum)
    setPrevSteps([...prevSteps,{step_number:stepNum,explanation:step.explanation,decision:"rejected"}])
    setStep(null)
  }

  async function fetchRepo() {
    if(!repoUrl.trim()) return
    setRepoLoading(true);setRepoFiles([]);setSelectedFiles([])
    try {
      const r=await fetch(API+"/github/tree",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({repo_url:repoUrl})})
      const d=await r.json(); if(d.files){setRepoFiles(d.files);setRepoOwner(d.owner+"/"+d.repo)}
    } catch(e){console.error(e)}
    setRepoLoading(false)
  }

  async function loadFiles() {
    if(!selectedFiles.length) return; setRepoLoading(true)
    try {
      const r=await fetch(API+"/github/contents",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({repo_url:repoUrl,file_paths:selectedFiles})})
      const d=await r.json(); if(d.combined){setCodebase(d.combined);setShowRepo(false)}
    } catch(e){console.error(e)}
    setRepoLoading(false)
  }

  async function genRunbook() {
    setRunbookLoading(true);setRunbook("")
    try {
      const res=await fetch(API+"/runbook",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({role,problem,diagnostic,steps:prevSteps})})
      const reader=res.body!.getReader();const dec=new TextDecoder();let full=""
      while(true){const {done,value}=await reader.read();if(done)break;full+=dec.decode(value);setRunbook(full)}
    } catch(e){console.error(e)}
    setRunbookLoading(false)
  }

  const domain = diagnostic?.domain || ""
  const canRun = role && codebase.trim() && problem.trim() && !loading

  return (
    <>
      <Navbar />
      <main style={{maxWidth:720,margin:"0 auto",padding:"32px 16px 80px"}}>

        {/* Header row */}
        <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",marginBottom:28}}>
          <div>
            <h1 style={{fontSize:20,fontWeight:600,color:"var(--text-1)",letterSpacing:-0.5}}>
              {role ? `${ROLES.find(r=>r.id===role)?.icon} ${ROLES.find(r=>r.id===role)?.label} workspace` : "What are you debugging?"}
            </h1>
            <p style={{fontSize:12,color:"var(--text-3)",marginTop:4}}>
              {role ? "Add your code · describe the problem · run diagnostic" : "Select a role to personalise your workspace"}
            </p>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:6,flexShrink:0}}>
            <kbd>⌘K</kbd><span style={{fontSize:11,color:"var(--text-3)"}}>reset</span>
            <span style={{color:"var(--border-2)",margin:"0 2px"}}>·</span>
            <kbd>⌘↵</kbd><span style={{fontSize:11,color:"var(--text-3)"}}>run</span>
            <span style={{color:"var(--border-2)",margin:"0 2px"}}>·</span>
            <kbd>Esc</kbd><span style={{fontSize:11,color:"var(--text-3)"}}>cancel</span>
          </div>
        </div>

        {/* ── Step 1: Role ── */}
        <section style={{marginBottom:20}}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",marginBottom:10}}>
            01 — Select role
          </p>
          <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:8}}>
            {ROLES.map(r=>(
              <button key={r.id} onClick={()=>setRole(r.id)}
                className={"card card-hover " + (role===r.id?"card-active":"")}
                style={{padding:"12px 8px",textAlign:"center",cursor:"pointer",border:"1px solid var(--border-1)",background:role===r.id?"var(--brand-dim)":"var(--bg-surface)"}}>
                <div style={{fontSize:20,marginBottom:6}}>{r.icon}</div>
                <div style={{fontSize:12,fontWeight:500,color:role===r.id?"var(--text-brand)":"var(--text-1)",lineHeight:1.3}}>{r.label}</div>
                <div style={{fontSize:10,color:"var(--text-3)",marginTop:3,lineHeight:1.4}}>{r.desc}</div>
              </button>
            ))}
          </div>
        </section>

        {/* ── Step 2: Code ── */}
        <section style={{marginBottom:16}}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",marginBottom:10}}>
            02 — Add your code
          </p>

          {/* Source tabs */}
          <div className="tabs" style={{marginBottom:12}}>
            <button className={"tab "+(showRepo?"":"tab-active")} onClick={()=>setShowRepo(false)}>
              Paste code
            </button>
            <button className={"tab "+(showRepo?"tab-active":"")} onClick={()=>setShowRepo(true)}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
              GitHub repo
            </button>
          </div>

          {showRepo && (
            <div className="card fade-in" style={{marginBottom:12,padding:16}}>
              <div style={{display:"flex",gap:8,marginBottom:12}}>
                <input className="input" value={repoUrl} onChange={e=>setRepoUrl(e.target.value)}
                  onKeyDown={e=>e.key==="Enter"&&fetchRepo()}
                  placeholder="https://github.com/owner/repo" style={{flex:1}} />
                <button className="btn btn-primary" onClick={fetchRepo} disabled={repoLoading||!repoUrl}>
                  {repoLoading?"Loading…":"Browse"}
                </button>
              </div>
              {repoFiles.length>0 && (
                <>
                  <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8}}>
                    <span style={{fontSize:11,color:"var(--text-3)"}}>{repoOwner} · {repoFiles.length} files · {selectedFiles.length} selected</span>
                    <button className="btn btn-success btn-sm" onClick={loadFiles} disabled={!selectedFiles.length||repoLoading}>
                      Load selected →
                    </button>
                  </div>
                  <div style={{maxHeight:200,overflowY:"auto",display:"flex",flexDirection:"column",gap:2}}>
                    {repoFiles.map((f:any)=>(
                      <button key={f.path} onClick={()=>setSelectedFiles(p=>p.includes(f.path)?p.filter(x=>x!==f.path):[...p,f.path])}
                        style={{textAlign:"left",padding:"5px 10px",borderRadius:8,fontSize:11,fontFamily:"monospace",
                          background:selectedFiles.includes(f.path)?"var(--brand-dim)":"transparent",
                          color:selectedFiles.includes(f.path)?"var(--text-brand)":"var(--text-3)",
                          border:selectedFiles.includes(f.path)?"1px solid var(--border-brand)":"1px solid transparent",
                          display:"flex",justifyContent:"space-between",cursor:"pointer"}}>
                        <span style={{overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{f.path}</span>
                        <span style={{opacity:0.5,marginLeft:8,flexShrink:0}}>{f.type}</span>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          <textarea className="input input-mono" value={codebase} onChange={e=>setCodebase(e.target.value)}
            rows={9} placeholder="Paste your code, SQL, config, or pipeline definition…" />
        </section>

        {/* ── Step 3: Problem ── */}
        <section style={{marginBottom:20}}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",marginBottom:10}}>
            03 — Describe the problem
          </p>
          <textarea className="input" value={problem} onChange={e=>setProblem(e.target.value)}
            rows={3} placeholder="What's going wrong? Include error messages, unexpected behaviour, or symptoms…" />
        </section>

        {/* ── Run button ── */}
        <div style={{display:"flex",gap:8,marginBottom:reqCount>0?8:20}}>
          <button className="btn btn-primary btn-lg" onClick={runDiagnostic} disabled={!canRun} style={{flex:1}}>
            {loading ? <><span className="spinner" />Analyzing…</> : "Run diagnostic"}
          </button>
          {(loading||diagnostic) && (
            <button className="btn btn-ghost btn-lg" onClick={loading?()=>{if(abortRef.current){abortRef.current.abort();abortRef.current=null};setLoading(false)}:resetAll}>
              {loading ? "✕ Cancel" : "↺ Reset"}
            </button>
          )}
        </div>

        {reqCount>0 && (
          <div style={{display:"flex",justifyContent:"flex-end",alignItems:"center",gap:8,marginBottom:20}}>
            <span style={{fontSize:11,color:"var(--text-3)"}}>{reqCount} diagnostic{reqCount!==1?"s":""} this session</span>
            <span className="badge" style={reqCount>=8
              ?{background:"var(--orange-dim)",color:"var(--orange)",borderColor:"rgba(251,146,60,0.2)"}
              :{background:"var(--bg-elevated)",color:"var(--text-3)"}}>
              {Math.max(0,10-reqCount)} left
            </span>
          </div>
        )}

        {/* ── Loading ── */}
        {loading && <LoadingCard color="var(--brand)" label="Analyzing your codebase…" />}

        {/* ── Diagnostic result ── */}
        {diagnostic && !loading && (
          <div className="card fade-up" style={{marginTop:0}}>
            {/* Header */}
            <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:16,flexWrap:"wrap"}}>
              <span className={"badge tag-"+domain}>{domain.replace("_"," ")}</span>
              <span className={"badge sev-"+diagnostic.severity} style={{background:"transparent",border:"none",fontWeight:600,textTransform:"uppercase",fontSize:11}}>
                {diagnostic.severity}
              </span>
              <span style={{marginLeft:"auto",fontSize:11,color:"var(--text-3)"}}>
                {Math.round((diagnostic.confidence||0)*100)}% confidence
              </span>
              {sessionId && (
                <span style={{fontSize:10,color:"var(--text-3)"}}>· Session {sessionId.slice(0,8)}…</span>
              )}
            </div>

            {/* Summary with typing effect */}
            <p style={{fontSize:13,lineHeight:1.65,color:"var(--text-2)",marginBottom:16}}>
              <TypingText text={diagnostic.summary||""} />
            </p>

            {/* Symptoms */}
            {diagnostic.symptoms?.length>0 && (
              <div style={{marginBottom:16}}>
                <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)",marginBottom:8}}>Symptoms detected</p>
                <div style={{display:"flex",flexDirection:"column",gap:6}}>
                  {diagnostic.symptoms.map((s:string,i:number)=>(
                    <div key={i} className="fade-in" style={{display:"flex",gap:8,animationDelay:`${i*80}ms`}}>
                      <span style={{color:"var(--text-brand)",flexShrink:0,marginTop:1}}>→</span>
                      <span style={{fontSize:13,color:"var(--text-2)"}}>{s}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Affected areas */}
            {diagnostic.affected_areas?.length>0 && (
              <div style={{marginBottom:20}}>
                <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)",marginBottom:8}}>Affected areas</p>
                <div style={{display:"flex",flexWrap:"wrap",gap:6}}>
                  {diagnostic.affected_areas.map((a:string,i:number)=>(
                    <span key={i} className="badge" style={{background:"var(--bg-elevated)",color:"var(--text-2)",borderColor:"var(--border-1)"}}>{a}</span>
                  ))}
                </div>
              </div>
            )}

            <div className="divider" />

            {/* ── Resolution mode selector ── */}
            <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)",marginBottom:10}}>
              How do you want to resolve this?
            </p>
            <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:8,marginBottom:12}}>
              {MODES.map(m=>(
                <button key={m.id} onClick={()=>{
                  if(abortRef.current){abortRef.current.abort();abortRef.current=null}
                  setMode(m.id);clearResult()
                }}
                  className={"card card-hover "+(mode===m.id?"card-active":"")}
                  style={{textAlign:"left",padding:"12px 14px",cursor:"pointer",
                    background:mode===m.id?"var(--brand-dim)":"var(--bg-elevated)",
                    border:`1px solid ${mode===m.id?"var(--border-brand)":"var(--border-1)"}`}}>
                  <div style={{fontSize:16,marginBottom:4}}>{m.icon}</div>
                  <div style={{fontSize:12,fontWeight:600,color:mode===m.id?"var(--text-brand)":"var(--text-1)",marginBottom:2}}>{m.label}</div>
                  <div style={{fontSize:11,color:"var(--text-3)",lineHeight:1.4}}>{m.desc}</div>
                </button>
              ))}
            </div>

            <p style={{fontSize:12,color:"var(--text-3)",marginBottom:14,lineHeight:1.5}}>
              {mode==="advisory"?"You'll receive a prioritised list of issues with severity ratings, effort estimates, and exact action steps. No code will be changed.":
               mode==="automatic"?"The AI will analyse all issues and apply every fix at once, returning a fully patched codebase ready to copy or commit.":
               "Walk through each fix one step at a time. Approve, reject, or override with your own instructions at every checkpoint."}
            </p>

            <div style={{display:"flex",gap:8}}>
              {mode==="advisory"?(
                <button className="btn btn-primary" onClick={runAdvisory} disabled={advisoryLoading} style={{flex:1,height:40}}>
                  {advisoryLoading?<><span className="spinner"/>Generating…</>:"Get recommendations →"}
                </button>
              ):mode==="automatic"?(
                <button className="btn btn-primary" onClick={runAuto} disabled={autoLoading} style={{flex:1,height:40}}>
                  {autoLoading?<><span className="spinner"/>Applying fixes…</>:"Apply all fixes →"}
                </button>
              ):(
                <button className="btn btn-primary" onClick={()=>runStep()} disabled={stepLoading} style={{flex:1,height:40}}>
                  {stepLoading?<><span className="spinner"/>Generating step {stepNum}…</>:"Start guided resolution →"}
                </button>
              )}
              {(advisoryLoading||autoLoading||stepLoading||activeResult) && (
                <button className="btn btn-ghost" onClick={clearResult} style={{height:40}}>
                  {(advisoryLoading||autoLoading||stepLoading)?"✕":"↺"}
                </button>
              )}
            </div>
          </div>
        )}

        {/* ── Loading states ── */}
        {stepLoading     && <LoadingCard color="var(--purple)" label={`Generating fix for step ${stepNum}…`} />}
        {autoLoading     && <LoadingCard color="var(--green)"  label="Applying all fixes automatically…" />}
        {advisoryLoading && <LoadingCard color="var(--yellow)" label="Generating recommendations…" />}

        {/* ── Semi-auto step ── */}
        {step && !stepLoading && activeResult==="semi" && (
          <div className="card fade-up" style={{marginTop:16}}>
            <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:12}}>
              <span className="badge" style={{background:"var(--bg-elevated)",color:"var(--text-3)"}}>Step {stepNum}</span>
              {step.is_final && <span className="badge" style={{background:"var(--green-dim)",color:"var(--green)",borderColor:"var(--green-border)"}}>Final step</span>}
            </div>
            <h3 style={{fontSize:14,fontWeight:600,color:"var(--text-1)",marginBottom:8}}>{step.step_title}</h3>
            <p style={{fontSize:13,color:"var(--text-2)",lineHeight:1.65,marginBottom:14}}>{step.explanation}</p>
            {step.diff && <div className="code-block" style={{marginBottom:14}}>{step.diff}</div>}
            <input className="input" value={override} onChange={e=>setOverride(e.target.value)}
              placeholder="Optional: add specific instructions before approving…"
              style={{marginBottom:12}} />
            <div style={{display:"flex",gap:8}}>
              <button className="btn btn-success" onClick={approve} style={{flex:1}}>✓ Approve</button>
              <button className="btn btn-ghost" onClick={reject} style={{flex:1}}>✕ Reject</button>
              <button className="btn btn-brand-soft" onClick={()=>runStep()} style={{flex:1}}>↺ Override</button>
            </div>
          </div>
        )}

        {/* ── Resolution trail ── */}
        {prevSteps.length>0 && activeResult==="semi" && (
          <div style={{marginTop:16}}>
            <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)",marginBottom:10}}>Resolution trail</p>
            <div style={{display:"flex",flexDirection:"column",gap:6}}>
              {prevSteps.map((s,i)=>(
                <div key={i} style={{display:"flex",alignItems:"center",gap:10,padding:"8px 14px",
                  background:"var(--bg-surface)",border:"1px solid var(--border-1)",borderRadius:"var(--radius-md)"}}>
                  <div style={{width:7,height:7,borderRadius:"50%",flexShrink:0,
                    background:s.decision==="approved"?"var(--green)":"var(--text-3)",
                    boxShadow:s.decision==="approved"?"0 0 6px var(--green)":"none"}} />
                  <span style={{fontSize:11,color:"var(--text-3)",flexShrink:0}}>Step {s.step_number}</span>
                  <span style={{fontSize:12,color:"var(--text-2)",flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{s.explanation}</span>
                  <span style={{fontSize:11,fontWeight:500,color:s.decision==="approved"?"var(--green)":"var(--text-3)",flexShrink:0}}>
                    {s.decision}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Runbook button ── */}
        {prevSteps.length>0 && activeResult==="semi" && !step && !stepLoading && (
          <div style={{marginTop:12}}>
            <button className="btn btn-ghost" onClick={genRunbook} disabled={runbookLoading} style={{width:"100%",height:40}}>
              {runbookLoading?<><span className="spinner"/>Generating runbook…</>:"📋 Generate incident runbook →"}
            </button>
          </div>
        )}

        {runbook && (
          <div className="card fade-up" style={{marginTop:12}}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
              <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)"}}>Incident runbook</p>
              <button className="btn btn-ghost btn-sm" onClick={()=>navigator.clipboard.writeText(runbook)}>Copy</button>
            </div>
            <pre style={{fontSize:12,lineHeight:1.7,color:"var(--text-2)",whiteSpace:"pre-wrap",fontFamily:"inherit"}}>{runbook}</pre>
          </div>
        )}

        {/* ── Advisory result ── */}
        {advisory && !advisoryLoading && activeResult==="advisory" && (
          <div className="card fade-up" style={{marginTop:16}}>
            <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)",marginBottom:4}}>Advisory report</p>
            <p style={{fontSize:13,color:"var(--text-2)",lineHeight:1.65,marginBottom:20}}>{advisory.summary}</p>
            {advisory.quick_wins?.length>0 && (
              <div style={{padding:14,borderRadius:"var(--radius-md)",background:"var(--green-dim)",border:"1px solid var(--green-border)",marginBottom:20}}>
                <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--green)",marginBottom:10}}>⚡ Quick wins</p>
                <div style={{display:"flex",flexDirection:"column",gap:6}}>
                  {advisory.quick_wins.map((w:string,i:number)=>(
                    <div key={i} style={{fontSize:12,color:"rgba(52,211,153,0.85)",display:"flex",gap:8}}>
                      <span style={{flexShrink:0}}>→</span>{w}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div style={{display:"flex",flexDirection:"column",gap:10}}>
              {advisory.recommendations?.map((r:any,i:number)=>(
                <div key={i} className="card-sm fade-in" style={{animationDelay:`${i*60}ms`}}>
                  <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
                    <span className="badge" style={{background:"var(--bg-overlay)",color:"var(--text-3)",fontWeight:600}}>#{r.priority}</span>
                    <span style={{fontSize:11,fontWeight:600,textTransform:"uppercase",
                      color:r.severity==="critical"?"var(--red)":r.severity==="high"?"var(--orange)":r.severity==="medium"?"var(--yellow)":"var(--green)"}}>{r.severity}</span>
                    <span style={{marginLeft:"auto",fontSize:11,color:"var(--text-3)"}}>effort: {r.effort}</span>
                  </div>
                  <p style={{fontSize:13,fontWeight:600,color:"var(--text-1)",marginBottom:6}}>{r.title}</p>
                  <p style={{fontSize:12,color:"var(--text-2)",lineHeight:1.6,marginBottom:10}}>{r.explanation}</p>
                  <div style={{padding:"10px 12px",borderRadius:"var(--radius-sm)",background:"var(--bg-void)",border:"1px solid var(--border-1)"}}>
                    <p style={{fontSize:10,color:"var(--text-3)",marginBottom:4,textTransform:"uppercase",letterSpacing:"0.06em"}}>Action</p>
                    <p style={{fontSize:12,color:"var(--text-brand)",lineHeight:1.5}}>{r.action}</p>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={()=>navigator.clipboard.writeText(r.action)} style={{marginTop:8}}>
                    Copy action
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Auto result ── */}
        {autoResult && !autoLoading && activeResult==="auto" && (
          <div className="card fade-up" style={{marginTop:16}}>
            <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)",marginBottom:4}}>Automatic fix applied</p>
            <p style={{fontSize:13,color:"var(--text-2)",lineHeight:1.65,marginBottom:20}}>{autoResult.summary}</p>
            {autoResult.warnings?.length>0 && (
              <div style={{padding:14,borderRadius:"var(--radius-md)",background:"var(--yellow-dim)",border:"1px solid rgba(251,191,36,0.2)",marginBottom:20}}>
                <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--yellow)",marginBottom:10}}>⚠ Verify these</p>
                {autoResult.warnings.map((w:string,i:number)=>(
                  <p key={i} style={{fontSize:12,color:"rgba(251,191,36,0.85)",marginBottom:4}}>{w}</p>
                ))}
              </div>
            )}
            <div style={{display:"flex",flexDirection:"column",gap:10}}>
              {autoResult.fixes?.map((f:any,i:number)=>(
                <div key={i} className="card-sm fade-in" style={{animationDelay:`${i*60}ms`}}>
                  <p style={{fontSize:13,fontWeight:600,color:"var(--text-1)",marginBottom:6}}>{f.title}</p>
                  <p style={{fontSize:12,color:"var(--text-2)",marginBottom:10}}>{f.explanation}</p>
                  {f.fixed && <div className="code-block">{f.fixed}</div>}
                </div>
              ))}
            </div>
            {autoResult.patched_codebase && (
              <div style={{marginTop:16}}>
                <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8}}>
                  <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.07em",color:"var(--text-3)"}}>Patched codebase</p>
                  <button className="btn btn-ghost btn-sm" onClick={()=>navigator.clipboard.writeText(autoResult.patched_codebase)}>Copy all</button>
                </div>
                <div className="code-block" style={{maxHeight:320,overflowY:"auto"}}>{autoResult.patched_codebase}</div>
              </div>
            )}
          </div>
        )}

      </main>
    </>
  )
}
