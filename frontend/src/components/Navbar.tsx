"use client"
import { useEffect, useState } from "react"
import { supabase, signInWithGitHub, signOut } from "@/lib/supabase"
import type { User } from "@supabase/supabase-js"
import Link from "next/link"
import { useTheme } from "next-themes"

export default function Navbar() {
  const [user, setUser]       = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [mounted, setMounted] = useState(false)
  const { theme, setTheme }   = useTheme()

  useEffect(() => {
    setMounted(true)
    supabase.auth.getUser().then(({ data }) => { setUser(data.user); setLoading(false) })
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, s) => setUser(s?.user ?? null))
    return () => subscription.unsubscribe()
  }, [])

  return (
    <nav className="glass sticky top-0 z-50 px-5 py-0 h-14 flex items-center justify-between">
      <div className="flex items-center gap-5">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold"
            style={{background:"linear-gradient(135deg,#7c6dfa,#a855f7)"}}>
            DV
          </div>
          <span className="font-semibold text-sm" style={{color:"var(--text-1)"}}>DataVireon</span>
          <span className="badge" style={{background:"var(--brand-dim)",color:"var(--text-brand)",borderColor:"var(--border-brand)",fontSize:"10px"}}>beta</span>
        </Link>
        {user && (
          <Link href="/history" className="text-xs transition-colors" style={{color:"var(--text-3)"}}>
            History
          </Link>
        )}
      </div>
      <div className="flex items-center gap-2">
        {mounted && (
          <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="btn btn-ghost btn-icon btn-sm" style={{fontSize:"14px"}}>
            {theme === "dark" ? "☀︎" : "☽"}
          </button>
        )}
        {loading ? (
          <div className="shimmer" style={{width:80,height:28}} />
        ) : user ? (
          <div className="flex items-center gap-2">
            {user.user_metadata?.avatar_url && (
              <img src={user.user_metadata.avatar_url} alt=""
                className="w-6 h-6 rounded-full" style={{border:"1.5px solid var(--border-2)"}} />
            )}
            <span className="text-xs hidden sm:block" style={{color:"var(--text-3)"}}>
              {user.user_metadata?.user_name || user.email?.split("@")[0]}
            </span>
            <button onClick={signOut} className="btn btn-ghost btn-sm">Sign out</button>
          </div>
        ) : (
          <button onClick={signInWithGitHub} className="btn btn-primary btn-sm" style={{gap:6}}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
            </svg>
            Sign in with GitHub
          </button>
        )}
      </div>
    </nav>
  )
}
