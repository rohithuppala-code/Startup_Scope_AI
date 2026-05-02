"use client";
import dynamic from "next/dynamic";

const ParticleField = dynamic(() => import("@/components/ParticleField"), {
  ssr: false,
});

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)] relative overflow-hidden">
      {/* Three.js Particle Background */}
      <ParticleField particleCount={700} speed={0.12} opacity={0.45} />

      {/* Gradient Orbs — layered behind particles for depth */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="gradient-orb absolute top-1/4 -left-32 w-[500px] h-[500px] bg-violet-600/8 rounded-full" />
        <div className="gradient-orb absolute bottom-1/4 -right-32 w-[500px] h-[500px] bg-cyan-600/8 rounded-full" style={{ animationDelay: "-3s" }} />
        <div className="gradient-orb absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] bg-violet-500/5 rounded-full" style={{ animationDelay: "-5s" }} />
      </div>

      {/* Content */}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  );
}
