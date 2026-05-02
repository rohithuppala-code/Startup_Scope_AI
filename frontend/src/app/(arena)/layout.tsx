"use client";
import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/hooks/use-auth";
import { useUserStore } from "@/stores/user-store";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  Home,
  Search,
  MessageCircle,
  Users2,
  User,
  Zap,
  ArrowLeft,
  Star,
  TrendingUp,
  ChevronRight,
  LogOut,
} from "lucide-react";

const NAV_ITEMS = [
  { id: "feed", label: "Home", href: "/arena", icon: Home },
  { id: "explore", label: "Explore", href: "/arena/explore", icon: Search },
  { id: "messages", label: "Messages", href: "/arena/messages", icon: MessageCircle },
  { id: "groups", label: "Groups", href: "/arena/groups", icon: Users2 },
  { id: "profile", label: "Profile", href: "/arena/profile", icon: User },
] as const;

export default function ArenaLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId, karma, badges, logout } = useAuth();
  const pathname = usePathname();

  const getActiveNav = () => {
    if (pathname === "/arena") return "feed";
    if (pathname.startsWith("/arena/explore")) return "explore";
    if (pathname.startsWith("/arena/messages")) return "messages";
    if (pathname.startsWith("/arena/groups")) return "groups";
    if (pathname.startsWith("/arena/profile")) return "profile";
    return "feed";
  };

  const activeNav = getActiveNav();

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-primary)]">
      {/* ─── Top Bar ─── */}
      <header className="shrink-0 header-accent bg-[var(--bg-primary)]/85 backdrop-blur-2xl z-50">
        <div className="flex items-center justify-between px-5 h-14">
          <div className="flex items-center gap-3">
            <Link
              href="/nexus"
              className="flex items-center gap-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors text-sm"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Nexus</span>
            </Link>
            <div className="w-px h-5 bg-[var(--border-subtle)]" />
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 via-purple-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-violet-500/20">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <div>
                <span className="font-bold text-sm gradient-text">The Arena</span>
                <p className="text-[10px] text-[var(--text-muted)] leading-none mt-0.5">Compute-Driven Social</p>
              </div>
            </div>
          </div>

          {/* Right side: karma + profile */}
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--bg-glass)] border border-[var(--border-subtle)] backdrop-blur-md">
              <Star className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-xs font-bold text-amber-400 tabular-nums">{karma}</span>
              <span className="text-[10px] text-[var(--text-muted)]">karma</span>
            </div>
            {badges.length > 0 && (
              <div className="hidden md:flex items-center gap-1">
                {badges.slice(0, 3).map((badge) => (
                  <span key={badge} className="text-sm" title={badge}>
                    {badge === "first_post" ? "🌱" : badge === "serial_builder" ? "🏗️" : badge === "karma_100" ? "⚡" : badge === "karma_500" ? "🚀" : "👍"}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ─── 3-Column Layout ─── */}
      <div className="flex-1 flex min-h-0">
        {/* ── Left Column: Navigation ── */}
        <aside className="hidden md:flex w-[248px] shrink-0 glass-nav flex-col justify-between py-5">
          <nav className="px-3 space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = activeNav === item.id;
              return (
                <Link key={item.id} href={item.href}>
                  <motion.div
                    className={`nav-item ${isActive ? "active" : ""}`}
                    whileHover={{ x: 2 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <Icon className="w-5 h-5" />
                    <span>{item.label}</span>
                    {item.id === "messages" && (
                      <span className="ml-auto relative">
                        <span className="notification-dot" />
                      </span>
                    )}
                  </motion.div>
                </Link>
              );
            })}
          </nav>

          {/* Bottom: Quick Stats + Post Button */}
          <div className="px-3 space-y-3 mt-auto">
            {/* Post Button */}
            <Link href="/arena">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="w-full btn-primary flex items-center justify-center gap-2 py-3"
              >
                <Zap className="w-4 h-4" />
                <span>Share Idea</span>
              </motion.button>
            </Link>

            {/* User Card */}
            <div className="glass-card p-3.5">
              <div className="flex items-center gap-2.5 mb-2.5">
                <div className="avatar avatar-sm">
                  {userId ? userId.charAt(0).toUpperCase() : "?"}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold truncate text-[var(--text-primary)]">Founder</p>
                  <p className="text-[10px] text-[var(--text-muted)] truncate">{userId?.slice(0, 8)}...</p>
                </div>
              </div>
              <div className="section-divider mb-2" />
              <div className="flex items-center justify-between text-[10px]">
                <div className="flex items-center gap-1 text-amber-400">
                  <TrendingUp className="w-3 h-3" />
                  <span className="font-bold tabular-nums">{karma}</span>
                  <span className="text-[var(--text-muted)]">karma</span>
                </div>
                <button
                  onClick={logout}
                  className="text-[var(--text-muted)] hover:text-[var(--accent-rose)] transition-colors p-1 rounded-md hover:bg-rose-500/10"
                  title="Log out"
                >
                  <LogOut className="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        </aside>

        {/* ── Mobile Bottom Nav ── */}
        <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 mobile-nav-enhanced">
          <div className="flex items-center justify-around py-2.5 px-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = activeNav === item.id;
              return (
                <Link
                  key={item.id}
                  href={item.href}
                  className={`flex flex-col items-center gap-0.5 py-1 px-3 rounded-xl transition-all duration-200 ${
                    isActive
                      ? "text-[var(--accent-violet)] bg-violet-500/10"
                      : "text-[var(--text-muted)]"
                  }`}
                >
                  <Icon className="w-5 h-5" />
                  <span className="text-[10px] font-medium">{item.label}</span>
                </Link>
              );
            })}
          </div>
        </nav>

        {/* ── Center Column: Dynamic Main View ── */}
        <main className="flex-1 min-w-0 overflow-y-auto pb-16 md:pb-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>

        {/* ── Right Column: Contextual Intelligence ── */}
        <aside className="hidden lg:block w-[300px] shrink-0 border-l border-[var(--border-subtle)] bg-[var(--bg-secondary)]/20 overflow-y-auto">
          <RightSidebarContent activeNav={activeNav} />
        </aside>
      </div>
    </div>
  );
}

/* ─── Right Sidebar Content ─── */
function RightSidebarContent({ activeNav }: { activeNav: string }) {
  return (
    <div className="p-5 space-y-6">
      {activeNav === "feed" && <FeedSidebar />}
      {activeNav === "explore" && <ExploreSidebar />}
      {activeNav === "messages" && <MessagesSidebar />}
      {activeNav === "groups" && <GroupsSidebar />}
      {activeNav === "profile" && <ProfileSidebar />}
    </div>
  );
}

function FeedSidebar() {
  return (
    <>
      {/* Trending Ideas */}
      <TrendingSection />

      {/* Suggested Founders */}
      <SuggestedFoundersSection />

      {/* Platform Stats */}
      <PlatformStatsSection />
    </>
  );
}

function TrendingSection() {
  const [ideas, setIdeas] = React.useState<{id: string; title: string; upvote_count: number; author_username: string}[]>([]);
  const [loaded, setLoaded] = React.useState(false);
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [expandedContent, setExpandedContent] = React.useState<string>("");

  React.useEffect(() => {
    import("@/lib/api").then(({ api }) => {
      api<{id: string; title: string; upvote_count: number; author_username: string}[]>(
        "/api/v1/arena/trending?limit=5"
      )
        .then(setIdeas)
        .catch(() => {})
        .finally(() => setLoaded(true));
    });
  }, []);

  const handleClick = async (ideaId: string) => {
    if (expandedId === ideaId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(ideaId);
    setExpandedContent("Loading...");
    try {
      const { api } = await import("@/lib/api");
      const post = await api<{ content?: string; title?: string }>(`/api/v1/arena/posts/${ideaId}`);
      setExpandedContent(post.content || post.title || "No content available.");
    } catch {
      setExpandedContent("Could not load idea details.");
    }
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded-lg bg-cyan-500/10 flex items-center justify-center">
          <TrendingUp className="w-3.5 h-3.5 text-[var(--accent-cyan)]" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Trending Ideas</h3>
      </div>
      <div className="space-y-2">
        {!loaded ? (
          [1, 2, 3].map((i) => (
            <div key={i} className="glass-card p-3 glass-card-hover">
              <div className="skeleton h-3 w-3/4 mb-2" />
              <div className="skeleton h-2 w-1/2" />
            </div>
          ))
        ) : ideas.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">No trending ideas yet. Be the first!</p>
        ) : (
          ideas.map((idea) => (
            <div
              key={idea.id}
              onClick={() => handleClick(idea.id)}
              className="glass-card p-3 glass-card-hover cursor-pointer"
            >
              <p className="text-xs font-medium text-[var(--text-primary)] truncate">
                {idea.title || "Untitled Idea"}
              </p>
              <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
                by @{idea.author_username} · ⬆{idea.upvote_count}
              </p>
              {expandedId === idea.id && (
                <div className="mt-2 pt-2 border-t border-[var(--border-subtle)]">
                  <p className="text-[11px] text-[var(--text-secondary)] whitespace-pre-wrap line-clamp-4">
                    {expandedContent}
                  </p>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function SuggestedFoundersSection() {
  const [founders, setFounders] = React.useState<{id: string; username: string; display_name: string | null; karma_score: number}[]>([]);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    import("@/lib/api").then(({ api }) => {
      api<{id: string; username: string; display_name: string | null; karma_score: number}[]>(
        "/api/v1/arena/suggested-founders?limit=5"
      )
        .then(setFounders)
        .catch(() => {})
        .finally(() => setLoaded(true));
    });
  }, []);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded-lg bg-violet-500/10 flex items-center justify-center">
          <Users2 className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Suggested Founders</h3>
      </div>
      <div className="space-y-1.5">
        {!loaded ? (
          [1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-2.5 p-2 rounded-lg">
              <div className="avatar avatar-sm">{String.fromCharCode(64 + i)}</div>
              <div className="flex-1 min-w-0">
                <div className="skeleton h-3 w-20 mb-1" />
                <div className="skeleton h-2 w-14" />
              </div>
            </div>
          ))
        ) : founders.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">No founders to suggest yet.</p>
        ) : (
          founders.map((f) => (
            <div key={f.id} className="flex items-center gap-2.5 p-2.5 rounded-xl hover:bg-white/[0.03] transition-all cursor-pointer">
              <div className="avatar avatar-sm">{f.username.charAt(0).toUpperCase()}</div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--text-primary)] truncate">{f.display_name || f.username}</p>
                <p className="text-[10px] text-[var(--text-muted)]">@{f.username} · ⚡{f.karma_score}</p>
              </div>
              <button className="text-[10px] px-2.5 py-1 rounded-lg bg-[var(--accent-violet)]/10 text-[var(--accent-violet)] font-medium hover:bg-[var(--accent-violet)]/20 transition-colors">
                Follow
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function ExploreSidebar() {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded-lg bg-cyan-500/10 flex items-center justify-center">
          <Search className="w-3.5 h-3.5 text-[var(--accent-cyan)]" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Search Tips</h3>
      </div>
      <div className="glass-card p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <ChevronRight className="w-3 h-3 text-[var(--accent-violet)]" />
          <span>Search by market gap keywords</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <ChevronRight className="w-3 h-3 text-[var(--accent-violet)]" />
          <span>Find founders by username</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <ChevronRight className="w-3 h-3 text-[var(--accent-violet)]" />
          <span>Filter ideas by tags</span>
        </div>
      </div>
    </div>
  );
}

function MessagesSidebar() {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded-lg bg-emerald-500/10 flex items-center justify-center">
          <MessageCircle className="w-3.5 h-3.5 text-[var(--accent-emerald)]" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Quick Actions</h3>
      </div>
      <div className="glass-card p-4 space-y-2">
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          Share ideas in DMs to get instant AI validation. Click the <strong>+</strong> button in any chat to run an AI analysis.
        </p>
      </div>
    </div>
  );
}

function GroupsSidebar() {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded-lg bg-violet-500/10 flex items-center justify-center">
          <Users2 className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Your Groups</h3>
      </div>
      <p className="text-xs text-[var(--text-muted)] leading-relaxed">
        Join a group to see members and the leaderboard here.
      </p>
    </div>
  );
}

function ProfileSidebar() {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded-lg bg-amber-500/10 flex items-center justify-center">
          <Star className="w-3.5 h-3.5 text-amber-400" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Achievements</h3>
      </div>
      <div className="glass-card p-4">
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          Earn badges by publishing ideas, receiving upvotes, and engaging with the community.
        </p>
      </div>
    </div>
  );
}

function PlatformStatsSection() {
  const [stats, setStats] = React.useState({ ideas: 0, founders: 0 });

  React.useEffect(() => {
    import("@/lib/supabase").then(({ supabase }) => {
      Promise.all([
        supabase.from("validations").select("id", { count: "exact", head: true }),
        supabase.from("profiles").select("id", { count: "exact", head: true }),
      ]).then(([valRes, profRes]) => {
        setStats({
          ideas: valRes.count || 0,
          founders: profRes.count || 0,
        });
      }).catch(() => {});
    });
  }, []);

  return (
    <div className="glass-card p-4">
      <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">Platform</h3>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xl font-bold gradient-text tabular-nums">{stats.ideas}</p>
          <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Ideas Validated</p>
        </div>
        <div>
          <p className="text-xl font-bold text-[var(--accent-emerald)] tabular-nums">{stats.founders}</p>
          <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Founders Active</p>
        </div>
      </div>
    </div>
  );
}
