"use client";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { FlaskConical, Swords, Zap, ArrowRight } from "lucide-react";
import dynamic from "next/dynamic";

const ParticleField = dynamic(() => import("@/components/ParticleField"), {
  ssr: false,
});

const cards = [
  {
    title: "Enter The Studio",
    subtitle: "Run private, AI-grounded validations.",
    description:
      "Submit your startup idea and watch as multi-model AI agents dissect pricing, patents, market size, and competitive landscape in real-time.",
    href: "/studio",
    icon: FlaskConical,
    gradient: "from-violet-600 via-purple-500 to-indigo-600",
    glowColor: "rgba(139, 92, 246, 0.15)",
    accentBorder: "hover:border-violet-500/40",
    features: ["Progressive AI Streaming", "PDF Export", "Idea Comparison"],
  },
  {
    title: "Enter The Arena",
    subtitle: "Join the community, chat, and roast ideas.",
    description:
      "Publish your validated ideas, battle-test them with upvotes and polls, join hubs, and chat with founders in real-time channels.",
    href: "/arena",
    icon: Swords,
    gradient: "from-cyan-500 via-teal-500 to-emerald-500",
    glowColor: "rgba(6, 182, 212, 0.15)",
    accentBorder: "hover:border-cyan-500/40",
    features: ["Live Voting & Polls", "Real-time Chat", "Karma & Badges"],
  },
];

export default function NexusPage() {
  const router = useRouter();
  useAuth();

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[var(--bg-primary)] relative overflow-hidden px-4 py-12">
      {/* Three.js Particle Background */}
      <ParticleField particleCount={600} speed={0.1} opacity={0.35} />

      {/* Background orbs */}
      <div className="gradient-orb absolute top-0 left-1/4 w-[600px] h-[600px] bg-violet-600/5" />
      <div className="gradient-orb absolute bottom-0 right-1/4 w-[600px] h-[600px] bg-cyan-600/5" style={{ animationDelay: "-4s" }} />

      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: [0.4, 0, 0.2, 1] }}
        className="text-center mb-16 relative z-10"
      >
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.1, duration: 0.6 }}
          className="flex items-center justify-center gap-3 mb-6"
        >
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-600 via-purple-500 to-cyan-500 flex items-center justify-center shadow-xl shadow-violet-500/25">
            <Zap className="w-7 h-7 text-white" />
          </div>
        </motion.div>
        <h1 className="text-4xl md:text-6xl font-bold mb-4 tracking-tight">
          <span className="gradient-text">The Nexus</span>
        </h1>
        <p className="text-[var(--text-secondary)] text-lg md:text-xl max-w-lg mx-auto leading-relaxed">
          Choose your path. Validate in private or battle-test in public.
        </p>
      </motion.div>

      {/* Cards */}
      <div className="grid md:grid-cols-2 gap-8 w-full max-w-4xl relative z-10">
        {cards.map((card, i) => (
          <motion.button
            key={card.href}
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 + 0.15 * i, ease: [0.4, 0, 0.2, 1] }}
            whileHover={{ y: -8, scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => router.push(card.href)}
            className={`glass-card card-shine p-8 md:p-10 text-left cursor-pointer group transition-all duration-500 ${card.accentBorder}`}
            style={{
              boxShadow: `0 0 0px ${card.glowColor}`,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.boxShadow = `0 0 40px ${card.glowColor}, 0 0 80px ${card.glowColor}`;
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.boxShadow = `0 0 0px ${card.glowColor}`;
            }}
          >
            {/* Icon */}
            <div
              className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${card.gradient} flex items-center justify-center mb-6 shadow-lg transition-all duration-500 group-hover:scale-110 group-hover:shadow-xl`}
            >
              <card.icon className="w-7 h-7 text-white" />
            </div>

            {/* Content */}
            <h2 className="text-2xl font-bold text-[var(--text-primary)] mb-1.5 tracking-tight">
              {card.title}
            </h2>
            <p className="text-sm font-medium text-[var(--accent-violet)] mb-3">
              {card.subtitle}
            </p>
            <p className="text-[var(--text-secondary)] text-sm leading-relaxed mb-8">
              {card.description}
            </p>

            {/* Features */}
            <div className="flex flex-wrap gap-2 mb-8">
              {card.features.map((f) => (
                <span
                  key={f}
                  className="text-xs px-3.5 py-1.5 rounded-full bg-white/[0.04] text-[var(--text-muted)] border border-white/[0.06] backdrop-blur-sm"
                >
                  {f}
                </span>
              ))}
            </div>

            {/* CTA */}
            <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)] group-hover:gap-3 transition-all duration-300">
              Launch
              <ArrowRight className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1" />
            </div>
          </motion.button>
        ))}
      </div>
    </div>
  );
}
