"use client";
import Link from "next/link";
import { Zap, ArrowLeft } from "lucide-react";

export default function StudioLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      {/* Top Nav */}
      <header className="sticky top-0 z-50 header-accent bg-[var(--bg-primary)]/85 backdrop-blur-2xl">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-6 h-14">
          <div className="flex items-center gap-3">
            <Link
              href="/nexus"
              className="flex items-center gap-2 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors text-sm"
            >
              <ArrowLeft className="w-4 h-4" />
              Nexus
            </Link>
            <div className="w-px h-5 bg-[var(--border-subtle)]" />
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-600 via-purple-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <span className="font-bold text-sm tracking-tight">The Studio</span>
            </div>
          </div>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
