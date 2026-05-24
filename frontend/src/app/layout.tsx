import type { Metadata } from "next"
import "./globals.css"
import { ThemeProvider } from "@/components/ThemeProvider"
import { Inter } from "next/font/google"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "DataVireon — AI Resolution Platform",
  description: "Role-aware AI problem resolution for data and engineering teams",
  openGraph: {
    title: "DataVireon — AI Resolution Platform",
    description: "Role-aware AI problem resolution for data and engineering teams",
    url: "https://data-vireon.vercel.app",
    siteName: "DataVireon",
    images: [{ url: "https://data-vireon.vercel.app/android-chrome-512x512.png", width: 512, height: 512 }],
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "DataVireon — AI Resolution Platform",
    description: "Role-aware AI problem resolution for data and engineering teams",
    images: ["https://data-vireon.vercel.app/android-chrome-512x512.png"],
  },
  icons: {
    icon: [
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon.ico" },
    ],
    apple: { url: "/apple-touch-icon.png" },
    other: [
      { rel: "manifest", url: "/site.webmanifest" },
    ],
  },
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
