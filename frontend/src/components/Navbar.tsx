"use client"
import { useEffect, useState } from "react"
import { supabase, signInWithGitHub, signOut } from "@/lib/supabase"
import type { User } from "@supabase/supabase-js"
import Link from "next/link"
import { useTheme } from "next-themes"

export default function Navbar() {
  const [user, setUser]         = useState<User | null>(null)
  const [loading, setLoading]   = useState(true)
  const [mounted, setMounted]   = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const { theme, setTheme }     = useTheme()

  useEffect(() => {
    setMounted(true)
    supabase.auth.getUser().then(({ data }) => { setUser(data.user); setLoading(false) })
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, s) => setUser(s?.user ?? null))
    return () => subscription.unsubscribe()
  }, [])

  return (
    <>
      <nav className="glass sticky top-0 z-50"
        style={{height:56,display:"flex",alignItems:"center",justifyContent:"space-between",padding:"0 16px",gap:8}}>

        {/* Left — logo */}
        <Link href="/" style={{display:"flex",alignItems:"center",gap:8,flexShrink:0,textDecoration:"none"}}>
          <img src={mounted && theme === "light" ? "/logo-light-icon.png" : "/android-chrome-192x192.png"} alt="DataVireon"
            style={{height:26,width:26,borderRadius:5,objectFit:"contain"}} />
          <span style={{fontWeight:600,fontSize:14,color:"var(--text-1)"}}>DataVireon</span>
          <span className="badge" style={{background:"var(--brand-dim)",color:"var(--text-brand)",
            borderColor:"var(--border-brand)",fontSize:10}}>beta</span>
        </Link>

        {/* Right — actions */}
        <div style={{display:"flex",alignItems:"center",gap:6,flexShrink:0}}>

          {/* Desktop nav links */}
          {user && (
            <div className="nav-links" style={{display:"flex",alignItems:"center",gap:4}}>
              <Link href="/history" style={{fontSize:12,color:"var(--text-3)",textDecoration:"none",padding:"4px 8px",borderRadius:6}}>
                History
              </Link>
              <Link href="/schema" style={{fontSize:12,color:"var(--text-3)",textDecoration:"none",padding:"4px 8px",borderRadius:6}}>
                Schema
              </Link>
            </div>
          )}

          {/* Theme toggle */}
          {mounted && (
            <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="btn btn-ghost btn-icon btn-sm" style={{fontSize:14,flexShrink:0}}>
              {theme === "dark" ? "☀︎" : "☽"}
            </button>
          )}

          {/* Auth — desktop */}
          {!loading && user && (
            <div className="nav-links" style={{display:"flex",alignItems:"center",gap:6}}>
              {user.user_metadata?.avatar_url && (
                <img src={user.user_metadata.avatar_url} alt=""
                  style={{width:26,height:26,borderRadius:"50%",border:"1.5px solid var(--border-2)",flexShrink:0}} />
              )}
              <button onClick={signOut} className="btn btn-ghost btn-sm" style={{fontSize:11,padding:"0 8px",height:26}}>
                Sign out
              </button>
            </div>
          )}

          {!loading && !user && (
            <button onClick={signInWithGitHub} className="btn btn-primary btn-sm" style={{gap:5,fontSize:12,flexShrink:0}}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
              </svg>
              Sign in
            </button>
          )}

          {/* Hamburger — mobile only */}
          {user && (
            <button className="hamburger-btn btn btn-ghost btn-icon btn-sm"
              onClick={() => setMenuOpen(o => !o)}
              style={{fontSize:18,flexShrink:0}}>
              {menuOpen ? "✕" : "☰"}
            </button>
          )}
        </div>
      </nav>

      {/* Mobile menu dropdown */}
      {menuOpen && user && (
        <div className="mobile-menu fade-in" style={{
          position:"fixed",top:56,left:0,right:0,zIndex:49,
          background:"var(--bg-surface)",borderBottom:"1px solid var(--border-1)",
          padding:"12px 16px",display:"flex",flexDirection:"column",gap:4
        }}>
          {user.user_metadata?.avatar_url && (
            <div style={{display:"flex",alignItems:"center",gap:10,padding:"8px 0 12px",borderBottom:"1px solid var(--border-1)",marginBottom:8}}>
              <img src={user.user_metadata.avatar_url} alt=""
                style={{width:32,height:32,borderRadius:"50%",border:"1.5px solid var(--border-2)"}} />
              <div>
                <p style={{fontSize:13,fontWeight:500,color:"var(--text-1)"}}>
                  {user.user_metadata?.user_name || user.email?.split("@")[0]}
                </p>
                <p style={{fontSize:11,color:"var(--text-3)"}}>{user.email}</p>
              </div>
            </div>
          )}
          <Link href="/history" onClick={() => setMenuOpen(false)}
            style={{fontSize:14,color:"var(--text-1)",textDecoration:"none",
              padding:"10px 12px",borderRadius:"var(--radius-md)",background:"var(--bg-elevated)"}}>
            📋 History
          </Link>
          <Link href="/schema" onClick={() => setMenuOpen(false)}
            style={{fontSize:14,color:"var(--text-1)",textDecoration:"none",
              padding:"10px 12px",borderRadius:"var(--radius-md)",background:"var(--bg-elevated)"}}>
            🗄 Schema analyzer
          </Link>
          <Link href="/app" onClick={() => setMenuOpen(false)}
            style={{fontSize:14,color:"var(--text-1)",textDecoration:"none",
              padding:"10px 12px",borderRadius:"var(--radius-md)",background:"var(--bg-elevated)"}}>
            ⚡ App
          </Link>
          <button onClick={() => { signOut(); setMenuOpen(false) }}
            style={{fontSize:14,color:"var(--red)",textAlign:"left",
              padding:"10px 12px",borderRadius:"var(--radius-md)",background:"var(--red-dim)",
              border:"1px solid rgba(248,113,113,0.2)",cursor:"pointer",marginTop:4}}>
            Sign out
          </button>
        </div>
      )}
    </>
  )
}
