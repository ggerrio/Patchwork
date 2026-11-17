import type { Metadata } from "next";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Patchwork — Autonomous Incident Command Center",
  description: "Self-healing DevOps copilot dashboard with HITL PR approval",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/15 border border-sky-500/30 text-sky-400">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <span className="text-base font-bold tracking-tight text-slate-100">
                  Patchwork
                </span>
                <span className="ml-2 rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                  COMMAND CENTER
                </span>
              </div>
            </Link>
            <span className="text-xs text-slate-400">
              HITL Autonomous Incident Response
            </span>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
      </body>
    </html>
  );
}

