import type { Metadata } from "next"
import "./globals.css"
import Navbar from "@/components/Navbar"

export const metadata: Metadata = {
  title: "DataVireon — AI Resolution Platform",
  description: "Role-aware AI problem resolution for data and engineering teams",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen antialiased">
        <Navbar />
        {children}
      </body>
    </html>
  )
}
