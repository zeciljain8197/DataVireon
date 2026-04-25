import { createBrowserClient } from "@supabase/ssr"

export const supabase = createBrowserClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL as string,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string
)

export async function signInWithGitHub() {
  await supabase.auth.signInWithOAuth({
    provider: "github",
    options: { redirectTo: window.location.origin + "/auth/callback" },
  })
}

export async function signOut() {
  await supabase.auth.signOut()
}
