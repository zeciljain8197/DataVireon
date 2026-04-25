"use client"
import { useEffect, useState } from "react"
import { supabase, signInWithGitHub, signOut } from "@/lib/supabase"
import type { User } from "@supabase/supabase-js"

export default function Navbar() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setUser(data.user)
      setLoading(false)
    })
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      setUser(session?.user ?? null)
    })
    return () => subscription.unsubscribe()
  }, [])

  return (
    <nav className="border-b border-gray-800 bg-gray-950 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className="text-white font-semibold text-lg tracking-tight">DataVireon</span>
        <span className="text-xs text-gray-500 border border-gray-700 px-2 py-0.5 rounded-full">beta</span>
      </div>
      <div className="flex items-center gap-3">
        {loading ? (
          <div className="w-20 h-7 bg-gray-800 rounded animate-pulse" />
        ) : user ? (
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-400">{user.email ?? user.user_metadata?.user_name}</span>
            <button onClick={signOut}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-700 text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-all">
              Sign out
            </button>
          </div>
        ) : (
          <button onClick={signInWithGitHub}
            className="text-xs px-3 py-1.5 rounded-lg bg-white text-gray-900 font-medium hover:bg-gray-100 transition-all flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
            </svg>
            Sign in with GitHub
          </button>
        )}
      </div>
    </nav>
  )
}
