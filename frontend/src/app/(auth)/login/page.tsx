"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useUserStore } from "@/stores/user-store";
import { Zap, Loader2, AlertCircle, UserPlus, LogIn } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const login = useUserStore((s) => s.login);
  const register = useUserStore((s) => s.register);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "register") {
        await register(email, password, username || undefined, fullName || undefined);
      } else {
        await login(email, password);
      }
      router.push("/nexus");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `${mode === "register" ? "Registration" : "Login"} failed`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, ease: [0.4, 0, 0.2, 1] }}
      className="relative z-10 w-full max-w-md px-4"
    >
      <div className="glass-card noise-overlay p-8 md:p-10 shadow-2xl">
        {/* Logo */}
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.1, duration: 0.5 }}
          className="flex items-center gap-3 mb-8"
        >
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-violet-600 via-purple-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-violet-500/25">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">
              StartupScope
            </h1>
            <p className="text-xs text-[var(--text-muted)] tracking-wide">AI Validation Engine</p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5 }}
        >
          <h2 className="text-2xl font-bold mb-1 gradient-text tracking-tight">
            {mode === "login" ? "Welcome back" : "Create account"}
          </h2>
          <p className="text-sm text-[var(--text-secondary)] mb-8">
            {mode === "login"
              ? "Sign in to access The Studio & The Arena"
              : "Join the Compute-Driven Social Network"}
          </p>
        </motion.div>

        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="flex items-center gap-2 p-3 mb-5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm"
          >
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </motion.div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Registration-only fields */}
          {mode === "register" && (
            <>
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                transition={{ duration: 0.3 }}
              >
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                  Full Name
                </label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="input-dark"
                  placeholder="John Doe"
                />
              </motion.div>
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                transition={{ duration: 0.3, delay: 0.05 }}
              >
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
                  className="input-dark"
                  placeholder="johndoe"
                  maxLength={28}
                />
                <p className="text-[10px] text-[var(--text-muted)] mt-1.5">Letters, numbers, underscores only</p>
              </motion.div>
            </>
          )}

          <div>
            <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-dark"
              placeholder="founder@startup.com"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-dark"
              placeholder="••••••••"
              required
              minLength={6}
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full flex items-center justify-center gap-2 mt-3 py-3 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : mode === "login" ? (
              <>
                <LogIn className="w-4 h-4" />
                Sign In
              </>
            ) : (
              <>
                <UserPlus className="w-4 h-4" />
                Create Account
              </>
            )}
          </button>
        </form>

        {/* Toggle between login and register */}
        <div className="mt-8 pt-5 border-t border-[var(--border-subtle)] text-center">
          <p className="text-sm text-[var(--text-secondary)]">
            {mode === "login" ? "Don't have an account?" : "Already have an account?"}
            <button
              type="button"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
              }}
              className="ml-1.5 text-[var(--accent-violet)] font-semibold hover:underline transition-colors"
            >
              {mode === "login" ? "Sign up" : "Sign in"}
            </button>
          </p>
        </div>
      </div>
    </motion.div>
  );
}
