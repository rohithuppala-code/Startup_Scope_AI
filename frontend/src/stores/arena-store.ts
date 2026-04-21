import { create } from "zustand";

type NavItem = "feed" | "explore" | "messages" | "groups" | "profile";

interface ArenaState {
  // Navigation
  activeNav: NavItem;
  setActiveNav: (nav: NavItem) => void;

  // Active conversation (DM)
  activeConversationId: string | null;
  setActiveConversation: (id: string | null) => void;

  // Active group
  activeGroupId: string | null;
  setActiveGroup: (id: string | null) => void;

  // Composer state
  composerOpen: boolean;
  composerText: string;
  composerPollOpen: boolean;
  composerValidationId: string | null;
  composerStatus: "idle" | "submitting" | "streaming" | "completed" | "failed";
  setComposerOpen: (open: boolean) => void;
  setComposerText: (text: string) => void;
  setComposerPollOpen: (open: boolean) => void;
  setComposerValidationId: (id: string | null) => void;
  setComposerStatus: (status: ArenaState["composerStatus"]) => void;
  resetComposer: () => void;

  // Right sidebar context
  rightSidebarContext: "feed" | "group" | "messages" | "explore" | "profile";
  setRightSidebarContext: (ctx: ArenaState["rightSidebarContext"]) => void;
}

export const useArenaStore = create<ArenaState>()((set) => ({
  activeNav: "feed",
  setActiveNav: (nav) => set({ activeNav: nav }),

  activeConversationId: null,
  setActiveConversation: (id) => set({ activeConversationId: id }),

  activeGroupId: null,
  setActiveGroup: (id) => set({ activeGroupId: id }),

  composerOpen: false,
  composerText: "",
  composerPollOpen: false,
  composerValidationId: null,
  composerStatus: "idle",
  setComposerOpen: (open) => set({ composerOpen: open }),
  setComposerText: (text) => set({ composerText: text }),
  setComposerPollOpen: (open) => set({ composerPollOpen: open }),
  setComposerValidationId: (id) => set({ composerValidationId: id }),
  setComposerStatus: (status) => set({ composerStatus: status }),
  resetComposer: () =>
    set({
      composerOpen: false,
      composerText: "",
      composerPollOpen: false,
      composerValidationId: null,
      composerStatus: "idle",
    }),

  rightSidebarContext: "feed",
  setRightSidebarContext: (ctx) => set({ rightSidebarContext: ctx }),
}));
