"use client";
import Link from "next/link";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import {
  Swords,
  ArrowLeft,
  Hash,
  MessageCircle,
  Users,
  Plus,
  ChevronRight,
} from "lucide-react";

interface Hub {
  id: string;
  name: string;
  description: string | null;
  icon_url: string | null;
  member_count: number;
  channel_count: number;
}

interface Channel {
  id: string;
  hub_id: string | null;
  name: string;
  kind: string;
  description: string | null;
}

export default function ArenaLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId } = useAuth();
  const [hubs, setHubs] = useState<Hub[]>([]);
  const [selectedHub, setSelectedHub] = useState<Hub | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);

  useEffect(() => {
    api<Hub[]>("/api/v1/hubs").then(setHubs).catch(console.error);
  }, []);

  const selectHub = async (hub: Hub) => {
    setSelectedHub(hub);
    try {
      const chs = await api<Channel[]>(`/api/v1/hubs/${hub.id}/channels`);
      setChannels(chs);
    } catch {
      setChannels([]);
    }
  };

  const joinHub = async (hubId: string) => {
    if (!userId) return;
    await api(`/api/v1/hubs/${hubId}/join`, { method: "POST", userId });
  };

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-primary)]">
      {/* Top Bar */}
      <header className="shrink-0 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]/80 backdrop-blur-xl z-50">
        <div className="flex items-center justify-between px-4 h-12">
          <div className="flex items-center gap-3">
            <Link
              href="/nexus"
              className="flex items-center gap-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors text-sm"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Nexus
            </Link>
            <div className="w-px h-4 bg-[var(--border-subtle)]" />
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-cyan-500 to-emerald-500 flex items-center justify-center">
                <Swords className="w-3 h-3 text-white" />
              </div>
              <span className="font-semibold text-sm">The Arena</span>
            </div>
            {selectedHub && (
              <>
                <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                <span className="text-sm text-[var(--text-secondary)]">
                  {selectedHub.name}
                </span>
              </>
            )}
          </div>
        </div>
      </header>

      {/* 3-Column Layout */}
      <div className="flex-1 flex min-h-0">
        {/* Left: Hub Rail + Channel Panel */}
        <aside className="shrink-0 flex border-r border-[var(--border-subtle)]">
          {/* Hub Icons */}
          <div className="w-[72px] bg-[var(--bg-secondary)] flex flex-col items-center py-3 gap-2 border-r border-[var(--border-subtle)]">
            {/* Arena Feed shortcut */}
            <Link
              href="/arena"
              className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500 to-emerald-500 flex items-center justify-center hover:rounded-xl transition-all duration-300 mb-2"
            >
              <Swords className="w-5 h-5 text-white" />
            </Link>
            <div className="w-8 h-px bg-[var(--border-subtle)] mb-1" />

            {hubs.map((hub) => (
              <motion.button
                key={hub.id}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => selectHub(hub)}
                className={`w-12 h-12 rounded-2xl flex items-center justify-center text-sm font-bold transition-all duration-300 hover:rounded-xl ${
                  selectedHub?.id === hub.id
                    ? "bg-violet-600 text-white rounded-xl"
                    : "bg-[var(--bg-card)] text-[var(--text-muted)] hover:bg-violet-600/20 hover:text-[var(--text-primary)]"
                }`}
                title={hub.name}
              >
                {hub.icon_url ? (
                  <img
                    src={hub.icon_url}
                    alt=""
                    className="w-full h-full object-cover rounded-inherit"
                  />
                ) : (
                  hub.name.charAt(0).toUpperCase()
                )}
              </motion.button>
            ))}

            <button className="w-12 h-12 rounded-2xl flex items-center justify-center text-[var(--text-muted)] hover:bg-emerald-600/20 hover:text-emerald-400 hover:rounded-xl transition-all duration-300 border border-dashed border-[var(--border-subtle)]">
              <Plus className="w-5 h-5" />
            </button>
          </div>

          {/* Channel List */}
          {selectedHub && (
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 220, opacity: 1 }}
              className="bg-[var(--bg-secondary)]/50 overflow-y-auto"
            >
              <div className="p-4">
                <h3 className="font-semibold text-sm mb-1 truncate">
                  {selectedHub.name}
                </h3>
                <p className="text-xs text-[var(--text-muted)] mb-3">
                  {selectedHub.member_count} members
                </p>
                <button
                  onClick={() => joinHub(selectedHub.id)}
                  className="btn-primary w-full text-xs py-1.5 mb-4"
                >
                  Join Hub
                </button>

                <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider font-medium mb-2">
                  Channels
                </p>
                {channels.map((ch) => (
                  <Link
                    key={ch.id}
                    href={`/arena/hubs/${selectedHub.id}?channel=${ch.id}`}
                    className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm text-[var(--text-secondary)] hover:bg-white/5 hover:text-[var(--text-primary)] transition-colors"
                  >
                    {ch.kind === "text" ? (
                      <Hash className="w-4 h-4 text-[var(--text-muted)]" />
                    ) : (
                      <MessageCircle className="w-4 h-4 text-[var(--text-muted)]" />
                    )}
                    {ch.name}
                  </Link>
                ))}
              </div>
            </motion.div>
          )}
        </aside>

        {/* Center: Main Content */}
        <main className="flex-1 min-w-0 overflow-y-auto">{children}</main>

        {/* Right: Members */}
        <aside className="hidden lg:block w-[260px] shrink-0 border-l border-[var(--border-subtle)] bg-[var(--bg-secondary)]/30 overflow-y-auto">
          <div className="p-4">
            <div className="flex items-center gap-2 mb-4 text-sm font-medium text-[var(--text-secondary)]">
              <Users className="w-4 h-4" />
              Online Members
            </div>
            <p className="text-xs text-[var(--text-muted)]">
              Select a hub to see members.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
