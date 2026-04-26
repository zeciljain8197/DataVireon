import type { Metadata } from "next"
import "./globals.css"
import { ThemeProvider } from "@/components/ThemeProvider"
import { Inter } from "next/font/google"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "DataVireon — AI Resolution Platform",
  description: "Role-aware AI problem resolution for data and engineering teams",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className} style={{background:"var(--bg-base)"}}>
        <ThemeProvider>
          <div className="orb orb-1" />
          <div className="orb orb-2" />
          <div className="orb orb-3" />
          <div style={{position:"relative",zIndex:1}}>
            {children}
          </div>
        </ThemeProvider>
      </body>
    </html>
  )
}
