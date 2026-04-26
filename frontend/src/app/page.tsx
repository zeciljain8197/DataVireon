"use client"
import Link from "next/link"
import { useState, useEffect } from "react"
import { supabase, signInWithGitHub } from "@/lib/supabase"

const ROLES = [
  { label:"Data Engineer", color:"var(--blue)" },
  { label:"SDE",           color:"var(--purple)" },
  { label:"Data Analyst",  color:"var(--teal)" },
  { label:"MLE",           color:"var(--pink)" },
  { label:"Data Scientist",color:"var(--yellow)" },
]

const FEATURES = [
  { icon:"⚡", title:"Role-aware diagnosis", desc:"DataVireon understands your exact role. A Data Engineer gets pipeline analysis. An MLE gets model drift detection. Same codebase, completely different lens." },
  { icon:"🔬", title:"40 expert skill modules", desc:"Every role-domain combination has a deeply engineered expert prompt — from Airflow DAG failures to CUDA memory issues to SQL cartesian joins." },
  { icon:"🔀", title:"Three resolution modes", desc:"Let AI fix everything automatically, walk through changes step by step with full approval control, or get a prioritised advisory report." },
  { icon:"🐙", title:"GitHub repo integration", desc:"Connect any GitHub repo and browse files directly. Select exactly what you want analyzed — no copy-pasting entire codebases." },
  { icon:"📋", title:"Incident runbooks", desc:"Every resolved session generates a production-ready incident runbook in markdown. Ready to paste into Notion, Confluence, or your internal wiki." },
  { icon:"🕓", title:"Session history", desc:"Every diagnostic and resolution step is saved. Resume where you left off, review past fixes, and build a library of resolved issues." },
]

const DOMAINS = [
  { label:"Pipeline debugger",    color:"var(--blue-dim)",   text:"var(--blue)" },
  { label:"Schema & quality",     color:"var(--purple-dim)", text:"var(--purple)" },
  { label:"Performance & cost",   color:"var(--orange-dim)", text:"var(--orange)" },
  { label:"Model health",         color:"var(--pink-dim)",   text:"var(--pink)" },
  { label:"Security & compliance",color:"var(--red-dim)",    text:"var(--red)" },
  { label:"Code quality",         color:"var(--green-dim)",  text:"var(--green)" },
  { label:"Env & infra",          color:"var(--yellow-dim)", text:"var(--yellow)" },
  { label:"Testing & CI/CD",      color:"var(--teal-dim)",   text:"var(--teal)" },
]

const STEPS = [
  { num:"01", title:"Select your role",        desc:"Tell DataVireon whether you are a Data Engineer, SDE, MLE, Data Analyst, or Data Scientist. Everything adapts to your context." },
  { num:"02", title:"Add your code",           desc:"Paste a snippet, upload files, or connect your GitHub repo and browse files directly." },
  { num:"03", title:"Describe the problem",    desc:"Explain what is going wrong. Include error messages, symptoms, or just describe the unexpected behaviour." },
  { num:"04", title:"Run diagnostic",          desc:"DataVireon analyses your code through the lens of your role, classifies the problem domain, and generates a structured diagnostic report." },
  { num:"05", title:"Choose resolution mode",  desc:"Automatic, semi-automatic with step approval, or advisory recommendations only. You decide how much control you want." },
  { num:"06", title:"Get your fix",            desc:"Receive patched code, a step-by-step resolution trail, and a production-ready incident runbook. All saved to your session history." },
]

const GH_ICON = (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
  </svg>
)

export default function Landing() {
  const [user, setUser]           = useState<any>(null)
  const [activeRole, setActiveRole] = useState(0)

  useEffect(() => {
    supabase.auth.getUser().then(({data}) => setUser(data.user))
    const {data:{subscription}} = supabase.auth.onAuthStateChange((_,s) => setUser(s?.user ?? null))
    const t = setInterval(() => setActiveRole(r => (r+1) % ROLES.length), 2000)
    return () => { subscription.unsubscribe(); clearInterval(t) }
  }, [])

  const W = {maxWidth:1100, margin:"0 auto", padding:"0 24px"}
  const W4 = {maxWidth:900, margin:"0 auto", padding:"0 24px"}
  const W2 = {maxWidth:620, margin:"0 auto", padding:"0 24px", textAlign:"center" as const}

  return (
    <div style={{minHeight:"100vh",background:"var(--bg-base)",color:"var(--text-1)"}}>

      {/* Nav */}
      <nav style={{position:"sticky",top:0,zIndex:50,backdropFilter:"blur(16px)",
        background:"rgba(12,12,16,0.85)",borderBottom:"1px solid var(--border-1)",
        padding:"0 24px",height:56,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <div style={{width:28,height:28,borderRadius:8,background:"linear-gradient(135deg,#7c6dfa,#a855f7)",
            display:"flex",alignItems:"center",justifyContent:"center",color:"white",fontSize:11,fontWeight:700}}>DV</div>
          <span style={{fontWeight:600,fontSize:14,color:"var(--text-1)"}}>DataVireon</span>
          <span style={{fontSize:10,padding:"2px 8px",borderRadius:99,background:"var(--brand-dim)",
            color:"var(--text-brand)",border:"1px solid var(--border-brand)"}}>beta</span>
        </div>
        {user ? (
          <Link href="/app" style={{display:"inline-flex",alignItems:"center",gap:6,padding:"6px 16px",
            borderRadius:10,background:"var(--brand)",color:"white",fontSize:13,fontWeight:500,textDecoration:"none"}}>
            Go to app →
          </Link>
        ) : (
          <button onClick={signInWithGitHub} style={{display:"inline-flex",alignItems:"center",gap:6,padding:"6px 16px",
            borderRadius:10,background:"var(--bg-elevated)",color:"var(--text-1)",fontSize:13,fontWeight:500,
            border:"1px solid var(--border-2)",cursor:"pointer"}}>
            {GH_ICON} Sign in with GitHub
          </button>
        )}
      </nav>

      {/* Hero */}
      <section style={{...W2, paddingTop:96, paddingBottom:80}}>
        <div style={{display:"inline-flex",alignItems:"center",gap:8,padding:"6px 16px",borderRadius:99,
          background:"var(--brand-dim)",border:"1px solid var(--border-brand)",
          fontSize:12,color:"var(--text-brand)",marginBottom:32}}>
          <span style={{width:6,height:6,borderRadius:"50%",background:"var(--brand)",display:"inline-block"}} />
          AI-powered problem resolution for data and engineering teams
        </div>
        <h1 style={{fontSize:52,fontWeight:700,lineHeight:1.1,letterSpacing:-1.5,color:"var(--text-1)",marginBottom:24}}>
          Fix data and engineering<br />
          problems{" "}
          <span style={{background:"linear-gradient(135deg,#9d91fb,#c4b5fd 40%,#f59e0b)",
            WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",backgroundClip:"text"}}>
            10x faster
          </span>
        </h1>
        <p style={{fontSize:18,color:"var(--text-2)",lineHeight:1.65,marginBottom:40,maxWidth:520,margin:"0 auto 40px"}}>
          DataVireon diagnoses your codebase through the lens of your exact role,
          then walks you through production-grade fixes — step by step or all at once.
        </p>
        <div style={{display:"flex",gap:12,justifyContent:"center",flexWrap:"wrap",marginBottom:48}}>
          {user ? (
            <Link href="/app" style={{display:"inline-flex",alignItems:"center",gap:8,padding:"12px 28px",
              borderRadius:12,background:"var(--brand)",color:"white",fontSize:14,fontWeight:500,
              textDecoration:"none",boxShadow:"0 4px 20px var(--brand-glow)"}}>
              Go to app →
            </Link>
          ) : (
            <button onClick={signInWithGitHub} style={{display:"inline-flex",alignItems:"center",gap:8,
              padding:"12px 28px",borderRadius:12,background:"var(--brand)",color:"white",
              fontSize:14,fontWeight:500,border:"none",cursor:"pointer",
              boxShadow:"0 4px 20px var(--brand-glow)"}}>
              {GH_ICON} Sign in with GitHub
            </button>
          )}
          <a href="#how-it-works" style={{display:"inline-flex",alignItems:"center",padding:"12px 28px",
            borderRadius:12,background:"transparent",color:"var(--text-2)",fontSize:14,fontWeight:500,
            border:"1px solid var(--border-2)",textDecoration:"none"}}>
            See how it works ↓
          </a>
        </div>

        {/* Role pills */}
        <div style={{display:"flex",alignItems:"center",gap:8,justifyContent:"center",flexWrap:"wrap"}}>
          <span style={{fontSize:12,color:"var(--text-3)"}}>Built for</span>
          {ROLES.map((r,i) => (
            <span key={r.label} style={{fontSize:11,padding:"4px 12px",borderRadius:99,
              border:`1px solid ${i===activeRole ? r.color : "var(--border-1)"}`,
              color:i===activeRole ? r.color : "var(--text-3)",
              background:i===activeRole ? "rgba(124,109,250,0.06)" : "transparent",
              transition:"all 0.4s"}}>
              {r.label}
            </span>
          ))}
        </div>
      </section>

      {/* Domains strip */}
      <div style={{borderTop:"1px solid var(--border-1)",borderBottom:"1px solid var(--border-1)",
        background:"var(--bg-surface)",padding:"24px 0"}}>
        <div style={W}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",
            textAlign:"center",marginBottom:14}}>8 specialised problem domains</p>
          <div style={{display:"flex",flexWrap:"wrap",gap:8,justifyContent:"center"}}>
            {DOMAINS.map(d => (
              <span key={d.label} style={{fontSize:12,padding:"4px 12px",borderRadius:99,
                background:d.color,color:d.text,border:`1px solid ${d.text}30`}}>
                {d.label}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Features */}
      <section style={{padding:"80px 0"}}>
        <div style={W}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",textAlign:"center",marginBottom:8}}>Why DataVireon</p>
          <h2 style={{fontSize:32,fontWeight:600,color:"var(--text-1)",textAlign:"center",marginBottom:56}}>
            Not a chatbot. A resolution platform.
          </h2>
          <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:16}}>
            {FEATURES.map(f => (
              <div key={f.title} style={{background:"var(--bg-surface)",border:"1px solid var(--border-1)",
                borderRadius:16,padding:24,transition:"border-color 0.2s"}}>
                <div style={{fontSize:24,marginBottom:14}}>{f.icon}</div>
                <h3 style={{fontSize:14,fontWeight:600,color:"var(--text-1)",marginBottom:8}}>{f.title}</h3>
                <p style={{fontSize:13,color:"var(--text-2)",lineHeight:1.65}}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section style={{borderTop:"1px solid var(--border-1)",background:"var(--bg-surface)",padding:"80px 0"}} id="how-it-works">
        <div style={W4}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",textAlign:"center",marginBottom:8}}>How it works</p>
          <h2 style={{fontSize:32,fontWeight:600,color:"var(--text-1)",textAlign:"center",marginBottom:56}}>
            From problem to fix in minutes
          </h2>
          <div style={{display:"flex",flexDirection:"column",gap:20}}>
            {STEPS.map(s => (
              <div key={s.num} style={{display:"flex",gap:20,alignItems:"flex-start"}}>
                <span style={{fontSize:28,fontWeight:700,color:"var(--border-2)",flexShrink:0,width:48,lineHeight:1}}>{s.num}</span>
                <div style={{paddingTop:4}}>
                  <h3 style={{fontSize:14,fontWeight:600,color:"var(--text-1)",marginBottom:4}}>{s.title}</h3>
                  <p style={{fontSize:13,color:"var(--text-2)",lineHeight:1.6}}>{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Resolution modes */}
      <section style={{padding:"80px 0"}}>
        <div style={W}>
          <p style={{fontSize:11,textTransform:"uppercase",letterSpacing:"0.08em",color:"var(--text-3)",textAlign:"center",marginBottom:8}}>Resolution modes</p>
          <h2 style={{fontSize:32,fontWeight:600,color:"var(--text-1)",textAlign:"center",marginBottom:56}}>
            You choose how much control you want
          </h2>
          <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:16}}>
            {[
              {tag:"Fully automatic",color:"var(--green)",title:"AI fixes everything",
               desc:"DataVireon analyses all issues and applies every fix at once. Returns a fully patched codebase ready to copy or commit. Best for well-understood, isolated problems."},
              {tag:"Semi-automatic",color:"var(--brand)",title:"Step-by-step with approval",recommended:true,
               desc:"Walk through each fix with full visibility. Approve, reject, or override with your own instructions at every checkpoint. Best for production systems and learning."},
              {tag:"Advisory only",color:"var(--yellow)",title:"Recommendations, you act",
               desc:"Get a prioritised list of issues with severity, effort estimates, and exact action steps. No code changes made. Best for audits, code reviews, and planning."},
            ].map(m => (
              <div key={m.tag} style={{background:"var(--bg-surface)",
                border:`1px solid ${m.recommended?"var(--border-brand)":"var(--border-1)"}`,
                borderRadius:16,padding:24,position:"relative"}}>
                {m.recommended && (
                  <div style={{position:"absolute",top:-12,left:"50%",transform:"translateX(-50%)",
                    background:"var(--brand)",color:"white",fontSize:11,fontWeight:500,
                    padding:"3px 12px",borderRadius:99}}>Recommended</div>
                )}
                <div style={{fontSize:11,fontWeight:600,textTransform:"uppercase",letterSpacing:"0.06em",
                  color:m.color,marginBottom:10}}>{m.tag}</div>
                <h3 style={{fontSize:14,fontWeight:600,color:"var(--text-1)",marginBottom:8}}>{m.title}</h3>
                <p style={{fontSize:13,color:"var(--text-2)",lineHeight:1.65}}>{m.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section style={{borderTop:"1px solid var(--border-1)",background:"var(--bg-surface)",padding:"80px 0"}}>
        <div style={W2}>
          <h2 style={{fontSize:32,fontWeight:600,color:"var(--text-1)",marginBottom:12}}>
            Ready to fix your first issue?
          </h2>
          <p style={{fontSize:15,color:"var(--text-2)",marginBottom:32}}>
            Free to use. No credit card required. Sign in with GitHub and start in seconds.
          </p>
          {user ? (
            <Link href="/app" style={{display:"inline-flex",alignItems:"center",gap:8,padding:"14px 36px",
              borderRadius:12,background:"var(--brand)",color:"white",fontSize:15,fontWeight:500,
              textDecoration:"none",boxShadow:"0 4px 24px var(--brand-glow)"}}>
              Go to app →
            </Link>
          ) : (
            <button onClick={signInWithGitHub} style={{display:"inline-flex",alignItems:"center",gap:8,
              padding:"14px 36px",borderRadius:12,background:"var(--brand)",color:"white",
              fontSize:15,fontWeight:500,border:"none",cursor:"pointer",
              boxShadow:"0 4px 24px var(--brand-glow)"}}>
              {GH_ICON} Sign in with GitHub →
            </button>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer style={{borderTop:"1px solid var(--border-1)",padding:"24px",
        display:"flex",alignItems:"center",justifyContent:"space-between"}}>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <span style={{fontSize:13,fontWeight:500,color:"var(--text-2)"}}>DataVireon</span>
          <span style={{fontSize:10,padding:"2px 8px",borderRadius:99,background:"var(--bg-elevated)",
            color:"var(--text-3)",border:"1px solid var(--border-1)"}}>beta</span>
        </div>
        <Link href="/app" style={{fontSize:12,color:"var(--text-3)",textDecoration:"none"}}>Launch app</Link>
      </footer>
    </div>
  )
}
